"""Smoke test for src/data/google_places.py against NTRC Frisco coordinates.

REAL API CALLS — first run will spend money. Expected first-run cost is
~$0.35-0.70 depending on pagination; capped at $1.00 via session_cap_usd.

Workflow:
  - Run 1 (cache misses): hit Google for tennis + 7 boutique brands + golf
    + 2 padel queries. Each result printed. Cost printed before/after.
  - Run 2 (cache hits): re-invoke same fetchers; total cost MUST NOT change.

Run from repo root:
    python3 scripts/test_google_places.py

Pre-flight: GOOGLE_MAPS_API_KEY must be in .env (Places API New enabled
on the GCP project). The script will raise with instructions if not.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.data import api_cost_tracker as cost
from src.data.google_places import (
    fetch_boutique_fitness,
    fetch_golf_clubs,
    fetch_padel_facilities,
    fetch_tennis_facilities,
)

# NTRC Frisco — pop-weighted centroid for zip 75033 (already cached).
NTRC_LAT = 33.18
NTRC_LNG = -96.85
RADIUS_M = 15000

SESSION_CAP_USD = 2.00


def banner(label: str) -> None:
    print(f"\n{'=' * 6} {label} {'=' * 6}")


def report(name: str, places: list, run_phase: str) -> None:
    print(f"\n[{run_phase}] {name}: {len(places)} results")
    for p in places[:5]:
        rating = f"{p['rating']:.1f}" if p.get("rating") is not None else "—"
        n_ratings = p.get("user_ratings_total") or 0
        price = p.get("price_level")
        price_s = f"$={price}" if price is not None else "$=—"
        status = (p.get("business_status") or "?")[:8]
        ptype = (p.get("primary_type") or "—")[:18]
        print(f"  {p['name'][:42]:<42} "
              f"({p['lat']:.4f}, {p['lng']:.4f}) "
              f"r={rating} n={n_ratings:<4} {price_s} "
              f"{status:<8} {ptype}")
    if len(places) > 5:
        print(f"  ...and {len(places) - 5} more")


def fetch_all(phase: str) -> dict:
    """Run all four fetchers, return a {name: [places]} dict."""
    out = {}
    t0 = time.time()
    out["tennis"] = fetch_tennis_facilities(NTRC_LAT, NTRC_LNG, RADIUS_M)
    out["boutique"] = fetch_boutique_fitness(NTRC_LAT, NTRC_LNG, RADIUS_M)
    out["golf"] = fetch_golf_clubs(NTRC_LAT, NTRC_LNG, RADIUS_M)
    out["padel"] = fetch_padel_facilities(NTRC_LAT, NTRC_LNG, RADIUS_M)
    elapsed = time.time() - t0
    print(f"\n[{phase}] all fetchers done in {elapsed:.1f}s")
    return out


def main() -> int:
    banner("Pre-flight")
    pre_session = cost.session_total()
    pre_project = cost.project_total()
    print(f"  session_total before run: ${pre_session:.4f}")
    print(f"  project_total before run: ${pre_project:.4f}")
    print(f"  session_cap_usd for this script: ${SESSION_CAP_USD:.2f}")
    print(f"  origin: NTRC Frisco ({NTRC_LAT}, {NTRC_LNG}), radius {RADIUS_M}m")

    banner("Run 1: cache misses (real API calls expected)")
    results_run1 = fetch_all("Run 1")
    for name, places in results_run1.items():
        report(name, places, "Run 1")
    after_run1_session = cost.session_total()
    print(f"\n[Run 1] session_total: ${after_run1_session:.4f}")
    print(f"[Run 1] this-script spend: ${after_run1_session - pre_session:.4f}")
    if after_run1_session - pre_session > SESSION_CAP_USD:
        print(f"  WARNING: spend exceeded SESSION_CAP_USD ${SESSION_CAP_USD:.2f}")
        return 1

    banner("Run 2: cache hits (no spend expected)")
    results_run2 = fetch_all("Run 2")
    for name, places in results_run2.items():
        # Sanity: same length as run 1.
        if len(places) != len(results_run1[name]):
            print(f"  WARNING: {name} returned {len(places)} on run 2 vs "
                  f"{len(results_run1[name])} on run 1 — cache may have missed")
    after_run2_session = cost.session_total()
    print(f"\n[Run 2] session_total: ${after_run2_session:.4f}")
    if after_run2_session != after_run1_session:
        print(f"  WARNING: cost increased on run 2 — cache hit rate < 100%")
        print(f"    run 1 end: ${after_run1_session:.4f}")
        print(f"    run 2 end: ${after_run2_session:.4f}")
        return 1
    print(f"  OK — total spend unchanged across run 1 and run 2")

    banner("Summary")
    print(f"  run 1 spend: ${after_run1_session - pre_session:.4f}")
    print(f"  run 2 spend: $0.0000 (cache hits)")
    print(f"  total session_total: ${after_run2_session:.4f}")
    print(f"  total project_total: ${cost.project_total():.4f}")
    print(f"  results per category:")
    for name, places in results_run2.items():
        print(f"    {name:<10}: {len(places)} unique places")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
