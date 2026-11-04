"""RPSD pilot: all the machinery behind RPSD_Pilot.ipynb.

The notebook sets the settings (configure) and calls these functions in order.
Study rules (questions, labeling instructions, clinic names) live in rpsd_rules.py.

Money safety: nothing here calls a paid API unless ALLOW_SPENDING is True.
Free actions (checking keys, listing models, reading the Google files, cached labels,
normalizing, exporting) always work.
"""
import csv, hashlib, io, json, re, sys, time, uuid
from datetime import datetime, timezone
from getpass import getpass
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

import rpsd_rules as R

# ---------------------------------------------------------------- settings & state
REPO = Path(__file__).resolve().parent.parent      # RPSD-Capstone/
DATA_DIR = REPO / 'data' / 'track3'                 # gitignored (repo-wide data/ rule)
DATA = DATA_DIR
TESTER, BATCH_ID, TRIALS, SMOKE_TEST = 'Audrey', 'api-pilot-01', 3, False
MODELS = {'OpenAI': 'chat-latest', 'Claude': 'claude-sonnet-5-5', 'Gemini': 'gemini-3.8-flash'}   # free-tier default of each app
JUDGE_PROVIDER, JUDGE_MODEL = 'OpenAI', 'gpt-4.1'   # one fixed judge for every platform
SHEET_ID, SHEET_TABS, FACT_DOC_ID = '', {}, ''     # private: read from .env
FACT_SHEET_FILE, SHEET_FILES = '', {}               # optional local copies (used by the offline test)
LABEL_API_RESULTS, LABEL_SHEET_TABS, MAX_ANSWERS = True, [], None
ACCURACY_REFERENCE_TABS = ['Audrey']                # tabs whose hand accuracy labels were made from the fact sheet
ALLOW_SPENDING = False

KEYS, MODEL_LISTS, ACCESS = {}, {}, {}           # keys live only in this Python session
FACTS, FACT_TEXT, FACT_VERSION, FACT_FETCHED, FACT_IDS = [], '', '', '', set()
ITEMS, RESULTS, FAILED, SKIPPED = [], [], [], []
CACHE = {}


def configure(**settings):
    """Set module settings from the notebook (unknown names are an error, to catch typos)."""
    global DATA
    g = globals()
    for k, v in settings.items():
        if k not in g or k.startswith('_') or callable(g[k]) or k in ('DATA', 'REPO'):
            raise NameError(f'Unknown setting {k!r}')
        g[k] = v
    DATA = Path(DATA_DIR)
    DATA.mkdir(parents=True, exist_ok=True)
    text_dir().mkdir(exist_ok=True)
    CACHE.clear()
    CACHE.update({r['key']: r['value'] for r in read_jsonl(cache_path())})


class NeedsSpending(Exception):
    """Raised instead of making a paid call while ALLOW_SPENDING is False."""


def load_env(path=None):
    """Read KEY=value lines from the repo's .env (gitignored). Private IDs live there, not in the code."""
    path = Path(path or REPO / '.env')
    env = {}
    if path.exists():
        for line in path.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env

def sheet_tabs_from_env(value):
    """'Siya:111,Audrey:222' -> {'Siya': '111', 'Audrey': '222'}"""
    return dict(part.split(':', 1) for part in (value or '').split(',') if ':' in part)

def raw_path(provider):
    return DATA / f'{TESTER}-{BATCH_ID}-{provider.lower()}-raw.jsonl'

def text_dir():
    return DATA / f'{TESTER}-{BATCH_ID}-texts'

def cache_path():
    return DATA / 'autolabel-cache.jsonl'

def read_jsonl(path):
    return [json.loads(s) for s in path.read_text(encoding='utf-8').splitlines() if s.strip()] if path.exists() else []

def save_record(path, row):
    with path.open('a', encoding='utf-8') as f:
        f.write(json.dumps(row, ensure_ascii=False) + '\n')

# ---------------------------------------------------------------- HTTP
def http_json(url, headers, secret, body=None, timeout=300):
    data = json.dumps(body).encode() if body is not None else None
    hdrs = dict(headers)
    if data is not None:
        hdrs['content-type'] = 'application/json'
    req = Request(url, data=data, headers=hdrs, method='POST' if data is not None else 'GET')
    try:
        with urlopen(req, timeout=timeout) as resp:
            return json.load(resp)
    except HTTPError as exc:
        text = exc.read().decode('utf-8', errors='replace')
        try:
            err = json.loads(text).get('error', text)
            text = err.get('message', text) if isinstance(err, dict) else str(err)
        except (ValueError, AttributeError):
            pass
        msg = f'HTTP {exc.code}: {text[:1500]}'
        err = RuntimeError(msg.replace(secret, '[REDACTED]') if secret else msg)
        err.status = exc.code
        raise err from None
    except URLError as exc:
        raise RuntimeError(f'Could not connect: {exc.reason}') from None

def fetch_text(url, timeout=60):
    try:
        with urlopen(Request(url, headers={'User-Agent': 'rpsd-pilot'}), timeout=timeout) as resp:
            return resp.read().decode('utf-8')
    except HTTPError as exc:
        raise RuntimeError(f'HTTP {exc.code} fetching {url}. Is the file still shared as "anyone with the link"?') from None
    except URLError as exc:
        raise RuntimeError(f'Could not connect: {exc.reason}') from None

def call_with_retry(fn, *args):
    for attempt in range(3):
        try:
            return fn(*args)
        except RuntimeError as exc:
            if getattr(exc, 'status', None) in (429, 500, 502, 503, 504, 529) and attempt < 2:
                wait = 20 * (attempt + 1)
                print(f'    {exc} (retrying in {wait}s)')
                time.sleep(wait)
                continue
            raise

# ---------------------------------------------------------------- 2 · keys (free)
def _list_openai(key):
    return [m['id'] for m in http_json('https://api.openai.com/v1/models', {'Authorization': f'Bearer {key}'}, key).get('data', [])]

