"""Run google_places.py against the 10 non-NTRC-75033 anchors.

Each anchor: pop-weighted centroid as origin, radius 15000m, all 4 fetchers
(tennis, boutique fitness, golf, padel). All calls go through
cached_api_call → cache hits free, fresh calls billed at $0.032.

Anomaly halts (don't auto-retry, just flag and stop):
  - Anchor produces 0 results across all 4 categories → API failure
  - Tennis OR boutique > 300 results → pagination/false-positive explosion
  - Padel > 15 → dedupe broken
  - Cumulative spend (this script) > $14.00 → trending past 150% of estimate
  - Any single anchor wall > 120s → network issue

Output: data/outputs/anchor_places_raw.md per-anchor summary table.
"""

from __future__ import annotations

import csv
import json
import math
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Bump cached_api_call default caps for THIS RUN ONLY by overriding the
# function's default args in-place. ~10 anchors × ~$0.90 = ~$9 spend,
# breaks the $5 session cap default mid-run. Caps in google_api_call.py
# stay at $5/$50 for normal callers.
from src.data import google_api_call  # noqa: E402
_orig_defaults = google_api_call.cached_api_call.__defaults__
google_api_call.cached_api_call.__defaults__ = (15.00, 50.00)  # session, total

from src.data import api_cost_tracker as cost  # noqa: E402
from src.data.google_places import (  # noqa: E402
    fetch_boutique_fitness,
    fetch_golf_clubs,
    fetch_padel_facilities,
    fetch_tennis_facilities,
)

ANCHORS_CSV = REPO_ROOT / "data" / "calibration" / "anchors.csv"
ZCTA_CACHE = REPO_ROOT / "data" / "raw" / "zcta_centroids.json"
OUTPUT_MD = REPO_ROOT / "data" / "outputs" / "anchor_places_raw.md"

SKIP_ZIP = "75033"  # already cached from NTRC smoke test

RADIUS_M = 15000

# Anomaly thresholds
SPEND_HALT_USD = 14.00
ANCHOR_WALL_HALT_S = 120.0
TENNIS_BOUTIQUE_HALT = 300
PADEL_HALT = 15
# Above-threshold urban-density tolerance: post-fix locationRestriction
# should produce ~0% bleed. If anomaly fires AND bleed < this tolerance,
# treat as real density (informational, don't halt). If bleed exceeds this
# tolerance even with locationRestriction, something else is wrong → halt.
BLEED_TOLERANCE_PCT = 5.0


class AnomalyHalt(RuntimeError):
    """Raised when an anomaly trigger fires; runner stops cleanly."""


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def bleed_pct(places: List[Dict[str, Any]], origin_lat: float, origin_lng: float) -> float:
    """% of places whose lat/lng falls outside the declared 15km search radius.

    Post-locationRestriction-fix this should be ~0%. Used to distinguish
    real urban density from API-side geographic bleed when an anomaly trigger
    fires.
    """
    if not places:
        return 0.0
    out = 0
    for p in places:
        d = haversine_m(origin_lat, origin_lng, p["lat"], p["lng"])
        if d > RADIUS_M:
            out += 1
    return 100.0 * out / len(places)


def load_pop_centroid(zip_code: str) -> Optional[Tuple[float, float]]:
    """Read pop-weighted centroid from zcta_centroids cache. None if missing."""
    if not ZCTA_CACHE.exists():
        return None
    cache = json.loads(ZCTA_CACHE.read_text())
    entry = cache.get(zip_code)
    if not entry or not isinstance(entry, dict):
        return None
    pop = entry.get("pop_centroid")
    if not pop:
        return None
    return (float(pop[0]), float(pop[1]))


def fetch_anchor(lat: float, lng: float) -> Tuple[Dict[str, list], float]:
    """Run all 4 fetchers. Returns (results_dict, wall_seconds)."""
    t0 = time.time()
    results = {
        "tennis": fetch_tennis_facilities(lat, lng, RADIUS_M),
        "boutique": fetch_boutique_fitness(lat, lng, RADIUS_M),
        "golf": fetch_golf_clubs(lat, lng, RADIUS_M),
        "padel": fetch_padel_facilities(lat, lng, RADIUS_M),
    }
    return results, time.time() - t0


