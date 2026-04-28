"""Site-level demographic hard gates — v0 canonical layered gating.

Per CLAUDE.md anti-pattern #15 ("Relying on a single demographic gate") and
METHODOLOGY.md "Layered gating: candidate-site demographics AND catchment
affluence": a candidate site must clear demographic floors at the zip
level AND its 15-min affluent catchment must clear an absolute population
floor. Either gate failing means the site cannot be BUILD-eligible
regardless of its composite signal score.

Gate values are sourced from operator-set defaults (CLAUDE.md hard-gate
section + METHODOLOGY "Catchment population hard gate — derivation from
anchor data"). Identical to scoring/thresholds.yaml hard_gates section
when that file is wired up; for v0 they live as module-level constants
here so the runner doesn't need yaml plumbing.

Public API:
    site_passes_demographic_gates(anchor_row, thresholds=DEFAULT)
        -> (passes_all, [failed_gate_names])
"""

from __future__ import annotations

from typing import Dict, List, Tuple


DEFAULT_GATE_THRESHOLDS = {
    "home_value_min": 500_000,
    "income_min": 100_000,
    "affluent_catchment_15min_min": 100_000,
}


def _coerce_int(value) -> int:
    """Empty strings / None → 0. Numeric strings → int. Used because
    anchor_row values are CSV strings."""
    if value is None or value == "":
        return 0
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def site_passes_demographic_gates(
    anchor_row: Dict[str, str],
    thresholds: Dict[str, int] = DEFAULT_GATE_THRESHOLDS,
) -> Tuple[bool, List[str]]:
    """Test a candidate site against the v0 demographic gates.

    Returns (passes_all, failed_gate_names). passes_all is True iff
    ALL three gates clear. failed_gate_names lists which gates failed
    in declaration order — useful for surface-level debugging output.

    A site fails if ANY of:
      - median_home_value < thresholds["home_value_min"]
      - median_household_income < thresholds["income_min"]
      - affluent_catchment_pop_15min < thresholds["affluent_catchment_15min_min"]
    """
    home_value = _coerce_int(anchor_row.get("median_home_value"))
    income = _coerce_int(anchor_row.get("median_household_income"))
    affluent = _coerce_int(anchor_row.get("affluent_catchment_pop_15min"))

    failed: List[str] = []
    if home_value < thresholds["home_value_min"]:
        failed.append("home_value")
    if income < thresholds["income_min"]:
        failed.append("income")
    if affluent < thresholds["affluent_catchment_15min_min"]:
        failed.append("affluent_catchment_15min")

    return (len(failed) == 0, failed)
