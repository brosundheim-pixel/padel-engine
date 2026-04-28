"""Census tract data for population-weighted ZCTA centroids.

Three primary data sources, each cached to disk on first fetch:

1. ZCTA-to-tract relationship file (Census 2020). Pipe-delimited, ~50MB.
   Maps each ZCTA to the set of tracts it overlaps.
   Cached at data/raw/census/zcta_tract_crosswalk.txt

2. Tract Gazetteer file (Census 2023). Tab-delimited, ~5MB extracted.
   Provides INTPTLAT / INTPTLONG for every US tract — Census's own
   internal point, which IS the population-weighted centroid for the tract.
   Cached at data/raw/census/tract_gazetteer.txt

3. ACS 2023 5-year B01003_001E (total population) per tract. Bulk-fetched
   per (state, county) since the ACS API supports tract:* wildcards within
   a county. Cached per-county at data/raw/census/tract_pop_{state}_{county}.json

Public API:
    tracts_in_zcta(zcta)          -> list of tract GEOID strings
    tract_centroid(tract_geoid)   -> (lat, lng) tuple
    tract_population(tract_geoid) -> int  (caches via county bulk fetch)
    pop_weighted_zcta_centroid(zcta) -> (lat, lng) tuple, or None on failure
"""

from __future__ import annotations

import csv
import io
import json
import os
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = REPO_ROOT / "data" / "raw" / "census"

CROSSWALK_URL = (
    "https://www2.census.gov/geo/docs/maps-data/data/rel2020/zcta520/"
    "tab20_zcta520_tract20_natl.txt"
)
CROSSWALK_PATH = RAW_DIR / "zcta_tract_crosswalk.txt"

GAZETTEER_URL = (
    "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/"
    "2023_Gazetteer/2023_Gaz_tracts_national.zip"
)
GAZETTEER_PATH = RAW_DIR / "tract_gazetteer.txt"

ACS_BASE = "https://api.census.gov/data/2023/acs/acs5"


_crosswalk_cache: Optional[Dict[str, List[str]]] = None
_gazetteer_cache: Optional[Dict[str, Tuple[float, float]]] = None
_pop_cache: Dict[Tuple[str, str], Dict[str, int]] = {}


def _ensure_dir() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)


def download_crosswalk() -> Path:
    """Download ZCTA-to-tract relationship file if not already cached."""
    _ensure_dir()
    if CROSSWALK_PATH.exists() and CROSSWALK_PATH.stat().st_size > 1_000_000:
        return CROSSWALK_PATH
    print(f"Downloading ZCTA-tract crosswalk ({CROSSWALK_URL})...")
    resp = requests.get(CROSSWALK_URL, timeout=300)
    resp.raise_for_status()
    CROSSWALK_PATH.write_bytes(resp.content)
    print(f"Saved {len(resp.content) / 1e6:.1f} MB to {CROSSWALK_PATH}")
    return CROSSWALK_PATH


def download_gazetteer() -> Path:
    """Download tract gazetteer (zipped), extract national tract centroids."""
    _ensure_dir()
    if GAZETTEER_PATH.exists() and GAZETTEER_PATH.stat().st_size > 1_000_000:
        return GAZETTEER_PATH
    print(f"Downloading tract gazetteer ({GAZETTEER_URL})...")
    resp = requests.get(GAZETTEER_URL, timeout=300)
    resp.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        # Filename inside zip should be 2023_Gaz_tracts_national.txt
        candidates = [n for n in zf.namelist() if n.endswith(".txt")]
        if not candidates:
            raise RuntimeError(f"No .txt file in gazetteer zip: {zf.namelist()}")
        inner = candidates[0]
        GAZETTEER_PATH.write_bytes(zf.read(inner))
    print(f"Extracted {GAZETTEER_PATH.stat().st_size / 1e6:.1f} MB to {GAZETTEER_PATH}")
    return GAZETTEER_PATH


def _load_crosswalk() -> Dict[str, List[str]]:
    """Parse crosswalk into {zcta -> [tract_geoid, ...]}, land-overlap rows only."""
    global _crosswalk_cache
    if _crosswalk_cache is not None:
        return _crosswalk_cache
    download_crosswalk()
    mapping: Dict[str, List[str]] = {}
    with CROSSWALK_PATH.open(encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="|")
        for row in reader:
            zcta = (row.get("GEOID_ZCTA5_20") or "").strip()
            tract = (row.get("GEOID_TRACT_20") or "").strip()
            land_part = row.get("AREALAND_PART") or "0"
            if not zcta or not tract:
                continue
            try:
                if int(land_part) <= 0:
                    continue
            except ValueError:
                continue
            mapping.setdefault(zcta, []).append(tract)
    _crosswalk_cache = mapping
    return mapping