def _list_claude(key):
    ids, after_id, seen = [], None, set()
    while True:
        params = {'limit': 100, **({'after_id': after_id} if after_id else {})}
        r = http_json('https://api.anthropic.com/v1/models?' + urlencode(params),
                      {'x-api-key': key, 'anthropic-version': '2026-10-21'}, key)
        ids += [m['id'] for m in r.get('data', [])]
        if not r.get('has_more'):
            return ids
        after_id = r.get('last_id')
        if not after_id or after_id in seen:
            raise RuntimeError('Model-list pagination did not advance. Retry.')
        seen.add(after_id)

def _list_gemini(key):
    ids, token, seen = [], None, set()
    while True:
        params = {'pageSize': 1000, **({'pageToken': token} if token else {})}
        r = http_json('https://generativelanguage.googleapis.com/v1beta/models?' + urlencode(params), {'x-goog-api-key': key}, key)
        ids += [m['name'].removeprefix('models/') for m in r.get('models', [])
                if 'generateContent' in m.get('supportedGenerationMethods', [])]
        token = r.get('nextPageToken')
        if not token:
            return ids
        if token in seen:
            raise RuntimeError('Model-list pagination did not advance. Retry.')
        seen.add(token)

_LISTERS = {'OpenAI': _list_openai, 'Claude': _list_claude, 'Gemini': _list_gemini}

def enter_keys(show_models=False):
    """Hidden prompt per provider (Enter = skip, or keep a key entered earlier). Listing models is free."""
    for provider in MODELS:
        key = getpass(f'{provider} API key (Enter to skip{" / keep" if provider in KEYS else ""}): ').strip()
        if not key:
            print(f'{provider}: ' + ('kept the key entered earlier.' if provider in KEYS else 'skipped.'))
            if provider not in KEYS:
                ACCESS[provider] = 'Skipped'
            continue
        try:
            MODEL_LISTS[provider] = sorted(_LISTERS[provider](key))
            KEYS[provider] = key
            ACCESS[provider] = f'Connected: {len(MODEL_LISTS[provider])} models listed'
            print(f'{provider}: connected ({len(MODEL_LISTS[provider])} models).')
            if show_models:
                print('  ' + '\n  '.join(MODEL_LISTS[provider]))
        except Exception as exc:
            ACCESS[provider] = 'Check failed'
            print(f'{provider}: {str(exc).replace(key, "[REDACTED]")}')
            print('  Check that this key belongs to the clinic Track 3 project/workspace.')
        finally:
            key = None

ENV_KEY_NAMES = {'OpenAI': 'OPENAI_API_KEY', 'Claude': 'ANTHROPIC_API_KEY', 'Gemini': 'GEMINI_API_KEY'}

def keys_from_env(env):
    """Command-line use: take API keys from .env / environment variables (checked by listing models, free)."""
    import os
    for provider, name in ENV_KEY_NAMES.items():
        key = (env.get(name) or os.environ.get(name) or '').strip()
        if not key:
            continue
        try:
            MODEL_LISTS[provider] = sorted(_LISTERS[provider](key))
            KEYS[provider] = key
            ACCESS[provider] = f'Connected: {len(MODEL_LISTS[provider])} models listed'
        except Exception as exc:
            ACCESS[provider] = 'Check failed'
            print(f'{provider}: key in {name} failed: {str(exc).replace(key, "[REDACTED]")}')
        finally:
            key = None

def ready_providers():
    return [p for p in MODELS if p in KEYS and MODELS[p] and MODELS[p].removeprefix('models/') in MODEL_LISTS.get(p, [])]

def status():
    """What's ready (no keys printed)."""
    for p, model in MODELS.items():
        if p not in KEYS:
            s = 'no key - will be skipped'
        elif not model:
            s = 'key OK, no model chosen'
        elif model.removeprefix('models/') not in MODEL_LISTS.get(p, []):
            s = f'key OK, but {model!r} is not available to this key'
        else:
            s = f'READY with {model}'
        print(f"{p}: {ACCESS.get(p, 'Not run yet')} | {s}")
    j = JUDGE_PROVIDER in KEYS and JUDGE_MODEL.removeprefix('models/') in MODEL_LISTS.get(JUDGE_PROVIDER, [])
    print(f"Fact-check judge: {JUDGE_PROVIDER} · {JUDGE_MODEL} | {'READY' if j else 'not available yet'}")
    print(f"ALLOW_SPENDING = {ALLOW_SPENDING}" + ('' if ALLOW_SPENDING else '  (free mode: no paid calls will be made)'))

# ---------------------------------------------------------------- 4 · collect (paid)
def _dedupe(links):
    seen, out = set(), []
    for link in links:
        if link.get('url') and link['url'] not in seen:
            seen.add(link['url']); out.append(link)
    return out

def ask_openai(model, prompt, key):
    r = http_json('https://api.openai.com/v1/responses', {'Authorization': f'Bearer {key}'}, key,
                  {'model': model, 'input': prompt, 'tools': [{'type': 'web_search'}]})
    texts, links, searches = [], [], 0
    for item in r.get('output', []):
        if item.get('type') == 'web_search_call':
            searches += 1
        if item.get('type') == 'message':
            for part in item.get('content', []):
                if part.get('type') == 'output_text':
                    texts.append(part.get('text', ''))
                    links += [{'url': a.get('url'), 'title': a.get('title')} for a in part.get('annotations', [])
                              if a.get('type') == 'url_citation']
                elif part.get('type') == 'refusal':
                    texts.append('[REFUSAL] ' + part.get('refusal', ''))
    return {'answer': '\n'.join(texts).strip(), 'links': _dedupe(links), 'retrieved': [], 'model_returned': r.get('model'),
            'stop': r.get('status'), 'searches': searches, 'usage': r.get('usage'), 'raw': r}

