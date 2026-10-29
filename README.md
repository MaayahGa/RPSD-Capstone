# RPSD Capstone – Track 1: Reputation Data Collection

DSC 180A capstone project with Reproductive Partners Fertility Center – San Diego (RPSD).
Track 1 collects online reviews of RPSD and nearby competitor clinics from **permitted
sources only** (official APIs, not scraping) for the rest of the reputation pipeline.

## What's here

```
RPSD-Capstone/
├── README.md, requirements.txt, .env.example   setup
├── clinics.json             RPSD + competitors, Google place IDs, name aliases
├── reputation_item.py       shared record format, SQLite database, CSV/JSON export
├── import_manual.py         imports hand-logged reviews/posts from a CSV (any source)
├── test_importers.py        offline tests for everything below (made-up data)
├── source_inventory.md      status, method and limits of every source
├── templates/               blank CSV template for import_manual.py
├── google/
│   ├── import_google_takeout.py   RPSD's full review history from Google Takeout
│   ├── places_test.py             live rating/review check for all clinics (Places API)
│   ├── test_places.py             offline tests for places_test.py
│   └── sample_place.json          made-up Places data for the tests
├── reddit/
│   ├── reddit_collector.py        saves posts + comments naming a clinic (needs approved API app)
│   └── reddit_test.py             early PRAW search test
├── yelp/
│   └── parse_yelp_paste.py        turns text copied from RPSD's Yelp dashboard into a CSV
└── data/                    collected data, NEVER committed (gitignored)
    ├── raw/google/  raw/yelp/  raw/reddit/   downloads and pastes
    ├── reputation.db                          the database
    └── exports/                               CSV/JSON for Tracks 2 and 4
```

**Run every command from the repo root** (the `RPSD-Capstone` folder).

## Setup

1. Clone the repo and go into the folder:
   ```
   git clone https://github.com/MaayahGa/RPSD-Capstone.git
   cd RPSD-Capstone
   ```
2. Install the packages. Use `python -m pip` so they go into the same Python you run the scripts with:
   ```
   python -m pip install -r requirements.txt
   ```
3. Copy the key template and fill in your own keys:
   ```
   cp .env.example .env
   ```
   `.env` is in `.gitignore`. **Never commit it or paste keys anywhere public.**

## Running

Offline tests:
```
python test_importers.py
python google/test_places.py
```

Live Google lookup for all clinics in `clinics.json`:
```
python google/places_test.py
```

## Collecting reviews into the database

Everything ends up in `data/reputation.db` as `reputation_item` records. **`data/` is gitignored:**
reviews contain real patients' health details, and this repo is public.

```
mkdir -p data/raw/google data/raw/yelp data/raw/reddit
python google/import_google_takeout.py data/raw/google/takeout-XXXX.zip
python yelp/parse_yelp_paste.py data/raw/yelp/yelp_*star*.txt
python import_manual.py data/raw/yelp/yelp_parsed.csv --source yelp --clinic RPSD
python reddit/reddit_collector.py                     # once Reddit approves the app
python reputation_item.py summary                     # counts per source and clinic
python reputation_item.py export                      # writes data/exports/
```

Re-running any importer only adds new items (duplicates are skipped by `id`).
`export` writes `reputation_items_all_sources.csv/.json` plus one file per source.

### Fields (same for every source)

| Field | Meaning |
| --- | --- |
| `id` | `<source>_<platform id>`, or a content hash for hand-entered items |
| `source` | `google`, `yelp`, `reddit`, ... |
| `clinic` | Clinic name from `clinics.json` |
| `posted_at` / `collected_at` | When it was posted / when we collected it |
| `rating` | 1-5, blank for Reddit |
| `title` | Reddit post title, blank otherwise |
| `text` | Exactly what was written (blank for star-only Google reviews) |
| `url` | Link to the post, or to the clinic's Google listing (Takeout has no per-review link) |
| `engagement` | Reddit score; blank otherwise |
| `owner_replied` | 1/0 whether the clinic replied publicly |
| `collection_method` | `google_takeout`, `manual_entry`, `reddit_api` |
| `insurance_period` | Export only: `before_2026` or `2026_onward` (clinic's insurance change in Jan 2026) |

No reviewer names, usernames or profile links are ever stored.

## Google Places API setup

1. In [Google Cloud Console](https://console.cloud.google.com), create a project and enable **Places API (New)**.
2. **Link the project to a billing account** (Billing → Link a billing account). The free trial credit works.
   Without this, Google still returns ratings but **silently drops the reviews field**, with no error.
3. Create an API key restricted to **Places API (New)** only, and put it in `.env` as `GOOGLE_PLACES_API_KEY`.

## Limits of the Places API

- **Max 5 reviews per place, chosen by Google** ("most relevant", which skews positive). There is no way to get more through this API.
- **Review content may not be stored.** Google's terms only allow saving **place IDs**. That's why the script prints
  to the screen and `clinics.json` holds only IDs. Don't commit review text, screenshots, or saved output.
- Reviews contain sensitive health details about real patients. Treat anything the scripts print as private.
- Requesting reviews uses Google's most expensive pricing tier. A few runs cost pennies against the free credit,
  but avoid putting this in a loop.
- Look clinics up **by place ID**, not by name search. Searching by name sometimes returned no reviews (RMA San Diego).

For RPSD's **full** review history, the clinic would need to grant access to the
**Google Business Profile API** (owner-only). That's the long-term source for the client's own reviews.

## Adding a clinic

1. Find its place ID with a one-off name search, or with Google's Place ID Finder.
2. Add an entry to `clinics.json` with `name`, `role` (`client` or `competitor`), and `google_place_id`.
3. Run `python google/test_places.py`, then `python google/places_test.py`.
