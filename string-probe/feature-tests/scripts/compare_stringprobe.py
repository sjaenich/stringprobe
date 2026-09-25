#!/usr/bin/env python3
"""Compare original StringProbe runs with matching optimization-level runs.

Python 3.10+, standard library only. Log content is parsed, never executed.
Run: python3 compare_stringprobe.py --baseline logs --compare logs-O0 logs-Os
"""
from __future__ import annotations

import argparse
import ast
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

HEADER = re.compile(r"^\*\*\* Run (\S+) for project: (.+?) \*\*\*\s*$")
ITERATION = re.compile(r"^=== Iteration (\d+) ===\s*$")
CONFIG = re.compile(r"^Ground truth flags for project (.+?)\s*:\s*(.*)$")
ENTRY = re.compile(r"^String and PC SourceStringEntry\(.*?, macro=(?:True|False)\)\s+(.*)$")
MISSING = '<not listed>'


def parse_flags(text):
    value = ast.literal_eval(text)
    if not isinstance(value, (dict, list, tuple, set)):
        raise ValueError('expected a dictionary or collection of macro/value pairs')
    pairs = value.items() if isinstance(value, dict) else value
    result = {}
    for pair in pairs:
        if not isinstance(pair, (tuple, list)) or len(pair) != 2:
            raise ValueError('expected macro/value pairs')
        name, val = pair
        if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z_]\w*', name):
            raise ValueError('invalid macro name')
        if not isinstance(val, (str, bool, int, float)):
            raise ValueError(f'unsupported value for {name}')
        val = str(val)
        if name in result and result[name] != val:
            raise ValueError(f'conflicting values for {name}')
        result[name] = val
    return result


def expression_macros(expression):
    """Read names in the condition, ignoring function names and string literals."""
    tree = ast.parse(expression, mode='eval')
    if any(isinstance(n, ast.Constant) and n.value is Ellipsis for n in ast.walk(tree)):
        raise ValueError('condition contains an ellipsis; the log may have truncated it')
    functions = {id(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)}
    return sorted({n.id for n in ast.walk(tree)
                   if isinstance(n, ast.Name) and id(n) not in functions})


