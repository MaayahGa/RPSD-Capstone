"""Rebuild the synthetic test sample in track3/test/testdata/.

Everything here is MADE UP: four short fake AI answers, fake hand labels, and scripted judge outputs
(written by hand below, not produced by a real model). It lets `python track3/run.py test` exercise
the whole pipeline offline and for free.

Re-run this after changing RULES_VERSION / CHECK_RULES_VERSION, the labeling schemas, or the judge model:
    python track3/test/make_testdata.py
"""
import csv, json, shutil, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import rpsd_rules as R     # noqa: E402
import rpsd_tools as T     # noqa: E402

OUT = HERE / 'testdata'
SEED = OUT / 'data_seed'

# ---- fake answers -------------------------------------------------------------------------------
A_T01 = """Here are some San Diego fertility clinics to compare. This is not a definitive ranking.

## 1. San Diego Fertility Center (SDFC)
Large IVF program in Del Mar.

## 2. Reproductive Partners Fertility Center – San Diego
Located in La Jolla and part of UC San Diego Health. Offers IVF and egg freezing, and offers donor egg programs.

## 3. Hanabusa IVF
Known for minimal-stimulation IVF."""

A_T02 = """Two well-known IVF options are San Diego Fertility Center and RMA San Diego / Pearl.
Compare their published success rates for your age group."""

A_T03 = """Reproductive Partners Fertility Center – San Diego (RPSD) is known for its focus on single-embryo transfer.
It also has 4.8 stars on Google."""

A_API = """### 1. Reproductive Partners Fertility Center – San Diego
**Best overall for personalized care**
Located in La Jolla.

### 2. Shady Grove Fertility — Solana Beach
Large national network with a local office."""

P = {q['id']: q for q in R.QUESTIONS}

SHEET_ROWS = [  # (Run ID, prompt, platform, answer, hand labels for columns L-S)
    ('T01', 'P01', 'ChatGPT', A_T01, ['Yes', '2', 'Not explicitly ranked — list/mention order only', 'SDFC; Hanabusa IVF',
                                       'Reproductive Partners … La Jolla', 'La Jolla; IVF; egg freezing; donor eggs',
                                       'Needs qualification — donation/surrogacy arranged externally', 'Synthetic.']),
    ('T02', 'P02', 'Claude', A_T02, ['No', 'N/A — RPSD absent', 'N/A — RPSD absent',
                                      'San Diego Fertility Center; RMA San Diego / Pearl', 'N/A', 'N/A', 'No RPSD claims', 'Synthetic.']),
    ('T03', 'P06', 'Gemini', A_T03, ['Yes', '1', 'N/A — branded description; no comparative recommendation', 'None named',
                                      'RPSD is known for…', 'eSET; 4.8 stars', 'Supported + not documented', 'Synthetic.']),
]

# ---- scripted judge outputs (what a judge model would return), keyed by the answer's first words -----
LABELS = {
    'Here are some San Diego': {'rpsd_mentioned': 'Yes', 'explicit_recommendation_rank': 2,   # judge wrongly "ranks" a hedged list
        'clinics_in_order': [{'name': 'San Diego Fertility Center (SDFC)', 'is_rpsd': False},
                             {'name': 'Reproductive Partners Fertility Center – San Diego', 'is_rpsd': True},
                             {'name': 'Hanabusa IVF', 'is_rpsd': False}],
        'rpsd_claims': [{'claim': 'Located in La Jolla', 'quote': 'Located in La Jolla.'},
                        {'claim': 'Offers IVF and egg freezing', 'quote': 'Offers IVF and egg freezing'},
                        {'claim': 'Offers donor egg programs', 'quote': 'offers donor egg programs'},
                        {'claim': 'Part of UC San Diego Health', 'quote': 'part of UC San Diego Health'}],
        'identity_note': ''},
    'Two well-known IVF options': {'rpsd_mentioned': 'No', 'explicit_recommendation_rank': 0, 'rpsd_claims': [], 'identity_note': '',
        'clinics_in_order': [{'name': 'San Diego Fertility Center', 'is_rpsd': False},
                             {'name': 'RMA San Diego / Pearl', 'is_rpsd': False}]},
    'Reproductive Partners Fertility Center – San Diego (RPSD) is known': {'rpsd_mentioned': 'Yes', 'explicit_recommendation_rank': 0,
        'clinics_in_order': [{'name': 'Reproductive Partners Fertility Center – San Diego (RPSD)', 'is_rpsd': True}],
        'rpsd_claims': [{'claim': 'Focuses on single-embryo transfer', 'quote': 'focus on single-embryo transfer'},
                        {'claim': 'Has 4.8 stars on Google', 'quote': '4.8 stars on Google'},
                        {'claim': 'Has 40 physicians', 'quote': 'forty physicians on staff'}],      # quote not in answer -> dropped
        'identity_note': ''},
    '### 1. Reproductive Partners': {'rpsd_mentioned': 'Yes', 'explicit_recommendation_rank': 1,
        'clinics_in_order': [{'name': 'Reproductive Partners Fertility Center – San Diego', 'is_rpsd': True},
                             {'name': 'Shady Grove Fertility — Solana Beach', 'is_rpsd': False}],
        'rpsd_claims': [{'claim': 'Located in La Jolla', 'quote': 'Located in La Jolla.'}], 'identity_note': ''},
}
CHECKS = {  # claim text -> (verdict, fact ids, explanation)
    'Located in La Jolla': ('supported', ['F02'], ''),
    'Offers IVF and egg freezing': ('supported', ['F04', 'F05', 'F99'], ''),          # F99 is invented -> removed
    'Offers donor egg programs': ('supported', ['F06'], ''),                       # lenient donor rule (check-v3)
    'Part of UC San Diego Health': ('needs_qualification', [], 'The fact sheet describes a relationship, not UCSD ownership.'),
    'Focuses on single-embryo transfer': ('supported', ['F07'], ''),
    'Has 4.8 stars on Google': ('not_documented', [], 'The fact sheet has no ratings.'),
}