def ask_claude(model, prompt, key):
    messages = [{'role': 'user', 'content': prompt}]
    tools = [{'type': 'web_search_20260209', 'name': 'web_search', 'max_uses': 5}]
    headers = {'x-api-key': key, 'anthropic-version': '2026-10-21'}
    raws, content = [], []
    for _ in range(4):                                   # resume if the server pauses a long search turn
        r = http_json('https://api.anthropic.com/v1/messages', headers, key,
                      {'model': model, 'max_tokens': 16000, 'tools': tools, 'messages': messages})
        raws.append(r); content += r.get('content', [])
        if r.get('stop_reason') != 'pause_turn':
            break
        messages = messages + [{'role': 'assistant', 'content': r['content']}]
    texts, links, retrieved, searches = [], [], [], 0
    for b in content:
        t = b.get('type')
        if t == 'text':
            texts.append(b.get('text', ''))
            links += [{'url': c.get('url'), 'title': c.get('title')} for c in b.get('citations') or []
                      if c.get('type') == 'web_search_result_location']
        elif t == 'server_tool_use' and b.get('name') == 'web_search':
            searches += 1
        elif t == 'web_search_tool_result' and isinstance(b.get('content'), list):
            retrieved += [{'url': x.get('url'), 'title': x.get('title')} for x in b['content']]
    usage = {}
    for r in raws:
        for k, v in (r.get('usage') or {}).items():
            if isinstance(v, (int, float)):
                usage[k] = usage.get(k, 0) + v
    return {'answer': ''.join(texts).strip(), 'links': _dedupe(links), 'retrieved': _dedupe(retrieved),
            'model_returned': raws[-1].get('model'), 'stop': raws[-1].get('stop_reason'), 'searches': searches,
            'usage': usage, 'raw': raws if len(raws) > 1 else raws[0]}

def ask_gemini(model, prompt, key):
    r = http_json(f'https://generativelanguage.googleapis.com/v1beta/models/{model.removeprefix("models/")}:generateContent',
                  {'x-goog-api-key': key}, key,
                  {'contents': [{'role': 'user', 'parts': [{'text': prompt}]}], 'tools': [{'google_search': {}}]})
    cand = (r.get('candidates') or [{}])[0]
    texts = [p['text'] for p in (cand.get('content') or {}).get('parts', []) if 'text' in p and not p.get('thought')]
    gm = cand.get('groundingMetadata') or {}
    links = [{'url': c['web'].get('uri'), 'title': c['web'].get('title')} for c in gm.get('groundingChunks', []) if 'web' in c]
    return {'answer': ''.join(texts).strip(), 'links': _dedupe(links), 'retrieved': [], 'model_returned': r.get('modelVersion'),
            'stop': cand.get('finishReason'), 'searches': len(gm.get('webSearchQueries', [])),
            'search_queries': gm.get('webSearchQueries', []), 'usage': r.get('usageMetadata'), 'raw': r}

ASK = {'OpenAI': ask_openai, 'Claude': ask_claude, 'Gemini': ask_gemini}

def collect():
    """Send each not-yet-saved question/trial to each READY provider. Already-saved slots are never re-sent."""
    plan = [(q, t) for q in R.QUESTIONS for t in range(1, TRIALS + 1)]
    if SMOKE_TEST:
        plan = plan[:1]
    ready = ready_providers()
    if not ready:
        print('No provider is READY. Run the keys and status cells first.')
    would_cost = 0
    for provider in ready:
        path, model = raw_path(provider), MODELS[provider]
        done = {(r['prompt_id'], r['repeat']) for r in read_jsonl(path) if r.get('status') == 'success'}
        todo = [(q, t) for q, t in plan if (q['id'], t) not in done]
        print(f'\n=== {provider} · {model} · {len(plan) - len(todo)} already saved, {len(todo)} to send')
        if not ALLOW_SPENDING:
            would_cost += len(todo)
            continue
        for q, trial in todo:
            row = {'scan_id': str(uuid.uuid4()), 'run_id': f'{BATCH_ID}-{provider.lower()}', 'tester': TESTER,
                   'prompt_id': q['id'], 'category': q['category'], 'prompt_type': q['prompt_type'], 'prompt': q['text'],
                   'engine': provider, 'model': model, 'repeat': trial,
                   'collected_at': datetime.now(timezone.utc).isoformat(),
                   'collection_mode': 'api_web_search', 'search_setting': 'web_search_on',
                   'session_note': 'Fresh single-turn API request; no history, no system prompt, provider default sampling',
                   'synthetic': False, 'needs_capture_review': False, 'citation_review_pending': True}
            try:
                res = call_with_retry(ASK[provider], model, q['text'], KEYS[provider])
                if not res['answer']:
                    raise ValueError(f'Empty answer (stop reason: {res["stop"]})')
                text_file = text_dir() / f'{row["scan_id"]}-original.txt'
                text_file.write_text(res['answer'], encoding='utf-8')
                row.update(status='success', answer=res['answer'], original_capture=res['answer'],
                           sources_cited=[l['url'] for l in res['links']], source_link_details=res['links'],
                           sources_retrieved=res['retrieved'], search_count=res['searches'],
                           search_queries=res.get('search_queries'), model_returned=res['model_returned'],
                           stop_reason=res['stop'], usage=res['usage'], raw_response=res['raw'],
                           citation_capture='API citation fields (see rpsd_tools.ask_*)',
                           capture_method='api_response_text', raw_text_path=str(text_file),
                           completed_at=datetime.now(timezone.utc).isoformat())
            except Exception as exc:
                row.update(status='failed', answer=None, error_type=type(exc).__name__, error_message=str(exc)[:1500])
            save_record(path, row)
            extra = (f'{len(row.get("sources_cited", []))} citations, {row.get("search_count", 0)} searches, '
                     f'usage={row.get("usage")}') if row['status'] == 'success' else row['error_message'][:300]
            print(f'  {q["id"]} trial {trial}: {row["status"]} · {extra}')
            time.sleep(2)
    export_answers_csv()
    if not ALLOW_SPENDING:
        print(f'\nFree mode: {would_cost} paid call(s) would be sent. Nothing was sent. '
              'Set ALLOW_SPENDING = True in Settings to run them.' if would_cost else '\nNothing new to send.')

def _tokens(usage):
    """(input, output) tokens, whatever the provider calls them."""
    u = usage or {}
    return (u.get('input_tokens', u.get('promptTokenCount', '')),
            u.get('output_tokens', u.get('candidatesTokenCount', '')))

