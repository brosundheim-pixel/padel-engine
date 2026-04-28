"""Zip code → centroid lookup.

Two centroid types supported:

  zip_to_centroid(zip)           -> geographic centroid via OSM Nominatim.
                                    The display point Nominatim returns for the
                                    ZCTA. Adequate when polygon centroid is fine.

  pop_weighted_centroid(zip)     -> population-weighted centroid computed from
                                    tract-level data (see src/data/census_tracts).
                                    Center of where people actually live, not the
                                    polygon's geometric middle. Use this for
                                    drive-time isochrone origins — riders care
                                    about distance from homes, not from the
                                    middle of a ZCTA polygon that may be half
                                    industrial / parkland.

Cache schema (data/raw/zcta_centroids.json):
  { "75033": { "geo_centroid": [lat,lng], "pop_centroid": [lat,lng] } }

Old flat-list schema { "75033": [lat,lng] } is migrated in-place on first
read: the existing list is treated as geo_centroid; pop_centroid is fetched
on demand and merged in.

Initial geocoder attempt was zippopotam.us; switched to Nominatim (via
osmnx) when zippopotam returned 404 for common zips like 75033.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Tuple

import osmnx as ox

from src.data.census_tracts import pop_weighted_zcta_centroid

REPO_ROOT = Path(__file__).resolve().parents[2]
CACHE_PATH = REPO_ROOT / "data" / "raw" / "zcta_centroids.json"


def _load_cache() -> dict:
    """Read cache, migrating flat-list rows to dict schema in-place."""
    if not CACHE_PATH.exists():
        return {}
    raw = json.loads(CACHE_PATH.read_text())
    migrated = False
    for zip_code, value in list(raw.items()):
        if isinstance(value, list):
            raw[zip_code] = {"geo_centroid": [float(value[0]), float(value[1])]}
            migrated = True
    if migrated:
        CACHE_PATH.write_text(json.dumps(raw, indent=2, sort_keys=True))
    return raw


def _save_cache(cache: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, indent=2, sort_keys=True))


def _ensure_entry(cache: dict, zip_code: str) -> dict:
    entry = cache.get(zip_code)
    if entry is None or not isinstance(entry, dict):
        entry = {}
        cache[zip_code] = entry
    return entry


def zip_to_centroid(zip_code: str) -> Optional[Tuple[float, float]]:
    """Return geographic centroid (lat, lng) via OSM Nominatim. Cached."""
    zip_code = zip_code.strip()
    cache = _load_cache()
    entry = cache.get(zip_code) or {}
    geo = entry.get("geo_centroid") if isinstance(entry, dict) else None
    if geo:
        return (float(geo[0]), float(geo[1]))

    try:
        lat, lng = ox.geocode(f"{zip_code}, USA")
    except Exception:
        return None

    entry = _ensure_entry(cache, zip_code)
    entry["geo_centroid"] = [float(lat), float(lng)]
    _save_cache(cache)
    return (float(lat), float(lng))


def pop_weighted_centroid(zip_code: str) -> Optional[Tuple[float, float]]:
    """Return population-weighted centroid (lat, lng) computed from tracts.

    Falls back to None if tract data is unavailable for the ZCTA. Caller
    decides whether to substitute the geographic centroid (zip_to_centroid).
    Cached alongside geo_centroid in zcta_centroids.json.
    """
    zip_code = zip_code.strip()
    cache = _load_cache()
    entry = cache.get(zip_code) or {}
    pop = entry.get("pop_centroid") if isinstance(entry, dict) else None
    if pop:
        return (float(pop[0]), float(pop[1]))

    centroid = pop_weighted_zcta_centroid(zip_code)
    if centroid is None:
        return None

    entry = _ensure_entry(cache, zip_code)
    entry["pop_centroid"] = [float(centroid[0]), float(centroid[1])]
    _save_cache(cache)
    return centroid
