"""
Import hand-logged reviews/posts from a CSV (Yelp, Reddit, FertilityIQ, ...).

Use this for sources without an export or approved API yet: copy each
review from the clinic's own business dashboard (e.g. biz.yelp.com ->
Reviews) or log a Reddit thread you found, one row per review/post/comment.

Start from templates/manual_reviews_template.csv (save your copy in
data/raw/, which is gitignored). Columns:

  source         yelp, reddit, fertilityiq, ...       (required)
  clinic         full name or alias from clinics.json  (required)
  posted_at      YYYY-MM-DD                            (required)
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
    python reputation_item.py export
"""

import argparse
import csv
import json
import re
from pathlib import Path

from reputation_item import DB_PATH, make_item, save_items

CLINICS_FILE = Path(__file__).parent / "clinics.json"
REQUIRED = ["source", "clinic", "posted_at", "text"]
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}")


def resolve_clinic(value, clinics):
    value = value.strip().lower()
    for clinic in clinics:
        names = [clinic["name"]] + clinic.get("aliases", [])
        if any(value == n.lower() for n in names):
            return clinic["name"]
    return None


def parse_bool(value):
    value = (value or "").strip().lower()
    if value in ("yes", "y", "true", "1"):
        return True
    if value in ("no", "n", "false", "0"):
        return False
    return None


def parse_rows(rows, clinics):
    """Return (items, errors). Rows with problems are reported, not imported."""
    items, errors = [], []
    for line, row in enumerate(rows, start=2):  # line 1 is the header
        row = {k.strip(): (v or "").strip() for k, v in row.items() if k}
        if not any(row.values()):
            continue
        missing = [f for f in REQUIRED if not row.get(f)]
        if missing:
            errors.append(f"line {line}: missing {', '.join(missing)}")
            continue
        clinic = resolve_clinic(row["clinic"], clinics)
        if clinic is None:
            errors.append(f"line {line}: clinic '{row['clinic']}' not in clinics.json")
            continue
        if not DATE_RE.match(row["posted_at"]):
            errors.append(f"line {line}: posted_at must be YYYY-MM-DD")
            continue
        try:
            items.append(make_item(
                source=row["source"].lower(),
                clinic=clinic,
                text=row["text"],
                posted_at=row["posted_at"],
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
    parser.add_argument("--db", default=DB_PATH)
    args = parser.parse_args()

    clinics = json.loads(CLINICS_FILE.read_text())
    with open(args.csv_file, newline="", encoding="utf-8-sig") as f:
        items, errors = parse_rows(csv.DictReader(f), clinics)
    for e in errors:
        print("NOT IMPORTED -", e)
    added, skipped = save_items(items, args.db)
    print(f"Added {added} new, skipped {skipped} already saved, {len(errors)} rows had problems.")


if __name__ == "__main__":
    main()
