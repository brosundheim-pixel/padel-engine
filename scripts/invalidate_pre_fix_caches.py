"""Delete Google Places cache files generated under the pre-fix locationBias
Text Search queries. Run once after switching to locationRestriction.

For each pre-fix anchor + each Text Search query the runner issued, the
buggy query body is reconstructed, hashed identically to disk_cache._key(),
and the matching cache file is deleted. Page-2 files (with pageToken) are
also caught by reading the page-1 response BEFORE deletion to extract the
token.

Search Nearby caches are NOT touched — Search Nearby always used
locationRestriction.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.data.google_places import BOUTIQUE_FITNESS_BRANDS, PADEL_TEXT_QUERIES

ZCTA_CACHE = REPO_ROOT / "data" / "raw" / "zcta_centroids.json"
PLACES_CACHE = REPO_ROOT / "data" / "raw" / "google_places"
RADIUS_M = 15000

PRE_FIX_ANCHORS = [
    ("ntrc_frisco_75034", "75034"),
    ("ntrc_frisco_75035", "75035"),
    ("sensa_germantown", "37208"),
    ("roanoke_al", "36272"),
]

TEXT_QUERIES = (
    ["tennis club"]
    + BOUTIQUE_FITNESS_BRANDS
    + ["country club"]
    + PADEL_TEXT_QUERIES
)


def cache_key(endpoint: str, query: dict) -> str:
    payload = json.dumps(
        {"endpoint": endpoint, "query": query},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def buggy_text_query(text_query: str, lat: float, lng: float, page_token: Optional[str] = None) -> dict:
    q = {
        "textQuery": text_query,
        "locationBias": {
            "circle": {
                "center": {"latitude": lat, "longitude": lng},
                "radius": float(RADIUS_M),
            }
        },
        "maxResultCount": 20,
    }
    if page_token is not None:
        q["pageToken"] = page_token
    return q


def main() -> int:
    centroids = json.loads(ZCTA_CACHE.read_text())

    deleted: List[str] = []
    skipped: List[str] = []

    for location_id, zip_code in PRE_FIX_ANCHORS:
        entry = centroids.get(zip_code) or {}
        pop = entry.get("pop_centroid")
        if not pop:
            print(f"SKIP {location_id} ({zip_code}): no pop centroid")
            continue
        lat, lng = float(pop[0]), float(pop[1])

        for tq in TEXT_QUERIES:
            page1_query = buggy_text_query(tq, lat, lng)
            page1_key = cache_key("google.places.text_search", page1_query)
            page1_path = PLACES_CACHE / f"{page1_key}.json"

            page2_token: Optional[str] = None
            if page1_path.exists():
                # Read the page-1 file to extract nextPageToken for page-2 cache
                try:
                    page1_data = json.loads(page1_path.read_text())
                    page2_token = page1_data.get("nextPageToken")
                except Exception:
                    page2_token = None
                page1_path.unlink()
                deleted.append(f"{location_id} | {tq!r:<25} | page1 | {page1_key}")
            else:
                skipped.append(f"{location_id} | {tq!r:<25} | page1 (not found)")

            if page2_token:
                page2_query = buggy_text_query(tq, lat, lng, page_token=page2_token)
                page2_key = cache_key("google.places.text_search", page2_query)
                page2_path = PLACES_CACHE / f"{page2_key}.json"
                if page2_path.exists():
                    page2_path.unlink()
                    deleted.append(f"{location_id} | {tq!r:<25} | page2 | {page2_key}")

    print(f"Deleted {len(deleted)} pre-fix Text Search cache files:")
    for d in deleted:
        print(f"  {d}")
    if skipped:
        print(f"\n{len(skipped)} not found (already absent):")
        for s in skipped[:5]:
            print(f"  {s}")
        if len(skipped) > 5:
            print(f"  ...and {len(skipped) - 5} more")
    print(f"\nRemaining cache files in {PLACES_CACHE}:")
    remaining = sorted(PLACES_CACHE.glob("*.json"))
    print(f"  {len(remaining)} files (Search Nearby caches preserved)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