ANSWER_COLUMNS = ['Run ID', 'Tester', 'Provider', 'Model requested', 'Model returned', 'Prompt ID', 'Category',
                  'Prompt type', 'Exact prompt', 'Trial', 'Status', 'Collected at (UTC)', 'Completed at (UTC)',
                  'Answer', 'Citation URLs', 'Citation titles', 'Web searches', 'Search queries',
                  'Input tokens', 'Output tokens', 'Error']

def export_answers_csv(quiet=False):
    """All collected API answers as one CSV (latest attempt per provider/question/trial). Free."""
    rows = []
    for provider in MODELS:
        slots = {}
        for r in read_jsonl(raw_path(provider)):
            k = (r['prompt_id'], r['repeat'])
            if k not in slots or slots[k].get('status') != 'success':
                slots[k] = r
        for r in sorted(slots.values(), key=lambda r: (r['prompt_id'], r['repeat'])):
            links = r.get('source_link_details') or []
            tin, tout = _tokens(r.get('usage'))
            rows.append({
                'Run ID': f"API-{provider}-{r['prompt_id']}-{r['repeat']}", 'Tester': r.get('tester', ''),
                'Provider': provider, 'Model requested': r.get('model', ''), 'Model returned': r.get('model_returned', ''),
                'Prompt ID': r['prompt_id'], 'Category': r.get('category', ''), 'Prompt type': r.get('prompt_type', ''),
                'Exact prompt': r.get('prompt', ''), 'Trial': r['repeat'], 'Status': r.get('status', ''),
                'Collected at (UTC)': r.get('collected_at', ''), 'Completed at (UTC)': r.get('completed_at', ''),
                'Answer': r.get('answer') or '', 'Citation URLs': '\n'.join(l.get('url') or '' for l in links),
                'Citation titles': '\n'.join(str(l.get('title') or '') for l in links),
                'Web searches': r.get('search_count', ''), 'Search queries': '\n'.join(r.get('search_queries') or []),
                'Input tokens': tin, 'Output tokens': tout, 'Error': r.get('error_message', '')})
    if not rows:
        return None
    path = DATA / f'{TESTER}-{BATCH_ID}-answers.csv'
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=ANSWER_COLUMNS); w.writeheader()
        for row in rows:
            w.writerow({k: _safe(v) for k, v in row.items()})
    if not quiet:
        print(f'Saved {len(rows)} collected answers → {path.name}')
    return path

def results_table():
    rows = []
    for provider in MODELS:
        slots = {}
        for r in read_jsonl(raw_path(provider)):
            k = (r['prompt_id'], r['repeat'])
            if k not in slots or slots[k].get('status') != 'success':
                slots[k] = r
        for r in slots.values():
            ans = r.get('answer') or ''
            rows.append({'engine': provider, 'model': r.get('model_returned') or r.get('model'), 'prompt': r['prompt_id'],
                         'trial': r['repeat'], 'status': r['status'],
                         'RPSD named': bool(re.search(R.RPSD_PATTERN, ans, re.I)) if ans else None,
                         'citations': len(r.get('sources_cited') or []), 'searches': r.get('search_count'),
                         'words': len(ans.split()), 'error': (r.get('error_message') or '')[:120]})
    return pd.DataFrame(rows).sort_values(['engine', 'prompt', 'trial']) if rows else pd.DataFrame()

def show_answer(provider, prompt_id, trial):
    for r in read_jsonl(raw_path(provider)):
        if r['prompt_id'] == prompt_id and r['repeat'] == trial and r.get('status') == 'success':
            print(r['answer'], '\n\nCitations:')
            for l in r['source_link_details']:
                print(' -', l.get('title') or '', l['url'])
            print('\nUsage:', r.get('usage'))
            return
    print('No successful record for that provider/prompt/trial yet.')

# ---------------------------------------------------------------- 6 · fact sheet + sheet (free)
class _DocParser(HTMLParser):
    """Collects tables (rows of cell text) and the text blocks between them, in order."""
    def __init__(self):
        super().__init__()
        self.items, self.depth, self.cell, self.block = [], 0, None, None
    def handle_starttag(self, tag, attrs):
        if tag == 'table':
            self.depth += 1
            if self.depth == 1:
                self.items.append(('table', []))
        elif self.depth and tag == 'tr':
            self.items[-1][1].append([])
        elif self.depth and tag == 'td':
            self.cell = []
        elif not self.depth and tag in ('p', 'h1', 'h2', 'h3', 'h4', 'li'):
            self.block = []
        elif tag == 'br' and self.cell is not None:
            self.cell.append(' ')
    def handle_endtag(self, tag):
        if tag == 'table':
            self.depth -= 1
        elif tag == 'td' and self.cell is not None:
            self.items[-1][1][-1].append(' '.join(''.join(self.cell).split()))
            self.cell = None
        elif not self.depth and tag in ('p', 'h1', 'h2', 'h3', 'h4', 'li') and self.block is not None:
            text = ' '.join(''.join(self.block).split())
            if text:
                self.items.append(('text', text))
            self.block = None
    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)
        elif self.block is not None:
            self.block.append(data)

