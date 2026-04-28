# CLAUDE.md — padel-engine

Operating context for any Claude Code session working in this repo. Read it fully before making changes. If something here conflicts with the codebase, the codebase wins for current state — but flag the conflict, the doc may be stale.

---

## What this is

A geographic scoring engine that identifies underserved affluent suburban markets for premium indoor racket sports facilities (padel + pickleball). Outputs ranked sub-suburb geographies (zip codes or Census tracts) classified BUILD / INVESTIGATE / PASS, intended to drive real capital allocation decisions for **Tony's Racket** — a premium indoor racket sports club rollup.

This is deal-sourcing infrastructure for a real business, not a research toy. Output flows into a $1.2-2.0M capital decision per location. Be conservative about claims. Surface uncertainty rather than projecting false precision.

Sister repo: `brosundheim-pixel/opportunity-engine` (laundromat rollup). Core scoring infrastructure was copied from there. Patterns that look generic across asset classes (geography iteration, drive-time isochrones, supply-gap math) come from that lineage. Padel-specific logic is in the demand signals, supply handling, and calibration anchors.

---

## The business this serves

**Tony's Racket** — premium indoor racket sports club chain targeting underserved affluent US suburbs.

### Facility model (location one)

- **Court config:** 4 padel + 2 pickleball
- **Footprint:** 18,000-20,000 sqft indoor, 22-24ft minimum clear ceiling
- **Real estate target:** light-industrial flex, warehouse conversion, former big-box retail with high ceilings
- **Capex all-in:** $1.2-2.0M (not $390-645K — earlier briefing numbers were undercooked. HVAC, electrical, fire suppression, permits, and TI on a 19K sqft industrial conversion add up fast.)
- **Staffing:** minimal — head pro / coaching partner + contracted services (cleaning, maintenance). NOT zero employees; that framing was aspirational and doesn't survive operating reality at this scale.
- **Pricing anchors (NTRC verified):** $59.99/mo pickleball, $159/mo padel, $209/mo all-sports premium
- **Stabilization target:** 300-400 members, $70-95K/mo revenue, $216-380K EBITDA
- **Framing:** real first location anchoring the rollup. NOT lean MVP. Capital deployment is real; due diligence bar is real.

### The thesis

Affluent US suburbs with strong tennis culture and no padel within 30-min drive are the highest-value first-mover sites. Sophisticated capital is in NYC and Miami. PE ignores individual suburban deals because they're too small. The suburban middle is uncontested.

Padel is 2-3 years behind pickleball on US adoption. 92% first-session retention. First-mover defensibility in a suburb that hasn't been identified yet beats second-mover position in any contested metro.

### Strategic refinement: target suburbs adjacent to proven urban operators

The strongest targets are affluent suburbs **15-25 minutes from an existing urban padel operator** that has done market education for free.

- DFW suburbs adjacent to NTRC Frisco (Southlake, Westlake, Colleyville, Prosper)
- Nashville suburbs adjacent to Sensa Padel Germantown (Brentwood, Belle Meade, Franklin, Forest Hills)
- Atlanta suburbs without urban anchor yet — higher uncertainty but strong demographics (Milton, Johns Creek)
- Chicago North Shore — no urban anchor yet, higher uncertainty (Winnetka, Glencoe, Lake Forest)

You inherit demand validation without paying urban rent or competing head-to-head.

---

## Critical geographic insight: sub-suburb resolution

**Do not score whole municipalities.** "Frisco" includes both NTRC's affluent core and newer working-class developments. "Sugar Land" includes both $300K and $1.5M home zip codes. Heterogeneity within suburbs matters more than between them.

The engine indexes at **zip code or Census tract level**, not at incorporated-place level. Score the demographic core of each suburb, not the suburb's mean.

### The industrial-pocket pattern

Every affluent suburb has a 1-2 mile pocket of older light-industrial flex on its edge — typically near a freeway interchange or rail corridor, originally built for distribution or auto service. Rent is $14-20/sqft vs. $20-28/sqft for prime suburban retail. Same suburb, 5-7 minute drive for affluent residents, 30-40% rent savings.

Examples:
- Brentwood TN: Wilson Pike / Old Hickory corridor (vs. Maryland Farms retail at $25-35/sqft)
- Frisco TX: eastern edge near rail corridor (vs. prime retail strips)

