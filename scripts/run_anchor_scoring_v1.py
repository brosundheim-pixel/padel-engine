"""v1 scoring runner — adds site-level demographic gate + self-exclusion
of co-located operators from the competitor set.

Two v1 fixes vs the prior capped runner:

  FIX 1: Site-level demographic hard gate. Before composite scoring, each
  pure-BUILD/PASS anchor is tested against the v0 demographic gates
  (home_value ≥ $500K, income ≥ $100K, affluent_catchment_15min ≥ 100K).
  GATE_FAIL anchors are classified PASS with composite=None — they're
  pre-filtered out of any threshold derivation. BUILD_DESTINATION_URBAN
  and BUILD_OUTDOOR_VARIANT skip the gate (their existence as labels is
  the operator hedge for non-standard demand mechanisms).

  FIX 2: Self-exclusion from competitor set. For each candidate, drop any
  padel facility whose location falls inside the candidate's 7-min
  isochrone. A co-located operator IS the BUILD signal, not a competitor
  reducing the candidate's BUILD case.

Cap-10 retained from prior runner (Brooklyn, Miami need it for tractable
Overpass usage).
"""

from __future__ import annotations

import csv
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from shapely.geometry import Point

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
from src.scoring.gates import (
    DEFAULT_GATE_THRESHOLDS,
    site_passes_demographic_gates,
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
COMPETITOR_CAP = 10  # v0_provisional


def origin_for(zip_code: str) -> Optional[Tuple[float, float]]:
    pop = pop_weighted_centroid(zip_code)
    return pop if pop is not None else zip_to_centroid(zip_code)


def cap_competitors(padel_facilities: List[Dict], max_count: int = COMPETITOR_CAP) -> List[Dict]:
    """Top N by quality proxy (rating × user_ratings_total)."""
    if len(padel_facilities) <= max_count:
        return padel_facilities

    def quality_proxy(p):
        return (p.get("rating") or 0) * (p.get("user_ratings_total") or 0)

    return sorted(padel_facilities, key=quality_proxy, reverse=True)[:max_count]


def self_exclude_competitors(
    padel_facilities: List[Dict],
    inner_iso_polygon,
) -> Tuple[List[Dict], List[Dict]]:
    """Drop padel facilities whose location falls inside candidate's 7-min ring.

    Returns (kept, excluded). FIX 2 of v1: a co-located operator IS the
    BUILD signal for the anchor's zip, not a competitor that captures the
    candidate's catchment.
    """
    kept: List[Dict] = []
    excluded: List[Dict] = []
    for p in padel_facilities:
        pt = Point(p["lng"], p["lat"])
        if inner_iso_polygon.contains(pt):
            excluded.append(p)
        else:
            kept.append(p)
    return kept, excluded


def determine_classification_method(label: str, anchor_row: Dict[str, str]) -> Tuple[str, List[str]]:
    """Returns (classification_method, failed_gates).

    Hierarchy:
      - BUILD_DESTINATION_URBAN / BUILD_OUTDOOR_VARIANT label → use as-is
        (skip gate; excluded from threshold derivation downstream)
      - Otherwise: apply demographic gates. GATE_PASS or GATE_FAIL.
    """
    if label in EXCLUDED_FROM_DERIVATION:
        return label, []
    passes, failed = site_passes_demographic_gates(anchor_row)
    return ("GATE_PASS" if passes else "GATE_FAIL"), failed


def score_anchor(row: Dict[str, str]) -> Dict[str, Any]:
    zip_code = row["zip"].strip()
    location_id = row["location_id"].strip()
    label = row["ground_truth_label"].strip()
    affluent_15 = int(row.get("affluent_catchment_pop_15min") or 0)

    classification_method, failed_gates = determine_classification_method(label, row)

    record = {
        "location_id": location_id,
        "zip": zip_code,
        "label": label,
        "classification_method": classification_method,
        "failed_gates": failed_gates,
        "affluent_catchment_15min": affluent_15,
        "padel_count_raw": 0,
        "padel_count_after_self_exclude": 0,
        "padel_count_capped": 0,
        "competitor_polygons_used": 0,
        "tennis_density": 0.0,
        "boutique_density": 0.0,
        "golf_density": 0.0,
        "demand_score": 0.0,
        "drive_time_to_padel_min": float("inf"),
        "uncaptured_affluent": 0,
        "captured_affluent": 0,
        "capture_fraction": 0.0,
        "composite_score": None,
    }

    if classification_method == "GATE_FAIL":
        # Don't compute composite — record stays with composite=None
        return record

    # Origin + cached Google Places data
    origin = origin_for(zip_code)
    if origin is None:
        raise RuntimeError(f"No origin centroid for {location_id} ({zip_code})")
    lat, lng = origin

    tennis_raw = fetch_tennis_facilities(lat, lng, RADIUS_M)
    boutique_raw = fetch_boutique_fitness(lat, lng, RADIUS_M)
    golf_raw = fetch_golf_clubs(lat, lng, RADIUS_M)
    padel_raw = fetch_padel_facilities(lat, lng, RADIUS_M)

    tennis_q = quality_filter(tennis_raw)
    boutique_q = quality_filter(boutique_raw)
    golf_q = quality_filter(golf_raw)

    tennis_density = tennis_density_per_affluent_capita(len(tennis_q), affluent_15)
    boutique_density = boutique_density_per_affluent_capita(len(boutique_q), affluent_15)
    golf_density = golf_density_per_affluent_capita(len(golf_q), affluent_15)
    demand = composite_demand_score(tennis_density, boutique_density, golf_density)

    # FIX 2: self-exclusion. Drop padel facilities inside candidate's 7-min ring.
    inner_iso = get_isochrone(lat, lng, 7)
    padel_after_self, padel_self_excluded = self_exclude_competitors(padel_raw, inner_iso)

    # Cap surviving competitors
    padel_capped = cap_competitors(padel_after_self)

    candidate_iso_15 = get_isochrone(lat, lng, 15)
    competitor_polygons = []
    print(
        f"  [{location_id}] padel raw={len(padel_raw)} → "
        f"after self-exclude={len(padel_after_self)} (dropped {len(padel_self_excluded)}) → "
        f"capped={len(padel_capped)}"
    )
    for p in padel_capped:
        try:
            poly = get_isochrone(p["lat"], p["lng"], 15)
            competitor_polygons.append(poly)
        except Exception as e:
            print(f"    skip competitor {p['name'][:40]} — {e}")

    uncaptured = supply_overlap_uncaptured_demand(
        candidate_iso_15, affluent_15, competitor_polygons
    )
    captured = max(0, affluent_15 - uncaptured)
    capture_fraction = (captured / affluent_15) if affluent_15 > 0 else 0.0

    composite = composite_score(demand, uncaptured, affluent_15)
    drive_time = drive_time_to_nearest_padel(lat, lng, padel_raw)

    record.update({
        "padel_count_raw": len(padel_raw),
        "padel_count_after_self_exclude": len(padel_after_self),
        "padel_count_capped": len(padel_capped),
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
    })
    return record


def main() -> int:
    with ANCHORS_CSV.open() as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    if "composite_score_v0" not in fieldnames:
        fieldnames.append("composite_score_v0")
    if "capture_fraction_v0" not in fieldnames:
        fieldnames.append("capture_fraction_v0")

    print(f"COMPETITOR_CAP = {COMPETITOR_CAP} (v0_provisional)")
    print(f"Demographic gates: {DEFAULT_GATE_THRESHOLDS}")
    print()

    scored: List[Dict[str, Any]] = []
    for row in rows:
        location_id = row["location_id"].strip()
        print(f"=== Scoring {location_id} ===")
        t0 = time.time()
        try:
            result = score_anchor(row)
        except Exception as e:
            print(f"  ERROR scoring {location_id}: {type(e).__name__}: {e}")
            row["composite_score_v0"] = ""
            continue
        elapsed = time.time() - t0
        if result["classification_method"] == "GATE_FAIL":
            print(
                f"  classification_method=GATE_FAIL  failed_gates={result['failed_gates']}  "
                f"composite=None  ({elapsed:.1f}s)"
            )
            row["composite_score_v0"] = ""
            row["capture_fraction_v0"] = ""
        else:
            print(
                f"  method={result['classification_method']}  "
                f"demand={result['demand_score']:.4f}  "
                f"uncaptured={result['uncaptured_affluent']:,}  "
                f"composite={result['composite_score']:.4f}  ({elapsed:.1f}s)"
            )
            row["composite_score_v0"] = f"{result['composite_score']:.6f}"
            row["capture_fraction_v0"] = f"{result['capture_fraction']:.6f}"
        scored.append(result)
        print()

    # Threshold derivation — only over rows with non-None composite. Pass
    # capture_fraction so derive_thresholds can apply the saturated-BUILD
    # exclusion (CLAUDE.md anti-pattern #16; v0_provisional 0.85 cutoff).
    scored_for_derivation = [
        {"location_id": s["location_id"], "label": s["label"],
         "composite_score": s["composite_score"],
         "capture_fraction": s["capture_fraction"]}
        for s in scored
        if s["composite_score"] is not None
    ]
    print("=== Threshold derivation ===")
    build_thr, pass_thr, clean = derive_thresholds(scored_for_derivation)
    gap = build_thr - pass_thr
    print(f"  BUILD threshold: {build_thr:.4f}")
    print(f"  PASS threshold:  {pass_thr:.4f}")
    print(f"  separation_gap:  {gap:+.4f}")
    print(f"  separation_clean: {clean}")

    # Classify scored anchors against derived thresholds
    for s in scored:
        if s["composite_score"] is None:
            s["classification"] = "PASS"  # GATE_FAIL → PASS
        else:
            s["classification"] = classify(s["composite_score"], build_thr, pass_thr)

    # Build a label_disagreements call adapted to handle GATE_FAIL anchors
    issues = label_disagreements(scored_for_derivation, build_thr, pass_thr)
    if issues:
        print("\n=== LABEL DISAGREEMENTS ===")
        for it in issues:
            print(
                f"  {it['location_id']}: label={it['label']} but "
                f"classified={it['classification']} "
                f"(composite={it['composite_score']:.4f}, "
                f"delta={it['delta_from_threshold']:+.4f})"
            )
    else:
        print("\nNo label disagreements — calibration clean.")

    # Write back to anchors.csv
    with ANCHORS_CSV.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nUpdated {ANCHORS_CSV}")

    # Write markdown report
    OUTPUT_MD.parent.mkdir(parents=True, exist_ok=True)
    md: List[str] = []
    md.append("# Anchor scoring (v1: gates + self-exclusion)\n\n")
    md.append(
        "**v1 changes vs v0**: (1) site-level demographic hard gate applied "
        "before composite scoring; GATE_FAIL anchors get composite=None and "
        "classify PASS by gate. (2) Self-exclusion: padel facilities inside "
        "the candidate's 7-min isochrone are dropped from the competitor set "
        "(co-located operator = BUILD signal, not competitor).\n\n"
    )
    md.append(f"**Demographic gates**: home_value ≥ ${DEFAULT_GATE_THRESHOLDS['home_value_min']:,}, "
              f"income ≥ ${DEFAULT_GATE_THRESHOLDS['income_min']:,}, "
              f"affluent_catchment_15min ≥ {DEFAULT_GATE_THRESHOLDS['affluent_catchment_15min_min']:,}\n\n")
    md.append(f"**Competitor cap**: top {COMPETITOR_CAP} per anchor by rating × reviews (v0_provisional)\n\n")
    md.append(f"BUILD threshold: **{build_thr:.4f}**  \n")
    md.append(f"PASS threshold:  **{pass_thr:.4f}**  \n")
    md.append(f"Separation gap (BUILD − PASS): **{gap:+.4f}**  \n")
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
        "| anchor | label | method | classification | composite | demand | "
        "padel raw | post-self-excl | capped | uncaptured | capture % | failed_gates |\n"
        "|---|---|---|---|---|---|---|---|---|---|---|---|\n"
    )
    def sort_key(s):
        return s["composite_score"] if s["composite_score"] is not None else -1.0
    for s in sorted(scored, key=sort_key, reverse=True):
        comp = f"{s['composite_score']:.4f}" if s["composite_score"] is not None else "—"
        demand = f"{s['demand_score']:.4f}" if s["composite_score"] is not None else "—"
        uncap = f"{s['uncaptured_affluent']:,}" if s["composite_score"] is not None else "—"
        cap_pct = f"{s['capture_fraction']:.1%}" if s["composite_score"] is not None else "—"
        gates = ",".join(s["failed_gates"]) if s["failed_gates"] else "—"
        md.append(
            f"| {s['location_id']} | {s['label']} | {s['classification_method']} | "
            f"{s['classification']} | **{comp}** | {demand} | "
            f"{s['padel_count_raw']} | {s['padel_count_after_self_exclude']} | "
            f"{s['padel_count_capped']} | {uncap} | {cap_pct} | {gates} |\n"
        )

    md.append("\n## BUILD vs PASS composite distribution (gate-passers only)\n\n")
    build_s = sorted([s["composite_score"] for s in scored
                      if s["label"] in BUILD_LABELS and s["composite_score"] is not None])
    pass_s = sorted([s["composite_score"] for s in scored
                     if s["label"] in PASS_LABELS and s["composite_score"] is not None])
    excl_s = [(s["location_id"], s["composite_score"]) for s in scored
              if s["label"] in EXCLUDED_FROM_DERIVATION and s["composite_score"] is not None]
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