def load_fact_sheet():
    """Read the fact sheet Google Doc into numbered facts F01..; saves a versioned snapshot."""
    global FACTS, FACT_TEXT, FACT_VERSION, FACT_FETCHED, FACT_IDS
    html = (Path(FACT_SHEET_FILE).read_text(encoding='utf-8') if FACT_SHEET_FILE
            else fetch_text(f'https://docs.google.com/document/d/{FACT_DOC_ID}/export?format=html'))
    p = _DocParser(); p.feed(html)
    facts, section, n = [], 'General', 0
    for kind, content in p.items:
        if kind == 'text':
            if content.startswith('*'):
                n += 1
                facts.append({'id': f'F{n:02d}', 'section': section, 'category': 'Note', 'fact': content.lstrip('* '), 'source': '', 'verified': ''})
            elif len(content) < 60 and not content.endswith('.'):
                section = content                        # short line before a table = section heading
            continue
        rows = [r for r in content if any(c for c in r)]
        if len(rows) < 2 or any('Example insurance fact' in c for r in rows for c in r):
            continue                                     # empty or the template table
        header = rows[0]
        for r in rows[1:]:
            r = r + [''] * (len(header) - len(r))
            cols = {h.lower(): v for h, v in zip(header, r)}
            source = next((v for h, v in cols.items() if h.startswith('source')), '')
            verified = next((v for h, v in cols.items() if h.startswith('last verified')), '')
            body = [f'{h}: {v}' for h, v in zip(header[1:], r[1:]) if v and not h.lower().startswith(('source', 'last verified'))]
            n += 1
            facts.append({'id': f'F{n:02d}', 'section': section, 'category': r[0], 'fact': '; '.join(body),
                          'source': source, 'verified': verified})
    FACT_TEXT = '\n'.join(f"{f['id']} [{f['section']} / {f['category']}] {f['fact']}"
                          + (f" (source: {f['source']}; verified {f['verified']})" if f['source'] or f['verified'] else '')
                          for f in facts)
    FACTS, FACT_IDS = facts, {f['id'] for f in facts}
    FACT_VERSION = hashlib.sha256(FACT_TEXT.encode()).hexdigest()[:10]
    FACT_FETCHED = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    snap = DATA / f'factsheet-snapshot-{FACT_VERSION}.json'
    snap.write_text(json.dumps({'fetched': datetime.now(timezone.utc).isoformat(), 'doc_id': FACT_DOC_ID,
                                'version': FACT_VERSION, 'facts': facts}, ensure_ascii=False, indent=1), encoding='utf-8')
    with (DATA / f'factsheet-snapshot-{FACT_VERSION}.csv').open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['id', 'section', 'category', 'fact', 'source', 'verified']); w.writeheader()
        w.writerows(facts)
    print(f'{len(facts)} fact-sheet rows · version {FACT_VERSION} · snapshot {snap.stem}.csv/.json')
    return pd.DataFrame(facts)[['id', 'section', 'category', 'fact']]

def _load_sheet_tab(tab):
    text = (Path(SHEET_FILES[tab]).read_text(encoding='utf-8') if tab in SHEET_FILES
            else fetch_text(f'https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={SHEET_TABS[tab]}'))
    rows = list(csv.reader(io.StringIO(text)))
    h = next(i for i, r in enumerate(rows) if 'Run ID' in r and 'Full response verbatim' in r)
    header = rows[h]
    out = []
    for r in rows[h + 1:]:
        rec = dict(zip(header, r + [''] * (len(header) - len(r))))
        if rec.get('Run ID') and rec.get('Full response verbatim', '').strip():
            out.append(rec)
    return out

def gather_items():
    """API results + every sheet row with a pasted answer. Hand labels (L-S) are kept for comparison."""
    ITEMS.clear()
    if LABEL_API_RESULTS:
        for provider in MODELS:
            slots = {}
            for r in read_jsonl(raw_path(provider)):
                if r.get('status') == 'success':
                    slots[(r['prompt_id'], r['repeat'])] = r
            for r in slots.values():
                ITEMS.append({'source': 'api', 'human': None, 'base': {
                    'Run ID': f"API-{provider}-{r['prompt_id']}-{r['repeat']}", 'Tester': r['tester'],
                    'Prompt ID': r['prompt_id'], 'Category': r['category'], 'Prompt type': r['prompt_type'],
                    'Exact prompt': r['prompt'], 'AI platform': f"{provider} API ({r.get('model_returned') or r['model']}, web search)",
                    'Run number': r['repeat'], 'Status': 'Completed', 'Full response verbatim': r['answer'],
                    'Raw response / screenshot link': str(text_dir() / Path(r['raw_text_path']).name) if r.get('raw_text_path') else '',
                    'Citation URLs': '\n'.join(r.get('sources_cited') or []) or 'No citation URLs returned by the API',
                    '_cited_titles': ' '.join(str(l.get('title') or '') for l in (r.get('source_link_details') or []))}})
    for tab in LABEL_SHEET_TABS:
        for rec in _load_sheet_tab(tab):
            ITEMS.append({'source': f'sheet:{tab}', 'base': {k: rec.get(k, '') for k in R.TRACKER_HEADERS},
                          'human': {k: rec.get(k, '') for k in R.TRACKER_HEADERS[11:19]}})
    return pd.Series([i['source'] for i in ITEMS]).value_counts() if ITEMS else 'none'

# ---------------------------------------------------------------- normalization (free)
def _low(s):
    return ' '.join((s or '').replace('–', '-').replace('—', '-').replace('’', "'").split()).lower()

def canonical_clinic(name):
    n = _low(name)
    for canon, pat in R.CANONICAL_CLINICS:
        if re.search(pat, n):
            return canon
    return re.sub(r'\s*\([A-Z]{2,6}\)\s*$', '', (name or '').strip())   # drop a trailing "(ABC)" abbreviation

def canonical_list(names):
    out = []
    for n in names:
        if not _low(n) or _low(n).startswith(('n/a', 'none')):
            continue
        c = canonical_clinic(n)
        if c not in out:
            out.append(c)
    return out

_ITEM = re.compile(r'^\s*(?:#{1,6}\s*)?(?:[*_]{1,2})?(\d{1,2})[.)](?:[*_]{1,2})?\s+(.*)$')

def numbered_position(answer):
    """Number of the first numbered heading/list item whose own line names RPSD; '' if none."""
    for line in (answer or '').splitlines():
        m = _ITEM.match(line)
        if m and re.search(R.RPSD_PATTERN, m.group(2), re.I):
            return int(m.group(1))
    return ''

def rpsd_item_text(answer):
    """Text of RPSD's numbered entry (its line through the next numbered line); '' if not in a numbered list."""
    lines = (answer or '').splitlines()
    for i, line in enumerate(lines):
        m = _ITEM.match(line)
        if m and re.search(R.RPSD_PATTERN, m.group(2), re.I):
            out = [line]
            for nxt in lines[i + 1:]:
                if _ITEM.match(nxt):
                    break
                out.append(nxt)
            return '\n'.join(out)
    return ''