def scripted_judge(system, user, schema, name):
    if name == 'rpsd_labels':
        answer = user.split('<answer>\n', 1)[1]
        return next(v for k, v in LABELS.items() if answer.startswith(k))
    claims = [line.split('. ', 1)[1].split(' (answer says:')[0]
              for line in user.split('<claims>\n', 1)[1].splitlines() if line[:1].isdigit()]
    return {'judgments': [{'claim_number': i, 'verdict': CHECKS[c][0], 'fact_ids': CHECKS[c][1], 'explanation': CHECKS[c][2]}
                          for i, c in enumerate(claims, 1)]}


def main():
    shutil.rmtree(SEED, ignore_errors=True); SEED.mkdir(parents=True)
    # tracker tab in the same layout as the real sheet (title/notes rows, then the header)
    with (OUT / 'tracker_sample.csv').open('w', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        w.writerow(['Pilot Testing 1 — SYNTHETIC SAMPLE (made up for the offline test)'])
        for _ in range(6):
            w.writerow([''])
        w.writerow(R.TRACKER_HEADERS[:21])
        for rid, pid, platform, answer, labels in SHEET_ROWS:
            q = P[pid]
            w.writerow([rid, 'Test', pid, q['category'], q['prompt_type'], q['text'], platform, '1', 'Completed',
                        answer, 'synthetic', *labels, '', ''])
    # one saved API answer
    q = P['P01']
    raw = {'scan_id': 'sample-0001', 'run_id': 'sample-openai', 'tester': 'Test', 'prompt_id': 'P01', 'category': q['category'],
           'prompt_type': q['prompt_type'], 'prompt': q['text'], 'engine': 'OpenAI', 'model': 'chat-latest', 'repeat': 1,
           'collected_at': '2026-01-01T00:00:00+00:00', 'collection_mode': 'api_web_search', 'search_setting': 'web_search_on',
           'synthetic': True, 'status': 'success', 'answer': A_API, 'model_returned': 'chat-latest',
           'sources_cited': ['https://www.fertilityclinicsandiego.com/'],
           'source_link_details': [{'url': 'https://www.fertilityclinicsandiego.com/', 'title': 'Sample'}]}
    (SEED / 'Test-sample-openai-raw.jsonl').write_text(json.dumps(raw, ensure_ascii=False) + '\n', encoding='utf-8')

    # produce the judge cache by running the real pipeline with the scripted judge
    work = T.REPO / 'data' / 'track3-test-build'
    shutil.rmtree(work, ignore_errors=True); shutil.copytree(SEED, work)
    T.configure(DATA_DIR=work, TESTER='Test', BATCH_ID='sample', ALLOW_SPENDING=True,
                FACT_SHEET_FILE=str(OUT / 'fact_sheet_sample.html'),
                SHEET_FILES={'Sample': str(OUT / 'tracker_sample.csv')}, SHEET_TABS={'Sample': ''},
                LABEL_API_RESULTS=True, LABEL_SHEET_TABS=['Sample'], MAX_ANSWERS=None)
    T.KEYS[T.JUDGE_PROVIDER] = 'not-used'
    T.judge_json = scripted_judge
    T.http_json = T.fetch_text = lambda *a, **k: (_ for _ in ()).throw(AssertionError('offline'))
    T.load_fact_sheet(); T.gather_items(); T.run_labels()
    shutil.copy(work / 'autolabel-cache.jsonl', SEED / 'autolabel-cache.jsonl')
    shutil.rmtree(work)
    print(f'Rebuilt {OUT} ({len(T.RESULTS)} answers labeled, rules {R.RULES_VERSION}).')


if __name__ == '__main__':
    main()