def parse_section(path, numbered_lines, fallback_run):
    project = None
    run_number = fallback_run
    snapshots = []
    declared_flags = None
    iteration = None
    associations = []
    warnings = []
    association_errors = 0
    completed = False
    result_line = None
    ground_truth_config = None
    initial_binary = None
    i = 0
    while i < len(numbered_lines):
        lineno, line = numbered_lines[i]
        if m := HEADER.match(line):
            run_number, project = m.groups()
        if m := ITERATION.match(line):
            iteration = int(m[1])
        if line.startswith('Ground_truth_config ') and ground_truth_config is None:
            ground_truth_config = line[len('Ground_truth_config '):].strip().strip('\"\'')
        if line.startswith('THIS IS BINARY PATH ') and initial_binary is None:
            initial_binary = line[len('THIS IS BINARY PATH '):].strip().strip('\"\'')
        if line.startswith('FLAGS:') and declared_flags is None:
            try:
                declared_flags = parse_flags(line.split(':', 1)[1].strip())
            except (ValueError, SyntaxError) as exc:
                warnings.append(f'line {lineno}: invalid FLAGS: {exc}')
        if m := CONFIG.match(line):
            config_project, literal = m.groups()
            if project is not None and project != config_project:
                raise ValueError(f'line {lineno}: conflicting project names')
            project = config_project
            try:
                flags = parse_flags(literal)
            except (ValueError, SyntaxError) as exc:
                flags = None
                warnings.append(f'line {lineno}: invalid configuration: {exc}')
            snapshots.append({'iteration': iteration, 'line': lineno, 'flags': flags})
        if line.startswith('Result:'):
            completed = True
            result_line = lineno
            if 'build_success=False' in line or 'config_found=False' in line:
                warnings.append(f'line {lineno}: run reports failure: {line}')

        if m := ENTRY.match(line):
            parts = [m[1]]
            j = i + 1
            while j < len(numbered_lines) and numbered_lines[j][1].startswith((' ', '\t')):
                parts.append(numbered_lines[j][1].strip())
                j += 1
            expression = ' '.join(parts)
            try:
                macros = expression_macros(expression)
                associations.append({'line': lineno, 'format': 'String and PC',
                                     'macros': macros, 'condition': expression})
            except (SyntaxError, ValueError, RecursionError) as exc:
                association_errors += 1
                warnings.append(f'line {lineno}: unreadable string condition: {exc}')
            i = j
            continue

        if line.startswith('Added to solver '):
            parts = [line[len('Added to solver '):]]
            j = i + 1
            condition = None
            while True:
                expression = ' '.join(parts)
                match = re.match(r'^(.*?)\s*==\s*InBinary\(', expression)
                if match:
                    condition = match[1]
                    break
                if j >= len(numbered_lines) or j - i >= 300:
                    break
                next_line = numbered_lines[j][1]
                if not (next_line.startswith((' ', '\t', 'InBinary('))):
                    break
                parts.append(next_line.strip())
                j += 1
            try:
                if condition is None:
                    raise ValueError('missing == InBinary(...)')
                associations.append({'line': lineno, 'format': 'Added to solver',
                                     'macros': expression_macros(condition),
                                     'condition': condition})
            except (SyntaxError, ValueError, RecursionError) as exc:
                association_errors += 1
                warnings.append(f'line {lineno}: unreadable legacy string condition: {exc}')
            i = j
            continue
        i += 1

    if project is None or not snapshots:
        return None
    initial = snapshots[0]
    last = snapshots[-1]
    final = last if last['iteration'] == iteration else None
    if final is None:
        warnings.append('last iteration has no configuration; final comparison unavailable')
    if initial['iteration'] != 1:
        warnings.append('first recorded iteration is not 1; initial configuration may be incomplete')
    if not completed:
        warnings.append('no Result line: run may be incomplete or failed')
    if not associations:
        warnings.append('no readable string conditions: string-related scope is unknown')
    if declared_flags is not None and initial['flags'] != declared_flags:
        warnings.append('FLAGS differs from iteration 1; using iteration 1 as initial ground truth')
    macros = sorted({macro for a in associations for macro in a['macros']})
    return {'project': project, 'run': run_number, 'path': str(path),
            'ground_truth_config': ground_truth_config, 'initial_binary': initial_binary,
            'section_line': numbered_lines[0][0], 'initial': initial, 'final': final,
            'iterations': snapshots, 'string_macros': macros,
            'association_status': ('partial' if association_errors else 'available')
                                  if associations else 'unavailable',
            'associations': associations, 'completed': completed,
            'result_line': result_line, 'warnings': warnings}


def read_runs(path):
    lines = path.read_text(encoding='utf-8', errors='replace').splitlines()
    starts = [i for i, line in enumerate(lines) if HEADER.match(line)]
    if not starts:
        starts = [0]
    runs = []
    for start, end in zip(starts, starts[1:] + [len(lines)]):
        if start == end:
            continue
        run = parse_section(path, list(enumerate(lines[start:end], start + 1)), path.stem)
        if run:
            run['id'] = f'{path}:{start + 1}'
            runs.append(run)
    return runs


def flags_at(run, stage):
    snapshot = run[stage]
    return snapshot['flags'] if snapshot is not None else None


