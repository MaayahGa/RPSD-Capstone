# RPSD Capstone – Track 1: Reputation Data Collection

DSC 180A capstone project with Reproductive Partners Fertility Center – San Diego (RPSD).
Track 1 collects online reviews of RPSD and nearby competitor clinics from **permitted
sources only** (official APIs, not scraping) for the rest of the reputation pipeline.

## What's here

| File | What it does |
| --- | --- |
| `places_test.py` | Looks up each clinic on Google by place ID and prints its rating, review count, and up to 5 reviews |
| `clinics.json` | RPSD and the 3 priority competitors, with their Google place IDs |
| `test_places.py` | Offline tests for the Places code (no API key or internet needed) |
| `sample_place.json` | **Made-up** review data in Google's format, used by the tests |
| `reddit_test.py` | Early test of searching Reddit for clinic mentions (PRAW) |
| `reputation_item.py` | Shared record format, SQLite database (`data/reputation.db`), and CSV/JSON export |
| `import_google_takeout.py` | Imports RPSD's **full** Google review history from a Google Takeout export |
| `import_manual.py` | Imports hand-logged reviews/posts (Yelp, Reddit, FertilityIQ...) from a CSV |
| `templates/manual_reviews_template.csv` | Blank template for `import_manual.py` |
| `reddit_collector.py` | Saves Reddit posts **and comments** naming a clinic (needs approved API app) |
| `test_importers.py` | Offline tests for the importers, all made-up data |
| `source_inventory.md` | Status, method and limits for every source |
| `requirements.txt` | Python packages the scripts need |
| `.env.example` | Template for your API keys |

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

Offline tests (should print `6/6 tests passed`):
```
python test_places.py
```

Live Google lookup for all clinics in `clinics.json`:
```
python places_test.py
```

## Collecting reviews into the database

Everything ends up in `data/reputation.db` as `reputation_item` records. **`data/` is gitignored:**
reviews contain real patients' health details, and this repo is public.

```
mkdir -p data/raw                                     # put downloads here
python import_google_takeout.py data/raw/takeout-XXXX.zip
python import_manual.py data/raw/yelp_rpsd.csv
python reddit_collector.py                            # once Reddit approves the app
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
3. Run `python test_places.py`, then `python places_test.py`.
