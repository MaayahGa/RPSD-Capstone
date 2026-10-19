"""
Test for the Google Places API (New) for Track 1.

Looks up RPSD and the three high-priority competitors and prints
their rating, review count, and the (max 5) reviews Google returns.

Note: Places API terms don't allow storing review content, so this
script only prints to the screen. Reviewer names are not requested.

Setup:
  1. Put GOOGLE_PLACES_API_KEY=your_key in a .env file next to this script
  2. pip install -r requirements.txt
  3. python places_test.py
"""

import os
import requests
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("GOOGLE_PLACES_API_KEY")

CLINICS = [
    "Reproductive Partners Fertility Center San Diego",
    "RMA San Diego fertility",
    "San Diego Fertility Center",
    "Shady Grove Fertility Solana Beach",
]

URL = "https://places.googleapis.com/v1/places:searchText"

# Only ask for the fields we need (this also controls cost).
# authorAttribution is deliberately left out so no reviewer names come back.
FIELDS = ",".join([
    "places.id",
    "places.displayName",
    "places.formattedAddress",
    "places.rating",
    "places.userRatingCount",
    "places.reviews.rating",
    "places.reviews.publishTime",
    "places.reviews.text",
])


def search_clinic(query):
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": API_KEY,
        "X-Goog-FieldMask": FIELDS,
    }
    resp = requests.post(URL, headers=headers, json={"textQuery": query}, timeout=30)
    resp.raise_for_status()
    places = resp.json().get("places", [])
    return places[0] if places else None


def main():
    if not API_KEY:
        raise SystemExit("Missing GOOGLE_PLACES_API_KEY in your .env file.")

    for query in CLINICS:
        print("=" * 70)
        print(f"Search: {query}")
        try:
            place = search_clinic(query)
        except requests.HTTPError as e:
            print(f"  Request failed: {e.response.status_code} {e.response.text[:300]}")
            continue

        if not place:
            print("  No match found.")
            continue

        print(f"  Name:    {place.get('displayName', {}).get('text')}")
        print(f"  Address: {place.get('formattedAddress')}")
        print(f"  Rating:  {place.get('rating')} ({place.get('userRatingCount')} total reviews)")

        reviews = place.get("reviews", [])
        print(f"  Reviews returned by API: {len(reviews)}")
        for i, r in enumerate(reviews, 1):
            text = (r.get("text") or {}).get("text", "").replace("\n", " ")
            print(f"   [{i}] {r.get('rating')}* | {r.get('publishTime', '')[:10]} | {text[:150]}")


if __name__ == "__main__":
    main()
