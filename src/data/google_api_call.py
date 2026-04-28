"""Single entrypoint for any paid Google API call.

ARCHITECTURAL RULE: every paid Google call goes through `cached_api_call`.
No raw `requests.get(...)` to a Google endpoint anywhere else in the codebase.
This is the safety net — caching, budget enforcement, and logging are baked
in. Forgetting to wrap a call site is the only way to bypass them.

Wire pattern in caller (e.g., src/data/google_places.py):

    def nearby_search(lat, lng, radius_m, keyword):
        endpoint = "google.places.nearby_search"
        query = {"lat": lat, "lng": lng, "radius_m": radius_m, "keyword": keyword}
        def fetcher():
            return requests.get(URL, params={...}, timeout=30).json()
        return cached_api_call(
            endpoint=endpoint,
            query=query,
            cost_usd=0.032,
            fetcher=fetcher,
        )

If `cached_api_call` raises BudgetExceededError, the fetcher closure was
never invoked — no spend, no log entry.
"""

from __future__ import annotations

from typing import Any, Callable, Dict

from src.data import api_cost_tracker as cost
from src.data import disk_cache as cache


def cached_api_call(
    endpoint: str,
    query: Dict[str, Any],
    cost_usd: float,
    fetcher: Callable[[], Any],
    session_cap_usd: float = 20.00,
    total_cap_usd: float = 50.00,
) -> Any:
    """Single entrypoint for any Google API call.

    Order of operations:
      1. Check disk cache. Hit → return cached response, fetcher untouched.
      2. assert_budget_ok against the caps. Over budget → raise; fetcher never called.
      3. Invoke fetcher() — the only line that actually spends money.
      4. Cache the response to disk.
      5. Log the cost to the persistent ledger.
      6. Return the response.
    """
    # 1. Cache check — never spend if the answer is on disk
    if cache.is_cached(endpoint, query):
        return cache.get(endpoint, query)

    # 2. Budget check — raise BEFORE fetcher runs so no money flows on a fail
    cost.assert_budget_ok(
        next_call_cost_usd=cost_usd,
        session_cap_usd=session_cap_usd,
        total_cap_usd=total_cap_usd,
    )

    # 3. Spend
    response = fetcher()

    # 4. Persist response so the next identical call is free
    cache.set(endpoint, query, response)

    # 5. Persist cost so future budget checks reflect the actual ledger
    cost.log_call(endpoint, query, cost_usd)

    # 6. Return
    return response
