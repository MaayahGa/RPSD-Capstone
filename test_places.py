"""
Offline tests for places_test.py. No API key or internet needed:
uses the made-up data in sample_place.json.

Run with:
  python test_places.py
"""

import json
import os

from places_test import load_clinics, summarize_place

HERE = os.path.dirname(os.path.abspath(__file__))


def load_sample():
    with open(os.path.join(HERE, "sample_place.json")) as f:
        return json.load(f)


def test_basic_fields():
    s = summarize_place(load_sample())
    assert s["place_id"] == "TEST_PLACE_ID_123"
    assert s["name"] == "Example Fertility Clinic"
    assert s["rating"] == 4.2
    assert s["rating_count"] == 87


def test_reviews_parsed():
    s = summarize_place(load_sample())
    assert len(s["reviews"]) == 3
    assert s["reviews"][0]["text"] == "Friendly front desk and clear communication."
    assert s["reviews"][1]["rating"] == 2


def test_rating_only_review_has_empty_text():
    s = summarize_place(load_sample())
    assert s["reviews"][2]["text"] == ""


def test_no_reviewer_names():
    s = summarize_place(load_sample())
    assert "Test Reviewer" not in json.dumps(s)


def test_place_with_no_reviews():
    s = summarize_place({"id": "X", "displayName": {"text": "Empty"}})
    assert s["reviews"] == []
    assert s["rating_count"] == 0


def test_clinics_file():
    clinics = load_clinics()
    assert len(clinics) == 4
    for c in clinics:
        assert c["google_place_id"].startswith("ChIJ")
        assert c["role"] in ("client", "competitor")


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except AssertionError:
            failed += 1
            print(f"FAIL  {t.__name__}")
    print(f"\n{len(tests) - failed}/{len(tests)} tests passed")
