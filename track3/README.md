# Track 3: What AI assistants say about RPSD

Part of **Report B** (Track 3 + Tracks 2/4). We ask AI assistants the same 6 patient questions, 3 separate trials each, in two ways:
- **Manual browser runs:** each tester types the questions into the AI websites (ChatGPT, Claude, Gemini, Grok, Microsoft Copilot), using a fresh logged-out incognito session per run, and pastes the full answer into the tracker sheet.
- **API runs:** `run.py collect` sends the same questions to the OpenAI, Anthropic and Gemini APIs, with web search on.

Every answer, from either source, is then labeled for RPSD's visibility (mentioned? in what position? next to which competitors?), and every claim about RPSD is checked against the clinic's fact sheet.

## How the work fits together

Collect answers, label them, explore the results, then send a CSV to Track 2.
A full API batch has **54 answers: 6 questions × 3 trials × 3 providers**.
Keep browser and API results separate because they can produce different answers.

## Files

```text
track3/
├── README.md
├── .env.example                      # Blank private-settings template
├── requirements.txt                  # Collection, labeling, preparation, tests
├── requirements_eda.txt              # EDA and notebook dependencies
├── RPSD_Pilot.ipynb                   # Interactive collection and labeling
├── run.py                            # Command-line pipeline and offline demo test
├── rpsd_rules.py                     # Exact prompts, label rules, clinic aliases
├── rpsd_tools.py                     # Collection, saved labels, fact checks, exports
├── prepare_eda.py                    # Build the EDA input from saved API outputs
├── notebooks/
│   └── 02_explore_responses.ipynb     # Research questions, graphs, and findings
└── test/
    ├── make_testdata.py              # Rebuild synthetic fixtures
    ├── test_eda.py                  # Input-preparation and notebook matching checks
    └── testdata/                     # Fake answers, fact sheet, tracker, cached judgments
```

Save real data and results in **`data/track3/`**. This folder and `track3/.env`
are excluded from Git. Share data privately with the team.

## Setup