def compare_pair(original, variant, variant_root):
    """Use the original initial flags as the common ground truth for both."""
    truth = flags_at(original, 'initial')
    other_initial = flags_at(variant, 'initial')
    original_final = flags_at(original, 'final')
    variant_final = flags_at(variant, 'final')
    candidates = set(original['string_macros'])
    scope = sorted(candidates & set(truth or {}))
    scope_known = original['association_status'] == 'available' and truth is not None
    initial_differences = []
    if truth is not None and other_initial is not None:
        for macro in sorted(truth.keys() & other_initial.keys()):
            if truth[macro] != other_initial[macro]:
                initial_differences.append({'macro': macro,
                                           'original': truth.get(macro),
                                           'variant': other_initial.get(macro)})
    details = []
    for macro in scope:
        a = None if original_final is None else original_final.get(macro)
        b = None if variant_final is None else variant_final.get(macro)
        correct_a = (a is not None and a == truth[macro]) if original_final is not None else None
        correct_b = (b is not None and b == truth[macro]) if variant_final is not None else None
        details.append({'macro': macro, 'ground_truth': truth[macro],
                        'variant_initial': None if other_initial is None else other_initial.get(macro),
                        'original_final': a, 'variant_final': b,
                        'original_correct': correct_a, 'variant_correct': correct_b,
                        'correct_in_both': correct_a and correct_b
                        if correct_a is not None and correct_b is not None else None})
    def count(field, available):
        return sum(d[field] is True for d in details) if scope_known and available else None
    return {
        'project': original['project'], 'run': original['run'], 'variant_run': variant['run'],
        'variant_root': str(variant_root),
        'original_path': original['path'], 'variant_path': variant['path'],
        'same_initial_config': not initial_differences if truth is not None and other_initial is not None else None,
        'same_initial_string_config': all(m not in other_initial or truth[m] == other_initial[m] for m in scope)
        if scope_known and other_initial is not None else None,
        'string_macro_count': len(scope) if scope_known else None,
        'original_correct': count('original_correct', original_final is not None),
        'variant_correct': count('variant_correct', variant_final is not None),
        'correct_in_both': count('correct_in_both', original_final is not None and variant_final is not None),
        'original_missing': sum(m not in original_final for m in scope)
        if scope_known and original_final is not None else None,
        'variant_missing': sum(m not in variant_final for m in scope)
        if scope_known and variant_final is not None else None,
        'original_initial_line': original['initial']['line'],
        'variant_initial_line': variant['initial']['line'],
        'original_final_line': original['final']['line'] if original['final'] else None,
        'variant_final_line': variant['final']['line'] if variant['final'] else None,
        'original_final_iteration': original['final']['iteration'] if original['final'] else None,
        'variant_final_iteration': variant['final']['iteration'] if variant['final'] else None,
        'original_complete': original['completed'], 'variant_complete': variant['completed'],
        'unscored_string_macros': sorted(candidates - set(truth or {})),
        'initial_differences': initial_differences, 'macros': details,
    }


def cell(value):
    return (str(value).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            .replace('|', '\\|').replace('\n', ' '))


def display(value):
    return MISSING if value is None else value


def yes_no(value):
    return 'N/A' if value is None else ('Yes' if value else 'No')


def score(value, total):
    return 'N/A' if value is None or total is None else f'{value}/{total}'


SUMMARY_FIELDS = [
    'project', 'run', 'variant_run', 'match_method', 'variant_root', 'same_initial_config', 'same_initial_string_config',
    'string_macro_count', 'original_correct', 'variant_correct', 'correct_in_both',
    'original_missing', 'variant_missing', 'original_complete', 'variant_complete',
    'original_path', 'variant_path', 'original_initial_line', 'variant_initial_line',
    'original_final_line', 'variant_final_line', 'original_final_iteration', 'variant_final_iteration',
]


