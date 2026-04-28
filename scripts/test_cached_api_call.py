"""Smoke test for the single entrypoint cached_api_call.

Three properties to verify:
  1. Fetcher closure is NOT called on cache hit.
  2. Fetcher closure IS called on cache miss.
  3. Budget cap raises BEFORE fetcher runs (no spend on overrun).

Property #3 is the load-bearing one — last project's $550 spend was a budget
gate that ran AFTER the call. We're verifying we don't repeat that.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.data import api_cost_tracker as cost
from src.data import disk_cache as cache
from src.data.api_cost_tracker import BudgetExceededError
from src.data.google_api_call import cached_api_call


ENDPOINT = "google.places.nearby_search"
COST_PER_CALL = 0.032


class FetcherCalledWhenItShouldNotBe(AssertionError):
    """Sentinel raised by a fetcher that should never run."""


def banner(label: str) -> None:
    print(f"\n{'=' * 6} {label} {'=' * 6}")


def main() -> int:
    cost.reset_log()
    test_query_1 = {"lat": 33.18, "lng": -96.85, "radius_m": 15000, "keyword": "tennis_club"}
    test_query_2 = {"lat": 36.17, "lng": -86.80, "radius_m": 7000, "keyword": "fitness"}
    for q in (test_query_1, test_query_2):
        p = cache.cache_path(ENDPOINT, q)
        if p.exists():
            p.unlink()

    banner("Test 1: cache miss → fetcher IS called")
    miss_call_count = {"n": 0}

    def miss_fetcher():
        miss_call_count["n"] += 1
        return {"results": ["court_a", "court_b"]}

    response = cached_api_call(ENDPOINT, test_query_1, COST_PER_CALL, miss_fetcher)
    assert miss_call_count["n"] == 1, f"fetcher should run once, ran {miss_call_count['n']}"
    assert response == {"results": ["court_a", "court_b"]}
    assert cache.is_cached(ENDPOINT, test_query_1), "response should be cached"
    assert cost.session_total() == COST_PER_CALL, "spend should be logged"
    print(f"  fetcher called {miss_call_count['n']}x (expected 1) — OK")
    print(f"  response: {response}")
    print(f"  cached on disk: {cache.is_cached(ENDPOINT, test_query_1)}")
    print(f"  session_total: ${cost.session_total():.4f}")

    banner("Test 2: cache hit → fetcher is NOT called")
    def landmine_fetcher():
        raise FetcherCalledWhenItShouldNotBe(
            "Fetcher invoked despite cache hit — cached_api_call is broken"
        )

    response = cached_api_call(ENDPOINT, test_query_1, COST_PER_CALL, landmine_fetcher)
    assert response == {"results": ["court_a", "court_b"]}, "should return cached value"
    assert cost.session_total() == COST_PER_CALL, "spend should NOT increase on cache hit"
    print(f"  fetcher landmine NOT triggered — OK")
    print(f"  response (from cache): {response}")
    print(f"  session_total: ${cost.session_total():.4f} (unchanged)")

    banner("Test 3: budget exceeded → fetcher is NOT called, no spend")
    pre_session_total = cost.session_total()
    pre_log_size = (REPO_ROOT / "data" / "raw" / "api_call_log.jsonl").stat().st_size

    def landmine_fetcher_2():
        raise FetcherCalledWhenItShouldNotBe(
            "Fetcher invoked despite budget overrun — money would have been spent"
        )

    raised = False
    try:
        cached_api_call(
            endpoint=ENDPOINT,
            query=test_query_2,
            cost_usd=0.50,
            fetcher=landmine_fetcher_2,
            session_cap_usd=0.10,  # already exceeded by current $0.032 + next $0.50
        )
    except BudgetExceededError as e:
        raised = True
        print(f"  BudgetExceededError raised:")
        print(f"    {e}")

    assert raised, "expected BudgetExceededError to be raised"
    assert cost.session_total() == pre_session_total, "no spend should be logged"
    post_log_size = (REPO_ROOT / "data" / "raw" / "api_call_log.jsonl").stat().st_size
    assert post_log_size == pre_log_size, "log file must not grow on budget reject"
    assert not cache.is_cached(ENDPOINT, test_query_2), "no cache entry should be written"
    print(f"  fetcher landmine NOT triggered — OK (no spend occurred)")
    print(f"  session_total: ${cost.session_total():.4f} (unchanged from pre-test)")
    print(f"  log file size: {post_log_size}B (unchanged from pre-test)")
    print(f"  cache entry for blocked query: {cache.is_cached(ENDPOINT, test_query_2)} (false expected)")

    banner("All three properties verified")
    print("  1. fetcher NOT called on cache hit ✓")
    print("  2. fetcher IS called on cache miss ✓")
    print("  3. budget cap raises BEFORE fetcher; no spend on overrun ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
