#!/usr/bin/env python3
"""Validate independent batches, append observations, and export 10 clinic/topic CSVs."""
import argparse
from collections import defaultdict
import json
from pathlib import Path

from common import (CLINICS, DEFAULT_DATA, TOPICS, atomic_json, fingerprint, planned_rows,
                    successful_records, validate_manifest, write_csv)


def combine(directories, output, allow_partial=False, allow_model_differences=False):
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
    if missing and not allow_partial:
        raise ValueError(f'{missing} missing/failed slots; see {output / "coverage_report.csv"}. Resume collection, or use --allow-partial for an explicitly incomplete handoff. No response exports were updated.')
    if not records:
        raise ValueError('No successful responses to export.')
    rows = [records[k] for k in sorted(records)]
    groups = defaultdict(list)
    for row in rows:
        groups[row['clinic_id'], row['topic']].append(row)
    write_csv(output / 'responses_master.csv', rows)
    counts = {}
    for clinic in CLINICS:
        for topic in TOPICS:
            name = f'{clinic}_{topic}.csv'
            group = groups[clinic, topic]
            write_csv(output / 'exports' / name, group)
            counts[name] = len(group)
    atomic_json(output / 'handoff_summary.json', {
        'schema_version': 1, 'complete': not missing, 'missing_or_failed_slots': missing,
        'response_count': len(rows), 'expected_response_count': len(coverage),
        'batches': [{k: m[k] for k in ('batch_id', 'tester', 'models', 'trials', 'question_set_sha256')}
                    for m in manifests],
        'collection_settings_differ': len(settings) > 1, 'files': counts,
        'sentiment_status': 'Unscored; question framing is not response sentiment.',
        'review': 'Review target-clinic relevance and passages before sentiment scoring. See review_note.'})
    print(f'{len(rows)} responses from {len(manifests)} unique batches; {missing} missing/failed slots.')
    print(f'Master, coverage, summary: {output}\n10 CSVs for Keilani: {output / "exports"}')
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batches', type=Path, nargs='+', required=True,
                        help='Batch folders (manifest.json + attempts.jsonl), or their responses.csv paths')
    parser.add_argument('--output', type=Path, default=DEFAULT_DATA / 'combined')
    parser.add_argument('--allow-partial', action='store_true')
    parser.add_argument('--allow-model-differences', action='store_true')
    args = parser.parse_args()
    try:
        combine(args.batches, args.output, args.allow_partial, args.allow_model_differences)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.exit(1, f'Cannot combine: {exc}\n')


if __name__ == '__main__':
    main()