def write_reports(output, pairs, runs, diagnostics):
    output.mkdir(parents=True, exist_ok=True)
    payload = {
        'ground_truth': 'Original run initial configuration, used for both scores.',
        'recovered_values': 'Last iteration configuration; Rec lines are ignored.',
        'scope': 'Original string-associated macros with a known original initial value.',
        'scoring_rule': 'Only explicitly assigned values matching original ground truth count as correct. Unassigned macros stay in the denominator and do not count as correct. Initial comparisons ignore omissions.',
        'comparisons': pairs, 'runs': runs, 'diagnostics': diagnostics,
    }
    (output / 'comparison.json').write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')
    with (output / 'comparison.csv').open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=SUMMARY_FIELDS, extrasaction='ignore')
        writer.writeheader()
        for pair in pairs:
            writer.writerow({k: 'N/A' if pair[k] is None else pair[k] for k in SUMMARY_FIELDS})
    with (output / 'macro_details.csv').open('w', newline='', encoding='utf-8') as handle:
        fields = ['project', 'run', 'variant_run', 'variant_root', 'macro', 'ground_truth', 'variant_initial',
                  'original_final', 'variant_final', 'original_correct', 'variant_correct',
                  'correct_in_both']
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for pair in pairs:
            for detail in pair['macros']:
                row = {**{k: pair[k] for k in ('project', 'run', 'variant_run', 'variant_root')}, **detail}
                for k in ('variant_initial', 'original_final', 'variant_final'):
                    row[k] = display(row[k])
                for k in ('original_correct', 'variant_correct', 'correct_in_both'):
                    row[k] = 'N/A' if row[k] is None else row[k]
                if detail['original_correct'] is None:
                    row['original_final'] = '<unavailable>'
                if detail['variant_correct'] is None:
                    row['variant_final'] = '<unavailable>'
                writer.writerow(row)
    md = ['# StringProbe optimization comparison', '',
          'Runs are paired within each project by original configuration, not by run number.',
          '**Both accuracy counts use the original run’s initial flags as ground truth.**',
          'Recovered values come from the last iteration’s configuration. Only explicitly assigned values matching ground truth count as correct; unassigned macros remain in the denominator.',
          'Initial configuration comparisons still ignore omitted entries. A correct recorded assignment is not proof that the solver uniquely determined it.',
          'If initial configurations differ, the scores are still against the original ground truth; this is not a controlled optimization-only comparison.', '',
          '| Project | Original run | Variant run | Variant directory | Same initial config | Same initial string flags | Original correct | Variant correct | Correct in both |',
          '|---|---|---|---|---|---|---:|---:|---:|']
    for p in pairs:
        total = p['string_macro_count']
        md.append('| ' + ' | '.join(map(cell, [p['project'], p['run'], p['variant_run'], p['variant_root'],
                  yes_no(p['same_initial_config']), yes_no(p['same_initial_string_config']),
                  score(p['original_correct'], total), score(p['variant_correct'], total),
                  score(p['correct_in_both'], total)])) + ' |')
    for p in pairs:
        md += ['', f"## {cell(p['project'])}, original {cell(p['run'])} vs variant {cell(p['variant_run'])}: {cell(p['variant_root'])}", '',
               f"Matched by: {p['match_method']}.",
               f"Original: `{p['original_path']}`; initial line {p['original_initial_line']}, final line {p['original_final_line']}.",
               f"Variant: `{p['variant_path']}`; initial line {p['variant_initial_line']}, final line {p['variant_final_line']}."]
        if not p['original_complete'] or not p['variant_complete']:
            md += ['', '**At least one log has no final Result record; its available configuration is provisional.**']
        if p['initial_differences']:
            md += ['', 'Initial configuration differences:', '', '| Macro | Original | Variant |', '|---|---|---|']
            for d in p['initial_differences']:
                md.append('| ' + ' | '.join(cell(display(d[k])) for k in ('macro', 'original', 'variant')) + ' |')
        if p['unscored_string_macros']:
            md += ['', 'String-associated macros without original ground truth (excluded from counts): '
                   + ', '.join(p['unscored_string_macros']) + '.']
        issues = [d for d in p['macros'] if d['correct_in_both'] is not True]
        if issues:
            md += ['', 'String-related macros not correct in both:', '',
                   '| Macro | Original ground truth | Original final | Variant final |', '|---|---|---|---|']
            for d in issues:
                md.append('| ' + ' | '.join(cell(display(d[k])) for k in
                                           ('macro', 'ground_truth', 'original_final', 'variant_final')) + ' |')
        elif p['string_macro_count'] is not None:
            md += ['', 'All scored string-related macros are correct in both runs.']
    md += ['', '## Diagnostics', '']
    md += [f'- {cell(d)}' for d in diagnostics] or ['No parsing or pairing warnings.']
    md += ['', '`N/A` means unavailable. `<not listed>` is different from False. See comparison.json for source conditions and parsing details.', '']
    (output / 'summary.md').write_text('\n'.join(md), encoding='utf-8')


def load_directory(root, projects, diagnostics):
    paths = sorted(root.rglob('*.log')) if root.is_dir() else [root]
    grouped = defaultdict(list)
    for path in paths:
        try:
            runs = read_runs(path.resolve())
        except (OSError, ValueError, SyntaxError, RecursionError) as exc:
            diagnostics.append(f'{path}: {exc}')
            continue
        for run in runs:
            if projects and run['project'] not in projects:
                continue
            grouped[(run['project'], run['run'])].append(run)
            diagnostics.extend(f"{run['path']} run {run['run']}: {w}" for w in run['warnings'])
    return grouped