### Drive-time tolerance: padel ≠ boutique fitness

Boutique fitness retention data shows steep drive-time elasticity past 7-12 minutes; member churn doubles or triples beyond 12 minutes. **Padel does not behave the same way.** Scheduled social play format (members coordinate doubles times in advance) and scarcity of alternatives (no nearby substitute facility) raise tolerated drive times materially above boutique-fitness norms. Operator read: 15-min drive is acceptable when rent savings substantially offset churn cost; 7-min drive is preferred when comparable rent is available.

### Dual-catchment scoring (canonical)

The engine scores every candidate at **both** a 7-min and 15-min drive-time isochrone. The two radii correspond to two distinct site strategies:

- **7-min radius — cheap-pocket strategy.** Light-industrial flex pocket inside the affluent suburb, 5-7 min from member homes. Rent savings of 30-40% vs. prime suburban retail. Lowest churn risk.
- **15-min radius — tertiary-suburb strategy.** Cheap unincorporated industrial / exurban flex 15 min from member homes. Larger rent savings, higher churn risk, viable when rent gap is large enough to outweigh retention cost.

Both demand scores are reported per candidate. Operator picks the strategy per-site based on available real estate. Do NOT collapse to a single radius; do NOT pick one as canonical.

### Engine implications

1. Demand scoring at zip-code or Census-tract resolution within target suburbs
2. Every candidate receives a 7-min score AND a 15-min score
3. Output ranks both; operator selects strategy per candidate
4. Phase 2 capability: industrial-flex pocket identifier within BUILD-classified geographies, evaluated separately at 5-7 min and 15-min radii
5. The target unit is "high-demand sub-suburb + cheap-rent industrial pocket" — radius depends on what real estate is available

---

## Calibration approach

**Confidence level on current calibration:** see `METHODOLOGY.md` section "Calibration limitations and confidence level" — that section is the canonical statement of where the engine actually stands on anchor coverage and threshold-derivation rigor. Read it before making claims about engine maturity, especially in any capital-decision context.

### Why anchors matter more than weights

The scoring weights and tier assignments inherited from initial briefing are **v0 hypotheses, not validated methodology.** They reflect intuition about what should drive padel demand, not analysis of what does. Treating them as locked truth is a false-precision trap that won't survive due diligence.

The engine becomes trustworthy when its outputs match real-world judgment on a meaningful set of calibration anchors. Until then, weights are starting points to tune against anchor data.

### Anchor categories (target 5-7 total)

**BUILD anchors — operating premium padel clubs with verified economics:**

| Anchor | Location | Type | Status | Key data |
|---|---|---|---|---|
| NTRC | Frisco TX, 75033 | Suburban premium | Operating, validated | $159/mo padel, $209/mo all-sports, pickleball waitlisted |
| Sensa Padel | Nashville Germantown 37208 | **Urban premium (NOT suburban)** | Operating | Tiers $89/$199/$349, partner stack (Next Health, 1 Hotel, Industrious) |

Sensa is included with a caveat: it's urban, not suburban. The engine should score it BUILD on demand strength, but the strategy filter excludes urban locations from Tony's Racket targets. Sensa serves as a useful test that the demand model works in urban contexts, even though we wouldn't build there.

Need to add 1-2 more verified suburban BUILD anchors. Investigation candidates:
- United Padel (NJ/NY suburbs)
- Other operating suburban US padel clubs (Padel Federation US directory, Reddit r/padel, LinkedIn outreach to operators)

**PASS anchors — should clearly score low:**

Pick 3-4 intentionally:
- A rural town under 25K population (fails catchment)
- An affluent urban neighborhood already saturated with operators (fails supply gap)
- An affluent newer Sunbelt suburb with no established tennis culture (fails Tier 1 demand)
- A suburb already adjacent to an existing padel facility (fails supply gap)

**INVESTIGATE anchors — real-world hard cases:**

Aspirational; this category will be sparse. Look for suburbs where Life Time, Chicken N Pickle, or Aledo Racquet Club's developers seriously considered locations. Even one or two real INVESTIGATE anchors is meaningful.

### Anchor storage

Anchors live in `data/calibration/anchors.csv` checked into the repo. Schema: location identifier, ground-truth label (BUILD/PASS/INVESTIGATE), label source/justification, demographic snapshot, supply context.

