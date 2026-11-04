# Track 3: What AI assistants say about RPSD

Part of **Report B** (Track 3 + Tracks 2/4). We ask AI assistants the same 6 patient questions, 3 separate trials each, in two ways:
- **Manual browser runs:** each tester types the questions into the AI websites (ChatGPT, Claude, Gemini, Grok, Microsoft Copilot), using a fresh logged-out incognito session per run, and pastes the full answer into the tracker sheet.
- **API runs:** `run.py collect` sends the same questions to the OpenAI, Anthropic and Gemini APIs, with web search on.

Every answer, from either source, is then labeled for RPSD's visibility (mentioned? in what position? next to which competitors?), and every claim about RPSD is checked against the clinic's fact sheet.

```
track3/
├── run.py              build script (all commands below)
├── RPSD_Pilot.ipynb    the same pipeline, step by step, for interactive use
├── rpsd_rules.py       study rules: questions, labeling + fact-check instructions, clinic names
├── rpsd_tools.py       the code: API calls, fact-sheet parsing, caching, normalization, export
├── requirements.txt
└── test/
    ├── make_testdata.py    rebuilds the synthetic sample
    └── testdata/           made-up answers, fact sheet and judge results for the offline test
data/track3/            real results (gitignored, never committed)
```

**Run every command from the repo root** (the `RPSD-Capstone` folder).

## 1. Quick check (no data, no keys, free)
```
python -m pip install -r track3/requirements.txt
python track3/run.py test
```
This runs the full pipeline offline on a synthetic sample and ends with `11/11 checks passed`.

## 2. Software dependencies
- Python **3.10+**
- `pandas` (see `track3/requirements.txt`). Everything else is the Python standard library, and the APIs are called over plain HTTPS.
- On macOS, the python.org installer needs its **"Install Certificates"** step, or every API call fails with "Could not connect". Miniforge/conda Python works as is.

## 3. Accessing and storing the data

| Data | Where it comes from | Access | Stored in |
|---|---|---|---|
| AI answers | Collected by `run.py collect` from the OpenAI, Anthropic and Google Gemini APIs | Your own API keys, from each provider's developer console (the team uses the clinic's Track 3 project/workspace) | `data/track3/<tester>-<batch>-<provider>-raw.jsonl` |
| Manual browser answers + hand labels | Collected by hand (see top) into the "Pilot Testing 1" Google Sheet, one tab per tester | **Private.** Ask the team for the sheet ID | read live, never copied into the repo |
| RPSD fact sheet (ground truth) | Google Doc maintained with the clinic | **Private** (it contains clinic-internal notes). Ask the team | snapshot in `data/track3/factsheet-snapshot-<version>.json` |
| Labels, fact-checks, exports | Produced by `run.py label` / `export` | n/a | `data/track3/` |

Setup for real runs:
1. `cp .env.example .env` in the repo root, then fill in the three `RPSD_*` Google IDs and the API keys you have (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`). `.env` is gitignored, so **never commit it**.
2. `data/` is gitignored. The project's real answers and labels are not published, so without access you can only run the synthetic test (section 1).

## 4. Reproducing the results

### Manual browser runs (by hand)
Each tester collects 6 questions × 5 platforms × 3 trials = 90 answers into their own tab of the tracker sheet:
1. Use the exact wording in `QUESTIONS` (`track3/rpsd_rules.py`). Freeze it before collecting.
2. Platforms: ChatGPT, Claude, Gemini, Grok and Microsoft Copilot (the top five AI chatbots by U.S. desktop visitors, Comscore, March 2026).
3. Use one fresh chat in a new incognito window per run, and close all incognito windows between runs. Stay logged out where possible. If a platform requires login, record the study account and its personalization settings.
4. Record the UTC time, the model shown (or "Unknown"), the search mode and the browser/session in the row.
5. Paste the full answer unchanged into *Full response verbatim*, along with any citation URLs. Answers longer than 32,767 characters (a Google Sheets cell's limit) go in a text file linked from the row.

Then `run.py label` labels these rows together with the API answers.

### API runs and labeling
```
python track3/run.py collect --smoke --spend   # 1 call per provider: check keys and output
python track3/run.py collect --spend           # all 6 questions × 3 trials per provider
python track3/run.py label --spend             # auto-label + fact-check (about 2 judge calls per answer)
python track3/run.py export                    # tracker CSVs + comparison with hand labels (free)
```
- **Without `--spend`, nothing paid is sent.** Each target reports what it *would* send. Saved answers and labels are cached in `data/track3/` and never paid for twice. Re-running resumes where it stopped.
- `--tester NAME` names the result files (default `Audrey`), `--tabs Siya,Audrey` picks the sheet tabs to label, and `--max N` caps labeling.
- Outputs in `data/track3/` (all CSV, open in Excel or Google Sheets):
  - `<tester>-<batch>-answers.csv`: every collected API answer, one row each (model, question, trial, time, full answer, citations, searches, tokens, status)
  - `factsheet-snapshot-<version>.csv`: the numbered fact sheet (F01…) each check used
  - `autolabels-*.csv`: tracker columns L–S plus V (Numbered-list position), ready to paste into the sheet
  - `handlabels-normalized-*.csv`: existing hand labels converted to the standard values
  - `autolabel-vs-human-*.csv`: agreement between the auto-labels and the hand labels
- Internal files (don't edit): `*-raw.jsonl` holds each provider's full raw response (used to resume runs), and `autolabel-cache.jsonl` holds saved judge results (prevents paying twice).
- The notebook `track3/RPSD_Pilot.ipynb` runs the same steps interactively. Its money switch is `ALLOW_SPENDING`.

## What to edit
| To change… | Edit |
|---|---|
| Questions | `QUESTIONS` in `rpsd_rules.py` |
| Labeling instructions | `LABEL_SYSTEM`, then bump `RULES_VERSION` (re-runs labeling) and run `python track3/test/make_testdata.py` |
| Fact-check instructions | `CHECK_SYSTEM`, then bump `CHECK_RULES_VERSION` (re-runs only the fact-check) and run `python track3/test/make_testdata.py` |
| Clinic name merging | `CANONICAL_CLINICS` |
| What counts as an explicit rank | `RANK_LANGUAGE` |
| Models / judge | `MODELS`, `JUDGE_MODEL` at the top of `rpsd_tools.py` (and step 1 of the notebook) |

## Method notes
- **API models:** each provider's everyday free-tier default (ChatGPT `chat-latest`, Claude Sonnet, Gemini Flash). The exact model version is recorded with every answer.
- **Fact-checking:** claims are checked against the fact sheet only. "Not documented" means the claim can't be confirmed, not that it's false.
- **Donor eggs, donor sperm, surrogacy, genetic counseling:** RPSD arranges these with outside partners. A claim that RPSD "offers" them counts as **supported** (lenient rule, `check-v3`).
- **Judge:** one fixed judge model (`gpt-4.1`) labels every platform's answers. Auto-labels are drafts for human review, especially *needs qualification* and *contradicted*.
- **Explicit rank** is recorded only when the AI itself ranks ("best overall", "#1 pick"). A plain numbered list goes in *Numbered-list position* instead.
- **Manual vs API answers:** manual browser answers show what a logged-out user sees on each website. API answers are easier to repeat but may differ from the websites, and no user location is sent with them. Both are labeled with the same rules, and the `AI platform` column says which is which.