def bundle(path):
    if path:
        for part in reversed(path.replace('\\', '/').split('/')):
            if part.endswith('_bundle'):
                return part
    return None


def match_original(variant, originals):
    """Return candidate original runs and the reason; never use a run number."""
    candidates = [r for r in originals if r['project'] == variant['project']]
    reference = variant.get('ground_truth_config')
    reference_bundle = bundle(reference)
    if reference:
        referenced = [r for r in candidates if
                      r.get('ground_truth_config') == reference or
                      (reference_bundle is not None and reference_bundle in
                       {bundle(r.get('initial_binary')), bundle(r.get('ground_truth_config'))})]
        if referenced:
            return referenced, 'original configuration path/bundle'
    initial = flags_at(variant, 'initial')
    if initial is None:
        return [], 'initial configuration unavailable'
    exact = [r for r in candidates if flags_at(r, 'initial') == initial]
    if exact:
        return exact, 'identical initial flags'
    compatible = []
    for r in candidates:
        baseline = flags_at(r, 'initial')
        if baseline and initial and baseline.keys() & initial.keys():
            if all(baseline[k] == initial[k] for k in baseline.keys() & initial.keys()):
                compatible.append(r)
    return compatible, 'shared initial flags agree; omitted entries ignored'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--baseline', required=True, type=Path, help='original logs directory (or one log file)')
    parser.add_argument('--compare', required=True, nargs='+', type=Path,
                        help='optimization-level directories (or corresponding log files)')
    parser.add_argument('--project', action='append', help='optional project filter, e.g. xz; repeat as needed')
    parser.add_argument('--output', '-o', type=Path, default=Path('stringprobe-comparison'))
    args = parser.parse_args(argv)
    roots = [args.baseline] + args.compare
    for root in roots:
        if not root.exists():
            parser.error(f'input does not exist: {root}')
    if len({r.resolve() for r in roots}) != len(roots):
        parser.error('baseline and variant inputs must be distinct')
    diagnostics = []
    originals = load_directory(args.baseline, args.project, diagnostics)
    if not originals:
        parser.error('no recognizable baseline runs found')
    pairs = []
    baseline_runs = [r for group in originals.values() for r in group]
    all_runs = list(baseline_runs)
    for root in args.compare:
        variants = load_directory(root, args.project, diagnostics)
        variant_runs = [r for group in variants.values() for r in group]
        all_runs.extend(variant_runs)
        matched = set()
        for variant in variant_runs:
            candidates, method = match_original(variant, baseline_runs)
            if len(candidates) != 1:
                sources = ', '.join(r['id'] for r in candidates) or 'none'
                diagnostics.append(f"{variant['path']} run {variant['run']}: skipped; "
                                   f"{len(candidates)} original matches by {method}: {sources}")
                continue
            original = candidates[0]
            matched.add(original['id'])
            pair = compare_pair(original, variant, root)
            pair['match_method'] = method
            pairs.append(pair)
        for original in baseline_runs:
            if original['id'] not in matched:
                diagnostics.append(f"{root}: no unique corresponding variant for "
                                   f"{original['project']} original run {original['run']} ({original['path']})")
    write_reports(args.output, pairs, all_runs, diagnostics)
    print('Scores use original initial flags for both runs; unassigned macros do NOT count as correct. Initial configuration comparisons ignore omissions.')
    for p in pairs:
        total = p['string_macro_count']
        print(f"{p['project']} original {p['run']} vs variant {p['variant_run']} [{p['variant_root']}]: "
              f"same initial={yes_no(p['same_initial_config'])}; "
              f"same string flags={yes_no(p['same_initial_string_config'])}; "
              f"original={score(p['original_correct'], total)}; "
              f"variant={score(p['variant_correct'], total)}; "
              f"both={score(p['correct_in_both'], total)}")
    print(f'{len(pairs)} matched pair(s). Reports: {args.output.resolve()}')
    if diagnostics:
        print(f'{len(diagnostics)} diagnostic(s); see summary.md.')
    return 0 if pairs else 1


if __name__ == '__main__':
    sys.exit(main())
