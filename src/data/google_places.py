"""Google Places API (New) wrapper. Demand-signal supply for the engine.

ARCHITECTURAL RULE: every paid call goes through `cached_api_call`. This
module never invokes `requests.get/post` against `places.googleapis.com`
outside of fetcher closures handed to `cached_api_call`. Caching, budget
enforcement, and cost logging are guaranteed by that single chokepoint.

Endpoints used:
  - Search Nearby:  POST https://places.googleapis.com/v1/places:searchNearby
  - Search Text:    POST https://places.googleapis.com/v1/places:searchText

Field mask is set tight (id, displayName, location, types, rating,
userRatingCount, nextPageToken) so we stay in the cheapest billing tier
($0.032/call as of the Google Places SKU pricing). Requesting Atmosphere
or Contact fields would bump us to higher tiers — don't.

Pagination: Google returns up to 20 places per call. We optionally fetch one
additional page (cap at 2 pages = 40 results) when `nextPageToken` is
present. EACH PAGE IS A SEPARATE BILLED CALL — accounted for explicitly.

Type taxonomy caveat: includedTypes for tennis (`tennis_club`, `tennis_court`,
`racquet_sport_club`) and golf (`golf_course`, `country_club`) are per the
spec the operator gave. Google's Place Types Table A is the source of truth;
if any of these are not valid the API will 400 and we'll need to fix. Padel
and "boutique fitness" have no clean type, so we use Text Search there.

Returned place dict shape (consistent across all four fetchers):
    {
        "place_id": str,
        "name": str,
        "lat": float,
        "lng": float,
        "types": list[str],
        "rating": float | None,
        "user_ratings_total": int | None,
    }
"""

from __future__ import annotations

import math
import os
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import requests
from dotenv import load_dotenv

from src.data.google_api_call import cached_api_call

REPO_ROOT = Path(__file__).resolve().parents[2]

# Google Places API (New) endpoints
NEARBY_URL = "https://places.googleapis.com/v1/places:searchNearby"
TEXT_URL = "https://places.googleapis.com/v1/places:searchText"

# Endpoint identifiers used for cache keys + cost log records.
GOOGLE_PLACES_NEARBY = "google.places.nearby_search"
GOOGLE_PLACES_TEXT = "google.places.text_search"

# Per-call cost (Google Places SKU pricing; basic field tier).
COST_PER_CALL_USD = 0.032

# Tight field mask = Pro billing tier. Per-place fields are identical for both
# endpoints; only Text Search exposes nextPageToken (Search Nearby doesn't
# paginate). Including nextPageToken in a Search Nearby mask returns 400
# "Cannot find matching fields for path 'nextPageToken'", so we split.
_PLACES_FIELDS = (
    "places.id,places.displayName,places.location,places.types,"
    "places.rating,places.userRatingCount,places.priceLevel,"
    "places.businessStatus,places.formattedAddress,places.primaryType"
)
FIELD_MASK_NEARBY = _PLACES_FIELDS
FIELD_MASK_TEXT = _PLACES_FIELDS + ",nextPageToken"

# Pagination cap. 1 = no pagination (single call). 2 = fetch one extra page.
MAX_PAGES = 2

# Per the Google Places API docs, nextPageToken takes a brief moment to
# become valid. Sleep before the second-page request.
NEXT_PAGE_TOKEN_WARMUP_S = 2.0

# Boutique fitness has no clean Google Place type. Search by brand name
# instead. Each chain is a separate Text Search (independently cached and
# budgeted). Order matches expected market presence; tweak as needed.
# 14 brands × $0.032 = $0.448 worst case per location, well under free tier.
BOUTIQUE_FITNESS_BRANDS = [
    "SoulCycle",
    "Orangetheory",
    "Pure Barre",
    "F45",
    "Barry's Bootcamp",
    "[solidcore]",
    "Equinox",
    "Club Pilates",
    "Lagree Fitness",
    "CorePower Yoga",
    "Y7",
    "Rumble Boxing",
    "CycleBar",
    "Pvolve",
]

# Padel-specific text queries (no native Google type for padel).
# Three queries for breadth — supply-side detection is load-bearing, false
# positives are cheaper than missing a real competitor.
PADEL_TEXT_QUERIES = ["padel club", "padel court", "padel"]

# Two distinct places within this many meters are treated as a single
# physical facility (e.g., "NTRC" + "Racquets & Strings at NTRC" co-located).
DEDUPE_PROXIMITY_METERS = 50.0

