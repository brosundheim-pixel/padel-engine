"""Compute total + affluent catchment for every anchor at 7-min and 15-min radii.

Reuses cached isochrone polygons (data/raw/isochrones/) and tract data
(gazetteer + per-county ACS demographics). No new OSM/Overpass calls.
Census ACS calls only for counties not yet bulk-fetched into the new
demographics cache.

Two aggregations per anchor per radius:
  - total: every tract whose centroid falls inside the polygon
  - affluent: same set, filtered by tract-level affluent gate (income +
    age 25-49 + ownership) per METHODOLOGY.md "Affluent-demand-only catchment"

Outputs:
  - data/calibration/anchors.csv: 4 columns (renames + 2 new)
      total_catchment_pop_7min  (was catchment_pop_7min)
      total_catchment_pop_15min (was catchment_pop_15min)
      affluent_catchment_pop_7min  (new)
      affluent_catchment_pop_15min (new)
  - data/outputs/anchor_catchment_pop.md: total + affluent + ratio table
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.geo.catchment_population import (
    compute_affluent_catchment_population,
    compute_catchment_population,
)
from src.geo.geocoding import pop_weighted_centroid, zip_to_centroid
from src.geo.isochrones import get_isochrone

ANCHORS_CSV = REPO_ROOT / "data" / "calibration" / "anchors.csv"
OUTPUT_MD = REPO_ROOT / "data" / "outputs" / "anchor_catchment_pop.md"

DRIVE_RADII = [7, 15]

# Column rename map: old → new
RENAMED_COLUMNS = {
    "catchment_pop_7min": "total_catchment_pop_7min",
    "catchment_pop_15min": "total_catchment_pop_15min",
}
NEW_COLUMNS = [
    "total_catchment_pop_7min",
    "total_catchment_pop_15min",
    "affluent_catchment_pop_7min",
    "affluent_catchment_pop_15min",
]


def origin_for(zip_code: str) -> Optional[Tuple[float, float]]:
    """Pop-weighted centroid (preferred) or geo centroid fallback."""
    pop = pop_weighted_centroid(zip_code)
    if pop is not None:
        return pop
    return zip_to_centroid(zip_code)


def migrate_columns(rows: List[Dict[str, str]], fieldnames: List[str]) -> List[str]:
    """Rename old column names in each row and return the new schema list.

    Old `catchment_pop_*` values are copied to `total_catchment_pop_*` and
    the old keys removed. The 2 new affluent columns are appended; values
    are filled in by the main loop.
    """
    new_fields: List[str] = []
    for col in fieldnames:
        if col in RENAMED_COLUMNS:
            new_fields.append(RENAMED_COLUMNS[col])
        else:
            new_fields.append(col)
    for col in NEW_COLUMNS:
        if col not in new_fields:
            new_fields.append(col)

    for row in rows:
        for old, new in RENAMED_COLUMNS.items():
            if old in row:
                row[new] = row.pop(old)
        for col in NEW_COLUMNS:
            row.setdefault(col, "")
    return new_fields


def main() -> int:
    with ANCHORS_CSV.open() as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    out_fields = migrate_columns(rows, fieldnames)
    summary: List[Dict[str, str]] = []

    for row in rows:
        zip_code = row["zip"].strip()
        location_id = row["location_id"].strip()
        label = row["ground_truth_label"].strip()

        print(f"\n=== {location_id} (zip {zip_code}, {label}) ===")

        origin = origin_for(zip_code)
        if origin is None:
            print(f"  ERROR: no origin centroid for {zip_code}; skipping")
            continue
        lat, lng = origin

        totals: Dict[int, int] = {}
        affluents: Dict[int, int] = {}
        for minutes in DRIVE_RADII:
            polygon = get_isochrone(lat, lng, minutes)
            total = compute_catchment_population(polygon)
            affluent = compute_affluent_catchment_population(polygon)
            totals[minutes] = total
            affluents[minutes] = affluent
            ratio = (affluent / total) if total > 0 else 0.0
            print(
                f"  {minutes}-min: total={total:,}  affluent={affluent:,}  "
                f"affluent/total={ratio:.2%}"
            )

        row["total_catchment_pop_7min"] = str(totals[7])
        row["total_catchment_pop_15min"] = str(totals[15])
        row["affluent_catchment_pop_7min"] = str(affluents[7])
        row["affluent_catchment_pop_15min"] = str(affluents[15])

        ratio15 = (affluents[15] / totals[15]) if totals[15] > 0 else 0.0
        summary.append({
            "location_id": location_id,
            "zip": zip_code,
            "label": label,
            "total_7": f"{totals[7]:,}",
            "total_15": f"{totals[15]:,}",
            "affluent_7": f"{affluents[7]:,}",
            "affluent_15": f"{affluents[15]:,}",
            "ratio_15": f"{ratio15:.1%}",
        })

    with ANCHORS_CSV.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=out_fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nUpdated {ANCHORS_CSV}")

    OUTPUT_MD.parent.mkdir(parents=True, exist_ok=True)
    md: List[str] = []
    md.append("# Anchor catchment population — total + affluent\n\n")
    md.append(
        "**Total catchment** = sum of population across Census tracts whose "
        "centroid (Census 2023 Gazetteer internal point) falls inside the "
        "drive-time isochrone polygon.\n\n"
    )
    md.append(
        "**Affluent catchment** = same set, filtered by tract-level affluent "
        "gate (median household income ≥ $100K AND pct_age_25_49 ≥ 25% AND "
        "ownership rate ≥ 50%). Per METHODOLOGY.md \"Affluent-demand-only "
        "catchment\" — this is the v0-canonical demand signal feeding "
        "scoring; total is reported only for visibility.\n\n"
    )
    md.append(
        "**affluent/total ratio** = how much of the total catchment passes "
        "the tract-level affluent filter. High ratio = surroundings are "
        "uniformly affluent. Low ratio = isochrone sweeps through mixed-"
        "density geography.\n\n"
    )
    md.append("## Per-anchor table\n\n")
    md.append(
        "| location_id | zip | label | total 7-min | total 15-min | "
        "affluent 7-min | affluent 15-min | affluent/total 15-min |\n"
        "|---|---|---|---|---|---|---|---|\n"
    )
    for r in summary:
        md.append(
            f"| {r['location_id']} | {r['zip']} | {r['label']} | "
            f"{r['total_7']} | {r['total_15']} | "
            f"{r['affluent_7']} | {r['affluent_15']} | "
            f"{r['ratio_15']} |\n"
        )

    OUTPUT_MD.write_text("".join(md))
    print(f"Wrote summary to {OUTPUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
