"""
Import RPSD's full Google review history from a Google Takeout export.

Google Takeout is Google's own "download your data" tool. For an account
that manages a Business Profile, it includes every review on the listing
(not just the 5 the Places API returns), and the clinic is allowed to keep
its own data.

How to get the export (logged into the capstone Google account):
  1. Go to https://takeout.google.com
  2. Click "Deselect all", then tick only "Google Business Profile"
  3. Next step -> "Export once", .zip -> Create export
  4. Download the .zip when Google emails the link (usually minutes)
  5. Move it into the data/raw/ folder of this repo (data/ is gitignored)

Then run:
    python import_google_takeout.py data/raw/takeout-XXXX.zip
    python reputation_item.py export

Reviewer names and profile photos in the export are dropped and never saved.
"""

import argparse
import json
import re
import zipfile
from pathlib import Path

from reputation_item import DB_PATH, make_item, save_items

STARS = {"ONE": 1, "TWO": 2, "THREE": 3, "FOUR": 4, "FIVE": 5}

CLINICS_FILE = Path(__file__).parent / "clinics.json"


def load_clinics():
    return json.loads(CLINICS_FILE.read_text())


def google_url(place_id):
    """Link to the clinic's Google listing (Takeout has no per-review URL)."""
    if not place_id:
        return ""
    return f"https://www.google.com/maps/place/?q=place_id:{place_id}"


def read_json_files(path):
    """Yield (relative_path, parsed_json) for every Business Profile JSON file
    inside a Takeout .zip or an already-unzipped folder."""
    path = Path(path)
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as zf:
            for name in zf.namelist():
                if "Business Profile" in name and name.endswith(".json"):
                    yield name, json.loads(zf.read(name).decode("utf-8"))
    else:
        for file in sorted(path.rglob("*.json")):
            rel = file.relative_to(path).as_posix()
            if "Business Profile" in rel or path.name.startswith("location-"):
                yield rel, json.loads(file.read_text(encoding="utf-8"))


def location_key(rel_path):
    match = re.search(r"location-[^/]+", rel_path)
    return match.group(0) if match else "location-unknown"


def listing_name(additional_data):
    for attr in additional_data.get("attributes", []):
        if attr.get("id", {}).get("attributeType") == "LISTING_NAME":
            try:
                return attr["values"][0]["datum"]["listingName"]["text"]
            except (KeyError, IndexError):
                return None
    return None


def match_clinic(name, clinics):
    """Map a Takeout listing name to the clinic entry in clinics.json."""
    if not name:
        return None
    lowered = name.lower()
    for clinic in clinics:
        names = [clinic["name"]] + clinic.get("aliases", [])
        if any(n.lower() in lowered or lowered in n.lower() for n in names):
            return clinic
    return None


def parse_takeout(path, clinics, default_clinic=None):
    """Return (items, notes). Each location's reviews become reputation_items."""
    reviews_by_location, names_by_location = {}, {}
    for rel, data in read_json_files(path):
        loc = location_key(rel)
        filename = rel.rsplit("/", 1)[-1]
        if filename.startswith("reviews") and isinstance(data, dict):
            reviews_by_location.setdefault(loc, []).extend(data.get("reviews", []))
        elif filename == "additionalData.json":
            names_by_location[loc] = listing_name(data)

    items, notes = [], []
    for loc, reviews in reviews_by_location.items():
        listing = names_by_location.get(loc)
        # Fall back to the client only when the export has no listing name;
        # a named listing that isn't in clinics.json is someone else's business.
        clinic = match_clinic(listing, clinics) if listing else default_clinic
        if clinic is None:
            notes.append(f"Skipped {len(reviews)} reviews from '{listing or loc}' "
                         f"(not in clinics.json)")
            continue
        for r in reviews:
            native_id = (r.get("reviewId")
                         or (r.get("name") or "").rsplit("/", 1)[-1] or None)
            items.append(make_item(
                source="google",
                clinic=clinic["name"],
                text=r.get("comment", ""),          # empty for star-only reviews
                posted_at=r.get("createTime", ""),
                rating=STARS.get(r.get("starRating")),
                url=google_url(clinic.get("google_place_id")),
                native_id=native_id,
                owner_replied="reviewReply" in r,
                collection_method="google_takeout",
            ))
        notes.append(f"{len(reviews)} reviews from '{listing or loc}' -> {clinic['name']}")
    return items, notes


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("takeout", help="Takeout .zip file or unzipped folder")
    parser.add_argument("--db", default=DB_PATH, help="SQLite database path")
    args = parser.parse_args()

    clinics = load_clinics()
    client = next(c for c in clinics if c["role"] == "client")
    items, notes = parse_takeout(args.takeout, clinics, default_clinic=client)
    for note in notes:
        print(note)
    if not items:
        print("No reviews found. Check that 'Google Business Profile' was selected "
              "in Takeout and that this account manages the listing.")
        return
    added, skipped = save_items(items, args.db)
    no_text = sum(1 for i in items if not i["text"])
    print(f"Added {added} new, skipped {skipped} already saved "
          f"({no_text} are star-only with no text).")


if __name__ == "__main__":
    main()
