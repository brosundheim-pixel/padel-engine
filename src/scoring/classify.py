"""BUILD / INVESTIGATE / PASS classification with anchor-derived thresholds.

Threshold derivation (v0 canonical per CLAUDE.md "Threshold derivation"):
  BUILD threshold = lowest composite score among label == 'BUILD' anchors
  PASS threshold  = highest composite score among label == 'PASS' anchors
  INVESTIGATE band = scores strictly between PASS_threshold and BUILD_threshold

BUILD_DESTINATION_URBAN (Sensa) and BUILD_OUTDOOR_VARIANT (Alpharetta) are
EXCLUDED from threshold derivation. Their labels reflect demand mechanisms
the v0 composite doesn't model (Sensa's destination-pull demand from
outside Germantown; Alpharetta's outdoor-format club economics differ
from Tony's Racket indoor thesis). They're scored for visibility but
should not gate the threshold.
"""

from __future__ import annotations

from typing import Dict, List, Tuple


# Labels that count toward BUILD threshold derivation
BUILD_LABELS = {"BUILD"}
# Labels that count toward PASS threshold derivation
PASS_LABELS = {"PASS"}
# Labels scored but EXCLUDED from threshold derivation by label-rule.
# PASS_SATURATED_URBAN reflects the calibration-boundary case (e.g.,
# Brooklyn Heights) — saturated NYC supply is policy-excluded by strategy
# regardless of composite score (CLAUDE.md "Default exclusions: All urban
# core neighborhoods"). Treated like the BUILD-class exclusions.
EXCLUDED_FROM_DERIVATION = {
    "BUILD_DESTINATION_URBAN",
    "BUILD_OUTDOOR_VARIANT",
    "PASS_SATURATED_URBAN",
}

# v0_provisional: BUILD anchors with capture_fraction above this threshold
# are excluded from BUILD floor derivation. Calibration-boundary handling
# per CLAUDE.md anti-pattern #16 / METHODOLOGY "Calibration boundary:
# saturated markets". The composite math cannot disambiguate
# "saturated and served-out" from "saturated but operators at capacity"
# without capacity data; saturated BUILD anchors must not gate the
# threshold lower than the unsaturated BUILD anchors are showing.
SATURATED_CAPTURE_THRESHOLD = 0.85

EPSILON = 1e-9


def _saturated(entry) -> bool:
    """True if entry has a capture_fraction above SATURATED_CAPTURE_THRESHOLD.
    Returns False for entries missing capture_fraction (treated as not-saturated)."""
    cf = entry.get("capture_fraction") if isinstance(entry, dict) else None
    return cf is not None and cf > SATURATED_CAPTURE_THRESHOLD


def derive_thresholds(
    anchor_scores: List[Dict],
) -> Tuple[float, float, bool]:
    """Compute (build_threshold, pass_threshold, separation_clean).

    `anchor_scores` is a list of dicts with at minimum {"label", "composite_score"}.
    Optional `capture_fraction` field triggers the saturated-BUILD exclusion
    rule (anti-pattern #16): BUILD anchors with capture_fraction > 0.85 are
    excluded from BUILD floor derivation as a calibration-boundary handler.

    Returns:
      build_threshold — lowest composite among non-saturated BUILD rows
      pass_threshold  — highest composite among PASS rows; defaults to 0.0
                         if no PASS anchors qualify (e.g., all gate-failed
                         or excluded by label)
      separation_clean — True iff pass_threshold < build_threshold
    """
    build_scores = [
        a["composite_score"] for a in anchor_scores
        if a["label"] in BUILD_LABELS and not _saturated(a)
    ]
    pass_scores = [
        a["composite_score"] for a in anchor_scores
        if a["label"] in PASS_LABELS
    ]

    if not build_scores:
        raise ValueError(
            "No BUILD-labeled anchors with capture <= 0.85 — cannot derive threshold. "
            "Either no BUILD anchors scored, or all BUILD anchors are saturated."
        )

    build_threshold = min(build_scores)
    # If no PASS anchors qualify (all gate-failed → composite=None excluded
    # by caller; or all PASS labels excluded e.g., PASS_SATURATED_URBAN),
    # default PASS threshold to 0. Anything strictly positive lands BUILD
    # or INVESTIGATE; nothing classifies PASS by score (only by gate/label).
    pass_threshold = max(pass_scores) if pass_scores else 0.0
    separation_clean = pass_threshold < build_threshold
    return build_threshold, pass_threshold, separation_clean


def classify(
    composite_score: float,
    build_threshold: float,
    pass_threshold: float,
) -> str:
    """Pure classification. Score ≥ build → BUILD; ≤ pass → PASS;
    strictly between → INVESTIGATE.

    Tie-breaking: scores exactly equal to a threshold land on the
    higher tier (≥ build → BUILD; ≤ pass → PASS, even if also ≥ build
    in degenerate inverted-threshold case)."""
    if composite_score >= build_threshold:
        return "BUILD"
    if composite_score <= pass_threshold:
        return "PASS"
    return "INVESTIGATE"


def label_disagreements(
    anchor_scores: List[Dict],
    build_threshold: float,
    pass_threshold: float,
) -> List[Dict]:
    """Find anchors where ground-truth label disagrees with v0 classification.

    For BUILD-labeled rows: classification != BUILD → disagreement
    For PASS-labeled rows: classification != PASS → disagreement
    BUILD_DESTINATION_URBAN / BUILD_OUTDOOR_VARIANT: not asserted (their
    labels are not v0-composite-grounded).

    Returns a list of dicts with {location_id, label, composite_score,
    classification} for each disagreement, in order of severity (largest
    threshold delta first). Empty list = clean calibration."""
    issues: List[Dict] = []
    for a in anchor_scores:
        label = a["label"]
        if label in EXCLUDED_FROM_DERIVATION:
            continue
        # Saturated BUILD anchors don't trigger disagreement either —
        # they're already excluded from threshold derivation by the
        # calibration-boundary rule (anti-pattern #16).
        if label in BUILD_LABELS and _saturated(a):
            continue
        cls = classify(a["composite_score"], build_threshold, pass_threshold)
        if label in BUILD_LABELS and cls != "BUILD":
            delta = build_threshold - a["composite_score"]
            issues.append({
                "location_id": a["location_id"],
                "label": label,
                "composite_score": a["composite_score"],
                "classification": cls,
                "delta_from_threshold": delta,
            })
        elif label in PASS_LABELS and cls != "PASS":
            delta = a["composite_score"] - pass_threshold
            issues.append({
                "location_id": a["location_id"],
                "label": label,
                "composite_score": a["composite_score"],
                "classification": cls,
                "delta_from_threshold": delta,
            })
    issues.sort(key=lambda x: -abs(x["delta_from_threshold"]))
    return issues
