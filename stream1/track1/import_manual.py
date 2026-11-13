"""
Import hand-logged reviews/posts from a CSV (Yelp, Reddit, FertilityIQ, ...).

Use this for sources without an export or approved API yet: copy each
review from the clinic's own business dashboard (e.g. biz.yelp.com ->
Reviews) or log a Reddit thread you found, one row per review/post/comment.

Start from templates/manual_reviews_template.csv (save your copy in
data/raw/, which is gitignored). Columns:

  source         yelp, reddit, fertilityiq, ...       (required)
  clinic         full name or alias from clinics.json  (required)
  posted_at      2026-10-12, 10/12/2026 or Oct 12, 2026 (required)
  rating         1-5, blank if the site has none
  title          Reddit post title (blank otherwise)
  text           the review, copied exactly            (required)
  url            link to the review or post
  native_id      the site's own ID if visible (Reddit post ID, Yelp review ID)
  engagement     Reddit score, Yelp "useful" count, etc. (optional)
  owner_replied  yes/no if the clinic replied publicly (optional)

NEVER enter reviewer names or usernames.

Run:
    python import_manual.py data/raw/yelp_rpsd.csv
    # a sheet with only posted_at, rating, text, owner_replied columns:
    python import_manual.py data/raw/yelp_rpsd.csv --source yelp --clinic RPSD
    python reputation_item.py export
"""

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path

from reputation_item import DB_PATH, make_item, save_items

CLINICS_FILE = Path(__file__).parent / "clinics.json"
REQUIRED = ["source", "clinic", "posted_at", "text"]


def resolve_clinic(value, clinics):
    value = value.strip().lower()
    for clinic in clinics:
        names = [clinic["name"]] + clinic.get("aliases", [])
        if any(value == n.lower() for n in names):
            return clinic["name"]
    return None


DATE_FORMATS = ["%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%b %d, %Y", "%B %d, %Y"]


def parse_date(value):
    """Accept the formats a person or a spreadsheet is likely to use
    (2026-10-12, 10/12/2026, Oct 12, 2026) and return YYYY-MM-DD, or None."""
    value = value.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def parse_bool(value):
    value = (value or "").strip().lower()
    if value in ("yes", "y", "true", "1"):
        return True
    if value in ("no", "n", "false", "0"):
        return False
    return None


def parse_rows(rows, clinics, default_source="", default_clinic=""):
    """Return (items, errors). Rows with problems are reported, not imported.

    default_source / default_clinic fill in those columns when a sheet
    leaves them out (e.g. a Yelp sheet that is all RPSD).
    """
    items, errors = [], []
    for line, row in enumerate(rows, start=2):  # line 1 is the header
        row = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
        if not any(row.values()):
            continue
        row["source"] = row.get("source") or default_source
        row["clinic"] = row.get("clinic") or default_clinic
        missing = [f for f in REQUIRED if not row.get(f)]
        if missing:
            errors.append(f"line {line}: missing {', '.join(missing)}")
            continue
        clinic = resolve_clinic(row["clinic"], clinics)
        if clinic is None:
            errors.append(f"line {line}: clinic '{row['clinic']}' not in clinics.json")
            continue
        posted_at = parse_date(row["posted_at"])
        if posted_at is None:
            errors.append(f"line {line}: can't read date '{row['posted_at']}' "
                          f"(use 2026-10-12, 10/12/2026 or Oct 12, 2026)")
            continue
        try:
            items.append(make_item(
                source=row["source"].lower(),
                clinic=clinic,
                text=row["text"],
                posted_at=posted_at,
                rating=row.get("rating") or None,
                url=row.get("url", ""),
                native_id=row.get("native_id") or None,
                title=row.get("title", ""),
                engagement=int(row["engagement"]) if row.get("engagement") else None,
                owner_replied=parse_bool(row.get("owner_replied")),
                collection_method="manual_entry",
            ))
        except ValueError as e:
            errors.append(f"line {line}: {e}")
    return items, errors


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("csv_file")
    parser.add_argument("--source", default="",
                        help="source for rows that leave it blank, e.g. yelp")
    parser.add_argument("--clinic", default="",
                        help="clinic for rows that leave it blank, e.g. RPSD")
    parser.add_argument("--db", default=DB_PATH)
    args = parser.parse_args()

    clinics = json.loads(CLINICS_FILE.read_text())
    with open(args.csv_file, newline="", encoding="utf-8-sig") as f:
        items, errors = parse_rows(csv.DictReader(f), clinics,
                                   args.source, args.clinic)
    for e in errors:
        print("NOT IMPORTED -", e)
    added, skipped = save_items(items, args.db)
    print(f"Added {added} new, skipped {skipped} already saved, {len(errors)} rows had problems.")


if __name__ == "__main__":
    main()
