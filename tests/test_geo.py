"""End-to-end test: zip → centroid → isochrone → zip membership.

Hits live zippopotam.us and OpenStreetMap on first run. Subsequent runs
hit the on-disk cache. Marked with no special skip — anchor zip 75033 is
load-bearing for Phase 0 calibration so the test should always run.
"""

from __future__ import annotations

import sys
from pathlib import Path

import geopandas as gpd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.geo.geocoding import zip_to_centroid
from src.geo.isochrones import get_isochrone, zips_in_isochrone


def test_ntrc_frisco_15min_isochrone():
    centroid = zip_to_centroid("75033")
    assert centroid is not None, "zippopotam.us lookup for 75033 failed"
    lat, lng = centroid

    # Frisco TX rough bounds — sanity check geocoder didn't return wrong city
    assert 32.9 < lat < 33.4, f"lat {lat} outside Frisco TX bounds"
    assert -97.1 < lng < -96.5, f"lng {lng} outside Frisco TX bounds"

    polygon = get_isochrone(lat, lng, 15)
    assert polygon is not None
    assert not polygon.is_empty
    assert polygon.is_valid

    # Project to UTM 14N (covers most of Texas) for accurate area in km²
    area_km2 = (
        gpd.GeoSeries([polygon], crs="EPSG:4326")
        .to_crs(epsg=32614)
        .area.iloc[0]
        / 1_000_000
    )
    # Wide ceiling reflects v0 convex-hull overestimate (1.5-2.5x true
    # reachable area). Empirical Frisco 15-min hull ≈ 830 km². Tighten
    # once isochrone construction swaps to alpha-shape.
    assert (
        50 <= area_km2 <= 1500
    ), f"15-min isochrone area {area_km2:.1f} km² outside [50, 1500] band"

    # Zip-membership check: caller supplies the candidate universe
    candidates = [
        "75033",  # self — must be inside
        "75034",  # NTRC adjacent — likely inside
        "75035",  # NTRC adjacent — likely inside
        "75070",  # McKinney — borderline, may or may not be inside
        "75205",  # Highland Park, ~30 mi south — must be outside
    ]
    inside = zips_in_isochrone(polygon, candidates)

    assert "75033" in inside, "self zip should be inside its own isochrone"
    assert (
        "75034" in inside or "75035" in inside
    ), "at least one neighboring NTRC zip should fall inside 15-min ring"
    assert (
        "75205" not in inside
    ), "Highland Park is ~30 mi south of Frisco — must be outside 15-min ring"
