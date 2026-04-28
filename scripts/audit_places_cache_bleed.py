"""Audit existing Google Places cache for locationBias bleed.

For each pre-fix anchor that already has cached Text Search responses,
rebuild the original (locationBias) query, compute its cache hash, read
the cached result, and count places that lie outside the declared 15km
search radius.

Read-only — does NOT modify any state. Reports per-query and per-anchor
bleed counts/percentages so the operator can decide whether to invalidate
the affected caches.

Run: python3 scripts/audit_places_cache_bleed.py
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Dict, List, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.data.google_places import BOUTIQUE_FITNESS_BRANDS, PADEL_TEXT_QUERIES

ZCTA_CACHE = REPO_ROOT / "data" / "raw" / "zcta_centroids.json"
PLACES_CACHE = REPO_ROOT / "data" / "raw" / "google_places"

RADIUS_M = 15000

# Only the anchors that actually got Google Places fetched in the pre-fix run.
PRE_FIX_ANCHORS = [
    ("ntrc_frisco_75034", "75034"),
    ("ntrc_frisco_75035", "75035"),
    ("sensa_germantown", "37208"),
    ("roanoke_al", "36272"),
]

# Text Search queries the runner issued per anchor (matches google_places.py).
TEXT_QUERIES = (
    ["tennis club"]
    + BOUTIQUE_FITNESS_BRANDS
    + ["country club"]
    + PADEL_TEXT_QUERIES
)


def cache_key(endpoint: str, query: dict) -> str:
    """Identical algorithm to disk_cache._key()."""
    payload = json.dumps(
        {"endpoint": endpoint, "query": query},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def pre_fix_text_query(text_query: str, lat: float, lng: float) -> dict:
    """Reconstructs the buggy locationBias-shaped query body the runner used."""
    return {
        "textQuery": text_query,
        "locationBias": {
            "circle": {
                "center": {"latitude": lat, "longitude": lng},
                "radius": float(RADIUS_M),
            }
        },
        "maxResultCount": 20,
    }


def load_cache_file(key: str) -> dict:
    path = PLACES_CACHE / f"{key}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


def audit_query(text_query: str, lat: float, lng: float) -> Tuple[int, int, int]:
    """Return (in_radius, out_radius, total) for the cached response."""
    query = pre_fix_text_query(text_query, lat, lng)
    key = cache_key("google.places.text_search", query)
    cached = load_cache_file(key)
    if cached is None:
        return (0, 0, 0)
    places = cached.get("places") or []
    in_count = 0
    out_count = 0
    for place in places:
        loc = place.get("location") or {}
        plat = loc.get("latitude")
        plng = loc.get("longitude")
        if plat is None or plng is None:
            continue
        d = haversine_m(lat, lng, float(plat), float(plng))
        if d <= RADIUS_M:
            in_count += 1
        else:
            out_count += 1
    return (in_count, out_count, in_count + out_count)


def main() -> int:
    if not ZCTA_CACHE.exists():
        print(f"ERROR: {ZCTA_CACHE} not found")
        return 1
    centroids = json.loads(ZCTA_CACHE.read_text())

    print(f"Auditing {len(PRE_FIX_ANCHORS)} pre-fix anchors × "
          f"{len(TEXT_QUERIES)} Text Search queries each at radius {RADIUS_M}m")
    print()

    overall_in = 0
    overall_out = 0
    overall_total = 0
    anchor_summary: List[Dict] = []
    bleed_alerts: List[str] = []

    for location_id, zip_code in PRE_FIX_ANCHORS:
        entry = centroids.get(zip_code) or {}
        pop = entry.get("pop_centroid")
        if not pop:
            print(f"SKIP {location_id} ({zip_code}) — no pop centroid")
            continue
        lat, lng = float(pop[0]), float(pop[1])

        anchor_in = 0
        anchor_out = 0
        anchor_total = 0
        per_query_results: List[Tuple[str, int, int, int]] = []

        for tq in TEXT_QUERIES:
            i, o, t = audit_query(tq, lat, lng)
            per_query_results.append((tq, i, o, t))
            anchor_in += i
            anchor_out += o
            anchor_total += t

        ratio = (anchor_out / anchor_total) if anchor_total else 0.0
        flag = ""
        if anchor_total and ratio > 0.05:
            flag = " ⚠ >5%"
            bleed_alerts.append(f"{location_id}: bleed {ratio:.1%} ({anchor_out}/{anchor_total})")
        elif anchor_total and ratio > 0.02:
            flag = " (2-5% gray)"

        print(f"=== {location_id} (zip {zip_code}, origin {lat:.4f}, {lng:.4f}) ===")
        print(f"  total_results={anchor_total}  in={anchor_in}  "
              f"out={anchor_out}  bleed={ratio:.1%}{flag}")
        # Show only queries with bleed > 0
        bleeders = [(q, i, o, t) for (q, i, o, t) in per_query_results if o > 0]
        if bleeders:
            print(f"  queries with bleed:")
            for q, i, o, t in sorted(bleeders, key=lambda x: -x[2]):
                print(f"    {q!r:<30}  {o}/{t} out-of-radius ({o/t:.0%})" if t else f"    {q!r}: ?")
        else:
            print(f"  no out-of-radius results in any cached query")
        print()

        overall_in += anchor_in
        overall_out += anchor_out
        overall_total += anchor_total
        anchor_summary.append({
            "location_id": location_id,
            "in": anchor_in,
            "out": anchor_out,
            "total": anchor_total,
            "ratio": ratio,
        })

    print(f"=== Overall ===")
    overall_ratio = (overall_out / overall_total) if overall_total else 0.0
    print(f"  total_results={overall_total}  in={overall_in}  "
          f"out={overall_out}  bleed={overall_ratio:.1%}")
    print()
    print("=== Decision rule (per plan) ===")
    print("  Any of NTRC 75034 / 75035 / Sensa with >5% bleed → invalidate that anchor's caches")
    print("  All <2% on those 3 → keep their caches, refetch only Roanoke + 6 remaining")
    print("  Roanoke caches → invalidate unconditionally (known-bad from runner halt)")
    print()
    if bleed_alerts:
        print("BLEED ALERTS (>5%):")
        for a in bleed_alerts:
            print(f"  {a}")
    else:
        print("No anchor exceeds 5% bleed threshold.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
