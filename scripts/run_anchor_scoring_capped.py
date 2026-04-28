"""Fallback scoring runner — competitor-isochrone count capped at 10 per anchor.

Use case: full supply-overlap math with all competitors per anchor (e.g.,
27 for Miami, 31 for Brooklyn) overwhelms free Overpass, hangs the
pipeline. The cap-10 version sorts competitors by quality proxy
(rating × user_ratings_total) and keeps only the top 10. Tractability
trade-off — we lose some smaller competitors but keep the heaviest hitters.

Document as v0_provisional. Operator-set cap. Real fix in v1: rank by
court count + member count via a competitor-data-augmentation step that
doesn't yet exist.

Cache-friendly: shares isochrone cache with `run_anchor_scoring.py`.
Already-built competitor isochrones are reused. Top-10 selection happens
BEFORE isochrone fetch, so capped runs may avoid building isochrones that
the full runner would have built.
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

# v0_provisional cap on competitor count per anchor. Set high enough to
# include the heaviest hitters in dense urban anchors (Miami 27 → top 10,
# Brooklyn 31 → top 10), low enough to keep Overpass tractable on free tier.
# v1 should drop this cap once an alternative competitor-isochrone backend
# is built (e.g., paid Google Routes, or a local OSM extract).
COMPETITOR_CAP = 10


def origin_for(zip_code: str) -> Optional[Tuple[float, float]]:
    pop = pop_weighted_centroid(zip_code)
    return pop if pop is not None else zip_to_centroid(zip_code)


def cap_competitors(padel_facilities: List[Dict], max_count: int = COMPETITOR_CAP) -> List[Dict]:
    """Sort competitors by quality proxy (rating × user_ratings_total) and
    keep top max_count. Prioritizes facilities with the most member
    engagement, which approximates the heaviest competitive draw.

    Ties-and-missing-data: places with no rating or no review count score 0
    and lose to any place with engagement data. Stable sort preserves
    original Google ranking among ties.
    """
    if len(padel_facilities) <= max_count:
        return padel_facilities

    def quality_proxy(p):
        rating = p.get("rating") or 0
        reviews = p.get("user_ratings_total") or 0
        return rating * reviews

    return sorted(padel_facilities, key=quality_proxy, reverse=True)[:max_count]


def score_anchor(row: Dict[str, str]) -> Dict[str, Any]:
    zip_code = row["zip"].strip()
    location_id = row["location_id"].strip()
    label = row["ground_truth_label"].strip()
    affluent_15 = int(row.get("affluent_catchment_pop_15min") or 0)

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

    candidate_iso = get_isochrone(lat, lng, 15)

    # Apply competitor cap BEFORE isochrone build so we don't pay the
    # Overpass cost for facilities we won't use anyway.
    padel_capped = cap_competitors(padel_raw)
    competitor_polygons = []
    print(
        f"  [{location_id}] padel raw={len(padel_raw)} → "
        f"capped to top {len(padel_capped)} by rating × reviews"
    )
    for p in padel_capped:
        if abs(p["lat"] - lat) < 0.005 and abs(p["lng"] - lng) < 0.005:
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
        "padel_count_raw": len(padel_raw),
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
    }


def main() -> int:
    with ANCHORS_CSV.open() as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    if "composite_score_v0" not in fieldnames:
        fieldnames.append("composite_score_v0")

    print(f"COMPETITOR_CAP = {COMPETITOR_CAP} (v0_provisional)")
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
        print(
            f"  demand={result['demand_score']:.4f}  "
            f"uncaptured={result['uncaptured_affluent']:,}  "
            f"composite={result['composite_score']:.4f}  ({elapsed:.1f}s)"
        )
        row["composite_score_v0"] = f"{result['composite_score']:.6f}"
        scored.append(result)
        print()

    print("=== Threshold derivation ===")
    build_thr, pass_thr, clean = derive_thresholds(scored)
    print(f"  BUILD threshold (lowest BUILD anchor):  {build_thr:.4f}")
    print(f"  PASS threshold  (highest PASS anchor):  {pass_thr:.4f}")
    print(f"  separation_clean: {clean}")

    for s in scored:
        s["classification"] = classify(s["composite_score"], build_thr, pass_thr)
    issues = label_disagreements(scored, build_thr, pass_thr)
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

    with ANCHORS_CSV.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nUpdated {ANCHORS_CSV}")

    OUTPUT_MD.parent.mkdir(parents=True, exist_ok=True)
    md: List[str] = []
    md.append("# Anchor scoring (v0, competitor-cap=10)\n\n")
    md.append(
        f"**Competitor cap: top {COMPETITOR_CAP} padel facilities per anchor** "
        f"(by rating × user_ratings_total). v0_provisional — operator-set to "
        f"keep Overpass tractable. v1 should drop the cap.\n\n"
    )
    md.append(
        "Composite score = demand × (uncaptured_affluent / affluent_catchment). "
        "Demand = 0.5·tennis_density + 0.3·boutique_density + 0.2·golf_density. "
        "Densities are per-1K-affluent-capita post quality filter "
        "(rating ≥ 3.5, reviews ≥ 30).\n\n"
    )
    md.append(f"BUILD threshold: **{build_thr:.4f}**  \n")
    md.append(f"PASS threshold:  **{pass_thr:.4f}**  \n")
    md.append(f"INVESTIGATE band width: **{build_thr - pass_thr:.4f}**  \n")
    md.append(f"Separation clean: **{clean}**\n\n")

    if issues:
        md.append("## Label disagreements\n\n")
        md.append("| anchor | label | classification | composite | delta |\n|---|---|---|---|---|\n")
        for it in issues:
            md.append(
                f"| {it['location_id']} | {it['label']} | "
                f"{it['classification']} | {it['composite_score']:.4f} | "
                f"{it['delta_from_threshold']:+.4f} |\n"
            )
        md.append("\n")

    md.append("## Per-anchor scoring table\n\n")
    md.append(
        "| anchor | label | classification | composite | demand | tennis dens | "
        "boutique dens | golf dens | padel min | padel raw | padel capped | "
        "uncaptured | capture % |\n"
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|\n"
    )
    for s in sorted(scored, key=lambda x: -x["composite_score"]):
        dt = s["drive_time_to_padel_min"]
        dt_s = "∞" if dt == float("inf") else f"{dt:.1f}"
        md.append(
            f"| {s['location_id']} | {s['label']} | {s['classification']} | "
            f"**{s['composite_score']:.4f}** | {s['demand_score']:.4f} | "
            f"{s['tennis_density']:.4f} | {s['boutique_density']:.4f} | "
            f"{s['golf_density']:.4f} | {dt_s} | {s['padel_count_raw']} | "
            f"{s['padel_count_capped']} | {s['uncaptured_affluent']:,} | "
            f"{s['capture_fraction']:.1%} |\n"
        )

    md.append("\n## Capture fraction per anchor\n\n")
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
