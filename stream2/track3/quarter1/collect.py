#!/usr/bin/env python3
"""Collect a frozen Quarter 1 batch. Defaults to a free, offline plan."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import time

from common import (DEFAULT_DATA, FIELDS, HERE, KEY_NAMES, atomic_json, fingerprint,
                    identifier, load_questions, planned_rows, successful_records, validate_manifest, write_csv)
from providers import ask


def now():
    return datetime.now(timezone.utc).isoformat()


def load_env(path):
    values = {}
    if path.exists():
        for line in path.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                values[k.strip()] = v.strip().strip('\"\'')
    return values


def prepare_batch(directory, batch, tester, models, trials, questions):
    identifier(batch)
    manifest = dict(schema_version=1, batch_id=batch, tester=tester.strip(), models=models,
                    trials=trials, questions=questions, question_set_sha256=fingerprint(questions))
    validate_manifest(manifest)
    path = directory / 'manifest.json'
    if path.exists():
        saved = json.loads(path.read_text(encoding='utf-8'))
        validate_manifest(saved)
        if any(saved.get(k) != v for k, v in manifest.items()):
            raise ValueError('Batch settings/questions changed. Restore the original settings or use a new --batch ID.')
        return saved
    if directory.exists() and any(directory.iterdir()):
        raise ValueError('Batch directory contains files but no manifest; use a new batch ID.')
    manifest['created_at_utc'] = now()
    atomic_json(path, manifest)
    return manifest


def collect_batch(directory, manifest, keys, spend=False, limit=None, delay=1.0, ask_fn=ask):
    """Append durable captures; a rerun skips all successful slots. Failures can be retried."""
    success = successful_records(directory, manifest)
    todo = [r for r in planned_rows(manifest) if r['record_id'] not in success]
    print(f"{manifest['batch_id']}: {len(success)} saved; {len(todo)} remaining collection slots.")
    if not spend:
        print('Plan only: no API calls. Add --spend to collect. Each slot can incur web-search charges too.')
        write_csv(directory / 'responses.csv', [success[k] for k in sorted(success)])
        return 0
    missing = [KEY_NAMES[p] for p in manifest['models']
               if any(r['provider'] == p for r in todo) and not keys.get(p)]
    if missing:
        raise ValueError('Missing API keys: ' + ', '.join(missing))
    failures = 0
    for row in todo[:limit] if limit is not None else todo:
        row = {**{k: '' for k in FIELDS}, **row, 'collected_at_utc': now()}
        capture = {}
        try:
            capture = ask_fn(row['provider'], row['model_requested'], row['prompt_text'], keys[row['provider']])
            if not capture['response_text'].strip():
                raise ValueError('Empty answer.')
            row.update({k: capture[k] for k in ('response_text', 'citation_urls', 'model_returned', 'search_count')})
            row['status'] = 'success'
            other_clinic = (r'\bsdfc\b|san diego fertility cent(?:er|re)' if row['clinic_id'] == 'rpsd'
                            else r'\brpsd\b|reproductive\s+partners')
            other = bool(re.search(other_clinic, row['response_text'], re.I))
            row['review_required'] = 'yes'
            row['review_note'] = ('Other study clinic mentioned; review clinic-specific scoring passage.' if other
                                  else 'Review target-clinic relevance and scoring passage before sentiment analysis.')
        except Exception as exc:
            failures += 1
            row.update(status='failed', review_required='yes', review_note='Collection failed; retry this slot.')
            message = str(exc)
            for secret in keys.values():
                if secret:
                    message = message.replace(secret, '[REDACTED]')
            capture = {'error_type': type(exc).__name__, 'error_message': message[:1000]}
        row['completed_at_utc'] = now()
        # Keep original provider payload and extracted text together; export can be rebuilt from this log.
        with (directory / 'attempts.jsonl').open('a', encoding='utf-8') as f:
            f.write(json.dumps({'record': row, 'capture': capture}, ensure_ascii=False) + '\n')
            f.flush(); os.fsync(f.fileno())
        print(f"{row['source_run_id']}: {row['status']}")
        if delay:
            time.sleep(delay)
    success = successful_records(directory, manifest)
    write_csv(directory / 'responses.csv', [success[k] for k in sorted(success)])
    print(f"Saved {len(success)} successful responses to {directory / 'responses.csv'}")
    if len(success) < len(list(planned_rows(manifest))):
        print('Batch incomplete. Resume the same command to collect remaining slots.')
    return failures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch', required=True, help='Unique ID, e.g. siya-q1-01')
    parser.add_argument('--tester', required=True)
    parser.add_argument('--config', type=Path, default=HERE / 'models.json', help='Shared provider-to-model JSON mapping')
    parser.add_argument('--trials', type=int, default=3)
    parser.add_argument('--data-dir', type=Path, default=DEFAULT_DATA)
    parser.add_argument('--env-file', type=Path, default=HERE.parent / '.env')
    parser.add_argument('--spend', action='store_true', help='Allow paid collection requests')
    parser.add_argument('--limit', type=int, help='At most this many unsaved slots this invocation')
    parser.add_argument('--delay', type=float, default=1.0)
    args = parser.parse_args()
    try:
        identifier(args.batch)
        if args.limit is not None and args.limit < 1 or args.delay < 0:
            raise ValueError('--limit must be positive and --delay nonnegative.')
        if not args.config.exists():
            raise ValueError('Create quarter1/models.json from models.example.json and choose accessible search-capable model IDs.')
        models = json.loads(args.config.read_text(encoding='utf-8'))
        if not isinstance(models, dict):
            raise ValueError('Model config must be a provider-to-model JSON object.')
        directory = args.data_dir / 'batches' / args.batch
        manifest = prepare_batch(directory, args.batch, args.tester, models, args.trials, load_questions())
        # Read keys only for an explicitly paid run. Planning works entirely offline.
        env = load_env(args.env_file) if args.spend else {}
        keys = {p: os.environ.get(k) or env.get(k, '') for p, k in KEY_NAMES.items()} if args.spend else {}
        failed = collect_batch(directory, manifest, keys, args.spend, args.limit, args.delay)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.exit(1, f'Cannot collect: {exc}\n')
    if failed:
        parser.exit(1, f'{failed} slot(s) failed; details are in the private attempts.jsonl. Resume to retry.\n')


if __name__ == '__main__':
    main()
