"""Per-anchor demand and supply signals. All pure functions, no I/O.

Signal density convention: per-1,000 affluent residents in the catchment.
A density of 0.1 means "1 facility per 10,000 affluent people in the
catchment." Numerator is post-quality-filter facility count; denominator
is the v0-canonical affluent catchment population (METHODOLOGY.md
"Affluent-demand-only catchment").

Quality filter (v0_provisional, tunable from anchor calibration):
  - rating >= 3.5 (excludes low-quality placeholder listings)
  - user_ratings_total >= 30 (excludes school courts, neighborhood courts,
    and unreviewed placeholders that inflate raw counts without representing
    real premium demand)

Drive-time-to-nearest-padel is a Tier 1 supply signal per CLAUDE.md
(target: zero padel within 30-min drive). Returned in minutes.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional

# v0 quality thresholds — applied at the place-filter step.
QUALITY_MIN_RATING = 3.5
QUALITY_MIN_REVIEWS = 30

# Approximate suburban driving speed for v0 padel-distance proxy.
# Real drive-time isochrone per competitor is the v1 upgrade.
HAVERSINE_KM_PER_MIN = 50.0 / 60.0  # 50 km/h average → 0.833 km/min


def quality_filter(places: List[Dict]) -> List[Dict]:
    """Drop low-quality / unreviewed places before density calculation."""
    out: List[Dict] = []
    for p in places:
        rating = p.get("rating") or 0
        reviews = p.get("user_ratings_total") or 0
        if rating >= QUALITY_MIN_RATING and reviews >= QUALITY_MIN_REVIEWS:
            out.append(p)
    return out


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6_371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def _density_per_1k(count: int, affluent_catchment_pop: int) -> float:
    """Per-1,000-affluent-capita density. Returns 0.0 if catchment is empty."""
    if not affluent_catchment_pop or affluent_catchment_pop <= 0:
        return 0.0
    return 1000.0 * count / affluent_catchment_pop


def tennis_density_per_affluent_capita(
    tennis_count: int, affluent_catchment_pop: int
) -> float:
    """Tennis facilities per 1K affluent residents. Caller pre-applies
    quality_filter() to drop schools and unreviewed courts."""
    return _density_per_1k(tennis_count, affluent_catchment_pop)


def boutique_density_per_affluent_capita(
    boutique_count: int, affluent_catchment_pop: int
) -> float:
    """Boutique fitness studios per 1K affluent residents. Caller pre-
    applies quality_filter()."""
    return _density_per_1k(boutique_count, affluent_catchment_pop)


def golf_density_per_affluent_capita(
    golf_count: int, affluent_catchment_pop: int
) -> float:
    """Golf courses + country clubs per 1K affluent residents."""
    return _density_per_1k(golf_count, affluent_catchment_pop)


def drive_time_to_nearest_padel(
    candidate_lat: float,
    candidate_lng: float,
    padel_facilities: List[Dict],
) -> float:
    """Minutes to nearest padel facility (Tier 1 supply signal).

    v0 approximation: minutes = haversine_km / HAVERSINE_KM_PER_MIN.
    Ignores road network detours, water, traffic. Acceptable for
    rank-ordering anchors in a single scoring pass; v1 should swap
    to actual drive-time isochrone per competitor.

    Returns float('inf') if no padel facilities supplied. Higher value
    = fewer nearby competitors = more attractive market.
    """
    if not padel_facilities:
        return float("inf")
    nearest_km = min(
        _haversine_km(candidate_lat, candidate_lng, p["lat"], p["lng"])
        for p in padel_facilities
    )
    return nearest_km / HAVERSINE_KM_PER_MIN