Run terminal commands from the **repository root**, `RPSD-Capstone/`.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r track3/requirements_eda.txt
```

This installs the packages needed for the full workflow. It was tested with
Python 3.14. In VS Code, select `.venv` as the notebook kernel. For collection
only, use `track3/requirements.txt` with Python 3.10 or later.

For live collection, copy the settings template:

```bash
cp -n track3/.env.example track3/.env
```

Add your API keys and clinic fact-sheet ID to `.env`. Add tracker IDs if you
are including manual responses. Keep this file private. The script reads Google
export links directly, so being signed in to Google in your browser may not be
enough for it to access a document.

## Try the process without keys or real data

```bash
python track3/prepare_eda.py --demo
```

This checks the pipeline using made-up data and creates:

```text
data/track3/eda/sample/responses_input.csv
```

Open `track3/notebooks/02_explore_responses.ipynb`, set `BATCH_ID = 'sample'`, and run
all cells. The demo has **one made-up API response**. It shows how the notebook
works; its results are not findings about RPSD.

## 1 Collect and label API responses

Open **`track3/RPSD_Pilot.ipynb`** and run its cells in order:

1. Give your run a unique `BATCH_ID`, such as `tester1_pilot-01`. Keep `TRIALS = 3`.
2. Check the model settings. Use the same questions in `rpsd_rules.py` for the whole batch.
3. Load the clinic fact-sheet ID from `track3/.env`. For an API-only run, set
   `SHEET_TABS = {}` in the settings cell. Otherwise, configure the intended tracker tabs.
4. Keep `ALLOW_SPENDING = False` while checking settings and provider access.
   The notebook's key cell asks for keys using hidden prompts.
5. Confirm the intended providers are READY. Set `ALLOW_SPENDING = True` to collect
   actual answers; the full three-provider batch has 54 collection requests.
6. Run collection, inspect saved answers, load the fact sheet, run labeling and
   claim checking, then export. New labels/checks also use paid judge calls.
7. Turn spending off after the run. Retain the raw captures and exported labels.

Original API responses are saved before analysis. Labels, snippets, and fact
checks are added separately; the answer is not rewritten. Rerunning the same
batch skips saved successful requests. Use a new batch ID for a new round.

You can also use the terminal for the **default batch configured in the code**:

```bash
python track3/run.py collect --spend
python track3/run.py label --spend
python track3/run.py export
```

`run.py` has no `--batch` option, so the notebook is easier for separate named
runs. The terminal label/export commands require the Google sheet and fact-sheet
IDs. `--spend` allows paid calls; without it, the script may still read Google
files or check model access. `--max N` limits labeling, not collection.

### Saved collection and label outputs

| File in `data/track3/` | Contents |
|---|---|
| `<batch>-<provider>-raw.jsonl` | Original provider payload, answer text, prompt/model metadata, citations, usage, status |
| `<batch>-texts/` | Individual extracted answer text files |
| `<batch>-answers.csv` | Answer table: provider/models, exact question, trial, UTC times, full answer, citations, searches, tokens, errors |
| `autolabels-api-<timestamp>.csv` | API answers with automatic visibility, claims, context, and fact-check evidence |
| `factsheet-snapshot-<version>.csv/.json` | Versioned clinic reference used for checking claims |
| `autolabel-cache.jsonl` | Saved judge results used to resume labeling |
| `handlabels-normalized-*.csv`, `autolabel-vs-human-*.csv` | Optional manual-label normalization and visibility agreement comparisons |

The raw filenames use the **batch ID**, not a separate tester prefix. Include your
name in a unique batch ID and pass the tester separately during EDA preparation.

## 2 Generate the EDA input

Use the answers CSV, the API-label export for that batch, and its raw JSONL files.
Obtain these privately from the collector or use your own saved run. No API keys,
Google access, or new model calls are required for this step.

For example, to prepare Siya's saved batch:

```bash
python track3/prepare_eda.py --batch siya-pilot-01 --tester Siya --labels data/track3/siya-pilot-01-labels.csv
```

Replace these values with your batch and label file. The normal label export is
named `autolabels-api-<timestamp>.csv`. Choose the file from the right run.

The script writes **`data/track3/eda/<batch>/responses_input.csv`**. It combines
successful answers, labels, and collection settings. It checks IDs and original
text so labels from another batch are not accidentally joined to your answers.

This input includes API responses only. Use `--answers`, `--raw-dir`, or `--output`
if your files are elsewhere. Rerunning the command replaces the generated input;
keep your own analysis in the notebook or a separate file.

## 3 Explore the research questions

Open **`track3/notebooks/02_explore_responses.ipynb`**, set the same `BATCH_ID`, and
run top to bottom. The notebook uses saved measurements; it does not repeat paid
collection, labeling, fact-checking, or sentiment scoring.

The notebook has graphs and short findings for six questions:

1. Which questions are associated with RPSD appearing or disappearing?
2. How consistent are the three trials?
3. When RPSD appears, how early is it mentioned?
4. Which competitors appear alongside it?
5. Which claim types most often need qualification?
6. Which records need human review?

P01–P05 do not name RPSD; P06 does. The notebook keeps them separate and shows
the counts behind each rate. Claim topics are grouped by keywords, so review
those groups and the automatic labels before using the findings in a report.

`auto_competitor_positions` estimates where competitors first appear in the
answer. It uses the saved competitor list and includes RPSD when matched.
These are **mention positions, not recommendation ranks**. Unmatched names stay
null, and uncertain matches are flagged. Existing labels are kept.

### EDA outputs

```text
data/track3/eda/<batch>/
├── responses_input.csv             # Generated combined input
├── responses_for_sentiment.csv     # Track 2 handoff
├── research_tables/                # Counts, denominators, record-level evidence
│   └── findings.csv                # Six short findings
└── figures/                        # Six research figure panels
```

Use `inspect_response(record_id)` to read the answer behind a result. Clear the
reusable notebook's saved outputs before committing it. Keep executed copies
with real responses in `data/`.

## 4 Hand off to Track 2

Share `responses_for_sentiment.csv` privately. It includes original responses,
collection metadata, RPSD visibility/context, and estimated competitor positions.
Track 2 adds the sentiment labels and scores.

`response_text` contains the full answer. `auto_rpsd_context_candidate` contains
RPSD snippets, which may not be complete paragraphs. Agree with Track 2 on which
passage to score. An absent mention is not neutral sentiment, and sentiment does
not tell you whether a claim is accurate.

## Manual browser runs (by hand)
Each tester collects 6 questions × 5 platforms × 3 trials = 90 answers into their own tab of the tracker sheet:
1. Use the exact wording in `QUESTIONS` (`track3/rpsd_rules.py`). Freeze it before collecting.
2. Platforms: ChatGPT, Claude, Gemini, Grok and Microsoft Copilot (the top five AI chatbots by U.S. desktop visitors, Comscore, March 2026).
3. Use one fresh chat in a new incognito window per run, and close all incognito windows between runs. Stay logged out where possible. If a platform requires login, record the study account and its personalization settings.
4. Record the UTC time, the model shown (or "Unknown"), the search mode and the browser/session in the row.
5. Paste the full answer unchanged into *Full response verbatim*, along with any citation URLs. Answers longer than 32,767 characters (a Google Sheets cell's limit) go in a text file linked from the row.

Then `run.py label` labels these rows together with the API answers.

## Tests

`track3/test/` contains software checks and fake example data. `test_eda.py` checks
CSV preparation and the competitor-position function defined in the notebook. It does not hold
our real responses. `make_testdata.py` rebuilds the examples after rule changes.

```bash
python track3/run.py test
python -m unittest discover -s track3/test -p 'test_*.py' -v
```

The first command runs **14 pipeline checks**. The second runs **8 checks** for
CSV preparation and competitor matching. Both work offline without keys or
spending. Passing means the code handles the examples correctly, not that every
automatic label on real data is correct.

## Changing the study

| Change | Edit |
|---|---|
| Questions | `QUESTIONS` in `rpsd_rules.py`; start a new batch after changing prompts |
| Visibility rules | `LABEL_SYSTEM` / schema; bump `RULES_VERSION` and rebuild synthetic fixtures |
| Fact-check rules | `CHECK_SYSTEM` / schema; bump `CHECK_RULES_VERSION` and rebuild fixtures |
| Canonical clinic names | `CANONICAL_CLINICS` in `rpsd_rules.py` |
| Competitor text matching | Competitor-position helper cell in `notebooks/02_explore_responses.ipynb` |
| Models / judge | Collection notebook settings or defaults in `rpsd_tools.py` |
| Research plots / provisional topics | `notebooks/02_explore_responses.ipynb` |

Rebuild fixtures with `python track3/test/make_testdata.py`.

## Interpretation notes

- API and consumer-site outputs can differ; record actual model versions and modes.
- The fixed judge is configured as `gpt-4.1`; automatic labels are drafts for review.
- Fact-checking uses the clinic fact sheet only. “Not documented” means unconfirmed,
  not false. Under `check-v3`, donor/surrogacy/genetic-counseling offerings may be
  supported when arranged through outside partners.
- First mention order, numbered-list position, and explicit recommendation rank
  measure different things. An ordinary numbered list is not an explicit rank.
- Human-label comparisons concern visibility; claim accuracy uses the fact sheet.
