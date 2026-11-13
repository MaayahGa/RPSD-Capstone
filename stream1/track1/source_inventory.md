# Track 1 Source Inventory

Updated: 2026-10-28. One row per source; update the status column weekly.

| Source | Method | What we get | Can we store it? | Status |
| --- | --- | --- | --- | --- |
| Google (RPSD) | Google Takeout export from the capstone account (`import_google_takeout.py`) | Every review: rating, full text, date, whether the clinic replied | Yes, it's the clinic's own data | **Ready to run.** Export is manual; repeat monthly or switch to the Business Profile API later |
| Google (RPSD, automated) | Google Business Profile API | Same as Takeout, on a schedule | Yes | Needs an API access application from the capstone account; Google reviews these |
| Google (competitors) | Places API (`places_test.py`) | Rating, review count, 5 reviews Google picks | **No**, only place IDs | Working; live checks only. Rating + count snapshots are the usable part |
| Yelp (RPSD) | Copy from biz.yelp.com Reviews page into the template (`import_manual.py`) | Rating, full text, date | Clinic's internal use; confirm with Brooke | Access granted. Asking Yelp rep (via Brooke) whether an official export exists |
| Yelp (competitors) | Yelp Places API (paid, $229+/mo) | 0-7 review excerpts | Check terms | On hold; not worth the cost for excerpts |
| Reddit | Reddit API + PRAW (`reddit_collector.py`) | Posts and comments naming a clinic, date, score | Per Reddit Data API terms | **Apply for access with UCSD email** (non-commercial research). Until approved, log threads by hand in the template |
| FertilityIQ | TBD | Detailed doctor/clinic reviews | Check terms | Check whether RPSD has a profile and what the terms allow |
| Healthgrades / Vitals / Zocdoc | TBD | Doctor-level reviews | Check terms | Check which RPSD physicians have profiles |
| Facebook | TBD | Page reviews/recommendations | Check terms | Ask Brooke if the clinic manages a Facebook page |

## Rules for every source
- Official API, the clinic's own export, or hand entry from the clinic's own dashboard. No scraping tools or browser extensions.
- Never store reviewer names, usernames or profile links.
- Never commit collected data to GitHub (`data/` is gitignored; the repo is public).

## Open questions for the clinic
1. Can the capstone account submit a Google Business Profile API access application?
2. Does the Yelp account rep offer a review export for RPSD (the clinic runs Yelp Ads, so it has a rep)?
3. Is it OK to copy Yelp reviews from the business dashboard into our dataset for internal analysis?
