"""Phase 0 anchor catchment pipeline.

For every anchor in data/calibration/anchors.csv:
  1. Compute pop-weighted ZCTA centroid (origin for isochrones)
  2. Compute 7-min and 15-min drive-time isochrones from pop centroid
  3. Pop-weighted zip-membership scan of metro-specific candidate universe
  4. Compare geo vs pop centroid (distance — flags meaningful displacement)

Output: data/outputs/anchor_isochrones.md

Per CLAUDE.md dual-radius scoring: report both 7-min and 15-min so the
operator can pick strategy per candidate. Pop-centroid origin reflects
where members actually live, not where the polygon happens to center.
"""

from __future__ import annotations

import csv
import math
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import geopandas as gpd

from src.geo.geocoding import pop_weighted_centroid, zip_to_centroid
from src.geo.isochrones import get_isochrone, zips_in_isochrone

ANCHORS_CSV = REPO_ROOT / "data" / "calibration" / "anchors.csv"
OUTPUT_MD = REPO_ROOT / "data" / "outputs" / "anchor_isochrones.md"

# Per-metro candidate zip universes for membership testing.
# Each universe is a list of zips reasonably within ~30km of the anchor.
# Anchor's own zip is always included.
CANDIDATE_ZIPS: Dict[str, List[str]] = {
    # DFW — Frisco anchor + adjacent suburbs. Highland Park (75205) and
    # Tarrant zips (76092, 76034) included as negative controls.
    "DFW": [
        "75033", "75034", "75035",
        "75024", "75025", "75093",
        "75070", "75071",
        "75056", "75057",
        "75002",
        "75205",
        "76092", "76034",
    ],
    # Nashville — Sensa Germantown + urban/suburban neighbors
    "Nashville": [
        "37208", "37203", "37206", "37210", "37212", "37215",
        "37027", "37205", "37067",
    ],
    # Rural Alabama — Roanoke + sparse adjacent
    "Rural_Alabama": [
        "36272", "36278", "36273", "36276",
    ],
    # South Florida — Miami Beach + adjacent
    "South_Florida": [
        "33139", "33140", "33141", "33154", "33109",
        "33129", "33131", "33132", "33134",
    ],
    # Atlanta_Outer — Winder + neighbors + Athens + Lawrenceville
    "Atlanta_Outer": [
        "30680", "30620", "30519", "30024", "30043", "30605",
    ],
    # NYC — Brooklyn Heights + Brooklyn/Manhattan neighbors
    "NYC": [
        "11201", "11215", "11217", "11231", "11211", "11205",
        "10004", "10038", "10002",
    ],
}

DRIVE_RADII = [7, 15]
DISPLACEMENT_FLAG_KM = 2.0
# Polite delay between fresh OSM fetches so Overpass doesn't throttle.
OVERPASS_INTER_REQUEST_PAUSE_S = 5


