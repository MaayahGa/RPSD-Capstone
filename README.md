# RPSD Capstone: AI Reputation Management for a Fertility Clinic

DSC 180AB capstone (UC San Diego) with **Reproductive Partners Fertility Center – San Diego (RPSD)**.
We study RPSD's online reputation from two angles, each with its own data stream and report group:

| | Data stream | What it captures | Report group |
| --- | --- | --- | --- |
| 1 | **Reviews** | What patients actually write about RPSD (Google, Yelp, and other permitted sources) | Track 1, Judy, Kang |
| 2 | **LLM responses** | What AI assistants say about RPSD when patients ask them | Track 3, Keilani, Kate |

## Repository layout

```
RPSD-Capstone/
├── README.md       this file
├── .gitignore      keeps patient data and API keys out of the repo
├── track1/         Data Stream 1: Reviews
└── stream2/        Data Stream 2: LLM responses
    ├── track2/     sentiment scoring
    └── track3/     collection, labeling, and analysis
```

Each data stream is self-contained: its own `README.md`, requirements, and `.env`.
Run Track 1 commands from inside `track1/` and Stream 2 commands from inside `stream2/`.

> **Privacy:** reviews contain real patients' health details and this repo is public.
> Collected data (`data/` folders, `*.db`) and private settings (`.env`) are gitignored. Never commit them.

---

## Data Stream 1: Reviews

Collects patient reviews of RPSD into one SQLite database with a shared record format
(`reputation_item`), then exports CSV/JSON for severity scoring and analysis.
Sources are **permitted only**: the clinic's own Google Business Profile export (Google Takeout),
the clinic's Yelp business dashboard, and Reddit once API access is approved.
Status of every source is in [`track1/source_inventory.md`](track1/source_inventory.md).

**Full instructions: [`track1/README.md`](track1/README.md)**

Quick start:

```
git clone https://github.com/MaayahGa/RPSD-Capstone.git
cd RPSD-Capstone/track1
python -m pip install -r requirements.txt
cp .env.example .env              # fill in your own keys
python test_importers.py          # offline tests, made-up data
python google/test_places.py      # offline tests, made-up data
```

Getting the data (requires clinic account access; see `track1/README.md` for each step):

```
python google/import_google_takeout.py data/raw/google/takeout-XXXX.zip
python yelp/parse_yelp_paste.py data/raw/yelp/yelp_*star*.txt
python import_manual.py data/raw/yelp/yelp_parsed.csv --source yelp --clinic RPSD
python reputation_item.py summary     # counts per source
python reputation_item.py export      # writes data/exports/*.csv and *.json
```

---

## Data Stream 2: LLM Responses

Asks AI assistants the same 6 patient questions, 3 trials each, then labels RPSD's visibility
(whether it is mentioned, how early, and next to which competitors) and checks each claim about
RPSD against the clinic's fact sheet. Five questions do not name RPSD; one does. Answers come from
two sources, which are kept separate because they can differ:

- **API runs:** OpenAI, Anthropic, and Gemini with web search on (54 answers per batch).
- **Manual browser runs:** each tester uses ChatGPT, Claude, Gemini, Grok, and Microsoft Copilot in
  fresh incognito sessions, logged out where possible, and logs the answers in a tracker sheet (90 answers per tester).

Both sources get the same labels and fact checks, but the analysis workflow below currently covers
API runs only. Labeled manual answers are exported separately as
`data/track3/autolabels-sheet-<tester>-<timestamp>.csv`.

**Full instructions: [`stream2/track3/README.md`](stream2/track3/README.md)**

Paths in this section are relative to `stream2/`.

**Data access and storage**

- Real data is saved in `data/track3/` inside `stream2/`. It is gitignored, so the team shares it privately.
- A real API run requires API keys for the three providers (the OpenAI key also runs labeling) and the
  private Google ID for the clinic fact sheet (ask a teammate), which goes in `track3/.env`. The collection
  notebook asks for keys in hidden prompts; only `track3/run.py` reads them from `track3/.env`.
- Labeling manual answers also requires the tracker sheet's ID and tab IDs in `track3/.env`. If the tab IDs
  are set, the notebook labels those rows too, which adds paid calls. For an API-only run, leave them blank
  or set `SHEET_TABS = {}` in the notebook.
- Without team access, you can still run the offline tests and demo, which need no keys or real data. Their fixtures in `track3/tests/fixtures/` are made up.

**Software dependencies**

- Full workflow, including both notebooks: `track3/requirements_eda.txt` (pandas, matplotlib, ipykernel),
  tested with Python 3.14.
- Command-line collection and labeling only (`track3/run.py`): Python 3.10 or later and `track3/requirements.txt`.

**Commands to reproduce**

Quick start (offline, no keys or spending):

```
git clone https://github.com/MaayahGa/RPSD-Capstone.git
cd RPSD-Capstone/stream2
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r track3/requirements_eda.txt
python track3/run.py test                                       # 14 pipeline checks
python -m unittest discover -s track3/tests -p 'test_*.py'      # 9 EDA checks
python track3/prepare_eda.py --demo                             # writes a one-answer sample input
# To see the analysis, run track3/notebooks/02_explore_responses.ipynb with BATCH_ID = 'sample'
```

Reproduce the results of a saved batch (no keys or spending). AI answers vary between runs, so this is the
way to reproduce a specific result. Ask the Track 3 team for the batch's private files and put them in
`data/track3/`: `<batch>-answers.csv`, one `<batch>-<provider>-raw.jsonl` per provider, and that batch's
`autolabels-api-<timestamp>.csv`. Then, after the install steps above:

```
python track3/prepare_eda.py --batch <batch> --tester <name> --labels data/track3/autolabels-api-<timestamp>.csv
# Then run track3/notebooks/02_explore_responses.ipynb with BATCH_ID = '<batch>'
```

Collect a new batch (**collection and labeling make paid API calls**; see `track3/README.md` for each step):

```
cp -n track3/.env.example track3/.env                           # fill in your Google IDs
# 1. Collect and label: run track3/notebooks/01_collect_and_label.ipynb with a new BATCH_ID
# 2. Build the analysis input:
python track3/prepare_eda.py --batch <batch> --tester <name> --labels data/track3/autolabels-api-<timestamp>.csv
# 3. Analyze: run track3/notebooks/02_explore_responses.ipynb with the same BATCH_ID
```

Results are written to `data/track3/eda/<batch>/`: research tables, figures, and
`responses_for_sentiment.csv`, which is shared privately with Track 2 for sentiment scoring.