def normalize_human(item):
    """Hand labels (L-S) mapped onto the standard values; returns (labels, list of changes)."""
    h, base, ch = item['human'], item['base'], []
    out = dict(h)
    m = h.get('RPSD mentioned', '').strip().capitalize()
    out['RPSD mentioned'] = m
    o = h.get('First mention order', '').strip()
    out['First mention order'] = o if o.isdigit() else (R.NA_ABSENT if m == 'No' else '')
    pos = '' if m == 'No' else numbered_position(base.get('Full response verbatim', ''))
    out['Numbered-list position'] = R.NA_ABSENT if m == 'No' else pos
    r = h.get('Explicit recommendation rank', '').strip()
    if m == 'No':
        out['Explicit recommendation rank'] = R.NA_ABSENT
    elif base.get('Prompt type') == 'Branded':
        out['Explicit recommendation rank'] = R.NA_BRANDED
    elif r.isdigit() and pos != '' and int(r) == pos:
        out['Explicit recommendation rank'] = ''
        ch.append(f"rank {r} was RPSD's numbered-list position, moved to Numbered-list position")
    elif r.isdigit():
        out['Explicit recommendation rank'] = r
        ch.append(f'rank {r} kept - check it is an explicit ranking')
    else:
        out['Explicit recommendation rank'] = ''
    out['Competitors mentioned'] = '; '.join(canonical_list(re.split(r'[;\n]', h.get('Competitors mentioned', ''))))
    a = _low(h.get('Accuracy assessment', ''))
    if a in R.HUMAN_ACCURACY_MAP:
        std = R.HUMAN_ACCURACY_MAP[a] or (R.NA_ABSENT if m == 'No' else 'No specific RPSD factual claims')
        if std != h.get('Accuracy assessment', '').strip():
            ch.append(f'accuracy "{h["Accuracy assessment"].strip()}" -> "{std}"')
        out['Accuracy assessment'] = std
    elif a:
        ch.append('accuracy wording not in HUMAN_ACCURACY_MAP, left as is')
    return out, ch

# ---------------------------------------------------------------- 7 · label + fact-check (paid, cached)
def _strip_additional(schema):
    if isinstance(schema, dict):
        return {k: _strip_additional(v) for k, v in schema.items() if k != 'additionalProperties'}
    if isinstance(schema, list):
        return [_strip_additional(v) for v in schema]
    return schema

def judge_json(system, user, schema, name):
    """One structured-output call to the judge model; returns parsed JSON."""
    p, m, key = JUDGE_PROVIDER, JUDGE_MODEL, KEYS[JUDGE_PROVIDER]
    if p == 'OpenAI':
        r = http_json('https://api.openai.com/v1/responses', {'Authorization': f'Bearer {key}'}, key,
                      {'model': m, 'instructions': system, 'input': user,
                       'text': {'format': {'type': 'json_schema', 'name': name, 'schema': schema, 'strict': True}}})
        text = ''.join(part.get('text', '') for item in r.get('output', []) if item.get('type') == 'message'
                       for part in item.get('content', []) if part.get('type') == 'output_text')
    elif p == 'Claude':
        r = http_json('https://api.anthropic.com/v1/messages', {'x-api-key': key, 'anthropic-version': '2026-10-21'}, key,
                      {'model': m, 'max_tokens': 16000, 'system': system, 'messages': [{'role': 'user', 'content': user}],
                       'output_config': {'format': {'type': 'json_schema', 'schema': schema}}})
        if r.get('stop_reason') == 'refusal':
            raise RuntimeError(f'Judge declined (refusal): {r.get("stop_details")}')
        text = ''.join(b.get('text', '') for b in r.get('content', []) if b.get('type') == 'text')
    elif p == 'Gemini':
        r = http_json(f'https://generativelanguage.googleapis.com/v1beta/models/{m.removeprefix("models/")}:generateContent',
                      {'x-goog-api-key': key}, key,
                      {'systemInstruction': {'parts': [{'text': system}]},
                       'contents': [{'role': 'user', 'parts': [{'text': user}]}],
                       'generationConfig': {'responseMimeType': 'application/json', 'responseJsonSchema': _strip_additional(schema)}})
        parts = ((r.get('candidates') or [{}])[0].get('content') or {}).get('parts', [])
        text = ''.join(x.get('text', '') for x in parts if not x.get('thought'))
    else:
        raise ValueError(f'Unknown judge provider {p}')
    try:
        return json.loads(text)
    except ValueError:
        raise RuntimeError(f'Judge did not return valid JSON: {text[:300]!r}') from None

def norm(s):
    s = (s or '').replace('’', "'").replace('‘', "'").replace('“', '"').replace('”', '"')
    s = s.replace('–', '-').replace('—', '-').replace(' ', ' ')
    s = re.sub(r'(?m)^[ \t]*(?:[-*•]|\d+[.)])[ \t]+', '', s)   # ignore list bullets / numbers at line starts
    s = re.sub(r'[*_#`>]+', '', s)                                  # ignore markdown emphasis/heading marks
    return ' '.join(s.split()).lower()

def cached(kind, payload, fn):
    """Reuse a saved judge result; only call fn (paid) when missing AND spending is allowed."""
    key = kind + ':' + hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    if key not in CACHE:
        if not ALLOW_SPENDING:
            raise NeedsSpending(kind)
        CACHE[key] = fn()
        save_record(cache_path(), {'key': key, 'value': CACHE[key]})
    return CACHE[key]

def snippets(answer, extra_quotes, chars=220, limit=3):
    spans = [(m.start(), m.end()) for m in re.finditer(R.RPSD_PATTERN, answer, re.I)]
    out, covered = [], 0
    for start, end in spans:
        if start < covered:
            continue
        a, b = max(covered, start - chars), min(len(answer), end + chars)   # never repeat earlier text
        out.append(answer[a:b].strip()); covered = b
        if len(out) == limit:
            break
    if not out:                                          # RPSD named some other way: fall back to the claim quotes
        out = extra_quotes[:limit]
    return '\n…\n'.join(out)

def assess(mentioned, claims, judgments):
    if mentioned == 'No':
        return 'N/A - RPSD not mentioned'
    if not claims:
        return 'No specific RPSD factual claims'
    verdicts = {j['verdict'] for j in judgments}
    if 'contradicted' in verdicts:
        return 'Contradicts fact sheet - review'
    if 'needs_qualification' in verdicts:
        return 'Needs qualification - review'
    if verdicts == {'supported'}:
        return 'Supported by fact sheet'
    if 'supported' in verdicts:
        return 'Supported + not documented'
    return 'Not documented in fact sheet'

