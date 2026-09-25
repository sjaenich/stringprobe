#!/usr/bin/env bash
set -euo pipefail

extract_block() {
    local which="$1"
    local file="$2"

    awk -v which="$which" '
        /^Ground truth flags for project / {
            cap = 1
            buf = $0
            if ($0 ~ /}/) {
                blocks[++n] = buf
                cap = 0
            }
            next
        }

        cap {
            buf = buf " " $0
            if ($0 ~ /}/) {
                blocks[++n] = buf
                cap = 0
            }
        }

        END {
            if (n == 0) exit 1
            if (which == "first") print blocks[1]
            else print blocks[n]
        }
    ' "$file"
}

extract_flags_as_pairs() {
    perl -ne "while(/\x27([^']+)\x27,\s*\x27([^']+)\x27/g){ print \"\$1=\$2\n\" }"
}

extract_flags_as_map() {
    perl -ne "while(/\x27([^']+)\x27,\s*\x27([^']+)\x27/g){ print \"\$1\t\$2\n\" }"
}

compare_file() {
    local file="$1"
    local first_block last_block project tmpdir

    first_block=$(extract_block first "$file") || {
        echo "No ground-truth block found in $file" >&2
        return 1
    }
    last_block=$(extract_block last "$file") || {
        echo "Could not extract last ground-truth block from $file" >&2
        return 1
    }

    project=$(sed -n 's/^Ground truth flags for project \(.*\) : .*/\1/p' <<< "$first_block")

    tmpdir=$(mktemp -d)

    printf '%s\n' "$first_block" | extract_flags_as_pairs | sort -u > "$tmpdir/first_pairs.txt"
    printf '%s\n' "$last_block"  | extract_flags_as_pairs | sort -u > "$tmpdir/last_pairs.txt"

    printf '%s\n' "$first_block" | extract_flags_as_map | sort -u > "$tmpdir/first_map.txt"
    printf '%s\n' "$last_block"  | extract_flags_as_map | sort -u > "$tmpdir/last_map.txt"

    echo "=================================================="
    echo "File   : $file"
    [[ -n "$project" ]] && echo "Project: $project"
    echo "=================================================="

    local total_first total_last exact_matches
    total_first=$(wc -l < "$tmpdir/first_pairs.txt" | tr -d ' ')
    total_last=$(wc -l < "$tmpdir/last_pairs.txt" | tr -d ' ')
    exact_matches=$(comm -12 "$tmpdir/first_pairs.txt" "$tmpdir/last_pairs.txt" | wc -l | tr -d ' ')

    echo "First iteration flags : $total_first"
    echo "Last iteration flags  : $total_last"
    echo "Exact matches         : $exact_matches"
    echo

    echo "Changed flags:"
    join -t $'\t' -j 1 "$tmpdir/first_map.txt" "$tmpdir/last_map.txt" \
        | awk -F'\t' '$2 != $3 { printf "  %s: %s -> %s\n", $1, $2, $3; found=1 } END { if (!found) print "  (none)" }'
    echo

    echo "Only in first iteration:"
    join -t $'\t' -v 1 -j 1 "$tmpdir/first_map.txt" "$tmpdir/last_map.txt" \
        | awk -F'\t' '{ printf "  %s=%s\n", $1, $2; found=1 } END { if (!found) print "  (none)" }'
    echo

    echo "Only in last iteration:"
    join -t $'\t' -v 2 -j 1 "$tmpdir/first_map.txt" "$tmpdir/last_map.txt" \
        | awk -F'\t' '{ printf "  %s=%s\n", $1, $2; found=1 } END { if (!found) print "  (none)" }'
    echo

    rm -rf "$tmpdir"
}

if [[ "$#" -lt 1 ]]; then
    echo "Usage: $0 file1.log [file2.log ...]"
    exit 1
fi

for file in "$@"; do
    compare_file "$file"
done
