"""Census tract data for catchment aggregation + pop-weighted ZCTA centroids.

Three primary data sources, each cached to disk on first fetch:

1. ZCTA-to-tract relationship file (Census 2020). Pipe-delimited, ~50MB.
   Maps each ZCTA to the set of tracts it overlaps.
   Cached at data/raw/census/zcta_tract_crosswalk.txt

2. Tract Gazetteer file (Census 2023). Tab-delimited, ~5MB extracted.
   Provides INTPTLAT / INTPTLONG for every US tract — Census's own
   internal point, which IS the population-weighted centroid for the tract.
   Cached at data/raw/census/tract_gazetteer.txt

3. ACS 2023 5-year tract demographics. Bulk-fetched per (state, county)
   in a single API call covering all 14 variables we need:
     - B01003_001E (total population)
     - B19013_001E (median household income)
     - B25003_001E, B25003_002E (ownership rate numerator + denominator)
     - B01001_011E..015E + B01001_035E..039E (10 fields, age 25-49 share)
   Cached at data/raw/census/tract_demographics_{state}_{county}.json
   with ratios precomputed.

   Legacy: prior pipeline cached only B01003_001E at
   data/raw/census/tract_pop_{state}_{county}.json. Those files are still
   read as a fallback for tract_population() — see _legacy_pop_cache_path.

Public API:
    tracts_in_zcta(zcta)              -> list of tract GEOID strings
    tract_centroid(tract_geoid)       -> (lat, lng) tuple
    tract_population(tract_geoid)     -> int (3-step fallback: new cache → old cache → fresh fetch)
    tract_demographics(tract_geoid)   -> dict {population, income, ownership_rate, pct_age_25_49}
    pop_weighted_zcta_centroid(zcta)  -> (lat, lng) tuple, or None on failure
"""

from __future__ import annotations

import csv
import io
import json
import os
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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

# Variables fetched per (state, county) bulk call. Order is significant only
# for parsing; we look up by header index.
ACS_VARIABLES = [
    "B01003_001E",  # total population
    "B19013_001E",  # median household income
    "B25003_001E",  # total occupied housing units (ownership denominator)
    "B25003_002E",  # owner-occupied units (ownership numerator)
    # Male age 25-49: 25-29, 30-34, 35-39, 40-44, 45-49
    "B01001_011E", "B01001_012E", "B01001_013E", "B01001_014E", "B01001_015E",
    # Female age 25-49 (same five 5-year buckets)
    "B01001_035E", "B01001_036E", "B01001_037E", "B01001_038E", "B01001_039E",
]

_AGE_25_49_VARS = [
    "B01001_011E", "B01001_012E", "B01001_013E", "B01001_014E", "B01001_015E",
    "B01001_035E", "B01001_036E", "B01001_037E", "B01001_038E", "B01001_039E",
]


_crosswalk_cache: Optional[Dict[str, List[str]]] = None
_gazetteer_cache: Optional[Dict[str, Tuple[float, float]]] = None
_demographics_cache: Dict[Tuple[str, str], Dict[str, Dict[str, Any]]] = {}


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
        candidates = [n for n in zf.namelist() if n.endswith(".txt")]
        if not candidates:
            raise RuntimeError(f"No .txt file in gazetteer zip: {zf.namelist()}")
        inner = candidates[0]
        GAZETTEER_PATH.write_bytes(zf.read(inner))
    print(f"Extracted {GAZETTEER_PATH.stat().st_size / 1e6:.1f} MB to {GAZETTEER_PATH}")
    return GAZETTEER_PATH


def _load_crosswalk() -> Dict[str, List[str]]:
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


def _county_demographics_cache_path(state: str, county: str) -> Path:
    return RAW_DIR / f"tract_demographics_{state}_{county}.json"


def _legacy_pop_cache_path(state: str, county: str) -> Path:
    return RAW_DIR / f"tract_pop_{state}_{county}.json"


def _coerce_int(value: Any) -> Optional[int]:
    """Census uses negative sentinels (-666666666 etc.) for missing — coerce to None."""
    if value is None:
        return None
    try:
        n = int(float(value))
    except (TypeError, ValueError):
        return None
    if n < 0:
        return None
    return n