# Map Google's priceLevel enum strings to int (0-4). PRICE_LEVEL_UNSPECIFIED
# and missing values become None.
_PRICE_LEVEL_MAP = {
    "PRICE_LEVEL_FREE": 0,
    "PRICE_LEVEL_INEXPENSIVE": 1,
    "PRICE_LEVEL_MODERATE": 2,
    "PRICE_LEVEL_EXPENSIVE": 3,
    "PRICE_LEVEL_VERY_EXPENSIVE": 4,
}


def _get_api_key() -> str:
    """Read GOOGLE_MAPS_API_KEY from .env. Raise with instructions if missing."""
    load_dotenv(REPO_ROOT / ".env")
    key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not key:
        raise RuntimeError(
            "GOOGLE_MAPS_API_KEY not found in environment. "
            f"Add it to {REPO_ROOT / '.env'} as a line:\n"
            "    GOOGLE_MAPS_API_KEY=your_key_here\n"
            "Get a key at https://console.cloud.google.com/google/maps-apis/ — "
            "enable the Places API (New) on the project before use."
        )
    return key


def _normalize_place(place: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Convert a raw Places API place dict to our canonical shape."""
    place_id = place.get("id")
    location = place.get("location") or {}
    if not place_id or "latitude" not in location or "longitude" not in location:
        return None
    name = (place.get("displayName") or {}).get("text") or place_id
    raw_price = place.get("priceLevel")
    return {
        "place_id": place_id,
        "name": name,
        "lat": float(location["latitude"]),
        "lng": float(location["longitude"]),
        "types": list(place.get("types") or []),
        "rating": place.get("rating"),
        "user_ratings_total": place.get("userRatingCount"),
        "price_level": _PRICE_LEVEL_MAP.get(raw_price) if raw_price else None,
        "business_status": place.get("businessStatus"),
        "formatted_address": place.get("formattedAddress"),
        "primary_type": place.get("primaryType"),
    }


def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in meters."""
    r = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmbd = math.radians(lng2 - lng1)
    h = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlmbd / 2) ** 2
    )
    return 2 * r * math.asin(math.sqrt(h))


def _nearby_search(
    lat: float,
    lng: float,
    radius_m: int,
    included_types: List[str],
) -> List[Dict[str, Any]]:
    """Search Nearby — single call, no pagination (the API doesn't support it)."""
    api_key = _get_api_key()
    base_query = {
        "includedTypes": included_types,
        "maxResultCount": 20,
        "locationRestriction": {
            "circle": {
                "center": {"latitude": lat, "longitude": lng},
                "radius": float(radius_m),
            }
        },
    }
    return _paginate(
        GOOGLE_PLACES_NEARBY, NEARBY_URL, api_key, base_query, FIELD_MASK_NEARBY
    )


def _text_search(text_query: str, lat: float, lng: float, radius_m: int) -> List[Dict[str, Any]]:
    """Search Text — paginated up to MAX_PAGES, each page a separate billed call."""
    api_key = _get_api_key()
    base_query = {
        "textQuery": text_query,
        "locationBias": {
            "circle": {
                "center": {"latitude": lat, "longitude": lng},
                "radius": float(radius_m),
            }
        },
        "maxResultCount": 20,
    }
    return _paginate(
        GOOGLE_PLACES_TEXT, TEXT_URL, api_key, base_query, FIELD_MASK_TEXT
    )


def _paginate(
    endpoint_id: str,
    url: str,
    api_key: str,
    base_query: Dict[str, Any],
    field_mask: str,
) -> List[Dict[str, Any]]:
    """Issue up to MAX_PAGES sequential requests, each via cached_api_call.

    Cache key uses the page-token-augmented query so page 1 and page 2 of the
    same logical search land in distinct cache files. This means a re-run hits
    cache on page 1 but does NOT need to re-derive page 2's token — page 2's
    cache entry is keyed by the original token from the prior fresh run.
    """
    all_places: List[Dict[str, Any]] = []
    page_token: Optional[str] = None
    headers_template = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": field_mask,
    }

    for page_idx in range(MAX_PAGES):
        query: Dict[str, Any] = dict(base_query)
        if page_token is not None:
            query["pageToken"] = page_token

        # Build cache key WITHOUT the api_key (key would invalidate cache when
        # rotated). Body to the actual fetcher includes whatever it needs.
        cache_query = dict(query)

        def fetcher(_query=query):
            if page_token is not None:
                # Page tokens take a moment to become valid.
                time.sleep(NEXT_PAGE_TOKEN_WARMUP_S)
            resp = requests.post(url, json=_query, headers=headers_template, timeout=30)
            resp.raise_for_status()
            return resp.json()

        response = cached_api_call(
            endpoint=endpoint_id,
            query=cache_query,
            cost_usd=COST_PER_CALL_USD,
            fetcher=fetcher,
        )

        for raw in response.get("places") or []:
            normalized = _normalize_place(raw)
            if normalized is not None:
                all_places.append(normalized)

        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return all_places


