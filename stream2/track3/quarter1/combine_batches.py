#!/usr/bin/env python3
"""Validate independent batches, append observations, and export 10 clinic/topic CSVs."""
import argparse
from collections import defaultdict
import json
from pathlib import Path

from common import (CLINICS, DEFAULT_DATA, TOPICS, atomic_json, fingerprint, planned_rows,
                    successful_records, validate_manifest, write_csv)


def combine(directories, output, allow_partial=False, allow_model_differences=False, complete_only=False):
    if complete_only and allow_partial:
        raise ValueError('--complete-only and --allow-partial cannot be used together.')
    manifests, records, batches = [], {}, {}
    coverage = []
    for directory in directories:
        directory = Path(directory).resolve()
        if directory.is_file() and directory.name == 'responses.csv':
            directory = directory.parent
        manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
        validate_manifest(manifest)
        success = successful_records(directory, manifest)
        signature = fingerprint({'manifest': manifest, 'success': success})
        batch = manifest['batch_id']
        if batch in batches:
            if batches[batch] != signature:
                raise ValueError(f'{batch}: conflicting copies of the same batch.')
            continue
        batches[batch] = signature
        manifests.append(manifest)
        for rid, row in success.items():
            if rid in records and records[rid] != row:
                raise ValueError(f'{rid}: conflicting duplicate record.')
            records[rid] = row
        for row in planned_rows(manifest):
            coverage.append({k: row[k] for k in ('record_id', 'batch_id', 'tester', 'clinic_id', 'topic',
                                                 'question_framing', 'question_id', 'provider', 'trial')} |
                            {'status': 'success' if row['record_id'] in success else 'missing_or_failed'})
    if not manifests:
        raise ValueError('Provide at least one batch.')
    if len({m['question_set_sha256'] for m in manifests}) != 1:
        raise ValueError('Question sets differ; do not combine different prompts/versions into this deliverable.')
    settings = {(tuple(sorted(m['models'].items())), m['trials']) for m in manifests}
    if len(settings) > 1 and not allow_model_differences:
        raise ValueError('Models, provider selection, or trial counts differ. Align batches or explicitly use --allow-model-differences.')
    output = Path(output).resolve()
    if any(output == Path(d).resolve() or output in Path(d).resolve().parents
           or Path(d).resolve() in output.parents for d in directories):
        raise ValueError('Output must be separate from every source batch directory.')
    missing = sum(r['status'] != 'success' for r in coverage)
    # Coverage is useful even when incomplete inputs prevent final exports.
    write_csv(output / 'coverage_report.csv', coverage, list(coverage[0]))
    if missing and not allow_partial and not complete_only:
        raise ValueError(f'{missing} missing/failed slots; see {output / "coverage_report.csv"}. Resume collection, or use --allow-partial for an explicitly incomplete handoff. No response exports were updated.')
    if not records:
        raise ValueError('No successful responses to export.')
    group_coverage = defaultdict(list)
    for row in coverage:
        group_coverage[row['clinic_id'], row['topic']].append(row)
    complete_groups = {key for key, group in group_coverage.items()
                       if all(r['status'] == 'success' for r in group)}
    selected_groups = complete_groups if complete_only else set(group_coverage)
    if not selected_groups:
        raise ValueError('No clinic/topic groups are complete across all input batches.')
    rows = [records[k] for k in sorted(records)
            if (records[k]['clinic_id'], records[k]['topic']) in selected_groups]
    groups = defaultdict(list)
    for row in rows:
        groups[row['clinic_id'], row['topic']].append(row)
    desired_files = {f'{clinic}_{topic}.csv' for clinic, topic in selected_groups}
    existing_files = {p.name for p in (output / 'exports').glob('*.csv')}
    if existing_files - desired_files:
        raise ValueError('Output contains exports outside the selected scope. Use a new output directory.')
    write_csv(output / 'responses_master.csv', rows)
    counts = {}
    group_report = []
    for clinic in CLINICS:
        for topic in TOPICS:
            key = (clinic, topic)
            expected_group = group_coverage[key]
            observed = sum(r['status'] == 'success' for r in expected_group)
            group_report.append({'clinic_id': clinic, 'topic': topic,
                                 'available_responses': observed, 'expected_responses': len(expected_group),
                                 'missing_responses': len(expected_group) - observed,
                                 'complete_across_batches': key in complete_groups,
                                 'included_in_export': key in selected_groups})
            if key not in selected_groups:
                continue
            name = f'{clinic}_{topic}.csv'
            group = groups[key]
            write_csv(output / 'exports' / name, group)
            counts[name] = len(group)
    write_csv(output / 'group_coverage.csv', group_report, list(group_report[0]))
    expected_selected = sum(len(group_coverage[key]) for key in selected_groups)
    atomic_json(output / 'handoff_summary.json', {
        'schema_version': 1, 'complete': not missing, 'missing_or_failed_slots': missing,
        'export_mode': 'complete_groups_only' if complete_only else 'all_groups',
        'selected_scope_complete': len(rows) == expected_selected,
        'expected_exported_response_count': expected_selected,
        'available_response_count_all_groups': len(records),
        'excluded_groups': [r for r in group_report if not r['included_in_export']],
        'response_count': len(rows), 'expected_response_count': len(coverage),
        'batches': [{k: m[k] for k in ('batch_id', 'tester', 'models', 'trials', 'question_set_sha256')}
                    for m in manifests],
        'collection_settings_differ': len(settings) > 1, 'files': counts,
        'sentiment_status': 'Unscored; question framing is not response sentiment.',
        'review': 'Review target-clinic relevance and passages before sentiment scoring. See review_note.'})
    print(f'{len(rows)} exported responses from {len(manifests)} unique batches; {missing} missing/failed slots across the full study.')
    print(f'Master, coverage, summary: {output}\n{len(counts)} CSVs for sentiment analysis: {output / "exports"}')
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batches', type=Path, nargs='+', required=True,
                        help='Batch folders (manifest.json + attempts.jsonl), or their responses.csv paths')
    parser.add_argument('--output', type=Path, default=DEFAULT_DATA / 'combined')
    parser.add_argument('--allow-partial', action='store_true')
    parser.add_argument('--allow-model-differences', action='store_true')
    parser.add_argument('--complete-only', action='store_true', help='Export only clinic/topic groups complete across every input batch and all planned providers/trials')
    args = parser.parse_args()
    try:
        combine(args.batches, args.output, args.allow_partial, args.allow_model_differences, args.complete_only)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.exit(1, f'Cannot combine: {exc}\n')


if __name__ == '__main__':
    main()