def evidence_text(claims, judgments):
    lines = [f'Auto fact-check vs RPSD fact sheet (fetched {FACT_FETCHED}, version {FACT_VERSION}); judge {JUDGE_MODEL}.']
    labels = {'supported': 'SUPPORTED', 'needs_qualification': 'NEEDS QUALIFICATION',
              'contradicted': 'CONTRADICTED', 'not_documented': 'NOT DOCUMENTED'}
    for verdict in ('contradicted', 'needs_qualification', 'not_documented', 'supported'):
        for c, j in zip(claims, judgments):
            if j['verdict'] == verdict:
                ids = ', '.join(j['fact_ids'])
                lines.append(f"{labels[verdict]}: {c['claim']}" + (f' [{ids}]' if ids else '') +
                             (f" - {j['explanation']}" if verdict != 'supported' else ''))
    lines.append('Method: claims compared only with the fact sheet; not documented = cannot confirm, not false. Draft - needs human review.')
    return '\n'.join(lines)

def label_one(item):
    answer, question = item['base']['Full response verbatim'], item['base']['Exact prompt']
    lab = cached('label', [R.RULES_VERSION, JUDGE_PROVIDER, JUDGE_MODEL, question, answer], lambda: call_with_retry(
        judge_json, R.LABEL_SYSTEM,
        f'Question the user asked:\n{question}\n\n<answer>\n{answer}\n</answer>', R.LABEL_SCHEMA, 'rpsd_labels'))
    n_answer = norm(answer)
    def quote_found(q):
        parts = [norm(x) for x in (q or '').splitlines() if norm(x)]
        return bool(parts) and all(p in n_answer for p in parts)
    claims = [c for c in lab['rpsd_claims'] if quote_found(c['quote'])]
    dropped = len(lab['rpsd_claims']) - len(claims)
    mentioned = lab['rpsd_mentioned']
    if mentioned == 'No' and re.search(R.RPSD_PATTERN, answer, re.I):
        mentioned = 'Unclear'                            # name appears but judge said no: flag for a human
    judgments = []
    if claims and mentioned != 'No':
        numbered = '\n'.join(f"{i}. {c['claim']} (answer says: \"{c['quote']}\")" for i, c in enumerate(claims, 1))
        chk = cached('check', [R.RULES_VERSION, JUDGE_PROVIDER, JUDGE_MODEL, FACT_VERSION, numbered], lambda: call_with_retry(
            judge_json, R.CHECK_SYSTEM,
            f"Today's date: {FACT_FETCHED}\n\n<fact_sheet>\n{FACT_TEXT}\n</fact_sheet>\n\n<claims>\n{numbered}\n</claims>",
            R.CHECK_SCHEMA, 'rpsd_fact_check'))
        by_num = {j['claim_number']: j for j in chk['judgments']}
        for i in range(1, len(claims) + 1):
            j = dict(by_num.get(i) or {'verdict': 'not_documented', 'fact_ids': [], 'explanation': 'Judge returned no verdict for this claim.'})
            j['fact_ids'] = [f for f in j['fact_ids'] if f in FACT_IDS]       # drop invented IDs
            judgments.append(j)
    clinics = lab['clinics_in_order']
    first = next((i for i, c in enumerate(clinics, 1) if c['is_rpsd']), None)
    competitors = canonical_list([c['name'] for c in clinics if not c['is_rpsd']])
    rank = lab['explicit_recommendation_rank']
    pos = numbered_position(answer)
    rank_note = ''
    if rank and pos != '' and rank == pos and not re.search(R.RANK_LANGUAGE, rpsd_item_text(answer), re.I):
        rank, rank_note = 0, f'Judge rank {pos} equals RPSD\'s numbered-list position with no ranking language; recorded as list position only.'
    priority = [p for p in R.PRIORITY_COMPETITORS if p in competitors]
    notes = [f'Auto-labeled ({R.RULES_VERSION}).']
    if dropped:
        notes.append(f'{dropped} claim(s) dropped: quote not found verbatim in the answer.')
    if rank_note:
        notes.append(rank_note)
    if lab['identity_note']:
        notes.append('Identity: ' + lab['identity_note'])
    if priority:
        notes.append('Priority competitors present: ' + '; '.join(priority) + '.')
    cited = (item['base'].get('Citation URLs', '') + ' ' + item['base'].get('_cited_titles', '')).lower()
    if mentioned == 'No' and 'fertilityclinicsandiego' in cited:
        notes.append("RPSD's website was cited as a source, but RPSD is not named in the answer.")
    row = dict(item['base'])
    row.update({
        'RPSD mentioned': mentioned,
        'First mention order': R.NA_ABSENT if mentioned == 'No' else (first or ''),
        'Explicit recommendation rank': R.NA_ABSENT if mentioned == 'No' else
            (R.NA_BRANDED if item['base'].get('Prompt type') == 'Branded' else (rank or '')),
        'Competitors mentioned': '; '.join(competitors),
        'RPSD snippet + surrounding context': snippets(answer, [c['quote'] for c in claims]) if mentioned != 'No' else R.NA_ABSENT,
        'RPSD factual claims': '; '.join(c['claim'] for c in claims) if claims else (R.NA_ABSENT if mentioned == 'No' else 'None extracted'),
        'Accuracy assessment': assess(mentioned, claims, judgments),
        'Evidence / fact-sheet reference': evidence_text(claims, judgments) if judgments else
            f'Fact sheet version {FACT_VERSION}: no RPSD claims to check.' + (' Visibility omission, not an accuracy failure.' if mentioned == 'No' else ''),
        'Numbered-list position': R.NA_ABSENT if mentioned == 'No' else numbered_position(answer),
    })
    own = [item['base'].get('Notes / deviations', '')] if item['source'].startswith('sheet:') else []
    row['Notes / deviations'] = ' '.join(filter(None, own + notes))
    return row, judgments

