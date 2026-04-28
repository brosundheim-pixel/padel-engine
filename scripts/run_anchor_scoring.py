"""Score all 11 anchors with v0 composite scoring; derive thresholds; flag
label disagreements.

Pipeline:
  1. Read anchors.csv (has affluent_catchment_15min for all 11 rows)
  2. For each anchor:
     - Pop centroid lookup
     - Cached Google Places fetch (free, instant — already cached)
     - Quality-filter demand signals
     - Per-1K-affluent densities → composite demand score
     - 15-min isochrone for candidate (cached from prior runs)
     - Competitor padel polygons (one isochrone per cached padel facility)
     - Supply-overlap uncaptured-demand math
     - Composite score (multiplicative)
  3. Derive BUILD/PASS thresholds from anchor distribution
  4. Classify; flag any label/classification disagreement
  5. Write outputs:
       - anchors.csv: composite_score_v0 column
       - data/outputs/anchor_scores.md: full per-anchor table + capture-fraction
                                         + composite-distribution analyses

No new Google Places calls (all cached). Some new OSM/Overpass calls for
competitor isochrones not previously cached — ~25-30s wall per fresh
fetch, free.
"""

from __future__ import annotations

import csv
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.data.google_places import (
    fetch_boutique_fitness,
    fetch_golf_clubs,
    fetch_padel_facilities,
    fetch_tennis_facilities,
)
from src.geo.geocoding import pop_weighted_centroid, zip_to_centroid
from src.geo.isochrones import get_isochrone
from src.scoring.aggregate import (
    composite_demand_score,
    composite_score,
    supply_overlap_uncaptured_demand,
)
from src.scoring.classify import (
    BUILD_LABELS,
    EXCLUDED_FROM_DERIVATION,
    PASS_LABELS,
    classify,
    derive_thresholds,
    label_disagreements,
)
from src.scoring.signals import (
    boutique_density_per_affluent_capita,
    drive_time_to_nearest_padel,
    golf_density_per_affluent_capita,
    quality_filter,
    tennis_density_per_affluent_capita,
)

ANCHORS_CSV = REPO_ROOT / "data" / "calibration" / "anchors.csv"
OUTPUT_MD = REPO_ROOT / "data" / "outputs" / "anchor_scores.md"

RADIUS_M = 15000


def origin_for(zip_code: str) -> Optional[Tuple[float, float]]:
    pop = pop_weighted_centroid(zip_code)
    return pop if pop is not None else zip_to_centroid(zip_code)


def score_anchor(row: Dict[str, str]) -> Dict[str, Any]:
    zip_code = row["zip"].strip()
    location_id = row["location_id"].strip()
    label = row["ground_truth_label"].strip()
    affluent_15 = int(row.get("affluent_catchment_pop_15min") or 0)

    origin = origin_for(zip_code)
    if origin is None:
        raise RuntimeError(f"No origin centroid for {location_id} ({zip_code})")
    lat, lng = origin

    # Pull cached Google Places data (instant; all anchors pre-fetched)
    tennis_raw = fetch_tennis_facilities(lat, lng, RADIUS_M)
    boutique_raw = fetch_boutique_fitness(lat, lng, RADIUS_M)
    golf_raw = fetch_golf_clubs(lat, lng, RADIUS_M)
    padel_raw = fetch_padel_facilities(lat, lng, RADIUS_M)

    tennis_q = quality_filter(tennis_raw)
    boutique_q = quality_filter(boutique_raw)
    golf_q = quality_filter(golf_raw)
    # Padel has no quality filter — supply detection should be unfiltered;
    # a low-rated competitor still serves customers.

    tennis_density = tennis_density_per_affluent_capita(len(tennis_q), affluent_15)
    boutique_density = boutique_density_per_affluent_capita(len(boutique_q), affluent_15)
    golf_density = golf_density_per_affluent_capita(len(golf_q), affluent_15)
    demand = composite_demand_score(tennis_density, boutique_density, golf_density)

    # Supply-overlap math
    candidate_iso = get_isochrone(lat, lng, 15)
    competitor_polygons = []
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
    print(f"  [{location_id}] building {len(padel_raw)} competitor isochrones...")
    for i, p in enumerate(padel_raw):
        # Skip the candidate itself if cached padel data includes own facility
        if (abs(p["lat"] - lat) < 0.005 and abs(p["lng"] - lng) < 0.005):
            continue
        try:
            poly = get_isochrone(p["lat"], p["lng"], 15)
            competitor_polygons.append(poly)
        except Exception as e:
            print(f"    skip competitor {p['name'][:40]} — isochrone fetch failed: {e}")

    uncaptured = supply_overlap_uncaptured_demand(
        candidate_iso, affluent_15, competitor_polygons
    )
    captured = max(0, affluent_15 - uncaptured)
    capture_fraction = (captured / affluent_15) if affluent_15 > 0 else 0.0

    composite = composite_score(demand, uncaptured, affluent_15)
    drive_time = drive_time_to_nearest_padel(lat, lng, padel_raw)

    return {
        "location_id": location_id,
        "zip": zip_code,
        "label": label,
        "affluent_catchment_15min": affluent_15,
        "tennis_count_q": len(tennis_q),
        "boutique_count_q": len(boutique_q),
        "golf_count_q": len(golf_q),
        "padel_count": len(padel_raw),
        "competitor_polygons_used": len(competitor_polygons),
        "tennis_density": tennis_density,
        "boutique_density": boutique_density,
        "golf_density": golf_density,
        "demand_score": demand,
        "drive_time_to_padel_min": drive_time,
        "uncaptured_affluent": uncaptured,
        "captured_affluent": captured,
        "capture_fraction": capture_fraction,
        "composite_score": composite,
    }


