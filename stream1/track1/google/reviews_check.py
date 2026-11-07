"""
Diagnostic: asks Google for just 3 fields for one business
and prints exactly what comes back, with nothing processed.
"""

import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("GOOGLE_PLACES_API_KEY")

URL = "https://places.googleapis.com/v1/places:searchText"
FIELD_MASK = "places.id,places.displayName,places.reviews"

headers = {
    "Content-Type": "application/json",
    "X-Goog-Api-Key": API_KEY,
    "X-Goog-FieldMask": FIELD_MASK,
}

print("Field mask being sent:", repr(FIELD_MASK))
resp = requests.post(URL, headers=headers, json={"textQuery": "Phil's BBQ San Diego"}, timeout=30)
print("Status code:", resp.status_code)

data = resp.json()
places = data.get("places", [])
if not places:
    print("No places returned. Full response:")
    print(json.dumps(data, indent=2)[:2000])
else:
    place = places[0]
    print("Fields returned:", list(place.keys()))
    print("Number of reviews:", len(place.get("reviews", [])))
    print()
    print("Raw response (first 2000 characters):")
    print(json.dumps(place, indent=2)[:2000])
