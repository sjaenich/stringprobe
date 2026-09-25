#!/usr/bin/env bash

set -euo pipefail

usage() {
    cat <<'USAGE'
Usage:
  count_groundtruth_macros.sh GROUND_TRUTH_LOG [ANALYSIS_LOG] [ITERATION]

Extract the macros from the selected iteration's "Ground truth flags" line,
then count their occurrences in these analysis-log records:

  String and PC ...
  Added to solver ...

ANALYSIS_LOG defaults to GROUND_TRUTH_LOG, and ITERATION defaults to 1.
The result is TSV on standard output, sorted by total count (descending).

Examples:
  ./count_groundtruth_macros.sh libopenssl.log
  ./count_groundtruth_macros.sh experiment.log solver-output.log 1
  ./count_groundtruth_macros.sh experiment.log solver-output.log 2 > counts.tsv
USAGE
}

if (( $# < 1 || $# > 3 )); then
    usage >&2
    exit 2
fi

ground_truth_log=$1
analysis_log=${2:-$ground_truth_log}
iteration=${3:-1}

if [[ ! -r $ground_truth_log ]]; then
    printf 'Error: cannot read ground-truth log: %s\n' "$ground_truth_log" >&2
    exit 1
fi

if [[ ! -r $analysis_log ]]; then
    printf 'Error: cannot read analysis log: %s\n' "$analysis_log" >&2
    exit 1
fi

if [[ ! $iteration =~ ^[0-9]+$ ]]; then
    printf 'Error: ITERATION must be a non-negative integer, got: %s\n' "$iteration" >&2
    exit 2
fi

work_dir=$(mktemp -d "${TMPDIR:-/tmp}/count-groundtruth-macros.XXXXXX")
trap 'rm -rf -- "$work_dir"' EXIT

macro_file=$work_dir/macros.tsv
count_file=$work_dir/counts.tsv

# Extract pairs such as OPENSSL_NO_ERR', 'False from the ground-truth set.
# SQ is passed separately so the awk program remains easy to quote in Bash.
awk -v wanted="=== Iteration $iteration ===" -v SQ="'" '
    {
        sub(/\r$/, "")
    }

    $0 == wanted {
        in_iteration = 1
        next
    }

    in_iteration && /^=== Iteration [0-9]+ ===$/ {
        exit
    }

    in_iteration && /^Ground truth flags/ {
        rest = $0
        pattern = "[A-Za-z_][A-Za-z0-9_]*" SQ ", " SQ "(True|False)" SQ

        while (match(rest, pattern)) {
            pair = substr(rest, RSTART, RLENGTH)
            split(pair, fields, SQ ", " SQ)
            macro = fields[1]
            value = fields[2]
            gsub(SQ, "", value)
            print macro "\t"
            rest = substr(rest, RSTART + RLENGTH)
        }
        exit
    }
' "$ground_truth_log" | sort -u > "$macro_file"

if [[ ! -s $macro_file ]]; then
    printf 'Error: no ground-truth flags found after "=== Iteration %s ===" in %s\n' \
        "$iteration" "$ground_truth_log" >&2
    exit 1
fi

# Count exact identifier tokens, so OPENSSL_NO_ERR does not accidentally match
# a longer identifier. Solver expressions may continue on following lines.
awk '
    FNR == NR {
        macro_order[++macro_count] = $1
        truth[$1] = $2
        wanted[$1] = 1
        next
    }

    function count_tokens(text, category, token) {
        while (match(text, /[A-Za-z_][A-Za-z0-9_]*/)) {
            token = substr(text, RSTART, RLENGTH)
            if (token in wanted) {
                if (category == "string_pc") {
                    string_pc[token]++
                } else {
                    solver[token]++
                }
            }
            text = substr(text, RSTART + RLENGTH)
        }
    }

    function is_log_boundary(text) {
        return text ~ /^(String and PC|Added to solver)([[:space:]]|$)/ ||
               text ~ /^(Getting |Index set size|SuperC |\/|=== |\*\*\* |FLAGS:|Running experiment|Source directory:|Unused macros:|Ground truth flags)/
    }

    {
        line = $0
        sub(/\r$/, "", line)
        stripped = line
        sub(/^[[:space:]]+/, "", stripped)

        if (stripped ~ /^String and PC([[:space:]]|$)/) {
            # Count only the path-condition expression after SourceStringEntry,
            # not a macro-like word that might occur inside the source string.
            payload = stripped
            if (match(payload, /macro=(True|False)\)[[:space:]]*/)) {
                payload = substr(payload, RSTART + RLENGTH)
            } else {
                sub(/^String and PC[[:space:]]*/, "", payload)
            }
            count_tokens(payload, "string_pc")
            in_solver_record = 0
            next
        }

        if (stripped ~ /^Added to solver([[:space:]]|$)/) {
            payload = stripped
            sub(/^Added to solver[[:space:]]*/, "", payload)
            count_tokens(payload, "solver")
            in_solver_record = 1
            next
        }

        if (in_solver_record) {
            if (stripped == "" || is_log_boundary(stripped)) {
                in_solver_record = 0
                next
            }
            count_tokens(stripped, "solver")
        }
    }

    END {
        for (i = 1; i <= macro_count; i++) {
            macro = macro_order[i]
            total = string_pc[macro] + solver[macro]
            print macro "\t" truth[macro] "\t" (string_pc[macro] + 0) "\t" \
                  (solver[macro] + 0) "\t" total
        }
    }
' "$macro_file" "$analysis_log" > "$count_file"

printf 'macro\tground_truth\tstring_and_pc\tadded_to_solver\ttotal\n'
sort -t $'\t' -k5,5nr -k1,1 "$count_file"

