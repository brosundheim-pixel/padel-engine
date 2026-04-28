"""Drive-time isochrones via OSMnx + OpenStreetMap road network.

Per CLAUDE.md dual-radius scoring: every candidate is evaluated at both
7-min and 15-min drive isochrones. Isochrones are expensive (network
fetch + graph build + ego_graph traversal), so all results cache to disk
as GeoJSON in data/raw/isochrones/.

V0 polygon construction: convex hull of reachable graph nodes. Empirically
overestimates the true reachable area by 1.5-2.5x — a 15-min isochrone in
DFW returns ~830 km² hull vs ~300-400 km² true reachable area, because the
hull bridges the gaps between highway spokes. Adequate for the catchment
aggregations Phase 0 needs (population sums, club counts at zip resolution
where boundary zips that fall inside the hull but outside true reachable
area are an acceptable false-positive). Phase 2 should swap to alpha-shape
or a buffer-union of reachable nodes once boundary accuracy starts driving
spurious BUILD/PASS calls.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

import networkx as nx
import osmnx as ox
import requests.exceptions
from osmnx._errors import ResponseStatusCodeError
from shapely.geometry import MultiPoint, Point, Polygon, mapping, shape

from src.geo.geocoding import zip_to_centroid

# Cap Overpass requests so a stalled mirror fails fast instead of hanging.
ox.settings.requests_timeout = 90

# Overpass endpoints to try in order. osmnx appends "/interpreter" internally
# so values must NOT include that suffix. kumi.systems was tried but
# repeatedly 502'd and connection-reset on the capacity-check ping, which
# triggers an osmnx 1.9.4 recursion bug. Sticking to overpass-api.de + lz4.
OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api",
    "https://lz4.overpass-api.de/api",
]
ox.settings.overpass_endpoint = OVERPASS_ENDPOINTS[0]

REPO_ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = REPO_ROOT / "data" / "raw" / "isochrones"

# Road-network fetch radius per drive-minute. Sized for ~90 km/h sustained
# (highway-arterial mix). Empirically: 30 km/min fetch wedges Overpass for
# >5 min in DFW suburbs; 22.5 km radius (1500 m/min × 15) fetches in ~30s.
# Trade-off: under-sizing truncates true reachable area on highway stretches.
NETWORK_RADIUS_M_PER_MIN = 1500

# Default speed (km/h) applied to OSM edges missing maxspeed tags.
# osmnx.add_edge_speeds applies this when fallback is needed.
DEFAULT_HIGHWAY_SPEED_KPH = 50


def _cache_filename(lat: float, lng: float, minutes: int) -> str:
    """Filename-safe cache key. Negatives become 'n', dots become '_'."""
    lat_s = f"{lat:.4f}".replace("-", "n").replace(".", "_")
    lng_s = f"{lng:.4f}".replace("-", "n").replace(".", "_")
    return f"{lat_s}_{lng_s}_{minutes}min.geojson"


def _cache_path(lat: float, lng: float, minutes: int) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / _cache_filename(lat, lng, minutes)


def _load_cached(path: Path) -> Optional[Polygon]:
    if not path.exists():
        return None
    feature = json.loads(path.read_text())
    geom = shape(feature["geometry"])
    return geom if isinstance(geom, Polygon) else None


def _save_cached(path: Path, polygon: Polygon, lat: float, lng: float, minutes: int) -> None:
    feature = {
        "type": "Feature",
        "properties": {
            "origin_lat": lat,
            "origin_lng": lng,
            "drive_minutes": minutes,
            "construction": "convex_hull_of_reachable_nodes",
        },
        "geometry": mapping(polygon),
    }
    path.write_text(json.dumps(feature, indent=2))


def _fetch_graph_with_failover(lat: float, lng: float, radius_m: int):
    """ox.graph_from_point with endpoint failover. Tries each Overpass
    mirror in turn on 5xx, JSON-decode failures, connection timeouts,
    and other network errors."""
    # UnboundLocalError + RecursionError catch an osmnx 1.9.4 bug where a
    # ConnectionError on the server-capacity ping triggers infinite recursion
    # in _get_overpass_pause and finally raises UnboundLocalError.
    retryable = (
        ResponseStatusCodeError,
        ValueError,
        requests.exceptions.ConnectionError,
        requests.exceptions.Timeout,
        requests.exceptions.ChunkedEncodingError,
        UnboundLocalError,
        RecursionError,
    )
    last_err: Optional[Exception] = None
    for endpoint in OVERPASS_ENDPOINTS:
        ox.settings.overpass_endpoint = endpoint
        try:
            return ox.graph_from_point(
                (lat, lng), dist=radius_m, network_type="drive"
            )
        except retryable as e:
            last_err = e
            print(f"  overpass {endpoint} failed ({type(e).__name__}); failing over...")
            continue
    raise RuntimeError(
        f"All Overpass endpoints failed for ({lat}, {lng}, {radius_m}m): {last_err}"
    )


def _build_isochrone(lat: float, lng: float, minutes: int) -> Polygon:
    """Compute isochrone via OSMnx ego_graph at travel-time radius."""
    radius_m = max(2000, minutes * NETWORK_RADIUS_M_PER_MIN)
    G = _fetch_graph_with_failover(lat, lng, radius_m)
    G = ox.add_edge_speeds(G, fallback=DEFAULT_HIGHWAY_SPEED_KPH)
    G = ox.add_edge_travel_times(G)

    center_node = ox.distance.nearest_nodes(G, lng, lat)
    travel_time_seconds = minutes * 60

    subgraph = nx.ego_graph(
        G, center_node, radius=travel_time_seconds, distance="travel_time"
    )

    points = [(data["x"], data["y"]) for _, data in subgraph.nodes(data=True)]
    if len(points) < 3:
        raise ValueError(
            f"Isochrone has only {len(points)} reachable nodes — too few for polygon"
        )

    hull = MultiPoint(points).convex_hull
    if not isinstance(hull, Polygon):
        raise ValueError(f"Convex hull collapsed to {hull.geom_type}, not Polygon")
    return hull


def get_isochrone(lat: float, lng: float, drive_minutes: int) -> Polygon:
    """Return drive-time isochrone polygon around (lat, lng).

    Cached to data/raw/isochrones/{lat}_{lng}_{minutes}min.geojson. First
    call for a given key fetches OSM network and computes; subsequent calls
    load from disk.
    """
    path = _cache_path(lat, lng, drive_minutes)
    cached = _load_cached(path)
    if cached is not None:
        return cached
    polygon = _build_isochrone(lat, lng, drive_minutes)
    _save_cached(path, polygon, lat, lng, drive_minutes)
    return polygon


def zips_in_isochrone(polygon: Polygon, candidate_zips: List[str]) -> List[str]:
    """Subset of candidate_zips whose centroid falls inside polygon.

    Caller supplies the candidate universe (anchors + scored candidates,
    typically). Avoids scanning all ~33K US ZCTAs every call.
    """
    inside: List[str] = []
    for zip_code in candidate_zips:
        centroid = zip_to_centroid(zip_code)
        if centroid is None:
            continue
        lat, lng = centroid
        # shapely uses (x=lng, y=lat) ordering
        if polygon.contains(Point(lng, lat)):
            inside.append(zip_code)
    return inside