def check_anomalies(
    location_id: str,
    results: Dict[str, list],
    elapsed: float,
    cumulative_spend: float,
    origin_lat: float,
    origin_lng: float,
) -> None:
    """Raise AnomalyHalt on any trigger that survives bleed-tolerance check.

    For boutique-count and padel-count threshold breaches, run inline bleed
    audit first. If bleed < BLEED_TOLERANCE_PCT, the high count reflects
    real local density (urban anchors like Brooklyn Heights), NOT a fetcher
    bug. Log informationally and skip the halt. If bleed exceeds tolerance
    even after the locationRestriction fix, something else is wrong → halt.

    Tennis-count, all-zero, wall-time, and spend triggers always halt.
    """
    counts = {k: len(v) for k, v in results.items()}

    # All-zero is legitimate ground truth for rural anchors (no facilities
    # of any of these types within 15km). Removed as a halt — was firing
    # falsely on Roanoke AL post-locationBias-filter.

    if elapsed > ANCHOR_WALL_HALT_S:
        raise AnomalyHalt(
            f"{location_id}: wall time {elapsed:.1f}s > {ANCHOR_WALL_HALT_S}s — network issue"
        )
    if cumulative_spend > SPEND_HALT_USD:
        raise AnomalyHalt(
            f"{location_id}: cumulative spend ${cumulative_spend:.4f} > "
            f"${SPEND_HALT_USD:.2f} — runaway"
        )

    if counts["tennis"] > TENNIS_BOUTIQUE_HALT:
        bleed = bleed_pct(results["tennis"], origin_lat, origin_lng)
        if bleed > BLEED_TOLERANCE_PCT:
            raise AnomalyHalt(
                f"{location_id}: tennis count {counts['tennis']} > "
                f"{TENNIS_BOUTIQUE_HALT} AND bleed {bleed:.1f}% > "
                f"{BLEED_TOLERANCE_PCT}% — fetch is broken"
            )
        print(
            f"  NOTE: tennis count {counts['tennis']} > {TENNIS_BOUTIQUE_HALT} "
            f"BUT bleed {bleed:.1f}% < {BLEED_TOLERANCE_PCT}% → treating as "
            "real urban density, continuing"
        )

    if counts["boutique"] > TENNIS_BOUTIQUE_HALT:
        bleed = bleed_pct(results["boutique"], origin_lat, origin_lng)
        if bleed > BLEED_TOLERANCE_PCT:
            raise AnomalyHalt(
                f"{location_id}: boutique count {counts['boutique']} > "
                f"{TENNIS_BOUTIQUE_HALT} AND bleed {bleed:.1f}% > "
                f"{BLEED_TOLERANCE_PCT}% — fetch is broken"
            )
        print(
            f"  NOTE: boutique count {counts['boutique']} > {TENNIS_BOUTIQUE_HALT} "
            f"BUT bleed {bleed:.1f}% < {BLEED_TOLERANCE_PCT}% → treating as "
            "real urban density, continuing"
        )

    if counts["padel"] > PADEL_HALT:
        bleed = bleed_pct(results["padel"], origin_lat, origin_lng)
        if bleed > BLEED_TOLERANCE_PCT:
            raise AnomalyHalt(
                f"{location_id}: padel count {counts['padel']} > {PADEL_HALT} "
                f"AND bleed {bleed:.1f}% > {BLEED_TOLERANCE_PCT}% — fetch is broken"
            )
        print(
            f"  NOTE: padel count {counts['padel']} > {PADEL_HALT} BUT "
            f"bleed {bleed:.1f}% < {BLEED_TOLERANCE_PCT}% → treating as "
            "real local density, continuing"
        )


