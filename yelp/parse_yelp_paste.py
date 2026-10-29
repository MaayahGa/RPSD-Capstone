"""
Turn text copied from RPSD's Yelp business dashboard (Reviews page) into a
CSV that import_manual.py can load. Reviewer names, friend counts and the
clinic's reply text are dropped; only date, rating, review text and whether
the clinic replied are kept.

How to copy (biz.yelp.com -> Reviews):
  1. Filter to ONE star rating (e.g. 1 star). Yelp shows stars as images,
     so the rating can't be copied; the file name carries it instead.
  2. Cmd+A, Cmd+C, then paste into TextEdit as plain text (Cmd+Shift+T)
  3. Save in data/raw/yelp/ with the rating in the name: yelp_1star.txt,
     yelp_5star_page2.txt, ...  (data/ is gitignored)

Run:
    python yelp/parse_yelp_paste.py data/raw/yelp/yelp_*.txt
        -> writes data/raw/yelp/yelp_parsed.csv; open it and spot-check
    python import_manual.py data/raw/yelp/yelp_parsed.csv --source yelp --clinic RPSD
"""

# Let this script (in a source subfolder) import shared code from the repo root.
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import argparse
import csv
import re
from datetime import datetime

# Lines between the reviewer's name and the review date.
STAT_LINE = re.compile(
    r"^(\d[\d,]*\s+(friends?|reviews?|photos?|check-?ins?)|Elite\b.*)$", re.IGNORECASE)
REVIEW_DATE = re.compile(r"^\d{1,2}/\d{1,2}/\d{2,4}$")
REPLY_LINE = re.compile(r"publicly responded on", re.IGNORECASE)
UPDATED_LINE = re.compile(r"^Updated review$", re.IGNORECASE)
# Links/sections for an older version of the same review. The older text
# isn't on the page, so these only mark where the current review ends.
PREVIOUS_LINE = re.compile(r"^(See .+'s previous review|Previous review)$", re.IGNORECASE)
RATING_IN_NAME = re.compile(r"(\d)\s*[-_ ]?star", re.IGNORECASE)

# Dashboard text that can follow the last review when copying a whole page.
FOOTER = re.compile(
    r"^(Page \d+ of \d+|Next|Previous|Load more|Show more|Need Help\?|©|Copyright)",
    re.IGNORECASE)


def rating_from_filename(path):
    match = RATING_IN_NAME.search(Path(path).name)
    return int(match.group(1)) if match and 1 <= int(match.group(1)) <= 5 else None


def to_iso(date_text):
    for fmt in ("%m/%d/%y", "%m/%d/%Y"):
        try:
            return datetime.strptime(date_text, fmt).date().isoformat()
        except ValueError:
            pass
    return None


def find_review_starts(lines):
    """Indexes of date lines that come right after a name + stats block."""
    starts = []
    for i, line in enumerate(lines):
        if not REVIEW_DATE.match(line):
            continue
        j = i - 1
        while j >= 0 and STAT_LINE.match(lines[j]):
            j -= 1
        if j < i - 1 and j >= 0:          # at least one stats line, plus a name
            starts.append((j, i))         # (name line, date line)
    return starts


def parse_text(text):
    lines = [l.strip() for l in text.splitlines()]
    lines = [l for l in lines if l]
    starts = find_review_starts(lines)
    reviews = []
    for k, (name_idx, date_idx) in enumerate(starts):
        end = starts[k + 1][0] if k + 1 < len(starts) else len(lines)
        body = lines[date_idx + 1:end]
        updated = bool(body) and bool(UPDATED_LINE.match(body[0]))
        if updated:
            body = body[1:]
        replied = False
        for n, line in enumerate(body):
            if REPLY_LINE.search(line):
                body, replied = body[:n], True
                break
            if PREVIOUS_LINE.match(line):
                body = body[:n]
                break
        if k + 1 == len(starts):          # last review: cut page footer
            for n, line in enumerate(body):
                if FOOTER.match(line):
                    body = body[:n]
                    break
        reviews.append({
            "posted_at": to_iso(lines[date_idx]),
            "text": "\n\n".join(body),
            "owner_replied": "yes" if replied else "",
            "updated": updated,
        })
    return reviews


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("files", nargs="+", help="pasted .txt files")
    parser.add_argument("--out", default=str(ROOT / "data" / "raw" / "yelp" / "yelp_parsed.csv"))
    args = parser.parse_args()

    rows = []
    for f in args.files:
        rating = rating_from_filename(f)
        reviews = parse_text(Path(f).read_text(encoding="utf-8"))
        print(f"{f}: {len(reviews)} reviews"
              + ("" if rating else "  (no star rating in file name; rating left blank)"))
        for r in reviews:
            r["rating"] = rating or ""
            del r["updated"]
        rows += reviews
        empty = sum(1 for r in reviews if not r["text"])
        if empty:
            print(f"  warning: {empty} review(s) came out with no text; check the paste")

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["posted_at", "rating", "text", "owner_replied"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} reviews to {args.out}. Spot-check it, then run:\n"
          f"  python import_manual.py {args.out} --source yelp --clinic RPSD")


if __name__ == "__main__":
    main()
