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
└── (Data Stream 2 folder goes here)
```

Each data stream is self-contained: its own `README.md`, `requirements.txt`, and `.env`.
Run each stream's commands from inside its own folder.

> **Privacy:** reviews contain real patients' health details and this repo is public.
> Collected data (`data/` folders, `*.db`) and API keys (`.env`) are gitignored. Never commit them.

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

*To be filled in by Report Group 2.*

- **Data access and storage:**
- **Software dependencies:**
- **Commands to reproduce:**