def _build_record(row_vals: Dict[str, Any]) -> Dict[str, Any]:
    """Compute ratios from raw ACS values. Returns the cached record shape."""
    pop = _coerce_int(row_vals.get("B01003_001E"))
    income = _coerce_int(row_vals.get("B19013_001E"))
    occ_total = _coerce_int(row_vals.get("B25003_001E"))
    occ_owner = _coerce_int(row_vals.get("B25003_002E"))
    age_counts = [_coerce_int(row_vals.get(v)) for v in _AGE_25_49_VARS]
    age_total = sum(c for c in age_counts if c is not None) if any(c is not None for c in age_counts) else None

    ownership_rate: Optional[float]
    if occ_total and occ_owner is not None:
        ownership_rate = round(occ_owner / occ_total, 4)
    else:
        ownership_rate = None

    pct_age_25_49: Optional[float]
    if pop and age_total is not None:
        pct_age_25_49 = round(age_total / pop, 4)
    else:
        pct_age_25_49 = None

    return {
        "population": pop or 0,
        "income": income,
        "ownership_rate": ownership_rate,
        "pct_age_25_49": pct_age_25_49,
    }


def _fetch_county_tract_demographics(state: str, county: str) -> Dict[str, Dict[str, Any]]:
    """Bulk-fetch all 14 ACS variables for every tract in (state, county).

    Three-step access pattern:
      1. In-memory cache (this process)
      2. On-disk cache at tract_demographics_{state}_{county}.json
      3. Fresh ACS API call
    """
    key = (state, county)
    if key in _demographics_cache:
        return _demographics_cache[key]
    cache_path = _county_demographics_cache_path(state, county)
    if cache_path.exists():
        _demographics_cache[key] = json.loads(cache_path.read_text())
        return _demographics_cache[key]

    load_dotenv(REPO_ROOT / ".env")
    api_key = os.getenv("CENSUS_API_KEY")
    if not api_key:
        raise RuntimeError("CENSUS_API_KEY missing from .env")

    params = {
        "get": ",".join(ACS_VARIABLES),
        "for": "tract:*",
        "in": f"state:{state} county:{county}",
        "key": api_key,
    }
    resp = requests.get(ACS_BASE, params=params, timeout=60)
    resp.raise_for_status()
    payload = resp.json()
    header, rows = payload[0], payload[1:]
    state_idx = header.index("state")
    county_idx = header.index("county")
    tract_idx = header.index("tract")

    out: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        row_vals = {var: row[header.index(var)] for var in ACS_VARIABLES}
        geoid = f"{row[state_idx]}{row[county_idx]}{row[tract_idx]}"
        out[geoid] = _build_record(row_vals)

    _ensure_dir()
    cache_path.write_text(json.dumps(out, indent=2, sort_keys=True))
    _demographics_cache[key] = out
    return out


def tracts_in_zcta(zcta: str) -> List[str]:
    """Return list of tract GEOIDs that overlap the given ZCTA on land."""
    return _load_crosswalk().get(zcta.strip(), [])


def tract_centroid(tract_geoid: str) -> Optional[Tuple[float, float]]:
    """Tract internal point (population-weighted by Census)."""
    return _load_gazetteer().get(tract_geoid)


def tract_demographics(tract_geoid: str) -> Optional[Dict[str, Any]]:
    """Full demographics for a tract: population, income, ownership_rate, pct_age_25_49.

    Cached via _fetch_county_tract_demographics — fetches one bulk call per
    (state, county) on first access, then in-memory + disk for the rest of
    the project lifetime.
    """
    if len(tract_geoid) != 11:
        return None
    state = tract_geoid[:2]
    county = tract_geoid[2:5]
    county_demo = _fetch_county_tract_demographics(state, county)
    return county_demo.get(tract_geoid)


def tract_population(tract_geoid: str) -> Optional[int]:
    """Tract total population. Three-step fallback for resilience:

      1. New demographics cache (preferred — has full record)
      2. Legacy population-only cache (tract_pop_{state}_{county}.json)
      3. Fresh demographics fetch via the new path

    Step 2 lets prior runs' cache files keep being useful even before the
    new demographics fetcher has touched a county.
    """
    if len(tract_geoid) != 11:
        return None
    state = tract_geoid[:2]
    county = tract_geoid[2:5]
    key = (state, county)

    # Step 1 — check new demographics cache (memory or disk)
    if key in _demographics_cache:
        rec = _demographics_cache[key].get(tract_geoid)
        return rec.get("population") if rec else None
    new_path = _county_demographics_cache_path(state, county)
    if new_path.exists():
        _demographics_cache[key] = json.loads(new_path.read_text())
        rec = _demographics_cache[key].get(tract_geoid)
        return rec.get("population") if rec else None

    # Step 2 — legacy population-only cache fallback (does NOT populate
    # demographics cache; it's missing the other fields)
    legacy_path = _legacy_pop_cache_path(state, county)
    if legacy_path.exists():
        legacy = json.loads(legacy_path.read_text())
        val = legacy.get(tract_geoid)
        if val is not None:
            return int(val)

    # Step 3 — fresh fetch via new path (populates demographics cache)
    county_demo = _fetch_county_tract_demographics(state, county)
    rec = county_demo.get(tract_geoid)
    return rec.get("population") if rec else None


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