def _dedupe(places: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Dedupe by place_id AND by lat/lng proximity ≤ DEDUPE_PROXIMITY_METERS.

    Catches co-located listings of the same physical facility under different
    Google place_ids (e.g., "NTRC" and "Racquets & Strings at NTRC" being
    the same building, different storefronts in Google's index).

    O(n²) — acceptable for typical result counts (< 500). First occurrence
    of each cluster wins, preserving the original rank order.
    """
    seen_ids: set = set()
    kept: List[Dict[str, Any]] = []
    for p in places:
        if p["place_id"] in seen_ids:
            continue
        too_close = False
        for prev in kept:
            if _haversine_m(p["lat"], p["lng"], prev["lat"], prev["lng"]) <= DEDUPE_PROXIMITY_METERS:
                too_close = True
                break
        if too_close:
            continue
        seen_ids.add(p["place_id"])
        kept.append(p)
    return kept


def fetch_tennis_facilities(lat: float, lng: float, radius_m: int = 15000) -> List[Dict[str, Any]]:
    """Tennis facilities via Option-C merge: Search Nearby on `tennis_court`
    (the only Google-supported tennis place type) + Text Search on
    "tennis club" (catches dedicated clubs that aren't tagged tennis_court).

    Probed Place Types Table A in Phase 0: `tennis_club` and
    `racquet_sport_club` returned 400 INVALID_ARGUMENT — only `tennis_court`
    is valid. Text Search supplement is the load-bearing accuracy fix.
    """
    nearby_results = _nearby_search(
        lat=lat,
        lng=lng,
        radius_m=radius_m,
        included_types=["tennis_court"],
    )
    text_results = _text_search("tennis club", lat, lng, radius_m)
    return _dedupe(nearby_results + text_results)


def fetch_boutique_fitness(lat: float, lng: float, radius_m: int = 15000) -> List[Dict[str, Any]]:
    """Boutique fitness via per-brand Text Search.

    Generic "fitness_center" / "gym" types capture too much (24 Hour Fitness,
    Planet Fitness, etc.) — we want the $150/mo recurring-spend signal, which
    only the named premium chains demonstrate. Each brand is one Text Search
    call, separately cached + budgeted.
    """
    merged: List[Dict[str, Any]] = []
    for brand in BOUTIQUE_FITNESS_BRANDS:
        merged.extend(_text_search(brand, lat, lng, radius_m))
    return _dedupe(merged)


def fetch_golf_clubs(lat: float, lng: float, radius_m: int = 15000) -> List[Dict[str, Any]]:
    """Golf clubs via Option-C merge: Search Nearby on `golf_course` + Text
    Search on "country club" (since `country_club` is NOT a valid Google
    Place type — probed in Phase 0 returning 400 INVALID_ARGUMENT). Text
    Search captures private country clubs that may have golf+tennis but
    don't carry the golf_course tag.
    """
    nearby_results = _nearby_search(
        lat=lat,
        lng=lng,
        radius_m=radius_m,
        included_types=["golf_course"],
    )
    text_results = _text_search("country club", lat, lng, radius_m)
    return _dedupe(nearby_results + text_results)


def fetch_padel_facilities(lat: float, lng: float, radius_m: int = 15000) -> List[Dict[str, Any]]:
    """Padel supply check via Text Search ('padel club' + 'padel court').

    Google has no native padel place type. Two text queries cover the
    naming variants; merged + deduped. This is the supply-side signal —
    anchors a candidate's competitive context.
    """
    merged: List[Dict[str, Any]] = []
    for q in PADEL_TEXT_QUERIES:
        merged.extend(_text_search(q, lat, lng, radius_m))
    return _dedupe(merged)