### Calibration as regression test

On every weight or methodology change, the engine re-scores all anchors. If any anchor's predicted classification moves out of band vs. its ground-truth label, surface the disagreement to the operator. Do NOT silently auto-correct. The disagreement is information — it forces the question "is the anchor mislabeled, or is the methodology wrong?"

### What NOT to do in calibration

- **Single-anchor calibration is circular.** Testing whether the methodology preserves NTRC's classification only confirms the methodology produces what the methodology produced. Multiple anchors in different conditions constrain the model meaningfully.
- **Anchor labels are not immutable.** If repeated runs surface a labeled-PASS anchor that consistently scores high across methodology variants, the label may be wrong. Flag for review rather than forcing the model to match.

---

## Methodology — current v0 hypotheses

**These are starting hypotheses, not locked methodology.** Weights live in `scoring/weights.yaml` (config), not in this doc. Reasoning behind each weight lives in `METHODOLOGY.md`. Any weight change requires:

1. Updating `METHODOLOGY.md` with justification
2. Running the calibration regression suite
3. Surfacing the change to the operator

### Demand signal hypotheses (v0)

Treat the categorizations below as starting points to validate, not final weights.

**Hypothesized strong signals:**

- Tennis club density per capita within 15-min drive isochrone (especially private clubs)
- Private tennis club presence (members already paying $3-8K/yr for racket access — direct conversion proxy)
- Boutique fitness studio density per capita (SoulCycle, Orangetheory, Pure Barre — proves $150/mo recurring spend tolerance)
- Median home value $700K+ (stronger wealth signal than income alone)
- Drive time to nearest existing padel court (target: zero within 30-min drive)

**Hypothesized supporting signals:**

- Age 25-50 concentration as % of population
- Homeownership rate
- Golf club density
- Population within 15-min drive isochrone (true catchment, not municipal population)
- Google Trends padel interest at metro level — USE AS METRO-GATE ONLY, too noisy at sub-metro resolution

**Hypothesized weak signals:**

- Household income $150K+
- Youth sports infrastructure density
- Population growth rate
- Hispanic/Latino population — apply only in Latin-culture metros (Miami, Houston, Dallas). Pattern is regional cultural, not generic demographic.

### Signals discarded (do not re-add without strong evidence)

- Generic fitness club density (too broad; captured by boutique signal)
- Pickleball court density (wrong demographic; pickleball player ≠ padel convert)
- College-educated percentage (collinear with income)
- Health/obesity rates (captured by Tier 1)

### Aggregation structure

Currently: linear weighted sum of normalized signals → composite score → BUILD/INVESTIGATE/PASS classification at fixed thresholds.

This is probably wrong. Real demand is compensatory, not additive — strong tennis culture might compensate for marginal income, and vice versa. Phase 2 work: validate whether multiplicative gates or rank-based aggregation outperform linear weighting against the anchor regression suite.

### Threshold derivation

Thresholds for BUILD/INVESTIGATE/PASS classification should be **derived from anchor data, not picked by intuition.**

Process:
1. Pull demographic data on all calibration anchors
2. Compute composite score for each
3. Set BUILD threshold at or slightly below the lowest BUILD anchor's score
4. Set PASS threshold at or slightly above the highest PASS anchor's score
5. INVESTIGATE band is everything in between

**Do not lock thresholds before this calibration pass is complete.** Pre-run threshold guesses bias the entire output.

---

## Hard gates vs. composite scoring

**Two true hard gates** (below these, the market cannot work regardless of other strengths):

1. **Population in 15-min drive isochrone ≥ 100K** — below this, member math doesn't support 4 padel + 2 pickleball even on the wider catchment radius. Derived from Phase 0 anchor data (see METHODOLOGY "Catchment population hard gate — derivation from anchor data"): Roanoke AL PASS catchment 29K cleanly fails; NTRC suburban floor 892K, Sensa urban floor 559K, so 100K leaves ~5x margin for affluent suburbs not yet anchored. Gate is applied to the 15-min isochrone (the wider of the two) so candidates that fail the 7-min radius but clear the 15-min radius still survive.
2. **Median home value ≥ $500K (zip-code level)** — below this, the demographic willing to pay $200/mo membership doesn't exist in density

