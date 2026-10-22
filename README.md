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