def run_labels():
    """Label up to MAX_ANSWERS answers. Cached ones are free; uncached ones need ALLOW_SPENDING."""
    if not FACT_VERSION:
        raise RuntimeError('Load the fact sheet first.')
    RESULTS.clear(); FAILED.clear(); SKIPPED.clear()
    todo = ITEMS if MAX_ANSWERS is None else ITEMS[:MAX_ANSWERS]
    for n, item in enumerate(todo, 1):
        rid = item['base']['Run ID']
        try:
            row, judgments = label_one(item)
            RESULTS.append((item, row, judgments))
            print(f"{n}/{len(todo)} {rid}: {row['RPSD mentioned']} · order {row['First mention order'] or '-'} · {row['Accuracy assessment']}")
        except NeedsSpending as exc:
            SKIPPED.append(rid)
        except Exception as exc:
            FAILED.append((rid, str(exc)))
            print(f'{n}/{len(todo)} {rid}: FAILED · {str(exc)[:300]}')
    print(f'\nLabeled {len(RESULTS)} (from cache or new), failed {len(FAILED)}, not attempted {len(ITEMS) - len(todo)}.')
    if SKIPPED:
        print(f'Free mode: {len(SKIPPED)} answer(s) need new judge calls (about {2 * len(SKIPPED)} calls) and were skipped: '
              f'{", ".join(SKIPPED[:10])}{" …" if len(SKIPPED) > 10 else ""}. Set ALLOW_SPENDING = True to run them.')

# ---------------------------------------------------------------- 8 · export + compare (free)
def _safe(v):
    v = '' if v is None else str(v)
    return "'" + v if v.lstrip().startswith(('=', '+', '-', '@')) else v

def _write(path, rows):
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=R.TRACKER_HEADERS, extrasaction='ignore'); w.writeheader()
        for row in rows:
            w.writerow({k: _safe(row.get(k, '')) for k in R.TRACKER_HEADERS})

def export_and_compare():
    """Save auto-labels and normalized hand labels as tracker CSVs; return the auto-vs-hand comparison table."""
    export_answers_csv()
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M')
    by_source = {}
    for item, row, _ in RESULTS:
        by_source.setdefault(item['source'].replace(':', '-'), []).append(row)
    for source, rows in by_source.items():
        path = DATA / f'autolabels-{source}-{stamp}.csv'; _write(path, rows)
        print(f'Saved {len(rows)} auto-labeled rows → {path.name}')
    human, by_tab = {}, {}
    for item in ITEMS:
        if not item['human'] or not item['human'].get('RPSD mentioned', '').strip():
            continue
        hn, changes = normalize_human(item)
        human[item['base']['Run ID']] = hn
        row = dict(item['base']); row.update(hn)
        if changes:
            row['Notes / deviations'] = ' '.join(filter(None, [row.get('Notes / deviations', ''), 'Normalized: ' + '; '.join(changes) + '.']))
        by_tab.setdefault(item['source'].split(':')[1], []).append(row)
    for tab, rows in by_tab.items():
        path = DATA / f'handlabels-normalized-{tab}-{stamp}.csv'; _write(path, rows)
        print(f'Saved {len(rows)} normalized hand-labeled rows → {path.name}')
    fields = ['RPSD mentioned', 'First mention order', 'Explicit recommendation rank', 'Accuracy assessment']
    recs = []
    for item, row, _ in RESULTS:
        hn = human.get(row['Run ID'])
        if not hn:
            continue
        tab = item['source'].split(':')[1]
        hs = set(hn['Competitors mentioned'].split('; ')) - {''}
        auto = set(row['Competitors mentioned'].split('; ')) - {''}
        rec = {'Run ID': row['Run ID'], 'platform': row['AI platform'], 'prompt': row['Prompt ID'],
               'competitor overlap': round(len(hs & auto) / len(hs | auto), 2) if (hs | auto) else 1.0}
        for k in fields:
            rec[f'{k} (human)'], rec[f'{k} (auto)'] = str(hn.get(k, '')), str(row.get(k, ''))
        if tab not in ACCURACY_REFERENCE_TABS:            # hand accuracy not made from the fact sheet: not a valid reference
            rec['Accuracy assessment (human)'] = 'not compared (not fact-sheet based)'
        recs.append(rec)
    if not recs:
        print('No hand-labeled sheet rows among the labeled answers to compare.')
        return pd.DataFrame()
    cmp = pd.DataFrame(recs)
    print(f'\nAuto vs normalized hand labels: {len(cmp)} rows')
    for k in fields:
        sub = cmp[cmp[f'{k} (human)'] != 'not compared (not fact-sheet based)']
        if sub.empty:
            print(f'  {k}: not compared (no fact-sheet-based hand labels among these rows; see ACCURACY_REFERENCE_TABS)')
            continue
        agree = sub[f'{k} (human)'].str.lower() == sub[f'{k} (auto)'].str.lower()
        print(f'  {k}: {agree.mean():.0%} agree (n={len(sub)})' + (f'  (disagree: {", ".join(sub.loc[~agree, "Run ID"])})' if (~agree).any() else ''))
    print(f"  Competitor list overlap (avg Jaccard): {cmp['competitor overlap'].mean():.2f}")
    path = DATA / f'autolabel-vs-human-{stamp}.csv'
    cmp.to_csv(path, index=False, encoding='utf-8-sig')
    print('Saved comparison →', path.name)
    for rid, err in FAILED:
        print('FAILED', rid, err[:200])
    return cmp

def inspect(run_id=None):
    for item, row, judgments in RESULTS:
        if run_id in (None, row['Run ID']):
            print(row['Run ID'], '·', row['AI platform'], '·', row['Exact prompt'])
            for k in R.TRACKER_HEADERS[11:19] + ['Numbered-list position', 'Notes / deviations']:
                print(f'\n[{k}]\n{row.get(k, "")}')
            if item['human']:
                print('\n--- hand labels ---')
                for k, v in item['human'].items():
                    print(f'[{k}] {v[:400]}')
            return
    print('Labeled Run IDs:', [r['Run ID'] for _, r, _ in RESULTS][:30])
