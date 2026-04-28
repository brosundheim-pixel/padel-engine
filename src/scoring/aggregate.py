"""Composite demand score + supply-overlap math + final composite score.

Three-step composition:

  1. composite_demand_score(densities) — linear weighted sum of
     per-1K-affluent demand signals. v0_hypothesis weights:
       tennis 0.5, boutique 0.3, golf 0.2

  2. supply_overlap_uncaptured_demand(...) — v0-canonical supply math.
     Polygon intersection of candidate's 15-min isochrone with the union
     of competitors' 15-min isochrones; sum affluent population in the
     uncaptured residual.

  3. composite_score(demand, uncaptured, total_affluent) — multiplicative
     formulation: demand × (uncaptured / total). Zero uncaptured produces
     zero score regardless of demand strength (saturated supply = no
     opportunity). v0_hypothesis. Alternatives (additive penalty,
     threshold gate, log decay) flagged for v1 if anchor calibration
     shows multiplicative is too aggressive or too weak.
"""

from __future__ import annotations

from typing import List

from shapely.geometry import Polygon
from shapely.ops import unary_union

from src.geo.catchment_population import (
    AffluentCriteria,
    DEFAULT_AFFLUENT,
    affluent_catchment_population,
)
from src.data.census_tracts import _load_gazetteer, tract_demographics


# v0_hypothesis demand weights — operator-set per CLAUDE.md "Hypothesized
# strong/supporting/weak signals". Tennis is highest-conviction racket-sport
# conversion proxy; boutique fitness is general premium-recurring-spend
# signal; golf is lifestyle-affluence signal but most distant from
# racket-sport demand. Tunable from anchor calibration.
DEMAND_WEIGHTS = {
    "tennis": 0.5,
    "boutique": 0.3,
    "golf": 0.2,
}


def composite_demand_score(
    tennis_density: float,
    boutique_density: float,
    golf_density: float,
) -> float:
    """Linear weighted sum of per-1K-affluent demand densities."""
    return (
        DEMAND_WEIGHTS["tennis"] * tennis_density
        + DEMAND_WEIGHTS["boutique"] * boutique_density
        + DEMAND_WEIGHTS["golf"] * golf_density
    )


# COMPETITOR UNIVERSE NOTE: Competitor padel facilities are enumerated from the cached
# Google Places search results, which were fetched at 15km radius from each anchor. The
# real bound on competitor enumeration is therefore the 15km Google Places search radius,
# not any haversine cap in this code. Competitors beyond 15km from an anchor are not in
# the cached data and would not appear in the supply-overlap math.
#
# v1 limitation: cross-metro candidates may need wider Places search radius. Example: an
# NJ candidate near the Hudson should capture Manhattan padel supply within drive-time
# even though Manhattan facilities are >15km haversine. v0 ignores this; v1 should re-fetch
# Places at 25-30km for candidates near dense metro borders.
def supply_overlap_uncaptured_demand(
    candidate_polygon: Polygon,
    candidate_affluent_catchment: int,
    competitor_polygons: List[Polygon],
    criteria: AffluentCriteria = DEFAULT_AFFLUENT,
) -> int:
    """Affluent population in candidate's catchment NOT served by competitors.

    v0-canonical supply math (METHODOLOGY.md "Supply-overlap-with-demand
    methodology"). Algorithm:
      1. Union the competitor polygons (shapely auto-dedupes overlaps).
      2. Intersect candidate polygon with that union → captured region.
      3. Sum affluent-tract population inside the captured region.
      4. Subtract from candidate's total affluent catchment.

    No competitor polygons → return full candidate_affluent_catchment
    (all demand uncaptured).

    Competitor universe (v0): cached padel facilities from each anchor's
    15km Google Places search. v1 may need wider radius for cross-metro
    candidates (e.g., NJ candidates capturing Manhattan supply); 30km
    haversine cap is a non-binding constraint at v0 since the cached
    data already limits candidate competitors to that ring.
    """
    if not competitor_polygons:
        return candidate_affluent_catchment

    competitor_union = unary_union(competitor_polygons)
    captured_region = candidate_polygon.intersection(competitor_union)
    if captured_region.is_empty:
        return candidate_affluent_catchment

    # Bbox-filter tracts inside the captured region, fetch demographics,
    # apply affluent filter, sum.
    captured_polygon = (
        captured_region if isinstance(captured_region, Polygon)
        else captured_region.buffer(0)  # MultiPolygon → unified geometry
    )
    captured_affluent = _affluent_population_in_polygon(captured_polygon, criteria)
    return max(0, candidate_affluent_catchment - captured_affluent)


def _affluent_population_in_polygon(polygon, criteria: AffluentCriteria) -> int:
    """Helper: sum affluent-tract population inside an arbitrary polygon
    (which may be a Polygon or MultiPolygon resulting from intersection)."""
    from shapely.geometry import Point  # local import; avoids top-level dep
    bbox = polygon.bounds
    if not bbox or len(bbox) != 4:
        return 0
    min_lng, min_lat, max_lng, max_lat = bbox
    gazetteer = _load_gazetteer()
    total = 0
    for geoid, (lat, lng) in gazetteer.items():
        if not (min_lat <= lat <= max_lat and min_lng <= lng <= max_lng):
            continue
        if not polygon.contains(Point(lng, lat)):
            continue
        record = tract_demographics(geoid)
        if not record:
            continue
        income = record.get("income")
        pct = record.get("pct_age_25_49")
        own = record.get("ownership_rate")
        if income is None or pct is None or own is None:
            continue
        if (income >= criteria.income_min
                and pct >= criteria.pct_age_25_49_min
                and own >= criteria.ownership_rate_min):
            total += record.get("population") or 0
    return total


def composite_score(
    demand_score: float,
    uncaptured_demand: int,
    candidate_affluent_catchment: int,
) -> float:
    """v0 multiplicative composite: demand × (uncaptured / total).

    Zero uncaptured → zero composite (market saturated, no opportunity).
    Pristine supply gap → composite ≈ demand_score.

    Returns 0.0 if catchment is zero (degenerate denominator).
    """
    if not candidate_affluent_catchment or candidate_affluent_catchment <= 0:
        return 0.0
    uncaptured_share = uncaptured_demand / candidate_affluent_catchment
    return demand_score * uncaptured_share
