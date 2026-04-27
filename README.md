# padel-engine

Geographic scoring engine for premium indoor racket sports facility site selection. Identifies underserved affluent suburban markets for Tony's Racket — a padel + pickleball club rollup.

Outputs ranked sub-suburb geographies (zip codes / Census tracts) classified BUILD / INVESTIGATE / PASS, intended to drive real capital allocation decisions.

## Status

Phase 0 — pulling demographic data on calibration anchors before any methodology lock-in.

## Quick start

See CLAUDE.md for full operating context. See METHODOLOGY.md for scoring rationale.

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Sister project

brosundheim-pixel/opportunity-engine (laundromat rollup). Architectural patterns originated there; this is a clean reimplementation for padel.
