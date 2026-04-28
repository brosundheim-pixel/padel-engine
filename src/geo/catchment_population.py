"""Sum tract populations whose centroids fall inside a polygon.

Pure function `catchment_population(polygon, tract_centroids, tract_populations)`
is the canonical scoring primitive — drop the same call into demand-signal
aggregation (per-capita densities, club counts) once those signals exist.

`compute_catchment_population(polygon)` is the convenience orchestrator: it
filters the national tract gazetteer to the polygon's bounding box, bulk-
fetches tract populations for the (state, county) pairs that survive the bbox
filter, then calls the pure function. Avoids touching all 85K US tracts per
call and avoids fetching ACS data for counties the polygon doesn't intersect.
"""

from __future__ import annotations

from typing import Dict, Iterable, Tuple

from shapely.geometry import Point, Polygon

from src.data.census_tracts import (
    _load_gazetteer,
    tract_population,
)


def catchment_population(
    polygon: Polygon,
    tract_centroids: Dict[str, Tuple[float, float]],
    tract_populations: Dict[str, int],
) -> int:
    """Sum populations of tracts whose centroid lies inside polygon.

    Pure: no I/O. Caller supplies the candidate tract set + their
    populations. Tracts in `tract_centroids` without an entry in
    `tract_populations` are skipped (treated as unknown population, not zero).
    """
    total = 0
    for geoid, centroid in tract_centroids.items():
        pop = tract_populations.get(geoid)
        if pop is None:
            continue
        lat, lng = centroid
        if polygon.contains(Point(lng, lat)):
            total += pop
    return total


def _tracts_in_bbox(
    min_lng: float, min_lat: float, max_lng: float, max_lat: float
) -> Dict[str, Tuple[float, float]]:
    """Return {geoid -> (lat, lng)} for tracts whose centroid falls in bbox."""
    gazetteer = _load_gazetteer()
    out: Dict[str, Tuple[float, float]] = {}
    for geoid, (lat, lng) in gazetteer.items():
        if min_lat <= lat <= max_lat and min_lng <= lng <= max_lng:
            out[geoid] = (lat, lng)
    return out


def _bulk_populations(geoids: Iterable[str]) -> Dict[str, int]:
    """Return {geoid -> pop} via tract_population (which bulk-caches per county)."""
    out: Dict[str, int] = {}
    for geoid in geoids:
        pop = tract_population(geoid)
        if pop is None:
            continue
        out[geoid] = pop
    return out


def compute_catchment_population(polygon: Polygon) -> int:
    """End-to-end: bbox-filter tracts, bulk-fetch pops, sum inside polygon."""
    min_lng, min_lat, max_lng, max_lat = polygon.bounds
    centroids = _tracts_in_bbox(min_lng, min_lat, max_lng, max_lat)
    populations = _bulk_populations(centroids.keys())
    return catchment_population(polygon, centroids, populations)