Everything else feeds the composite score. A sub-suburb can be weak on one signal and strong on another and still rank high.

**Do not hard-gate on income, age distribution, tennis density, or fitness density.** A sub-suburb might fail one of these by a small margin and still be a real BUILD candidate due to compensating strengths. Hard gates produce false negatives at far higher cost than the API spend they save.

---

## Run philosophy: score wide, filter on output ranking

**Aggressive output filtering, not aggressive input filtering.**

API spend per sub-suburb is roughly $0.11. Scoring 60 sub-suburbs is ~$7 and 45 minutes runtime. The cost of running wide is trivial. The cost of *missing a real BUILD candidate* because input filters were too aggressive is potentially seven figures over the rollup horizon.

Default approach:
1. Build a wide candidate universe (~30-50 sub-suburbs across 5-6 metros) clearing minimal hard gates
2. Score everything
3. Output top 5-7 BUILD candidates per metro for operator validation

The candidate universe is checked in as `markets/candidate_universe.yaml` so it's reproducible and addable-to without code changes.

### Watch for cherry-picking

When the engine surfaces a high-scoring sub-suburb the operator hasn't heard of (specific zip in McKinney TX, Cinco Ranch TX, Peachtree Corners GA), the temptation is to dismiss as engine error and focus on familiar names. Resist this. Surfacing markets the operator wouldn't have picked manually is the engine's whole value. Investigate before dismissing.

---

## Supply detection: manual, not automated

**Do not build automated padel-supply scraping into the engine.** The US padel universe is small (~180 facilities, ~688 courts as of early 2025). For any specific BUILD-classified candidate, the operator can verify supply manually in 2 minutes via Google Maps + Playtomic with higher accuracy and zero API cost.

The engine flags candidates based on demand signals. The operator confirms supply manually before promoting any candidate to investigation. Treat supply as a per-candidate manual override field, not an automated pipeline.

If automated supply ever becomes worth building (50+ candidates per run, frequent re-scoring), revisit. Not before.

---

## Supply scoring: demand-cluster-overlap model

This section is about HOW supply data enters the scoring math, not how it's collected (the section above covers collection). Both layers matter; they're separate decisions.

The wrong question: "how many padel facilities exist within X miles of the candidate?" Facility count is a coarse proxy that ignores who those competitors actually serve. Two facilities equidistant from a candidate can have wildly different supply impact based on whether their catchments overlap with the candidate's affluent demographic.

The right question: "how much of the candidate's affluent demand is already captured by existing competitors, and how much remains uncaptured?"

### Computation (v0 canonical — must be implemented from the first scoring run)

