"""
Shared reputation_item format for Track 1.

Every source (Google, Yelp, Reddit, ...) is converted into the same record
shape here, saved into one SQLite database, and exported as CSV/JSON for
Track 2 (sentiment) and Track 4 (dashboard).

Privacy: reviewer names, usernames and profile links are NEVER stored.

Usage from the command line:
    python reputation_item.py summary          # counts per source/clinic
    python reputation_item.py export           # writes data/exports/*.csv and *.json
"""

import csv
import hashlib
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
DB_PATH = DATA_DIR / "reputation.db"
EXPORT_DIR = DATA_DIR / "exports"

# Reviews posted on/after this date fall under the new insurance coverage
# the clinic described (wait times and processes changed).
INSURANCE_CHANGE_DATE = "2026-01-01"

# Column order used in the database and every export.
FIELDS = [
    "id",             # unique: "<source>_<native id>" or a content hash
    "source",         # google, yelp, reddit, ...
    "clinic",         # clinic name as written in clinics.json
    "posted_at",      # when the person posted it (YYYY-MM-DD or ISO time)
    "collected_at",   # when Track 1 collected it (ISO time, UTC)
    "rating",         # 1-5, or empty if the source has no ratings (Reddit)
    "title",          # Reddit post title; empty for reviews
    "text",           # exactly what the person wrote
    "url",            # link to the original (or the clinic's page)
    "engagement",     # Reddit score (upvotes minus downvotes); empty otherwise
    "owner_replied",  # 1 if the clinic replied publicly, 0 if not, empty if unknown
    "collection_method",  # e.g. google_takeout, manual_entry, reddit_api
]


def now_utc():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def make_id(source, native_id=None, clinic="", posted_at="", text=""):
    """Stable ID so re-importing the same item is skipped.

    Uses the platform's own ID when there is one; otherwise hashes the
    content (for hand-entered items that have no platform ID).
    """
    if native_id:
        return f"{source}_{native_id}"
    digest = hashlib.sha1(
        f"{source}|{clinic}|{posted_at}|{text.strip()[:500]}".encode("utf-8")
    ).hexdigest()[:16]
    return f"{source}_h{digest}"


def make_item(source, clinic, text, posted_at="", rating=None, url="",
              native_id=None, title="", engagement=None, owner_replied=None,
              collection_method="", collected_at=None):
    """Build one reputation_item dict. Only these fields are ever kept."""
    if rating not in (None, ""):
        rating = int(round(float(rating)))
        if not 1 <= rating <= 5:
            raise ValueError(f"rating must be 1-5, got {rating}")
    else:
        rating = None
    text = (text or "").strip()
    return {
        "id": make_id(source, native_id, clinic, posted_at, text),
        "source": source,
        "clinic": clinic,
        "posted_at": posted_at or "",
        "collected_at": collected_at or now_utc(),
        "rating": rating,
        "title": (title or "").strip(),
        "text": text,
        "url": url or "",
        "engagement": engagement,
        "owner_replied": None if owner_replied is None else int(bool(owner_replied)),
        "collection_method": collection_method,
    }


# ---------------------------------------------------------------- database

def connect(db_path=DB_PATH):
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reputation_item (
            id TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            clinic TEXT NOT NULL,
            posted_at TEXT,
            collected_at TEXT NOT NULL,
            rating INTEGER,
            title TEXT,
            text TEXT,
            url TEXT,
            engagement INTEGER,
            owner_replied INTEGER,
            collection_method TEXT
        )
    """)
    return conn


def save_items(items, db_path=DB_PATH):
    """Insert items, skipping IDs already in the database.

    Returns (added, skipped).
    """
    conn = connect(db_path)
    added = 0
    with conn:
        for item in items:
            cur = conn.execute(
                f"INSERT OR IGNORE INTO reputation_item ({', '.join(FIELDS)}) "
                f"VALUES ({', '.join('?' for _ in FIELDS)})",
                [item[f] for f in FIELDS],
            )
            added += cur.rowcount
    conn.close()
    return added, len(items) - added


def load_items(db_path=DB_PATH):
    conn = connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM reputation_item ORDER BY source, clinic, posted_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------- export

def insurance_period(posted_at):
    if not posted_at:
        return ""
    return "2026_onward" if posted_at[:10] >= INSURANCE_CHANGE_DATE else "before_2026"


def export(db_path=DB_PATH, out_dir=EXPORT_DIR):
    """Write one combined file plus one file per source, as CSV and JSON."""
    items = load_items(db_path)
    for item in items:
        item["insurance_period"] = insurance_period(item["posted_at"])
    columns = FIELDS + ["insurance_period"]

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    groups = {"all_sources": items}
    for item in items:
        groups.setdefault(item["source"], []).append(item)

    written = []
    for name, rows in groups.items():
        csv_path = out_dir / f"reputation_items_{name}.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows)
        json_path = out_dir / f"reputation_items_{name}.json"
        json_path.write_text(json.dumps(rows, indent=2, ensure_ascii=False),
                             encoding="utf-8")
        written += [csv_path, json_path]
    return written


def summary(db_path=DB_PATH):
    conn = connect(db_path)
    rows = conn.execute("""
        SELECT source, clinic, COUNT(*), ROUND(AVG(rating), 2),
               MIN(posted_at), MAX(posted_at)
        FROM reputation_item GROUP BY source, clinic ORDER BY source, clinic
    """).fetchall()
    conn.close()
    if not rows:
        print("Database is empty.")
        return
    print(f"{'source':<8} {'items':>5} {'avg':>5}  {'oldest':<10}  {'newest':<10}  clinic")
    for source, clinic, n, avg, oldest, newest in rows:
        print(f"{source:<8} {n:>5} {avg if avg is not None else '-':>5}  "
              f"{(oldest or '')[:10]:<10}  {(newest or '')[:10]:<10}  {clinic}")


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "summary"
    if command == "export":
        for path in export():
            print(f"wrote {path}")
    elif command == "summary":
        summary()
    else:
        print(__doc__)
