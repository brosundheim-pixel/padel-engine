"""Sum tract populations inside a polygon — total OR affluent-filtered.

Two parallel aggregators for the v0-canonical demand-side primitive:

  catchment_population(polygon, centroids, populations)
      Pure function. Sums every tract population whose centroid falls
      inside polygon.

  affluent_catchment_population(polygon, centroids, demographics, criteria)
      Pure function. Sums population only for tracts that ALSO pass the
      affluent-criteria gate (income / age 25-49 / ownership thresholds).

Each pure function has an end-to-end orchestrator (`compute_*`) that does
bbox filtering of the national gazetteer and bulk-fetches the per-county
data needed before calling the pure function.

The affluent-only aggregation is the v0-canonical demand signal per
METHODOLOGY.md "Affluent-demand-only catchment". Total catchment is kept
for visibility (reported alongside affluent) but does NOT feed scoring.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional, Tuple

from shapely.geometry import Point, Polygon

from src.data.census_tracts import (
    _load_gazetteer,
    tract_demographics,
    tract_population,
)


# ---------------------------------------------------------------------------
# Affluent criteria (v0 canonical thresholds — see METHODOLOGY.md)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AffluentCriteria:
    """Tract-level affluent gate. v0 thresholds locked in METHODOLOGY.md
    "Affluent-demand-only catchment". A tract must pass ALL three to count
    toward the affluent catchment population."""

    income_min: int = 100_000
    pct_age_25_49_min: float = 0.25
    ownership_rate_min: float = 0.50


DEFAULT_AFFLUENT = AffluentCriteria()


def affluent_tract_passes(
    income: Optional[int],
    pct_age_25_49: Optional[float],
    ownership_rate: Optional[float],
    criteria: AffluentCriteria = DEFAULT_AFFLUENT,
) -> bool:
    """True iff tract passes all three affluent gates. Pure function.

    Missing data → False (conservative: a tract with unknown income is not
    counted as affluent, even if other fields would qualify).
    """
    if income is None or pct_age_25_49 is None or ownership_rate is None:
        return False
    return (
        income >= criteria.income_min
        and pct_age_25_49 >= criteria.pct_age_25_49_min
        and ownership_rate >= criteria.ownership_rate_min
    )


# ---------------------------------------------------------------------------
# Pure aggregation functions (no I/O)
# ---------------------------------------------------------------------------


def catchment_population(
    polygon: Polygon,
    tract_centroids: Dict[str, Tuple[float, float]],
    tract_populations: Dict[str, int],
) -> int:
    """Total population sum for tracts whose centroid lies inside polygon."""
    total = 0
    for geoid, centroid in tract_centroids.items():
        pop = tract_populations.get(geoid)
        if pop is None:
            continue
        lat, lng = centroid
        if polygon.contains(Point(lng, lat)):
            total += pop
    return total


def affluent_catchment_population(
    polygon: Polygon,
    tract_centroids: Dict[str, Tuple[float, float]],
    tract_demos: Dict[str, Dict[str, Any]],
    criteria: AffluentCriteria = DEFAULT_AFFLUENT,
) -> int:
    """Sum populations of tracts that (a) have centroid inside polygon AND
    (b) pass the affluent-criteria gate. Tracts failing the gate contribute
    zero. Pure function: caller supplies the data dicts."""
    total = 0
    for geoid, centroid in tract_centroids.items():
        record = tract_demos.get(geoid)
        if record is None:
            continue
        if not affluent_tract_passes(
            record.get("income"),
            record.get("pct_age_25_49"),
            record.get("ownership_rate"),
            criteria,
        ):
            continue
        pop = record.get("population")
        if not pop or pop <= 0:
            continue
        lat, lng = centroid
        if polygon.contains(Point(lng, lat)):
            total += pop
    return total


# ---------------------------------------------------------------------------
# Helpers + orchestrators (do I/O — bbox filter + per-county bulk fetch)
# ---------------------------------------------------------------------------


def _tracts_in_bbox(
    min_lng: float, min_lat: float, max_lng: float, max_lat: float
) -> Dict[str, Tuple[float, float]]:
    """{geoid → (lat, lng)} for tracts whose centroid falls in bbox."""
    gazetteer = _load_gazetteer()
    out: Dict[str, Tuple[float, float]] = {}
    for geoid, (lat, lng) in gazetteer.items():
        if min_lat <= lat <= max_lat and min_lng <= lng <= max_lng:
            out[geoid] = (lat, lng)
    return out


def _bulk_populations(geoids: Iterable[str]) -> Dict[str, int]:
    """{geoid → pop} via tract_population (3-step fallback in census_tracts)."""
    out: Dict[str, int] = {}
    for geoid in geoids:
        pop = tract_population(geoid)
        if pop is None:
            continue
        out[geoid] = pop
    return out


def _bulk_demographics(geoids: Iterable[str]) -> Dict[str, Dict[str, Any]]:
    """{geoid → demographics record} via tract_demographics."""
    out: Dict[str, Dict[str, Any]] = {}
    for geoid in geoids:
        record = tract_demographics(geoid)
        if record is None:
            continue
        out[geoid] = record
    return out


def compute_catchment_population(polygon: Polygon) -> int:
    """End-to-end total catchment: bbox-filter, bulk-fetch pops, sum inside."""
    min_lng, min_lat, max_lng, max_lat = polygon.bounds
    centroids = _tracts_in_bbox(min_lng, min_lat, max_lng, max_lat)
    populations = _bulk_populations(centroids.keys())
    return catchment_population(polygon, centroids, populations)


def compute_affluent_catchment_population(
    polygon: Polygon,
    criteria: AffluentCriteria = DEFAULT_AFFLUENT,
) -> int:
    """End-to-end affluent catchment: bbox-filter tracts, bulk-fetch full
    demographics, apply tract-level filter + sum population for survivors
    inside polygon."""
    min_lng, min_lat, max_lng, max_lat = polygon.bounds
    centroids = _tracts_in_bbox(min_lng, min_lat, max_lng, max_lat)
    demos = _bulk_demographics(centroids.keys())
    return affluent_catchment_population(polygon, centroids, demos, criteria)
