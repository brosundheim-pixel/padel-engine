# METHODOLOGY

Justification log for every scoring decision. Each weight, threshold, and signal lives here with its rationale. Update this document when changing scoring/weights.yaml or scoring/thresholds.yaml.

## Status

v0 — pre-calibration. No weights or thresholds have been validated against anchor data yet. Treat all current values as starting hypotheses.

## Calibration anchors

See data/calibration/anchors.csv. Phase 0 priority is populating this file with real Census ACS data for:

- NTRC Frisco TX (zip 75033, 75034, 75035) — suburban premium BUILD
- Sensa Padel Nashville (zip 37208) — urban premium BUILD (with caveat — strategy excludes urban)
- 1-2 additional verified suburban BUILD anchors (TBD)
- 3-4 obvious-PASS comparisons (TBD)

## Signal weights

See scoring/weights.yaml. Rationale for each weight goes here once derived from anchor calibration.

## Thresholds

See scoring/thresholds.yaml. Hard gate values and BUILD/INVESTIGATE/PASS cutoffs go here once derived from anchor scores.

## Change log

- Repo initialized. No methodology decisions yet.