1. Compute candidate's 15-min demand isochrone (already built — `src/geo/isochrones.py`).
2. For each competitor padel facility within 30-min drive of candidate:
   - Compute competitor's 15-min catchment isochrone (same isochrone tooling, different origin).
   - Polygon-intersect candidate catchment with each competitor catchment.
   - Sum the **affluent-criteria-meeting population** (see anti-pattern #14) inside the intersection regions.
   - Dedupe overlapping competitors so a member counted as captured by competitor A is not double-counted by competitor B.
3. **Uncaptured affluent demand** = (candidate affluent catchment) − (sum of captured affluent population across all overlapping competitor catchments).
4. The uncaptured-affluent-demand value — NOT facility count — is the supply-gap signal that feeds composite scoring.

### Why this matters empirically

NTRC adjacency illustrates: facility count says "5 padel facilities exist in greater DFW within 15km of the candidate, supply is saturated." The overlap math says "of NTRC's affluent catchment of ~470K people, only ~X are inside any competitor's 15-min ring; the remaining ~Y are uncaptured affluent demand." The two answers can point in opposite directions.

This is the canonical v0 supply model. Facility count is explicitly an anti-pattern (#13).

---

## Critical anti-patterns

These have been considered and discarded. Do not reintroduce without explicit operator approval.

1. **City population as catchment proxy.** Always use 15-minute drive-time isochrones. A small incorporated town in a dense suburban corridor has 10-20x its city population within driving distance.
2. **Straight-line distance for competition radius.** Always use 30-minute drive-time isochrones. Freeways, rivers, and county lines distort access.
3. **Whole-municipality scoring.** Always score at zip-code or Census-tract resolution.
4. **Pickleball density as padel demand signal.** Wrong demographic.
5. **Generic Hispanic-population weighting.** Apply only in Latin-culture metros.
6. **National Google Trends at sub-metro resolution.** Use as metro gate only.
7. **Aggressive input thresholds.** Score wide, filter on output ranking.
8. **Single-anchor calibration.** Use multi-anchor regression suite.
9. **Auto-classifying South Florida as uncontested.** Already saturated with sophisticated operators (Reservoir, Pura, Padel Haus, etc.). Down-weight or exclude by default; operator override only.
10. **Single-radius catchment scoring.** Padel drive tolerance differs from boutique fitness; tertiary-suburb / 15-min sites are viable when rent savings outweigh churn cost. Score every candidate at BOTH 7-min and 15-min radii; let the operator pick the strategy per candidate. Do not collapse to one radius.
11. **California suburbs without economics gate.** Atherton/Los Altos/Woodside have demand but real estate costs break unit economics. Score for completeness; expect economic gate to filter.
12. **Threshold-setting before anchor calibration.** Derive thresholds from anchor data, not from intuition.
13. **Treating supply as facility-count-within-radius.** Real supply pressure depends on competitor catchment overlap with the candidate's demand cluster. Engine must compute polygon intersection between competitor isochrones and candidate demand isochrone, then aggregate population in the uncaptured residual. See "Supply scoring: demand-cluster-overlap model" below.
14. **Treating total catchment population as demand signal.** Total catchment overstates addressable demand in mixed-density zips (e.g., Brooklyn Heights's 4.7M total catchment massively overstates the affluent target). Engine must compute affluent-criteria-meeting population (income above threshold + age 25-50 + homeowner-rate gate) within the isochrone, not raw total population. See METHODOLOGY "Affluent-demand-only catchment" for the v0-canonical math.
15. **Relying on a single demographic gate (site-level OR catchment-level alone).** Layered gating required: candidate site must pass own demographic floors (income, home value, ownership at the zip level) AND catchment-affluent population must clear floor. Position-in-metro can lift an unaffluent candidate's catchment-affluent number via neighboring affluent zips (Winder GA empirically: 33% affluent ratio, 59K affluent catchment despite zip-level home value $245K). Candidate-site filter prevents that failure mode; catchment-affluence filter prevents the "isolated affluent enclave with no addressable demand pool" failure. Either alone is insufficient. See METHODOLOGY "Layered gating: candidate-site demographics AND catchment affluence".
16. **Treating high capture_share as definitive PASS signal.** Saturated markets can support new entrants when existing operators are at capacity (waitlists, court-time scarcity, member caps). v0 cannot distinguish capacity-constrained saturated markets from genuinely served-out markets without capacity data. Saturated BUILD anchors (capture_share > 0.85) are excluded from BUILD floor derivation as a known v0 limitation. v2 fix: scrape waitlist / court-time / member-cap signals from competitor sites. See METHODOLOGY "Calibration boundary: saturated markets".
17. **Estimating construction costs or operating economics quantitatively in the engine.** Numerical estimates of construction cost ($/sqft), property tax ($/year), permitting timeline (days), or unit-economics with 30-40% error bands undermine engine credibility. Use categorical `business_climate_tier` (4-tier framework: FAVORABLE / NEUTRAL / PREMIUM / PROHIBITIVE) instead. Tier signals an OUTPUT FLAG; never enters score computation. Real numbers belong in underwriting (site-specific lease quotes, real construction bids), not the screening engine. **If you find yourself wanting to add a "$/sqft" or "$/year property tax" field to anchors.csv or candidate_universe.yaml or any signal-input pipeline — refuse and surface to operator.** State defaults + metro overrides live in `markets/business_climate_tiers.yaml`. See METHODOLOGY "Business climate tier (v0 categorical, not quantitative)".

---

## Target markets (priority order)

### Tier 1 — proven metro demand, target sub-suburbs adjacent to operating clubs

1. **DFW suburbs adjacent to NTRC Frisco** — Southlake, Westlake, Colleyville, Prosper, Highland Park / University Park (specific zip codes only)
2. **Nashville suburbs adjacent to Sensa Germantown** — Brentwood, Belle Meade, Franklin (specific zip codes), Forest Hills

### Tier 2 — strong demographic candidates, no urban anchor yet (higher uncertainty)

3. **Atlanta suburbs** — Milton, Johns Creek, Alpharetta (zips 30022, 30005), Sandy Springs (Buckhead-adjacent zips), Dunwoody (specific zips)
4. **Chicago North Shore** — Winnetka, Glencoe, Lake Forest, Hinsdale, Northbrook, Highland Park
5. **Houston affluent** — West University Place, Bellaire, Memorial Villages (Hunters Creek/Bunker Hill/Piney Point), The Woodlands (specific affluent zips), Sugar Land (Riverstone/Greatwood)

### Tier 3 — score for completeness, expect economic constraints

6. **East Coast wealth corridor** — Bethesda/Potomac MD, Greenwich CT, Wellesley/Weston MA, Scarsdale/Bronxville NY
7. **California peninsula** — Atherton, Los Altos, Woodside (likely fail economics gate due to real estate cost)

### Default exclusions

- South Florida — saturated with sophisticated operators
- All urban core neighborhoods — outside strategic target

---

## Data sources

- **Census ACS** (American Community Survey) — demographics, income, home value, age, homeownership at zip-code or tract level. Free with API key. 5-year estimates.
- **Google Maps Places API** — tennis clubs, fitness studios, golf clubs within isochrones. Paid, rate-limited. Cache aggressively.
- **Google Maps Routes API** — drive-time isochrones. 7-min and 15-min for demand catchment (dual-radius scoring), 30-min for supply context if used. Paid. Cache by origin lat/lng + radius + time-of-day bucket.
- **Playtomic** — padel facility supply (manual reference, not automated scrape).
- **Google Trends** — metro-level padel interest (gate only).

**Persist all raw API responses to `data/raw/`** before transformation. Reproducibility matters more than freshness for an engine driving capital decisions. Any score should be reproducible from cached data.

---

## Code conventions

(Verify against actual repo state; update this section as the layout evolves.)

- **Language:** Python 3.11+
- **Backend:** FastAPI for any API surface
- **Storage:** SQLite for local development, Postgres if/when deployed
- **Spatial:** `shapely` for geometry, `geopandas` for spatial joins
- **Data:** `pandas` for tabular work, `pydantic` for schemas
- **Testing:** `pytest` with fixtures for cached API responses (offline-runnable test suite)
- **Linting/format:** `ruff` for both
- **Dependency management:** `uv` if present, otherwise `pip` + `requirements.txt`

Style:
- Type hints on all function signatures
- Pydantic models for any data crossing module boundaries
- Cache anything that hits a paid API
- Pure functions for scoring math (testable, reweightable, explainable)
- **Never put weights or thresholds in code — always in config**

---

## Repository layout

(Verify against actual repo; update as layout evolves.)

```
padel-engine/
├── CLAUDE.md                   # this file (operating context)
├── METHODOLOGY.md              # justification for each signal weight
├── README.md                   # human-facing description
├── pyproject.toml
├── scoring/
│   ├── weights.yaml            # all signal weights (canonical source)
│   └── thresholds.yaml         # BUILD/INVESTIGATE/PASS cutoffs (derived from anchors)
├── markets/
│   ├── candidate_universe.yaml # sub-suburbs to score per metro
│   └── filters.yaml            # hard gates (population, home value)
├── src/
│   ├── data/                   # API clients, raw data persistence
│   │   ├── census.py
│   │   ├── google_places.py
│   │   ├── google_routes.py
│   │   └── trends.py
│   ├── geo/                    # isochrones, spatial joins
│   ├── scoring/
│   │   ├── signals.py          # individual signal computation
│   │   ├── aggregate.py        # composite score from weighted signals
│   │   └── classify.py         # BUILD/INVESTIGATE/PASS logic
│   └── api/                    # FastAPI surface if exposed
├── data/
│   ├── raw/                    # cached API responses, never edit by hand
│   ├── processed/              # cleaned, joined data
│   ├── calibration/
│   │   └── anchors.csv         # ground-truth labeled anchors
│   └── outputs/                # scored markets, ranked lists per metro
├── notebooks/                  # exploration only, not production logic
└── tests/
    ├── fixtures/               # cached API responses for offline testing
    ├── test_calibration.py     # regression test on anchor predictions
    └── test_*.py
```

---

## Current priorities

In rough order. Update this list as work completes.

### Phase 0 — foundations (in order)

1. **Pull demographic data on calibration anchors.** NTRC zip codes (75033, 75034, 75035) and Sensa Germantown (37208), plus 2-3 obvious-PASS comparisons. Output: populated `data/calibration/anchors.csv` with real Census ACS numbers. **Until this is done, every threshold is a guess.**
2. **Derive hard gate thresholds from anchor data.** Set population minimum and home value minimum at or slightly below the lowest BUILD anchor. Document in `METHODOLOGY.md`.
3. **Dual-radius drive-time isochrones.** Replace any radius-based or straight-line lookup with drive-time isochrones from Google Routes API. Compute BOTH 7-min and 15-min isochrones per candidate; cache both. Demand signals that aggregate over a catchment (population, tennis density, fitness density, etc.) must be reported at both radii.

### Phase 1 — first real run

4. **Build candidate universe.** Compile zip-code-resolution candidate list across DFW, Nashville, Atlanta, Chicago North Shore, Houston affluent. Target 30-50 sub-suburbs total. Check in as `markets/candidate_universe.yaml`.
5. **Score the universe.** Run engine against full candidate list. Output ranked CSV per metro.
6. **Calibration regression test.** Lock anchor predictions into a test suite. Any methodology change disagreeing with anchor labels surfaces a flag.
7. **Top 5-7 BUILD candidate output per metro.** For operator manual supply verification and real-estate investigation.

### Phase 2 — sharper resolution

8. **Industrial-pocket finder.** For BUILD-classified sub-suburbs, identify light-industrial flex pockets within 5-7 min drive of demographic centroid.
9. **Aggregation structure validation.** Test whether multiplicative gates or rank-based aggregation outperform linear weighting against anchor regression suite.
10. **Smoke-test target picker.** Output single highest-confidence BUILD candidate per metro for deposit-based smoke test ($100-200 founding member deposits, 75-100 deposit threshold before lease commitment).

### Not yet priorities (track but don't build)

- Real estate vacancy/rent data integration
- Zoning/permitting feasibility scoring
- Cross-metro portfolio optimization (only relevant after locations 2-3)
- Public web UI
- Automated padel-supply scraping (manual is fine at current volume)

---

## Decisions that need operator input before changing

Surface to Brody, do not change unilaterally:

- Tier assignments or weights for any demand signal (after Phase 0 calibration)
- Hard gate threshold values (after Phase 0 calibration)
- Calibration anchor list and labels
- Default exclusion of South Florida
- Default exclusion of urban-core geographies
- Target metro priority order
- Capex assumption ($1.2-2.0M) — affects what economics make a market viable, which feeds back into thresholds
- Switching from manual supply detection to automated

---

## Things to flag, not silently fix

Surface to operator instead of resolving:

- Tier 1 signal returning null or unexpectedly low values for a known-good market
- API quota approaching limits
- New padel facilities appearing in target markets (changes competitive landscape)
- Discrepancies between anchor labels and engine predictions
- Discrepancies between Google Maps and Playtomic supply counts for the same facility
- Methodology changes that move BUILD anchors out of expected band
- Geocoding mismatches (anchor address resolves to wrong zip)

---

## Out of scope for this repo

This engine outputs scored sub-suburb geographies. It does NOT:

- Underwrite specific real estate deals (separate financial model)
- Forecast member acquisition curves (separate ramp model)
- Handle facility operations, booking, or member management (PingPod or alternative platform)
- Score asset classes other than premium indoor racket sports

If a request requires any of the above, ask before building it here. The right answer is usually a separate tool.

---

## Operator context

Brody Sundheim is the operator. He's 18, headed to Wharton fall 2026, working with parental capital backing. He prefers honest assessment over encouragement, dislikes over-explanation, and wants thorough research before capital deployment.

When in doubt:
- Surface tradeoffs, don't pick a path silently
- Flag uncertainty rather than projecting false confidence
- Show your work — the eventual audience for engine outputs is his father, who will see through false precision
- Treat methodology choices as defensible to a sophisticated investor, not as internal optimizations

The engine's outputs will at some point be presented to dad and potentially to William Taubman (Long Lake founder, family connection). Anything that wouldn't survive their diligence shouldn't be in the engine.