def haversine_km(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    """Great-circle distance between two (lat, lng) points, in km."""
    lat1, lng1 = a
    lat2, lng2 = b
    r = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmbd = math.radians(lng2 - lng1)
    h = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmbd / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def utm_epsg_for(lat: float, lng: float) -> int:
    """UTM zone EPSG for accurate area in km² (northern hemisphere only)."""
    zone = int((lng + 180) // 6) + 1
    return 32600 + zone  # northern hemisphere; all anchors are in US


def polygon_area_km2(polygon, lat: float, lng: float) -> float:
    epsg = utm_epsg_for(lat, lng)
    return (
        gpd.GeoSeries([polygon], crs="EPSG:4326")
        .to_crs(epsg=epsg)
        .area.iloc[0]
        / 1_000_000
    )


def pop_centroid_with_fallback(zip_code: str) -> Tuple[Optional[Tuple[float, float]], str]:
    """Return (centroid, source) where source is 'pop', 'geo', or 'none'."""
    pop = pop_weighted_centroid(zip_code)
    if pop is not None:
        return pop, "pop"
    geo = zip_to_centroid(zip_code)
    if geo is not None:
        return geo, "geo"
    return None, "none"


def membership_by_pop_centroid(polygon, candidate_zips: List[str]) -> List[str]:
    """Like zips_in_isochrone but tests pop-weighted centroids when available."""
    from shapely.geometry import Point

    inside: List[str] = []
    for zip_code in candidate_zips:
        centroid, _ = pop_centroid_with_fallback(zip_code)
        if centroid is None:
            continue
        lat, lng = centroid
        if polygon.contains(Point(lng, lat)):
            inside.append(zip_code)
    return inside


def main() -> int:
    with ANCHORS_CSV.open() as f:
        anchors = list(csv.DictReader(f))

    summary_rows: List[Dict[str, str]] = []
    detail_blocks: List[str] = []

    for anchor in anchors:
        zip_code = anchor["zip"].strip()
        metro = anchor["metro"].strip()
        label = anchor["ground_truth_label"].strip()
        location_id = anchor["location_id"].strip()

        print(f"\n=== {location_id} (zip {zip_code}, {metro}, {label}) ===")

        geo = zip_to_centroid(zip_code)
        pop = pop_weighted_centroid(zip_code)

        if geo is None:
            print(f"  ERROR: no geo centroid for {zip_code}")
            continue

        origin = pop if pop is not None else geo
        origin_source = "pop" if pop is not None else "geo (fallback)"
        displacement_km = haversine_km(geo, pop) if pop is not None else 0.0
        flag = " ⚠ MEANINGFUL DISPLACEMENT" if displacement_km > DISPLACEMENT_FLAG_KM else ""

        print(f"  geo centroid: {geo}")
        print(f"  pop centroid: {pop}")
        print(f"  displacement: {displacement_km:.2f} km{flag}")
        print(f"  isochrone origin: {origin_source} → {origin}")

        candidate_zips = CANDIDATE_ZIPS.get(metro, [zip_code])

        per_radius: Dict[int, Dict] = {}
        for minutes in DRIVE_RADII:
            print(f"  building {minutes}-min isochrone...")
            t0 = time.time()
            polygon = get_isochrone(origin[0], origin[1], minutes)
            elapsed = time.time() - t0
            # Pause only when this was a fresh fetch (not cache-hit).
            if elapsed > 1.0:
                time.sleep(OVERPASS_INTER_REQUEST_PAUSE_S)
            area = polygon_area_km2(polygon, origin[0], origin[1])
            inside = membership_by_pop_centroid(polygon, candidate_zips)
            per_radius[minutes] = {
                "area_km2": area,
                "inside_zips": inside,
                "elapsed": elapsed,
            }
            print(f"    area {area:.1f} km², {len(inside)} zips inside ({elapsed:.1f}s)")

        summary_rows.append({
            "location_id": location_id,
            "zip": zip_code,
            "metro": metro,
            "label": label,
            "geo_centroid": f"{geo[0]:.4f}, {geo[1]:.4f}",
            "pop_centroid": f"{pop[0]:.4f}, {pop[1]:.4f}" if pop else "—",
            "displacement_km": f"{displacement_km:.2f}" if pop else "n/a",
            "displacement_flag": "⚠" if displacement_km > DISPLACEMENT_FLAG_KM else "",
            "area_7min_km2": f"{per_radius[7]['area_km2']:.1f}",
            "area_15min_km2": f"{per_radius[15]['area_km2']:.1f}",
            "inside_7min": str(len(per_radius[7]["inside_zips"])),
            "inside_15min": str(len(per_radius[15]["inside_zips"])),
        })

        detail_blocks.append(
            f"### {location_id} — {anchor['name']} ({zip_code}, {label})\n\n"
            f"- Metro: `{metro}`\n"
            f"- Geo centroid: `{geo[0]:.4f}, {geo[1]:.4f}`\n"
            f"- Pop-weighted centroid: `{pop[0]:.4f}, {pop[1]:.4f}`"
            + (f" — **displacement {displacement_km:.2f} km ⚠ meaningful**" if displacement_km > DISPLACEMENT_FLAG_KM
               else f" (displacement {displacement_km:.2f} km)" if pop else "")
            + "\n"
            f"- 7-min isochrone: **{per_radius[7]['area_km2']:.1f} km²**, "
            f"zips inside: `{per_radius[7]['inside_zips']}`\n"
            f"- 15-min isochrone: **{per_radius[15]['area_km2']:.1f} km²**, "
            f"zips inside: `{per_radius[15]['inside_zips']}`\n"
        )

    OUTPUT_MD.parent.mkdir(parents=True, exist_ok=True)
    md_lines: List[str] = []
    md_lines.append("# Anchor catchment summary\n")
    md_lines.append(
        "Dual-radius (7-min + 15-min) drive-time isochrones from "
        "population-weighted ZCTA centroids per CLAUDE.md. Zip-membership "
        "tested against per-metro candidate universes using pop centroids "
        "for both origin and membership probes.\n"
    )
    md_lines.append("Methodology notes:\n")
    md_lines.append(
        "- Isochrone polygon = convex hull of OSM nodes reachable within "
        "drive-time budget. Overestimates true reachable area by 1.5-2.5x. "
        "Phase 2 should swap to alpha-shape.\n"
    )
    md_lines.append(
        "- Pop centroid = sum(tract_centroid × tract_population) / sum(tract_population) "
        "across tracts overlapping the ZCTA on land. Tract centroids from Census 2023 "
        "Gazetteer (which is itself pop-weighted internal point per tract). Tract "
        "population from ACS 2023 5-year B01003_001E.\n"
    )
    md_lines.append(
        f"- Displacement > {DISPLACEMENT_FLAG_KM} km between geo and pop centroid is "
        "flagged as **meaningful** — material difference between polygon center and "
        "where people actually live.\n"
    )

    md_lines.append("\n## Summary table\n")
    md_lines.append(
        "| location_id | zip | metro | label | geo centroid | pop centroid | "
        "Δ km | 7-min km² | 15-min km² | inside 7 | inside 15 |\n"
        "|---|---|---|---|---|---|---|---|---|---|---|\n"
    )
    for r in summary_rows:
        md_lines.append(
            f"| {r['location_id']} | {r['zip']} | {r['metro']} | {r['label']} | "
            f"{r['geo_centroid']} | {r['pop_centroid']} | "
            f"{r['displacement_km']}{r['displacement_flag']} | "
            f"{r['area_7min_km2']} | {r['area_15min_km2']} | "
            f"{r['inside_7min']} | {r['inside_15min']} |\n"
        )

    md_lines.append("\n## Per-anchor detail\n\n")
    md_lines.extend(detail_blocks)

    OUTPUT_MD.write_text("".join(md_lines))
    print(f"\nWrote summary to {OUTPUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
