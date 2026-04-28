"""API cost tracking + budget caps to prevent runaway Google Maps spend.

Last project hit $550 in unexpected spend from un-cached repeat calls. This
module is the second line of defense (the first being disk_cache.py — never
spend if the answer is on disk).

Wire it into every paid-API call site as:

    if disk_cache.is_cached(endpoint, query):
        return disk_cache.get(endpoint, query)
    api_cost_tracker.assert_budget_ok(next_call_cost_usd=COST_PER_CALL)
    response = real_api_call(...)
    disk_cache.set(endpoint, query, response)
    api_cost_tracker.log_call(endpoint, query, COST_PER_CALL)

If `assert_budget_ok` raises, the call never goes to the network — caller
sees BudgetExceededError and surfaces to the operator.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
LOG_PATH = REPO_ROOT / "data" / "raw" / "api_call_log.jsonl"


class BudgetExceededError(RuntimeError):
    """Raised when a paid API call would push session or project total over cap."""


def _canonical(query_dict: Dict[str, Any]) -> str:
    """Deterministic JSON for hashing — sorted keys, no whitespace."""
    return json.dumps(query_dict, sort_keys=True, separators=(",", ":"))


def _query_hash(query_dict: Dict[str, Any]) -> str:
    """16-hex-char SHA256 prefix. Collision-safe for caching scale."""
    return hashlib.sha256(_canonical(query_dict).encode()).hexdigest()[:16]


def _ensure_log_dir() -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def _today_iso_date() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _read_log() -> List[Dict[str, Any]]:
    if not LOG_PATH.exists():
        return []
    out: List[Dict[str, Any]] = []
    with LOG_PATH.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def log_call(
    endpoint: str,
    query_dict: Dict[str, Any],
    estimated_cost_usd: float,
) -> None:
    """Append one record to data/raw/api_call_log.jsonl."""
    _ensure_log_dir()
    record = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "date": _today_iso_date(),
        "endpoint": endpoint,
        "query_hash": _query_hash(query_dict),
        "cost_usd": float(estimated_cost_usd),
    }
    with LOG_PATH.open("a") as f:
        f.write(json.dumps(record) + "\n")


def session_total() -> float:
    """Sum of cost_usd for log records dated today (local time)."""
    today = _today_iso_date()
    return round(sum(r["cost_usd"] for r in _read_log() if r.get("date") == today), 4)


def project_total() -> float:
    """Sum of cost_usd across the entire log."""
    return round(sum(r.get("cost_usd", 0.0) for r in _read_log()), 4)


def assert_budget_ok(
    next_call_cost_usd: float,
    session_cap_usd: float = 5.00,
    total_cap_usd: float = 50.00,
) -> None:
    """Raise BudgetExceededError if the next call would push past either cap.

    Caller must invoke BEFORE making the paid API call. If this returns
    silently, the call is approved for spending.
    """
    projected_session = session_total() + next_call_cost_usd
    projected_total = project_total() + next_call_cost_usd

    if projected_session > session_cap_usd:
        raise BudgetExceededError(
            f"Session cap ${session_cap_usd:.2f} would be exceeded: "
            f"current ${session_total():.4f} + next ${next_call_cost_usd:.4f} "
            f"= ${projected_session:.4f}"
        )
    if projected_total > total_cap_usd:
        raise BudgetExceededError(
            f"Project cap ${total_cap_usd:.2f} would be exceeded: "
            f"current ${project_total():.4f} + next ${next_call_cost_usd:.4f} "
            f"= ${projected_total:.4f}"
        )


def reset_log() -> None:
    """Delete the log file. Test/dev only — do not call in production paths."""
    if LOG_PATH.exists():
        LOG_PATH.unlink()
