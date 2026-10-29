"""
Offline tests for the reputation_item store and importers.
All data here is made up. No internet, API keys or real reviews needed.

Run:  python test_importers.py
"""

import csv
import io
import json
import tempfile
import zipfile
from pathlib import Path
from types import SimpleNamespace

import sys
for _sub in ("google", "reddit", "yelp"):
    sys.path.insert(0, str(Path(__file__).parent / _sub))

import import_google_takeout as gt
import import_manual as manual
import parse_yelp_paste as yp
import reddit_collector as rc
import reputation_item as ri

CLINICS = json.loads((Path(__file__).parent / "clinics.json").read_text())
RPSD = CLINICS[0]["name"]

FAKE_REVIEWS = {"reviews": [
    {"reviewer": {"displayName": "Fake Person A"}, "starRating": "FIVE",
     "comment": "Made-up review: staff were kind.", "createTime": "2026-03-02T10:00:00Z",
     "name": "accounts/1/locations/2/reviews/AAA", "reviewReply": {"comment": "Thanks"}},
    {"reviewer": {"displayName": "Fake Person B"}, "starRating": "TWO",
     "comment": "Made-up review: waited a week for a call back.",
     "createTime": "2025-06-10T10:00:00Z", "name": "accounts/1/locations/2/reviews/BBB"},
    {"reviewer": {"displayName": "Fake Person C"}, "starRating": "FOUR",
     "createTime": "2025-01-01T10:00:00Z", "name": "accounts/1/locations/2/reviews/CCC"},
]}
FAKE_LISTING = {"attributes": [{"id": {"attributeType": "LISTING_NAME"},
                "values": [{"datum": {"listingName": {"text":
                 "Reproductive Partners Fertility Center - San Diego (RPSD)"}}}]}]}


def fake_takeout(tmp, listing=FAKE_LISTING):
    path = Path(tmp) / "takeout.zip"
    base = "Takeout/Google Business Profile/account-1/location-2/"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(base + "reviews.json", json.dumps(FAKE_REVIEWS))
        zf.writestr(base + "additionalData.json", json.dumps(listing))
    return path


def test_takeout_parses_all_fields():
    with tempfile.TemporaryDirectory() as tmp:
        items, _ = gt.parse_takeout(fake_takeout(tmp), CLINICS)
    assert len(items) == 3
    first = items[0]
    assert first["id"] == "google_AAA"
    assert first["clinic"] == RPSD and first["rating"] == 5
    assert first["owner_replied"] == 1 and items[1]["owner_replied"] == 0
    assert items[2]["text"] == ""          # star-only review kept
    assert "place_id:" in first["url"]


def test_no_reviewer_names_anywhere():
    with tempfile.TemporaryDirectory() as tmp:
        items, _ = gt.parse_takeout(fake_takeout(tmp), CLINICS)
    assert "Fake Person" not in json.dumps(items)


def test_unknown_listing_is_skipped_not_assigned_to_rpsd():
    other = json.loads(json.dumps(FAKE_LISTING).replace(
        "Reproductive Partners Fertility Center - San Diego (RPSD)", "Some Dental Office"))
    with tempfile.TemporaryDirectory() as tmp:
        items, notes = gt.parse_takeout(fake_takeout(tmp, other), CLINICS,
                                        default_clinic=CLINICS[0])
    assert items == [] and "Skipped" in notes[0]


def test_rerun_skips_duplicates_and_export_works():
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "test.db"
        items, _ = gt.parse_takeout(fake_takeout(tmp), CLINICS)
        assert ri.save_items(items, db) == (3, 0)
        assert ri.save_items(items, db) == (0, 3)
        files = ri.export(db, Path(tmp) / "exports")
        with open(Path(tmp) / "exports" / "reputation_items_all_sources.csv") as f:
            rows = list(csv.DictReader(f))
    assert len(rows) == 3 and len(files) == 4   # all_sources + google, csv + json
    periods = {r["id"]: r["insurance_period"] for r in rows}
    assert periods["google_AAA"] == "2026_onward"
    assert periods["google_BBB"] == "before_2026"


