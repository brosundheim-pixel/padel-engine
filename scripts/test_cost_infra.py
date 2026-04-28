"""Smoke test for api_cost_tracker + disk_cache.

Demonstrates:
  - 5 cached calls (after the first miss) return from disk; no spend, no log
  - 1 cache miss triggers a budget check, fake-API-call, cache write, log
  - session_total reflects today's costs only
  - project_total reflects all-time
  - assert_budget_ok raises when next call would exceed session or total cap

Run: python3 scripts/test_cost_infra.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.data import api_cost_tracker as cost
from src.data import disk_cache as cache
from src.data.api_cost_tracker import BudgetExceededError

ENDPOINT = "google.places.nearby_search"
COST_PER_CALL = 0.032  # actual Google Places Nearby Search per-request price


def fake_api_call(query: dict) -> dict:
    """Stand-in for the real Google API. Sleeps to simulate network latency."""
    time.sleep(0.15)
    return {"results": [f"fake_result_for_{query.get('keyword')}"]}


def cached_call(query: dict) -> tuple[dict, bool, float]:
    """Standard caller pattern. Returns (response, was_cache_hit, elapsed_s)."""
    t0 = time.time()
    if cache.is_cached(ENDPOINT, query):
        response = cache.get(ENDPOINT, query)
        return response, True, time.time() - t0
    cost.assert_budget_ok(next_call_cost_usd=COST_PER_CALL)
    response = fake_api_call(query)
    cache.set(ENDPOINT, query, response)
    cost.log_call(ENDPOINT, query, COST_PER_CALL)
    return response, False, time.time() - t0


def banner(label: str) -> None:
    print(f"\n{'=' * 6} {label} {'=' * 6}")


def main() -> int:
    # Clean slate so the test is deterministic.
    cost.reset_log()
    queries = [
        {"location": "33.18,-96.85", "keyword": "tennis_club", "radius": 15000},
        {"location": "36.17,-86.80", "keyword": "tennis_club", "radius": 15000},
        {"location": "40.69,-73.99", "keyword": "tennis_club", "radius": 15000},
        {"location": "33.18,-96.85", "keyword": "fitness", "radius": 7000},
        {"location": "36.17,-86.80", "keyword": "fitness", "radius": 7000},
    ]
    for q in queries:
        p = cache.cache_path(ENDPOINT, q)
        if p.exists():
            p.unlink()

    banner("Phase 1: 5 fresh calls (cache misses → spend)")
    for q in queries:
        _, hit, elapsed = cached_call(q)
        print(f"  {q['keyword']:<13} @ {q['location']:<16} "
              f"hit={hit} elapsed={elapsed * 1000:.1f}ms")
    print(f"  session_total: ${cost.session_total():.4f}")
    print(f"  project_total: ${cost.project_total():.4f}")
    expected = round(5 * COST_PER_CALL, 4)
    assert cost.session_total() == expected, f"expected ${expected:.4f}"
    assert cost.project_total() == expected
    print(f"  OK — 5 calls × ${COST_PER_CALL:.4f} = ${expected:.4f}")

    banner("Phase 2: same 5 queries replayed (cache hits → no spend)")
    for q in queries:
        _, hit, elapsed = cached_call(q)
        print(f"  {q['keyword']:<13} @ {q['location']:<16} "
              f"hit={hit} elapsed={elapsed * 1000:.1f}ms")
    print(f"  session_total: ${cost.session_total():.4f} (unchanged)")
    print(f"  project_total: ${cost.project_total():.4f} (unchanged)")
    assert cost.session_total() == expected, "cache hits must not log spend"

    banner("Phase 3: 1 new query (cache miss → spend)")
    new_q = {"location": "42.24,-71.17", "keyword": "tennis_club", "radius": 15000}
    cache.cache_path(ENDPOINT, new_q).unlink(missing_ok=True)
    _, hit, elapsed = cached_call(new_q)
    print(f"  new query hit={hit} elapsed={elapsed * 1000:.1f}ms")
    print(f"  session_total: ${cost.session_total():.4f}")
    print(f"  project_total: ${cost.project_total():.4f}")
    expected_after = round(6 * COST_PER_CALL, 4)
    assert cost.session_total() == expected_after, f"expected ${expected_after:.4f}"

    banner("Phase 4: assert_budget_ok scenarios")

    # Should pass: $0.20 + 6 × $0.032 = $0.392 < $1.00 default session cap
    cost.assert_budget_ok(next_call_cost_usd=0.20)
    print(f"  next $0.20 under default $1.00 session cap → OK")

    # Should fail: session cap drops below current
    try:
        cost.assert_budget_ok(next_call_cost_usd=0.05, session_cap_usd=0.10)
    except BudgetExceededError as e:
        print(f"  next $0.05 with $0.10 session cap → BudgetExceededError raised:")
        print(f"    {e}")

    # Should fail: total cap drops below current
    try:
        cost.assert_budget_ok(next_call_cost_usd=0.05, total_cap_usd=0.10)
    except BudgetExceededError as e:
        print(f"  next $0.05 with $0.10 total cap → BudgetExceededError raised:")
        print(f"    {e}")

    banner("Persistence check")
    log_path = REPO_ROOT / "data" / "raw" / "api_call_log.jsonl"
    line_count = sum(1 for _ in log_path.open())
    print(f"  {log_path.relative_to(REPO_ROOT)}: {line_count} records on disk")
    print(f"  Re-running this script would see project_total = "
          f"${cost.project_total():.4f} until reset_log() is called.")
    print(f"  Cache files at data/raw/google_places/:")
    for p in sorted((REPO_ROOT / "data" / "raw" / "google_places").iterdir()):
        print(f"    {p.name}  ({p.stat().st_size}B)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
