"""Google Places API (New): find properties in a region and fetch their photos.

Only the official API is used, never scraped Maps pages. Photos are fetched
fresh for each video job and deleted afterwards (see video.py).
"""

from __future__ import annotations

import time
from pathlib import Path

import requests

BASE = "https://places.googleapis.com/v1"
SEARCH_FIELDS = ",".join([
    "places.id", "places.displayName", "places.formattedAddress", "places.rating",
    "places.userRatingCount", "places.websiteUri", "places.internationalPhoneNumber",
    "places.googleMapsUri", "places.photos", "places.businessStatus", "nextPageToken",
])


class Places:
    def __init__(self, api_key: str, session: requests.Session | None = None):
        self.key = api_key
        self.http = session or requests.Session()

    def search(self, query: str, max_results: int = 60) -> list[dict]:
        """Text search, following page tokens up to max_results."""
        found: list[dict] = []
        token = None
        while len(found) < max_results:
            body = {"textQuery": query, "pageSize": min(20, max_results - len(found))}
            if token:
                body["pageToken"] = token
            r = self.http.post(
                f"{BASE}/places:searchText",
                json=body,
                headers={"X-Goog-Api-Key": self.key, "X-Goog-FieldMask": SEARCH_FIELDS},
                timeout=30,
            )
            r.raise_for_status()
            data = r.json()
            found += data.get("places", [])
            token = data.get("nextPageToken")
            if not token:
                break
            time.sleep(1)  # page tokens need a moment before they are valid
        return found

    def photos(self, place_id: str) -> list[dict]:
        """Current photo references for one place (references expire, so never store them)."""
        r = self.http.get(
            f"{BASE}/places/{place_id}",
            headers={"X-Goog-Api-Key": self.key, "X-Goog-FieldMask": "displayName,photos"},
            timeout=30,
        )
        r.raise_for_status()
        return r.json().get("photos", [])

    def download_photo(self, photo_name: str, dest: Path, max_width: int = 4800) -> Path:
        r = self.http.get(
            f"{BASE}/{photo_name}/media",
            params={"maxWidthPx": max_width, "key": self.key},
            timeout=60,
        )
        r.raise_for_status()
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(r.content)
        return dest


def to_lead(place: dict, region: str) -> dict:
    """The fields we keep for a lead from one search result."""
    return {
        "place_id": place["id"],
        "name": (place.get("displayName") or {}).get("text", "").strip(),
        "region": region,
        "address": place.get("formattedAddress"),
        "rating": place.get("rating"),
        "review_count": place.get("userRatingCount"),
        "photo_count": len(place.get("photos") or []),
        "website": place.get("websiteUri"),
        "phone": place.get("internationalPhoneNumber"),
        "maps_url": place.get("googleMapsUri"),
    }


def is_open(place: dict) -> bool:
    return place.get("businessStatus", "OPERATIONAL") == "OPERATIONAL"


def _norm(s: str) -> str:
    return "".join(ch for ch in s.lower() if ch.isalnum())


def rank_photos(photos: list[dict], business_name: str) -> list[dict]:
    """Business-credited photos first, then the widest landscape photos.

    A photo counts as the business's own when its author's display name
    matches the place name; customer photos belong to their photographers.
    """
    name = _norm(business_name)

    def own(p: dict) -> bool:
        authors = [_norm(a.get("displayName", "")) for a in p.get("authorAttributions") or []]
        return any(a and (a in name or name in a) for a in authors)

    def key(p: dict):
        w, h = p.get("widthPx", 0), p.get("heightPx", 1) or 1
        return (not own(p), not w >= h, -w)

    return sorted(photos, key=key)


def authors(photos: list[dict]) -> str:
    names = {a.get("displayName", "") for p in photos for a in p.get("authorAttributions") or []}
    return ", ".join(sorted(n for n in names if n))