MANUAL_CSV = """source,clinic,posted_at,rating,title,text,url,native_id,engagement,owner_replied
yelp,RPSD,2026-02-14,1,,Made-up Yelp review about billing.,,,3,yes
reddit,SDFC,2025-11-01,,Made-up title,Made-up post text.,https://reddit.com/x,abc,12,
yelp,Unknown Clinic,2026-01-01,5,,text,,,,
yelp,RPSD,Feb 2026,5,,text,,,,
yelp,RPSD,Oct 12 2026x,5,,text,,,,
yelp,RPSD,2026-01-01,9,,text,,,,
"""


def test_manual_import_validates_rows():
    items, errors = manual.parse_rows(csv.DictReader(io.StringIO(MANUAL_CSV)), CLINICS)
    assert len(items) == 2 and len(errors) == 4
    yelp, reddit = items
    assert yelp["clinic"] == RPSD and yelp["rating"] == 1 and yelp["owner_replied"] == 1
    assert yelp["id"].startswith("yelp_h")          # hashed: no native ID given
    assert reddit["id"] == "reddit_abc" and reddit["rating"] is None
    assert reddit["clinic"] == "San Diego Fertility Center"


def test_manual_dates_in_spreadsheet_formats():
    rows = "source,clinic,posted_at,text\n" + "".join(
        f"yelp,RPSD,{d},Made-up {i}\n"
        for i, d in enumerate(["2026-10-12", "10/12/2026", '"Oct 12, 2026"', "10/12/26"]))
    items, errors = manual.parse_rows(csv.DictReader(io.StringIO(rows)), CLINICS)
    assert errors == [] and {i["posted_at"] for i in items} == {"2026-10-12"}


def test_manual_short_sheet_with_defaults():
    rows = "posted_at,rating,text,owner_replied\n10/12/2026,2,Made-up short-sheet review,yes\n"
    items, errors = manual.parse_rows(csv.DictReader(io.StringIO(rows)), CLINICS,
                                      default_source="yelp", default_clinic="RPSD")
    assert errors == [] and items[0]["source"] == "yelp" and items[0]["clinic"] == RPSD
    assert items[0]["rating"] == 2 and items[0]["owner_replied"] == 1


FAKE_YELP_PASTE = """Reviews
175 reviews
Filter
Fake Name A.
0 friends
1 review
10/19/26
Made-up first paragraph.

Made-up second paragraph.
Fake Staff publicly responded on Oct 26, 11:58 AM
Made-up reply that must not be kept.
Fake Name B.
217 friends
3 reviews
Elite 26
1/5/2025
Made-up short review.
Page 1 of 9
Next
"""


def test_yelp_paste_parser():
    reviews = yp.parse_text(FAKE_YELP_PASTE)
    assert [r["posted_at"] for r in reviews] == ["2026-10-19", "2025-01-05"]
    assert reviews[0]["text"] == "Made-up first paragraph.\n\nMade-up second paragraph."
    assert reviews[0]["owner_replied"] == "yes" and reviews[1]["owner_replied"] == ""
    assert reviews[1]["text"] == "Made-up short review."      # footer cut off
    dump = json.dumps(reviews)
    assert "Fake Name" not in dump and "reply that must not" not in dump
    assert yp.rating_from_filename("data/raw/yelp_2star_page3.txt") == 2
    assert yp.rating_from_filename("yelp_page1.txt") is None


def test_reddit_comment_matching():
    patterns = rc.alias_patterns(CLINICS)
    comment = SimpleNamespace(
        id="c1", body="Made-up: I went to Reproductive Partners, friend used SDFC.",
        created_utc=1767225600, permalink="/r/IVF/comments/x/c1", score=4,
        author="should_never_be_saved")
    items = rc.comment_items(comment, patterns)
    assert {i["clinic"] for i in items} == {RPSD, "San Diego Fertility Center"}
    assert len({i["id"] for i in items}) == 2
    assert "should_never_be_saved" not in json.dumps(items)
    # "rpsd" inside another word must not match
    assert rc.clinics_mentioned("xrpsdx", patterns) == []


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    passed = 0
    for t in tests:
        try:
            t()
            passed += 1
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            print(f"FAIL {t.__name__} {e}")
    print(f"{passed}/{len(tests)} tests passed")