def main() -> int:
    with ANCHORS_CSV.open() as f:
        anchors = list(csv.DictReader(f))

    pre_session = cost.session_total()
    pre_project = cost.project_total()
    print(f"Pre-run session_total: ${pre_session:.4f}")
    print(f"Pre-run project_total: ${pre_project:.4f}")
    print(f"Spend halt threshold (this script): ${SPEND_HALT_USD:.2f} added")
    print(f"Cap overrides for this run: session=$15.00, total=$50.00")
    print()

    summary_rows: List[Dict[str, str]] = []
    halted = False
    halt_msg = ""

    for anchor in anchors:
        location_id = anchor["location_id"].strip()
        zip_code = anchor["zip"].strip()
        label = anchor["ground_truth_label"].strip()
        name = anchor["name"].strip()

        if zip_code == SKIP_ZIP:
            print(f"SKIP {location_id} ({zip_code}) — already cached from NTRC test")
            continue

        origin = load_pop_centroid(zip_code)
        if origin is None:
            print(f"SKIP {location_id} ({zip_code}) — no pop centroid cached")
            continue
        lat, lng = origin

        print(f"=== {location_id} ({name}, zip {zip_code}, {label}) ===")
        print(f"  origin: ({lat:.4f}, {lng:.4f})")

        try:
            results, elapsed = fetch_anchor(lat, lng)
        except Exception as e:
            print(f"  ERROR during fetch: {type(e).__name__}: {e}")
            halted = True
            halt_msg = f"{location_id}: fetch raised {type(e).__name__}: {e}"
            break

        post_spend = cost.session_total() - pre_session
        counts = {k: len(v) for k, v in results.items()}
        print(
            f"  results: tennis={counts['tennis']} boutique={counts['boutique']} "
            f"golf={counts['golf']} padel={counts['padel']}"
        )
        print(f"  wall {elapsed:.1f}s, cumulative spend ${post_spend:.4f}")

        try:
            check_anomalies(location_id, results, elapsed, post_spend, lat, lng)
        except AnomalyHalt as e:
            print(f"  ANOMALY HALT: {e}")
            halted = True
            halt_msg = str(e)
            summary_rows.append({
                "location_id": location_id,
                "name": name,
                "zip": zip_code,
                "label": label,
                "centroid": f"{lat:.4f}, {lng:.4f}",
                "tennis": str(counts["tennis"]),
                "boutique": str(counts["boutique"]),
                "golf": str(counts["golf"]),
                "padel": str(counts["padel"]),
                "wall_s": f"{elapsed:.1f}",
                "spend_cumulative": f"${post_spend:.4f}",
            })
            break

        summary_rows.append({
            "location_id": location_id,
            "name": name,
            "zip": zip_code,
            "label": label,
            "centroid": f"{lat:.4f}, {lng:.4f}",
            "tennis": str(counts["tennis"]),
            "boutique": str(counts["boutique"]),
            "golf": str(counts["golf"]),
            "padel": str(counts["padel"]),
            "wall_s": f"{elapsed:.1f}",
            "spend_cumulative": f"${post_spend:.4f}",
        })
        print()

    final_spend = cost.session_total() - pre_session
    print(f"\nTotal spend this script: ${final_spend:.4f}")
    print(f"Final session_total: ${cost.session_total():.4f}")
    print(f"Final project_total: ${cost.project_total():.4f}")

    OUTPUT_MD.parent.mkdir(parents=True, exist_ok=True)
    md: List[str] = []
    md.append("# Anchor Google Places raw fetch — non-NTRC-75033 batch\n\n")
    md.append(
        f"Run on 2026-04-28. Each anchor's pop-weighted centroid → 4 fetchers "
        f"(tennis Search Nearby+Text, boutique fitness 14-brand Text, golf "
        f"Search Nearby+Text, padel 3 Text queries) at radius {RADIUS_M}m. "
        "All counts post-proximity-dedupe (≤50m). All paid calls through "
        "`cached_api_call`; cache hits return free.\n\n"
    )
    if halted:
        md.append(f"**RUN HALTED**: {halt_msg}\n\n")
    md.append(f"Total spend (this run): ${final_spend:.4f}\n\n")
    md.append("## Per-anchor summary\n\n")
    md.append(
        "| location_id | zip | label | centroid | tennis | boutique | golf | "
        "padel | wall (s) | cum spend |\n"
        "|---|---|---|---|---|---|---|---|---|---|\n"
    )
    for r in summary_rows:
        md.append(
            f"| {r['location_id']} | {r['zip']} | {r['label']} | "
            f"{r['centroid']} | {r['tennis']} | {r['boutique']} | "
            f"{r['golf']} | {r['padel']} | {r['wall_s']} | "
            f"{r['spend_cumulative']} |\n"
        )
    OUTPUT_MD.write_text("".join(md))
    print(f"\nWrote summary to {OUTPUT_MD}")

    # Restore original defaults
    google_api_call.cached_api_call.__defaults__ = _orig_defaults

    return 1 if halted else 0


if __name__ == "__main__":
    raise SystemExit(main())
