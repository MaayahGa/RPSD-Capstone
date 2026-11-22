"""Quarter 1 file contracts; standard library only, independent of the pilot."""
import csv
import hashlib
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_DATA = HERE.parent.parent / 'data' / 'track3' / 'quarter1'
TOPICS = ('general', 'billing', 'scheduling', 'safety', 'communication')
CLINICS = {'rpsd': 'Reproductive Partners Fertility Center in San Diego',
           'sdfc': 'San Diego Fertility Center'}
KEY_NAMES = {'OpenAI': 'OPENAI_API_KEY', 'Claude': 'ANTHROPIC_API_KEY', 'Gemini': 'GEMINI_API_KEY'}
FIELDS = ['record_id', 'source_run_id', 'batch_id', 'tester', 'question_set_version',
          'clinic_id', 'clinic_name', 'topic', 'question_framing', 'question_id', 'prompt_text',
          'provider', 'model_requested', 'model_returned', 'trial', 'collected_at_utc',
          'completed_at_utc', 'collection_mode', 'search_setting', 'status', 'response_text',
          'citation_urls', 'search_count', 'review_required', 'review_note',
          'sentiment_score', 'sentiment_label', 'sentiment_method', 'sentiment_version']


def identifier(value):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', value):
        raise ValueError('Batch ID must contain only letters, numbers, dots, hyphens, or underscores.')
    return value


def load_questions(path=HERE / 'questions.csv'):
    with Path(path).open(encoding='utf-8-sig', newline='') as f:
        rows = list(csv.DictReader(f))
    expected = {(c, t, framing, str(n)) for c in CLINICS for t in TOPICS
                for framing in ('neutral', 'negative') for n in (1, 2)}
    actual, ids, versions = set(), set(), set()
    for q in rows:
        key = (q['clinic_id'], q['topic'], q['question_framing'], q['question_number'])
        if key not in expected or key in actual or q['question_id'] in ids:
            raise ValueError('Invalid or duplicate question definition.')
        if q['clinic_name'] != CLINICS[q['clinic_id']] or not q['prompt_text'].strip():
            raise ValueError('Invalid clinic name or empty prompt.')
        actual.add(key); ids.add(q['question_id']); versions.add(q['question_set_version'])
    if actual != expected or len(versions) != 1 or not next(iter(versions), ''):
        raise ValueError('Question set must have one version and exactly 40 clinic/topic/framing prompts.')
    return rows


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    tmp.replace(path)


def write_csv(path, rows, fields=FIELDS):
    """Machine-readable UTF-8 CSV; csv handles multiline answers without rewriting text."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    with tmp.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        writer.writeheader(); writer.writerows(rows)
    tmp.replace(path)


def source_id(provider, question_id, trial):
    return f'API-{provider}-{question_id}-{trial}'


def planned_rows(manifest):
    for q in manifest['questions']:
        for provider, model in manifest['models'].items():
            for trial in range(1, manifest['trials'] + 1):
                sid = source_id(provider, q['question_id'], trial)
                yield dict(q, source_run_id=sid, record_id=f"{manifest['batch_id']}:{sid}",
                           batch_id=manifest['batch_id'], tester=manifest['tester'], provider=provider,
                           model_requested=model, trial=str(trial), collection_mode='api_web_search',
                           search_setting='web_search_on')


def attempts(path):
    if not Path(path).exists():
        return []
    with Path(path).open(encoding='utf-8') as f:
        try:
            return [json.loads(line) for line in f if line.strip()]
        except json.JSONDecodeError as exc:
            raise ValueError(f'{path}: damaged attempt log; preserve it and repair the incomplete line before resuming.') from exc


def successful_records(directory, manifest):
    plan = {r['record_id']: r for r in planned_rows(manifest)}
    success = {}
    for attempt in attempts(Path(directory) / 'attempts.jsonl'):
        row = attempt['record']
        rid = row['record_id']
        if rid not in plan or any(str(row.get(k, '')) != str(v) for k, v in plan[rid].items() if k != 'question_number'):
            raise ValueError(f'{rid}: attempt metadata does not match the frozen batch manifest.')
        if row['status'] != 'success':
            continue
        if any(row.get(k) != attempt.get('capture', {}).get(k) for k in
               ('response_text', 'citation_urls', 'model_returned', 'search_count')):
            raise ValueError(f'{rid}: response differs from its original capture.')
        if not row.get('response_text', '').strip():
            raise ValueError(f'{rid}: successful response is empty.')
        if rid in success and success[rid] != row:
            raise ValueError(f'{rid}: conflicting successful captures.')
        success[rid] = row
    return success


def validate_manifest(manifest):
    if manifest.get('schema_version') != 1:
        raise ValueError('Unsupported batch schema.')
    identifier(manifest['batch_id'])
    if not manifest['tester'].strip() or type(manifest['trials']) is not int or manifest['trials'] < 1:
        raise ValueError('Invalid tester or trial count.')
    if not manifest['models'] or any(p not in KEY_NAMES or not isinstance(m, str) or not m.strip() or 'REPLACE_' in m
                                     for p, m in manifest['models'].items()):
        raise ValueError('Invalid provider/model configuration.')
    # Validate the frozen snapshot with the same rules as the shared source.
    questions = manifest['questions']
    expected = {(c, t, f, str(n)) for c in CLINICS for t in TOPICS for f in ('neutral', 'negative') for n in (1, 2)}
    if len(questions) != 40 or len({q['question_id'] for q in questions}) != 40:
        raise ValueError('Manifest must contain 40 distinct questions.')
    if {(q['clinic_id'], q['topic'], q['question_framing'], q['question_number']) for q in questions} != expected:
        raise ValueError('Incomplete question grid in manifest.')
    if len({q['question_set_version'] for q in questions}) != 1 or any(
            q['clinic_name'] != CLINICS[q['clinic_id']] or not q['prompt_text'].strip()
            or not q['question_set_version'] for q in questions):
        raise ValueError('Invalid frozen question metadata.')
    if manifest['question_set_sha256'] != fingerprint(questions):
        raise ValueError('Manifest question checksum mismatch.')
