"""
Track 1 test of the Google Places API (New).

Reads the clinics and their Google place IDs from clinics.json, looks each
one up directly by place ID (Place Details), and prints rating, review count,
and the (max 5) reviews Google returns.

Note: Places API terms don't allow storing review content, so this
script only prints to the screen. Place IDs are the one thing we may save.
Reviewer names are not printed.

Setup:
  1. Put GOOGLE_PLACES_API_KEY=your_key in a .env file next to this script
  2. python -m pip install -r requirements.txt
  3. python google/places_test.py   (run from the repo root)
"""

import json
import os

import requests
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
API_KEY = os.getenv("GOOGLE_PLACES_API_KEY")

HERE = os.path.dirname(os.path.abspath(__file__))
CLINICS_FILE = os.path.join(os.path.dirname(HERE), "clinics.json")  # repo root

DETAILS_URL = "https://places.googleapis.com/v1/places/{place_id}"

# Place Details field names have no "places." prefix (that's only for search).
FIELDS = "id,displayName,formattedAddress,rating,userRatingCount,reviews"


def load_clinics(path=CLINICS_FILE):
    with open(path) as f:
        return json.load(f)


def get_place(place_id):
    headers = {
        "X-Goog-Api-Key": API_KEY,
        "X-Goog-FieldMask": FIELDS,
    }
    resp = requests.get(DETAILS_URL.format(place_id=place_id), headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()


def summarize_place(place):
    """Turn Google's raw response into a simple dict. No reviewer names."""
    reviews = []
    for review in place.get("reviews", []):
        reviews.append({
            "rating": review.get("rating"),
            "when": review.get("relativePublishTimeDescription", ""),
            "publish_time": review.get("publishTime"),
            # Review text is nested: review["text"]["text"]
            "text": review.get("text", {}).get("text", ""),
        })
    return {
        "place_id": place.get("id"),
        "name": place.get("displayName", {}).get("text"),
        "address": place.get("formattedAddress"),
        "rating": place.get("rating"),
        "rating_count": place.get("userRatingCount", 0),
        "reviews": reviews,
    }


def print_summary(s):
    print(f"  Name:     {s['name']}")
    print(f"  Place ID: {s['place_id']}")
    print(f"  Address:  {s['address']}")
    print(f"  Rating:   {s['rating']} ({s['rating_count']} total reviews)")
    print(f"  Reviews returned by API: {len(s['reviews'])}")
    for i, r in enumerate(s["reviews"], start=1):
        text = r["text"] or "(no text, rating only)"
        print(f"\n  [{i}] {r['rating']} stars, {r['when']}")
        print(f"      {text[:400]}{'...' if len(text) > 400 else ''}")
    print()


def main():
    if not API_KEY:
        raise SystemExit("Missing GOOGLE_PLACES_API_KEY in your .env file.")

    for clinic in load_clinics():
        print("=" * 70)
        print(f"Looking up: {clinic['name']} ({clinic['role']})")
        try:
            place = get_place(clinic["google_place_id"])
        except requests.HTTPError as e:
            print(f"  Request failed: {e.response.status_code} {e.response.text[:300]}")
            continue
        print_summary(summarize_place(place))


if __name__ == "__main__":
    main()