def main() -> int:
    with ANCHORS_CSV.open() as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    if "composite_score_v0" not in fieldnames:
        fieldnames.append("composite_score_v0")

    scored: List[Dict[str, Any]] = []
    for row in rows:
        location_id = row["location_id"].strip()
        print(f"\n=== Scoring {location_id} ===")
        t0 = time.time()
        try:
            result = score_anchor(row)
        except Exception as e:
            print(f"  ERROR scoring {location_id}: {type(e).__name__}: {e}")
            row["composite_score_v0"] = ""
            continue
        elapsed = time.time() - t0
        print(
            f"  demand={result['demand_score']:.4f}  "
            f"uncaptured={result['uncaptured_affluent']:,}  "
            f"composite={result['composite_score']:.4f}  ({elapsed:.1f}s)"
        )
        row["composite_score_v0"] = f"{result['composite_score']:.6f}"
        scored.append(result)

    # Threshold derivation
    print("\n=== Threshold derivation ===")
    build_thr, pass_thr, clean = derive_thresholds(scored)
    print(f"  BUILD threshold (lowest BUILD anchor):  {build_thr:.4f}")
    print(f"  PASS threshold  (highest PASS anchor):  {pass_thr:.4f}")
    print(f"  separation_clean: {clean}")
    if not clean:
        print(
            "  WARNING: PASS threshold ≥ BUILD threshold — anchor distribution "
            "does not separate cleanly. v0 weights/formulation may need revision."
        )

    # Classify + disagreement check
    for s in scored:
        s["classification"] = classify(s["composite_score"], build_thr, pass_thr)
    issues = label_disagreements(scored, build_thr, pass_thr)
    if issues:
        print("\n=== LABEL DISAGREEMENTS ===")
        for it in issues:
            print(
                f"  {it['location_id']}: label={it['label']} but "
                f"classified={it['classification']} (composite={it['composite_score']:.4f}, "
                f"delta_from_threshold={it['delta_from_threshold']:+.4f})"
            )
    else:
        print("\nNo label disagreements — calibration clean.")

    # Write back to anchors.csv
    with ANCHORS_CSV.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nUpdated {ANCHORS_CSV}")

    # Markdown report
    OUTPUT_MD.parent.mkdir(parents=True, exist_ok=True)
    md: List[str] = []
    md.append("# Anchor scoring (v0)\n\n")
    md.append(
        "Composite score = demand × (uncaptured_affluent / affluent_catchment). "
        "Demand = 0.5·tennis_density + 0.3·boutique_density + 0.2·golf_density. "
        "Densities are per-1K-affluent-capita post quality filter "
        "(rating ≥ 3.5, reviews ≥ 30). Uncaptured = candidate's affluent "
        "catchment minus shapely-polygon-intersection of competitor 15-min "
        "isochrones with candidate's 15-min isochrone, summed over affluent "
        "tracts.\n\n"
    )
    md.append(f"BUILD threshold (lowest BUILD anchor): **{build_thr:.4f}**  \n")
    md.append(f"PASS threshold (highest PASS anchor):  **{pass_thr:.4f}**  \n")
    md.append(f"INVESTIGATE band width: **{build_thr - pass_thr:.4f}**  \n")
    md.append(f"Separation clean: **{clean}**\n\n")

    if issues:
        md.append("## Label disagreements\n\n")
        md.append("| anchor | label | classification | composite | delta |\n|---|---|---|---|---|\n")
        for it in issues:
            md.append(
                f"| {it['location_id']} | {it['label']} | {it['classification']} | "
                f"{it['composite_score']:.4f} | {it['delta_from_threshold']:+.4f} |\n"
            )
        md.append("\n")

    md.append("## Per-anchor scoring table\n\n")
    md.append(
        "| anchor | label | classification | composite | demand | tennis dens | "
        "boutique dens | golf dens | padel min | uncaptured | capture % |\n"
        "|---|---|---|---|---|---|---|---|---|---|---|\n"
    )
    for s in sorted(scored, key=lambda x: -x["composite_score"]):
        dt = s["drive_time_to_padel_min"]
        dt_s = "∞" if dt == float("inf") else f"{dt:.1f}"
        md.append(
            f"| {s['location_id']} | {s['label']} | {s['classification']} | "
            f"**{s['composite_score']:.4f}** | {s['demand_score']:.4f} | "
            f"{s['tennis_density']:.4f} | {s['boutique_density']:.4f} | "
            f"{s['golf_density']:.4f} | {dt_s} | "
            f"{s['uncaptured_affluent']:,} | {s['capture_fraction']:.1%} |\n"
        )

    md.append("\n## Capture fraction per anchor\n\n")
    md.append(
        "Fraction of candidate's affluent catchment ALREADY captured by "
        "competitor 15-min rings. High capture = supply-saturated; low "
        "capture = supply gap. Should track inversely with composite score.\n\n"
    )
    md.append(
        "| anchor | label | affluent | captured | uncaptured | capture % |\n"
        "|---|---|---|---|---|---|\n"
    )
    for s in sorted(scored, key=lambda x: -x["capture_fraction"]):
        md.append(
            f"| {s['location_id']} | {s['label']} | "
            f"{s['affluent_catchment_15min']:,} | {s['captured_affluent']:,} | "
            f"{s['uncaptured_affluent']:,} | {s['capture_fraction']:.1%} |\n"
        )

    md.append("\n## BUILD vs PASS composite distribution\n\n")
    build_s = sorted([s["composite_score"] for s in scored if s["label"] in BUILD_LABELS])
    pass_s = sorted([s["composite_score"] for s in scored if s["label"] in PASS_LABELS])
    excl_s = [(s["location_id"], s["composite_score"]) for s in scored if s["label"] in EXCLUDED_FROM_DERIVATION]
    md.append(f"BUILD anchors (n={len(build_s)}): " + ", ".join(f"{x:.4f}" for x in build_s) + "\n\n")
    md.append(f"PASS  anchors (n={len(pass_s)}): " + ", ".join(f"{x:.4f}" for x in pass_s) + "\n\n")
    md.append("Excluded from threshold derivation: " + ", ".join(f"{lid} ({sc:.4f})" for lid, sc in excl_s) + "\n\n")
    if build_s and pass_s:
        gap = min(build_s) - max(pass_s)
        md.append(f"Min BUILD − max PASS = **{gap:+.4f}** "
                  f"({'clean separation' if gap > 0 else 'OVERLAP — calibration failure'})\n\n")

    OUTPUT_MD.write_text("".join(md))
    print(f"Wrote {OUTPUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
