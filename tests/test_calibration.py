"""Calibration regression test.

Reads anchors.csv after a scoring run and asserts that ground-truth labels
are consistent with v0 composite scores against derived thresholds.

A future methodology change (different weights, different formulation,
different signal definition) that moves any BUILD anchor below the BUILD
threshold OR any PASS anchor above the PASS threshold surfaces here as a
test failure. That's the intended behavior — the test forces an explicit
operator decision: is the methodology change wrong, or is the anchor label
wrong?

BUILD_DESTINATION_URBAN (Sensa) and BUILD_OUTDOOR_VARIANT (Alpharetta) are
NOT asserted — their labels reflect demand mechanisms the v0 composite
doesn't model.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.scoring.classify import (
    BUILD_LABELS,
    EXCLUDED_FROM_DERIVATION,
    PASS_LABELS,
    SATURATED_CAPTURE_THRESHOLD,
    classify,
    derive_thresholds,
)

ANCHORS_CSV = REPO_ROOT / "data" / "calibration" / "anchors.csv"


def _load_scored_anchors():
    with ANCHORS_CSV.open() as f:
        rows = list(csv.DictReader(f))
    scored = []
    for row in rows:
        score_str = (row.get("composite_score_v0") or "").strip()
        if not score_str:
            continue
        capture_str = (row.get("capture_fraction_v0") or "").strip()
        capture = float(capture_str) if capture_str else None
        scored.append({
            "location_id": row["location_id"].strip(),
            "label": row["ground_truth_label"].strip(),
            "composite_score": float(score_str),
            "capture_fraction": capture,
        })
    return scored


def test_anchor_scores_match_labels():
    """Every BUILD-labeled anchor scores ≥ BUILD threshold;
    every PASS-labeled anchor scores ≤ PASS threshold."""
    scored = _load_scored_anchors()
    if not scored:
        pytest.skip("anchors.csv has no composite_score_v0 — run scripts/run_anchor_scoring.py first")

    build_thr, pass_thr, separation_clean = derive_thresholds(scored)

    assert separation_clean, (
        f"Threshold separation NOT clean: PASS_threshold={pass_thr:.4f} >= "
        f"BUILD_threshold={build_thr:.4f}. The v0 weights/formulation cannot "
        "distinguish BUILD from PASS at the current anchor distribution."
    )

    failures = []
    for s in scored:
        if s["label"] in EXCLUDED_FROM_DERIVATION:
            continue
        # Saturated BUILD anchors are calibration-boundary cases per
        # CLAUDE.md anti-pattern #16 — excluded from threshold derivation
        # AND from this BUILD-classification check. Their high capture
        # reflects v0's inability to distinguish "served-out" from
        # "operators at capacity"; we don't fail the test for that.
        cf = s.get("capture_fraction")
        if (s["label"] in BUILD_LABELS
                and cf is not None
                and cf > SATURATED_CAPTURE_THRESHOLD):
            continue
        cls = classify(s["composite_score"], build_thr, pass_thr)
        if s["label"] in BUILD_LABELS and cls != "BUILD":
            failures.append(
                f"{s['location_id']} (BUILD): scored {s['composite_score']:.4f} "
                f"→ classified {cls} (build_threshold={build_thr:.4f})"
            )
        elif s["label"] in PASS_LABELS and cls != "PASS":
            failures.append(
                f"{s['location_id']} (PASS): scored {s['composite_score']:.4f} "
                f"→ classified {cls} (pass_threshold={pass_thr:.4f})"
            )

    assert not failures, "Anchor label disagreements:\n  " + "\n  ".join(failures)
