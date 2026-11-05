"""Build an EDA input from saved API answers, labels, and raw captures. Offline only."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
ANSWER_COLUMNS = {
    'Run ID': 'source_run_id', 'Provider': 'provider', 'Model requested': 'model_requested',
    'Model returned': 'model_returned', 'Prompt ID': 'prompt_id', 'Category': 'category',
    'Prompt type': 'prompt_type', 'Exact prompt': 'prompt_text', 'Trial': 'trial',
    'Status': 'collection_status', 'Collected at (UTC)': 'collected_at_utc',
    'Completed at (UTC)': 'completed_at_utc', 'Answer': 'response_text',
    'Citation URLs': 'citation_urls', 'Citation titles': 'citation_titles',
    'Sources retrieved': 'retrieved_source_urls', 'Web searches': 'web_searches',
    'Search queries': 'search_queries', 'Input tokens': 'input_tokens',
    'Output tokens': 'output_tokens', 'Error': 'collection_error',
}
LABEL_COLUMNS = {
    'Run ID': 'source_run_id', 'Full response verbatim': 'label_response_text',
    'RPSD mentioned': 'auto_rpsd_mentioned', 'First mention order': 'auto_first_mention_order',
    'Explicit recommendation rank': 'auto_explicit_rank',
    'Numbered-list position': 'auto_numbered_list_position',
    'Competitors mentioned': 'auto_competitors',
    'RPSD snippet + surrounding context': 'auto_rpsd_context_candidate',
    'RPSD factual claims': 'auto_rpsd_claims', 'Accuracy assessment': 'auto_accuracy_assessment',
    'Evidence / fact-sheet reference': 'auto_fact_check_evidence',
    'Notes / deviations': 'auto_label_notes',
}


def read_table(path, mapping):
    table = pd.read_csv(path, dtype=str, keep_default_na=False)
    missing = set(mapping) - set(table.columns)
    if missing:
        raise ValueError(f'{path.name}: missing columns {sorted(missing)}')
    return table[list(mapping)].rename(columns=mapping)


def build_input(batch, tester, answers_path, labels_path, raw_dir, output):
    """Validate joins and original text, then write a deterministic, batch-specific table."""
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', batch):
        raise ValueError('Batch must be a filename-safe identifier, not a path.')
    answers = read_table(answers_path, ANSWER_COLUMNS)
    answers = answers.loc[answers.collection_status.eq('success')].copy()
    if answers.empty:
        raise ValueError('No successful answers to prepare.')
    labels = read_table(labels_path, LABEL_COLUMNS)
    for name, table in [('answers', answers), ('labels', labels)]:
        if table.source_run_id.eq('').any() or table.source_run_id.duplicated().any():
            raise ValueError(f'{name}: blank or duplicate Run IDs.')
    merged = answers.merge(labels, on='source_run_id', how='left', validate='one_to_one', indicator=True)
    if not merged['_merge'].eq('both').all():
        raise ValueError('Some answers have no matching labels. Export labels for this batch first.')
    if not merged.response_text.eq(merged.label_response_text).all():
        raise ValueError('Answer/label text mismatch: these labels may belong to a different batch.')
    merged = merged.drop(columns=['_merge', 'label_response_text'])

    captures = {}
    for provider in answers.provider.unique():
        path = raw_dir / f'{batch}-{provider.lower()}-raw.jsonl'
        for line in path.read_text(encoding='utf-8').splitlines():
            row = json.loads(line)
            if row.get('status') == 'success':
                key = f"API-{row['engine']}-{row['prompt_id']}-{row['repeat']}"
                captures[key] = row
    settings = []
    for _, answer in merged.iterrows():
        raw = captures.get(answer.source_run_id)
        if raw is None or raw.get('answer') != answer.response_text:
            raise ValueError(f'{answer.source_run_id}: missing or mismatched original capture.')
        if raw.get('model', '') != answer.model_requested or raw.get('prompt', '') != answer.prompt_text:
            raise ValueError(f'{answer.source_run_id}: original model/prompt metadata mismatch.')
        settings.append({name: raw.get(name, '') for name in
                         ['collection_mode', 'search_setting', 'session_note']})
    for name in ['collection_mode', 'search_setting', 'session_note']:
        merged[name] = [row[name] for row in settings]
    # Read provenance from saved label evidence, never from current model defaults.
    merged['visibility_label_source'] = merged.auto_fact_check_evidence.map(
        lambda text: 'automated:' + match.group(1) if (match := re.search(r'judge ([^\s;]+)', text))
        else 'automated:unspecified')
    merged.insert(0, 'record_id', batch + ':' + merged.source_run_id)
    merged.insert(1, 'batch_id', batch)
    merged.insert(2, 'tester', tester)
    output = output.resolve()
    protected = [answers_path, labels_path, *raw_dir.glob(f'{batch}-*-raw.jsonl')]
    if output in {path.resolve() for path in protected}:
        raise ValueError('Output must not overwrite a source file.')
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix('.tmp')
    merged.to_csv(temporary, index=False, encoding='utf-8-sig')
    temporary.replace(output)
    return merged


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch', help='Collection BATCH_ID, e.g. siya-pilot-01')
    parser.add_argument('--tester', help='Person who collected this batch')
    parser.add_argument('--answers', type=Path, help='Defaults to data/track3/<batch>-answers.csv')
    parser.add_argument('--labels', type=Path, help='Explicit autolabels-api-*.csv export for this batch')
    parser.add_argument('--raw-dir', type=Path, help='Defaults to the answers CSV directory')
    parser.add_argument('--output', type=Path, help='Defaults to data/track3/eda/<batch>/responses_input.csv')
    parser.add_argument('--demo', action='store_true', help='Run the synthetic offline test and prepare its one API answer')
    args = parser.parse_args()
    if args.demo:
        if any([args.batch, args.tester, args.answers, args.labels, args.raw_dir]):
            parser.error('--demo cannot be combined with real-data input arguments.')
        subprocess.run([sys.executable, str(REPO / 'track3/run.py'), 'test'], cwd=REPO, check=True)
        args.batch, args.tester = 'sample', 'Demo'
        args.answers = REPO / 'data/track3-test/sample-answers.csv'
        args.labels = next((REPO / 'data/track3-test').glob('autolabels-api-*.csv'))
    if not (args.batch and args.tester and args.labels):
        parser.error('Provide --batch, --tester, and --labels, or use --demo.')
    answers = args.answers or REPO / f'data/track3/{args.batch}-answers.csv'
    raw_dir = args.raw_dir or answers.parent
    output = args.output or REPO / f'data/track3/eda/{args.batch}/responses_input.csv'
    try:
        table = build_input(args.batch, args.tester, answers, args.labels, raw_dir, output)
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(1, f'Cannot prepare EDA input: {exc}\n')
    print(f'Prepared {len(table)} successful API answers: {output}')
    print('No API calls, credentials, or Google files used. Source files were not changed.')


if __name__ == '__main__':
    main()
