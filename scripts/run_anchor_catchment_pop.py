"""Compute 7-min and 15-min catchment population for every anchor.

Reuses already-cached isochrone polygons (data/raw/isochrones/) and tract
data (gazetteer + per-county ACS pops). No new OSM/Overpass calls; minimal
new ACS calls only when an isochrone bbox covers a county we haven't
fetched yet.

Outputs:
  - data/calibration/anchors.csv: adds catchment_pop_7min, catchment_pop_15min
  - data/outputs/anchor_catchment_pop.md: summary table + ratio analysis
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.geo.catchment_population import compute_catchment_population
from src.geo.geocoding import pop_weighted_centroid, zip_to_centroid
from src.geo.isochrones import get_isochrone

ANCHORS_CSV = REPO_ROOT / "data" / "calibration" / "anchors.csv"
OUTPUT_MD = REPO_ROOT / "data" / "outputs" / "anchor_catchment_pop.md"

DRIVE_RADII = [7, 15]
NEW_COLUMNS = ["catchment_pop_7min", "catchment_pop_15min"]


def origin_for(zip_code: str) -> Optional[Tuple[float, float]]:
    """Pop-weighted centroid (preferred) or geo centroid fallback."""
    pop = pop_weighted_centroid(zip_code)
    if pop is not None:
        return pop
    return zip_to_centroid(zip_code)


def main() -> int:
    with ANCHORS_CSV.open() as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    out_fields = list(fieldnames)
    for col in NEW_COLUMNS:
        if col not in out_fields:
            out_fields.append(col)

    summary: List[Dict[str, str]] = []

    for row in rows:
        zip_code = row["zip"].strip()
        location_id = row["location_id"].strip()
        label = row["ground_truth_label"].strip()
        zip_pop_str = row.get("total_population", "").strip()
        zip_pop = int(zip_pop_str) if zip_pop_str else 0

        print(f"\n=== {location_id} (zip {zip_code}, {label}) ===")

        origin = origin_for(zip_code)
        if origin is None:
            print(f"  ERROR: no origin centroid for {zip_code}; skipping")
            continue
        lat, lng = origin

        catchments: Dict[int, int] = {}
        for minutes in DRIVE_RADII:
            polygon = get_isochrone(lat, lng, minutes)
            pop = compute_catchment_population(polygon)
            catchments[minutes] = pop
            print(f"  {minutes}-min catchment population: {pop:,}")

        row["catchment_pop_7min"] = str(catchments[7])
        row["catchment_pop_15min"] = str(catchments[15])

        ratio = (catchments[15] / zip_pop) if zip_pop > 0 else 0.0
        summary.append({
            "location_id": location_id,
            "zip": zip_code,
            "label": label,
            "zip_pop": f"{zip_pop:,}",
            "catchment_7min": f"{catchments[7]:,}",
            "catchment_15min": f"{catchments[15]:,}",
            "ratio_15min_over_zip": f"{ratio:.2f}x" if zip_pop > 0 else "n/a",
        })

    with ANCHORS_CSV.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=out_fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nUpdated {ANCHORS_CSV}")

    OUTPUT_MD.parent.mkdir(parents=True, exist_ok=True)
    md: List[str] = []
    md.append("# Anchor catchment population\n\n")
    md.append(
        "Population summed across Census tracts whose centroid (Census 2023 "
        "Gazetteer internal point) falls inside the anchor's drive-time "
        "isochrone. Tract pop from ACS 2023 5-year B01003_001E. Isochrone "
        "origin = pop-weighted ZCTA centroid.\n\n"
    )
    md.append("## Per-anchor table\n\n")
    md.append(
        "| location_id | zip | label | zip pop | 7-min catchment | "
        "15-min catchment | 15-min / zip pop |\n"
        "|---|---|---|---|---|---|---|\n"
    )
    for r in summary:
        md.append(
            f"| {r['location_id']} | {r['zip']} | {r['label']} | "
            f"{r['zip_pop']} | {r['catchment_7min']} | "
            f"{r['catchment_15min']} | {r['ratio_15min_over_zip']} |\n"
        )

    OUTPUT_MD.write_text("".join(md))
    print(f"Wrote summary to {OUTPUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