def _load_gazetteer() -> Dict[str, Tuple[float, float]]:
    """Parse tract gazetteer into {tract_geoid -> (lat, lng)}."""
    global _gazetteer_cache
    if _gazetteer_cache is not None:
        return _gazetteer_cache
    download_gazetteer()
    mapping: Dict[str, Tuple[float, float]] = {}
    with GAZETTEER_PATH.open(encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            row = {k.strip(): (v.strip() if isinstance(v, str) else v) for k, v in row.items()}
            geoid = row.get("GEOID")
            lat_s = row.get("INTPTLAT")
            lng_s = row.get("INTPTLONG") or row.get("INTPTLONG\t") or row.get("INTPTLONG ")
            if not (geoid and lat_s and lng_s):
                continue
            try:
                lat = float(lat_s)
                lng = float(lng_s)
            except ValueError:
                continue
            mapping[geoid] = (lat, lng)
    _gazetteer_cache = mapping
    return mapping


def _county_pop_cache_path(state: str, county: str) -> Path:
    return RAW_DIR / f"tract_pop_{state}_{county}.json"


def _fetch_county_tract_populations(state: str, county: str) -> Dict[str, int]:
    """Bulk-fetch ACS B01003_001E for all tracts in (state, county). Cached."""
    key = (state, county)
    if key in _pop_cache:
        return _pop_cache[key]
    cache_path = _county_pop_cache_path(state, county)
    if cache_path.exists():
        data = json.loads(cache_path.read_text())
        _pop_cache[key] = {k: int(v) for k, v in data.items()}
        return _pop_cache[key]

    load_dotenv(REPO_ROOT / ".env")
    api_key = os.getenv("CENSUS_API_KEY")
    if not api_key:
        raise RuntimeError("CENSUS_API_KEY missing from .env")

    params = {
        "get": "B01003_001E",
        "for": "tract:*",
        "in": f"state:{state} county:{county}",
        "key": api_key,
    }
    resp = requests.get(ACS_BASE, params=params, timeout=60)
    resp.raise_for_status()
    payload = resp.json()
    header, rows = payload[0], payload[1:]
    pop_idx = header.index("B01003_001E")
    state_idx = header.index("state")
    county_idx = header.index("county")
    tract_idx = header.index("tract")
    out: Dict[str, int] = {}
    for row in rows:
        try:
            pop = int(row[pop_idx])
        except (TypeError, ValueError):
            pop = 0
        if pop < 0:
            pop = 0
        geoid = f"{row[state_idx]}{row[county_idx]}{row[tract_idx]}"
        out[geoid] = pop
    cache_path.write_text(json.dumps(out, indent=2, sort_keys=True))
    _pop_cache[key] = out
    return out


def tracts_in_zcta(zcta: str) -> List[str]:
    """Return list of tract GEOIDs that overlap the given ZCTA on land."""
    return _load_crosswalk().get(zcta.strip(), [])


def tract_centroid(tract_geoid: str) -> Optional[Tuple[float, float]]:
    """Tract internal point (population-weighted by Census)."""
    return _load_gazetteer().get(tract_geoid)


def tract_population(tract_geoid: str) -> Optional[int]:
    """Total tract population from ACS 2023 5-year. Bulk-cached per county."""
    if len(tract_geoid) != 11:
        return None
    state = tract_geoid[:2]
    county = tract_geoid[2:5]
    county_pops = _fetch_county_tract_populations(state, county)
    return county_pops.get(tract_geoid)


def pop_weighted_zcta_centroid(zcta: str) -> Optional[Tuple[float, float]]:
    """Population-weighted centroid of a ZCTA, computed from its tracts.

    Returns None if the ZCTA has no tract overlap, no gazetteer entries,
    or zero total population (e.g., PO-box-only ZCTAs).
    """
    tracts = tracts_in_zcta(zcta)
    if not tracts:
        return None

    weighted_lat = 0.0
    weighted_lng = 0.0
    total_pop = 0

    for tract_geoid in tracts:
        centroid = tract_centroid(tract_geoid)
        if centroid is None:
            continue
        pop = tract_population(tract_geoid) or 0
        if pop <= 0:
            continue
        lat, lng = centroid
        weighted_lat += lat * pop
        weighted_lng += lng * pop
        total_pop += pop

    if total_pop == 0:
        return None
    return (weighted_lat / total_pop, weighted_lng / total_pop)
