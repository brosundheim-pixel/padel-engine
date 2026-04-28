# METHODOLOGY

Justification log for every scoring decision. Each weight, threshold, and signal lives here with its rationale. Update this document when changing scoring/weights.yaml or scoring/thresholds.yaml.

## Status

v0 — pre-calibration. No weights or thresholds have been validated against anchor data yet. Treat all current values as starting hypotheses.

## Calibration limitations and confidence level

Honest read on engine maturity. Update as anchors are added.

- **Current anchor base:** 4 BUILD-class rows (3 NTRC zips same operator + 1 Sensa urban) + 4 PASS rows.
- **Effective unique BUILD operators:** 2 (NTRC, Sensa). The 3 NTRC zip rows are correlated — same operator, same metro, same demographic profile — and contribute one effective BUILD-operator data point, not three.
- **Effective unique BUILD metros:** 2 (DFW, Nashville).
- **Metros with zero anchors:** Atlanta, Chicago, Houston, NYC suburbs, California, East Coast wealth corridor. Exactly the metros CLAUDE.md flags as next-priority targets.
- **PASS anchor coverage:** Roanoke (rural / fails catchment) + Winder (Sunbelt unaffluent / fails demographic gate) + Miami Beach (saturated urban / fails supply policy) + Brooklyn Heights (affluent but supply-adjacent / fails supply gap). One anchor per failure mode — useful for direction but no statistical rigor on any single gate.
- **Confidence level on current thresholds:** **low — tentative**. Sufficient to begin v0 scoring runs but **not adequate for capital decisions** standalone.
- **Required additions for "Phase 0 complete":** 2-3 more verified suburban BUILD anchors from distinct metros and operators. 2-3 more PASS anchors that fail on demographics rather than supply or policy (current PASS set leans heavily on supply/policy failures).
- **v0 scoring math implementation requirements:** when scoring code gets written, it MUST use the demand-cluster-overlap supply model ("Supply-overlap-with-demand methodology" below) and the affluent-criteria-only demand catchment ("Affluent-demand-only catchment" below) from day one. The simpler facility-count and total-catchment models are explicitly wrong (CLAUDE.md anti-patterns #13 and #14). Building scoring on the wrong primitives now would force a rip-and-replace later.

This section is the operating honest read on engine maturity. Anything downstream — threshold values, weights, classification — inherits the limitations stated here.

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

## Catchment radius — dual-radius scoring

The engine computes every catchment-aggregated signal (population, tennis club density, boutique fitness density, golf club density, drive-time-to-nearest-padel adjacency) at TWO drive-time isochrones per candidate: 7-min and 15-min. Two demand scores are reported per candidate.

Two strategies, two radii:

- **7-min radius — cheap-pocket strategy.** Light-industrial flex pocket inside the affluent suburb, 5-7 min from member homes. Rent savings 30-40% vs. prime suburban retail. Lowest churn risk. Preferred when comparable rent is available within the 7-min ring.
- **15-min radius — tertiary-suburb strategy.** Cheap unincorporated industrial / exurban flex 15 min from member homes. Larger rent savings, higher churn risk. Acceptable when rent savings substantially outweigh churn cost.

### Rationale

Boutique fitness retention literature shows steep drive-time elasticity past 7-12 minutes; member churn doubles or triples beyond 12 minutes. Operator read: padel does NOT behave the same way. Two specific format properties raise drive tolerance:

1. **Scheduled social play.** Padel members coordinate doubles times in advance; sessions are calendared, not impulse drop-ins. Drive friction matters less when the visit is pre-committed.
2. **Scarcity of alternatives.** Padel supply in the US is sparse (~180 facilities). A member willing to play padel has no nearby substitute facility, so price-elasticity-of-distance compresses.

Hard gate (population ≥ 100K within 15-min isochrone — see "Catchment population hard gate" below) applies on the wider radius so a candidate failing 7-min but clearing 15-min still survives input filtering. Operator selects strategy per-candidate based on real-estate availability in the surrounding rings.

### Validation status

Dual-radius scoring is operator-driven hypothesis. Optimal radius likely varies by market real estate availability. Validate against operating data once 2-3 locations exist.

## Pop-weighted centroid: empirical validation

Isochrone origins use the population-weighted ZCTA centroid (sum(tract_centroid × tract_population) / sum(tract_population)), not the geographic polygon centroid. Tract centroids come from Census 2023 Gazetteer (which is itself the pop-weighted internal point per tract). Tract populations come from ACS 2023 5-year B01003_001E.

The choice was operator-driven hypothesis: people don't live evenly across a ZCTA, so distance-from-polygon-center misrepresents distance-from-actual-residents. The Phase 0 anchor pipeline run validated the hypothesis against real anchor data.

### Displacement results across 8 anchors

| anchor | label | geo→pop displacement (km) |
|---|---|---|
| 75033 NTRC Frisco | BUILD | 0.76 |
| 75034 NTRC Frisco | BUILD | 1.33 |
| 75035 NTRC Frisco | BUILD | 1.57 |
| 37208 Sensa Germantown | BUILD_DESTINATION_URBAN | 0.63 |
| 36272 Roanoke AL | PASS | **2.67 ⚠** |
| 33139 Miami Beach | PASS | 0.64 |
| 30680 Winder GA | PASS | **4.32 ⚠** |
| 11201 Brooklyn Heights | PASS | 0.21 |

### Findings

Displacement >2 km flagged as material. Two PASS anchors triggered:

- **Roanoke AL (2.67 km).** Rural ZCTA polygon spans large area of farmland. Geo centroid lands in unpopulated countryside; pop centroid lands in the actual town core where residents live. Isochrone built from geo centroid would model drive-time from the wrong origin.
- **Winder GA (4.32 km).** Population concentrated on the NW (Athens / Atlanta-adjacent) edge of the ZCTA. Geo centroid lands in the rural east. 4.3 km displacement = >2 minutes of drive time — material at the 7-min radius.

Affluent suburban BUILD anchors all show <1.6 km displacement. NTRC Frisco zips and Sensa Germantown have populations distributed reasonably evenly across their ZCTAs, so geo and pop centroids are close. Brooklyn Heights at 0.21 km is essentially identical (dense urban grid, no empty corners).

### Conclusion

Pop-weighting matters most for the candidates we're least likely to BUILD. For affluent dense suburbs (the actual target set), the methodology adds rigor without changing outcomes meaningfully. For rural and exurban anchors (the negative-control PASS set), it materially relocates the isochrone origin and prevents false catchment readings driven by the wrong geographic anchor.

Run cost: ~50MB Census ZCTA-tract crosswalk + ~7MB tract Gazetteer + per-county ACS bulk fetches (cached). Marginal cost per new candidate ZCTA: <1 sec after initial setup.

## Known methodology limitations

### Convex-hull isochrone construction (v0)

Isochrones are built as the convex hull of OSM nodes reachable within the drive-time budget. Empirical Phase 0 results show two distinct failure modes:

- **Inland metros: hull overestimates by 1.5-2.5x.** DFW 15-min isochrones return 750-1000 km² convex hull vs ~300-400 km² true reachable area. The hull bridges gaps between highway spokes, capturing area between radial corridors that isn't actually reachable in the time budget.
- **Water-bounded metros: hull approximates true area.** Miami Beach 15-min hull = 237 km², Brooklyn Heights 15-min hull = 389 km². Coastal water and dense urban grids constrain the reachable polygon to roughly its true shape — the hull doesn't have empty radial gaps to bridge.

Net effect: zip-membership tests have false positives at the boundary in inland metros (zips inside the hull but not in the true reachable area get counted in catchment). For Phase 0 anchor-floor derivation this is an acceptable signal-vs-noise tradeoff; for finer candidate scoring at the BUILD/INVESTIGATE boundary it is not.

**Phase 2 fix:** swap convex hull to alpha-shape (`alphashape` library) or buffer-union of reachable nodes. Triggers reconsideration once isochrone-driven false positives start appearing in BUILD candidate ranking.

## Catchment population hard gate — derivation from anchor data

`scoring/thresholds.yaml hard_gates.population_15min_isochrone_min = 100000`. Anchor-derived, not picked by intuition.

### Empirical anchor catchments (15-min isochrone, ACS 2023 5-year tract pop)

| anchor | label | 15-min catchment |
|---|---|---|
| ntrc_frisco (75033) | BUILD | 891,607 |
| ntrc_frisco_75034 | BUILD | 1,272,386 |
| ntrc_frisco_75035 | BUILD | 922,750 |
| sensa_germantown (37208) | BUILD_DESTINATION_URBAN | 558,744 |
| roanoke_al (36272) | PASS | **29,312** ← only PASS that fails on catchment alone |
| miami_beach (33139) | PASS | 652,189 |
| winder_ga (30680) | PASS | 177,085 |
| brooklyn_heights (11201) | PASS | 4,696,986 |

### Derivation logic

- **Lowest BUILD-class catchment:** Sensa Germantown 559K (urban). Suburban BUILD floor (NTRC zips): 892K.
- **Only PASS that fails on catchment:** Roanoke AL 29K. Other PASS anchors clear catchment but fail on supply (Brooklyn Heights, Miami Beach), home value (Winder), or default policy (Miami Beach urban exclusion).
- **Gate value: 100K.** Cleanly excludes Roanoke (29K). Provides 5.6x margin below Sensa's 559K BUILD floor — leaves room for affluent suburbs not yet anchored that may have smaller catchments. East Coast wealth corridor (Greenwich CT, Bethesda MD) and California peninsula (Atherton, Los Altos) likely have <500K 15-min catchment due to lower metro population density; setting the gate too tight could false-negative those before they're scored.
- **Could be tightened to 200K** once East Coast / California anchors are added without affecting current BUILD anchor inclusions. Defer until that data exists.
- **Do NOT make catchment the only PASS-discriminating gate.** Three of four PASS anchors clear 100K (Miami Beach 652K, Winder 177K, Brooklyn Heights 4.7M). They are correctly excluded by other mechanisms — supply policy, home-value gate, urban exclusion. Catchment gate's job is the rural-pop case only.

### Position-in-metro effect

Catchment population favors central locations within a metro, not just demographically affluent zips. See "Position-in-metro effect on catchment" below for the NTRC 75034 vs 75033 finding (1.27M vs 892K despite being 5 miles apart).

## Position-in-metro effect on catchment

Catchment population is geometrically driven, not just demographically driven. The same demographic profile in a peripheral suburb yields lower catchment than in a central suburb.

### Empirical NTRC finding

Three NTRC zips, ~5 miles apart, similar demographics:

| zip | 15-min catchment | position |
|---|---|---|
| 75033 | 892K | northern edge of Frisco — 15-min ring partly empties to north |
| 75034 | **1,272K (+43% vs 75033)** | central south Frisco — 15-min ring reaches deep into Plano + McKinney + 75033 itself |
| 75035 | 923K | east Frisco — ring partly extends into less-developed east |

75034 sits more centrally within the DFW metro grid than 75033 or 75035. Its 15-min isochrone catches more dense suburban zips before hitting metro periphery. Same suburb, same wealth profile, materially different catchment-pop signal.

### Implication for engine design

- **Per-capita signals normalize this naturally.** When demand signals (tennis density, fitness density) are scored as count-per-100K-residents over the catchment, the position effect cancels out — both 75033 and 75034 will have similar density readings even though 75034's denominator is 43% larger.
- **Catchment-pop hard gate slightly favors central locations.** A peripheral suburb with strong demographics but smaller catchment (e.g., a hypothetical Houston suburb on the metro edge) could fail the 100K gate even if its per-capita signals are excellent. Current 100K gate is conservative-low specifically to avoid this false-negative pattern.
- **Operator-facing implication.** When ranked output surfaces a candidate with strong demographics but lower-than-peer catchment, treat it as a position-in-metro signal, not a demand-quality signal. Don't auto-downrank — investigate whether the smaller catchment reflects real market constraint (sparse adjacent population, water/highway barrier) or just metro-edge geometry.
- **Do NOT add a "catchment-pop weight" to the composite score.** It would double-count: catchment is already the denominator under per-capita signals, AND the floor under hard-gate eligibility. Weighting it as a third use would punish peripheral candidates a third time.

### Validation status

NTRC data is the only direct evidence so far. Hypothesis to test against future anchors: do peripheral-but-affluent suburbs (e.g., a Houston Energy Corridor zip vs. an inner Memorial Villages zip) show similar 30-50% catchment-pop differences with comparable demographics? If yes, position-in-metro effect is generalized. If no, the NTRC finding may be DFW-specific (sprawl + grid).

## Supply-overlap-with-demand methodology (v0 canonical)

**Decision:** the supply-pressure signal feeding scoring is *uncaptured affluent demand within the candidate's catchment*, NOT facility count within a radius. This is the v0-canonical model and must be implemented from the first scoring run.

### Operator rationale

Facility count is a coarse proxy that ignores who competitors actually serve. Two competitors equidistant from a candidate can have wildly different supply impact based on whether their catchments overlap with the candidate's affluent demographic. NTRC adjacency illustrates: facility-count says "5 padel facilities exist in greater DFW within 15km of a candidate, supply is saturated"; the overlap question is "of that candidate's affluent catchment, how much is *already inside* a competitor's 15-min ring vs. genuinely uncaptured?" The two framings can point in opposite directions on the same site.

### Math sketch

For each candidate ZCTA:

1. Compute candidate's 15-min demand isochrone P_c (existing infrastructure: `src/geo/isochrones.py`).
2. Compute candidate's *affluent* catchment population A_c (see "Affluent-demand-only catchment" below) inside P_c.
3. For each competitor padel facility within 30-min drive of the candidate:
   - Compute competitor i's 15-min catchment isochrone P_i.
   - Polygon-intersect P_c ∩ P_i → I_i.
   - Sum affluent population inside I_i → captured_i.
4. Dedupe overlapping competitors so a member counted as captured by competitor A is not double-counted by competitor B (union of all intersections, not sum).
5. Total_captured = affluent population inside ∪ I_i.
6. **Uncaptured affluent demand = A_c − Total_captured.** This is the supply-side signal feeding scoring.

Larger uncaptured value = better supply position. Zero uncaptured = fully served by competitors. Negative is impossible by construction.

### Implementation prerequisites (already built)

- Isochrone polygons: `src/geo/isochrones.py get_isochrone()`
- Tract centroids + populations: `src/data/census_tracts.py`
- Catchment population aggregation: `src/geo/catchment_population.py compute_catchment_population()`

What still needs to be built: (a) affluent-tract filter at the tract level (see next section), (b) polygon intersection logic via shapely, (c) a per-candidate competitor enumeration that pulls competitor isochrones from cache.

### DFW padel ground truth (post-bleed-fix)

Pre-bleed-fix Google Places data falsely included Atlanta and Houston padel facilities in DFW catchments because Text Search `locationBias` allowed Google to relax geographically when the local 15km circle had few real matches. (Note: Google Places API New `locationRestriction.circle` is not valid for Text Search — only Search Nearby. Text Search must stay on `locationBias.circle` and apply a client-side haversine cutoff.) After adding the post-fetch 15km haversine filter to Text Search, the corrected DFW supply count is:

- **DFW padel within 15km of NTRC centroid: 1 facility** (NTRC itself). Pre-fix value was 4.

This materially changes the Frisco-adjacent suburb supply gap. Earlier corrupted data suggested the Frisco market was already half-served by 4 surrounding padel facilities; the corrected data shows Frisco-adjacent suburbs north and east of NTRC have a substantially cleaner supply gap than that estimate implied.

For comparison, post-fix padel-supply ground truth at other anchors:

- **Cresskill NJ: 10 padel facilities within 15km** — NYC-suburbs metro has substantial padel buildout already; the BUILD anchor sits in a competitive market. Supply-overlap math at Cresskill candidates is load-bearing.
- **Dedham MA: 7** — Boston-area padel growing fast.
- **Alpharetta GA: 2** — Atlanta suburban supply still thin.
- **Sensa Germantown: 3** — Nashville urban density.
- **Miami Beach: 27**, **Brooklyn Heights: 31** — saturated urban (matches existing PASS labels).
- **Winder GA: 0**, **Roanoke AL: 0** — sparse.

These corrected numbers should drive supply-overlap modeling for Phase 1 candidates in each metro.

## Affluent-demand-only catchment (v0 canonical)

**Decision:** demand-side catchment population is the sum of population from tracts that *independently* meet affluent criteria, NOT total tract-population sum.

### Operator rationale

Brooklyn Heights illustrates the pathology: 4.7M total catchment because the 15-min isochrone from Brooklyn Heights covers all five boroughs and slices of NJ. Most of those 4.7M people are not the demographic willing to pay $159-$209/mo for padel. Total catchment overstates addressable demand 10-50x in mixed-density urban-adjacent geographies. Comparing NTRC's 892K total catchment to Brooklyn Heights's 4.7M total catchment makes Brooklyn Heights look 5x stronger when in real-affluent terms it is likely smaller.

### Math sketch

For each candidate isochrone P_c:

1. Enumerate tracts whose centroid falls inside P_c (existing logic).
2. For each such tract, look up tract-level ACS demographics: median household income, median age (or age-25-50 share), homeownership rate.
3. Apply affluent-criteria gate per tract. v0 starting criteria (revisable post first scoring run):
   - Tract median household income ≥ $100,000
   - Tract pct_age_25_49 ≥ 25% (excludes nursing-home-dominant tracts and college-dorm tracts)
   - Tract homeownership rate ≥ 50% (excludes high-renter density urban cores)
4. Sum tract populations only for tracts that pass all three gates → A_c.
5. **A_c is the affluent-demand catchment, used as the denominator for per-capita signals AND as the population pool for supply-overlap math.**

### Notes on the criteria

- These are tract-level criteria, NOT zip-level. ZCTA-level demographics (which we have in `anchors.csv`) average across tracts and would smooth over the heterogeneity that's the whole point of this filter.
- The three gates are conservative-low (each is an obvious must-have, not a discriminator). Tightening individual gates is a v1+ refinement once anchor data on tract-level filtered-vs-total catchments exists.
- Total catchment population is still computed and reported alongside affluent-only catchment for visibility, but it does NOT feed scoring.

### Implementation prerequisites

- Tract demographics at the same fields we currently fetch at zip level. Census ACS tract-level B19013_001E (income), B25003 (ownership), B01001 (age) — same SKU, just different geography. No new API integration; same `src/data/census.py` patterns.
- Affluent-tract filter at the tract level: a new function `affluent_catchment_population(polygon, criteria)` in `src/geo/catchment_population.py` (extends existing `catchment_population`).

### Empirical findings from anchor calibration

Pipeline run on 2026-04-28 against all 11 anchors. Results validate the methodology decision and surface specific calibration anchors:

- **Affluent filter does materially more discrimination work than total catchment alone.** Under a 100K hard gate, total catchment cleanly excludes 1 of 4 PASS anchors (Roanoke 29K). Under the same 100K gate on affluent catchment, 3 of 4 PASS anchors fail (Roanoke 0, Miami Beach 39K, Winder GA 59K). The affluent filter does ~3x the discrimination work the total filter did at the same threshold value.
- **Sensa Germantown's 112K affluent catchment is tight margin against the 100K hard gate (12% headroom).** Reflects Germantown's gentrifying-urban character: ownership-rate gate alone fails most surrounding tracts (Germantown ZCTA-level ownership is 33%). Sensa's BUILD label depends on destination-pull demand (members shop into Germantown for the experience, partner stack with Industrious / 1 Hotel / Next Health) — that demand mechanism is NOT modeled by catchment math. Tightening the affluent hard gate above 112K would falsely fail Sensa; the destination-urban label is the methodology hedge for this.
- **Brooklyn Heights's 341K affluent catchment exceeds 4 of 7 BUILD-class anchors** (Sensa 112K, Cresskill 201K, Alpharetta 299K, Dedham 303K). Demographics alone — even after the affluent filter — cannot exclude saturated urban markets. Supply-overlap methodology ("Supply-overlap-with-demand methodology" above) is necessary, not optional. The affluent filter is a NECESSARY but NOT SUFFICIENT methodology improvement.
- **75034 NTRC has 711K affluent catchment — highest of any anchor**, confirming the position-in-metro effect persists at the affluent-denominator level too. NTRC 75034 sits more centrally in the DFW metro grid than 75033 (627K affluent) or 75035 (623K affluent), and its 15-min ring captures more affluent population because more affluent suburbs lie within its reach. Same operator-flagged effect as documented in "Position-in-metro effect on catchment" — affluent filter does not normalize it away.

These findings DO NOT trigger threshold changes in this turn; they're calibration data feeding future scoring code design.

### Empirical demand-density baselines (post-bleed-fix)

Google Places fetch run on 2026-04-28 against all 11 anchors at 15km radius, post-locationBias-bleed-fix. Counts are post-proximity-dedupe (≤50m) and post-haversine-15km filter. These are the ground-truth raw signal counts; per-capita normalization (signal / affluent_catchment_pop) is the next step before composite scoring.

| anchor type | example | tennis | boutique | golf | padel |
|---|---|---|---|---|---|
| Suburban affluent BUILD (DFW) | NTRC 75034/75035 | 35-36 | 65-68 | 23-24 | 1 |
| Northeast suburban BUILD | Cresskill NJ, Dedham MA, Alpharetta GA | 40-45 | 49-90 | 30-34 | 2-10 |
| Urban gentrifying BUILD | Sensa Germantown | 38 | 77 | 20 | 3 |
| Saturated urban PASS | Brooklyn Heights, Miami Beach | 40-44 | 67-238 | 23-24 | 27-31 |
| Unaffluent Sunbelt PASS | Winder GA | 11 | 4 | 8 | 0 |
| Rural PASS | Roanoke AL | 0 | 0 | 0 | 0 |

Methodology consequences:

- **Pre-bleed-fix counts inflated boutique fitness density by 2-4x in suburban anchors** (NTRC 75034 reported 216 boutique pre-fix vs 68 post-fix; Sensa 182 vs 77). Earlier interpretations of "180-220 boutique looks reasonable" were overstated by Google's geographic relaxation.
- **Pre-bleed-fix produced ∞x false positives in rural anchors** (Roanoke 381 boutique pre-fix; 0 post-fix). All 381 were Atlanta and Birmingham gyms relaxed in.
- **Per-capita normalization is required before comparing across anchors with different catchment sizes.** NTRC zips have 627-711K affluent catchment vs Cresskill 201K — NTRC's larger denominator means per-capita boutique density (68 / 627K = 0.108 per 1K affluent) is comparable to or HIGHER than Cresskill's (49 / 201K = 0.244 per 1K affluent), even though Cresskill has fewer raw boutique places. Raw count comparisons across anchors are misleading.
- **Brooklyn Heights's 238 boutique density is real**, not a bleed artifact (post-fix bleed audit = 0%). NYC has the highest per-area boutique density of any anchor metro. Combined with the 4.7M total / 341K affluent catchment, raw NYC boutique counts will dominate any unnormalized comparison — another reason per-capita is mandatory.
- **Padel supply-side counts are now trustworthy.** DFW: 1 (NTRC self). Atlanta-suburban (Alpharetta): 2. Boston-suburban (Dedham): 7. NYC-suburban (Cresskill): 10. Urban Brooklyn: 31. Urban Miami Beach: 27. These feed supply-overlap math directly.

## Calibration boundary: saturated markets

The v0 supply-overlap math cannot distinguish two distinct market types that both produce capture_share near 1.0:

- **Saturated and unattractive**: Brooklyn Heights NYC. Capture_share ~0.83. Many existing operators have served the affluent demand pool. A new entrant would compete head-to-head with established saturation. Correctly classified PASS by ground truth.
- **Saturated but supports new entrants**: Cresskill NJ. Capture_share ~1.0 (8 surviving competitors after self-exclusion fully cover its 201K affluent catchment). But Padel United operates successfully there — proving the market sustains its operator. The capture_share doesn't tell us the existing competitors are at capacity (waitlists, court-time scarcity, member-cap closures), and v0 has no capacity data to disambiguate.

Both formulations the engine considered (multiplicative, additive penalty) treat capture_share = 1.0 as zero opportunity. This contradicts Cresskill's BUILD ground truth.

### Root cause

Disambiguating "saturated and served-out" from "saturated but operators at capacity" requires capacity data the engine doesn't capture: waitlist mentions, court-time availability scraping, member-cap closures, social-media saturation signals. METHODOLOGY backlog item "Membership cap / waitlist signals" (v2) covers this; until built, the boundary stays ambiguous.

### Phase 0 handling

BUILD anchors with capture_share > 0.85 are excluded from BUILD floor derivation, alongside the existing exclusions (BUILD_DESTINATION_URBAN, BUILD_OUTDOOR_VARIANT). They're scored for visibility but don't gate the threshold.

This is operator-set v0_provisional. Implemented as `SATURATED_CAPTURE_THRESHOLD = 0.85` in `src/scoring/classify.py`.

### Engine reliability domain

The v0 engine is **reliable** for unsaturated candidate suburbs (capture_share < 0.50). For those, the composite scoring math produces sensible BUILD/INVESTIGATE/PASS classifications.

The engine is **unreliable** for already-saturated markets (capture_share > 0.85). Those should be flagged in output as "calibration boundary" — they should not drive operator capital decisions until v2 capacity-data signals exist.

The engine is **partially reliable** in the 0.50-0.85 mid-band — composite reflects partial supply pressure but the multiplicative formulation still over-weights capture. Tunable from anchor calibration.

### What this means for candidate scoring

When a candidate's catchment shows capture_share > 0.85, surface that as the dominant signal in the output, NOT the composite score. The composite gets noisy near saturation; the capture_share itself is the operator-actionable number ("this market has X% of its affluent pool already inside competitor catchments").

## Layered gating: candidate-site demographics AND catchment affluence

**Decision:** the engine applies BOTH a candidate-site demographic gate AND a catchment-affluence gate. Either one alone is insufficient.

### Empirical motivation: Winder GA

The 2026-04-28 affluent-catchment run produced a counterintuitive Winder result: 33% affluent ratio, 59K affluent population in the 15-min ring. Winder's own zip (30680) fails the home-value gate ($245K, well below $500K floor) and is correctly labeled PASS. But its 15-min isochrone reaches into Buford, Suwanee, Lawrenceville, and Athens-adjacent affluent suburbs, pulling in ~59K affluent residents from those neighboring zips.

Position-in-metro can geometrically lift an unaffluent candidate site if it sits between affluent pockets. A scoring math that relied on catchment-affluence alone would surface Winder as more attractive than its zip-level demographics warrant.

### Why both gates are needed

- **Candidate-site demographic gate.** Candidate zip itself must clear demographic floors: median income, median home value, ownership rate. Filters sites that are themselves unaffluent regardless of what their isochrone catches in neighboring areas. **Reason it matters:** an affluent customer living in a *neighboring* zip already has racket-sport options closer to themselves; they will not consistently drive to a site located in an unaffluent zip just because the math says they could in 15 minutes. Drive-time is a necessary condition, not a sufficient one. Members converge on facilities in their *own* perceived neighborhood, not on isochrone-reachable facilities in zips they'd otherwise avoid.
- **Catchment-affluence gate.** Candidate's 15-min affluent catchment population must clear an absolute floor (currently 100K v0). Filters sites with insufficient addressable demand pool — even if the candidate zip itself is wealthy, an isolated affluent enclave with no nearby affluent population to draw on cannot scale to the 300-400 member target.

### Failure modes each gate prevents

| Gate | Prevents | Anchor example |
|---|---|---|
| Candidate-site only | Misses the "isolated affluent island" failure (e.g., a hypothetical small wealthy enclave with no affluent neighbors) | Theoretical — none of current 11 anchors hit this |
| Catchment-affluence only | Misses the "geometrically attractive but locally unaffluent" failure | Winder GA 30680 (33% ratio, 59K affluent catchment, but zip itself $245K home value) |

### Implementation note

When scoring code lands, both gates are applied as hard filters BEFORE composite scoring. A candidate that fails either is excluded from BUILD/INVESTIGATE consideration, not just composite-downweighted. Composite scoring runs only on candidates that survive both.

This is logically equivalent to: BUILD-eligible ⟺ (site_clears_demographic_floors) AND (catchment_affluence ≥ 100K) — both required.

## Business climate tier (v0 categorical, not quantitative)

**Decision:** the engine deliberately does NOT estimate construction costs, property taxes, or permitting timelines numerically. Instead, each candidate (and each anchor) is tagged with a categorical `business_climate_tier` drawn from a 4-tier framework. The tier signals an OUTPUT FLAG only — it never enters composite-score computation.

### Why categorical, not quantitative

Approximated unit-economics inputs would inject error bands large enough to undermine the engine's other outputs. Construction cost per sqft varies 3-4x across markets the engine considers; property tax effective rates vary by local assessment quirks that public data smooths over; permitting timelines depend on specific municipality + project type. A field that says "estimated $/sqft = $250" with a real range of $180-$400 is worse than no number at all — operator could anchor on it. Underwriting (specific site, real lease quotes, real construction bids from contractors who know the local market) is the right place for precise numbers. The engine's job is to surface candidates worth underwriting, not to do underwriting.

Categorical tiers group markets by well-understood structural characteristics. They flag where unit economics likely thrive vs. where they likely struggle, without claiming false precision.

### Four tiers

- **TIER_1_FAVORABLE** — 0%-low income tax + low-moderate property tax + fast permitting + low construction cost. Strong unit economics. BUILD candidates score without caveat. Examples (state-level): TX, TN, FL, NV, WY, SD, AZ.
- **TIER_2_NEUTRAL** — moderate tax + moderate permitting. No structural blocker, no advantage. BUILD candidates score without caveat. Examples: GA, NC, CO, OH, IL, IN, MO, MI, others (25 states total).
- **TIER_3_PREMIUM** — high tax + slow permitting. Premium pricing power assumed compensates. BUILD candidates carry caveat: "BUILD with assumed pricing power" — premium pricing must hold for unit economics to work. Examples: NY (suburbs), CT, MA, NJ, MD, VA, PA, MN, OR, WA. **Sub-flag for states with effective property tax > 2%**: candidates from those states (currently NJ at 2.08% effective, the highest in the country) carry an additional flag — "TIER_3 with extreme property tax burden — premium pricing must hold AND property tax is highest tier in country." Other TIER_3 states carry baseline TIER_3 caveat only.
- **TIER_4_PROHIBITIVE** — construction + permitting kill unit economics at the $1.2-2M capex target. BUILD candidates carry flag: "BUILD demographically, ECONOMIC_GATE_RISK for underwriting" — likely fail underwriting even when demographics qualify. Examples: CA (state default), DC (district), and metro overrides for NYC-proper, Seattle-proper.

### Source of truth

State defaults + metro overrides live in `markets/business_climate_tiers.yaml`. The file covers all 50 states + DC. Metro overrides (NYC-proper → TIER_4, Chicago-city → TIER_3, Seattle-proper → TIER_4, Austin-metro → TIER_2 step-down, Rural-VA-non-NOVA → TIER_2 step-down, Rural-PA-non-Philly → TIER_2 step-down) handle within-state heterogeneity.

### How the tier signal flows through the engine

1. Candidate definition in `candidate_universe.yaml` carries `business_climate_tier` field (resolved from state default + metro override at definition time).
2. Scoring runner reads the tier as metadata — does NOT pass it into `composite_demand_score`, `supply_overlap_uncaptured_demand`, or any signal density. Tier never affects score values.
3. Output (`candidate_scores.md`) prints tier alongside composite + classification, with the appropriate caveat flag attached based on tier value.

### Refusal commitment

If any future code path or schema change wants to add quantitative cost fields ($/sqft, $/year property tax, days-to-permit estimates) to anchors.csv, candidate_universe.yaml, or any signal-input pipeline — refuse. Surface to operator. The categorical tier is the v0 design; quantitative numbers belong in underwriting, not screening. See CLAUDE.md anti-pattern #17.

### Validation status

v0 tier assignments based on documented state-level tax + permitting + construction-cost characteristics. Some assignments are contested at the boundary (NH, VT, ME at TIER_3 instead of operator-example TIER_2; AZ at TIER_1 instead of TIER_2; MI at TIER_2 instead of operator-example TIER_3). Operator approved Claude Code's contested-case proposals. Refine as more market data accumulates.

## Methodology backlog — adjacent fixes prioritized as v1/v2

The two methodology decisions above (overlap-supply, affluent-only-demand) are v0 canonical. The fixes below are KNOWN improvements deferred to later phases. Documented now so they don't get lost and so v0 implementations don't accidentally close off space for them.

### v1 — build before first capital decision

- **Capacity-weighted supply.** NTRC at 4 padel courts is heavier competition than a 2-court studio. Weight competitors by court count, member count where known, and a reputation proxy (rating × user_ratings_total). The supply-overlap math currently treats every competitor's catchment as full-strength capture; capacity weighting scales that capture by some fraction of full strength.
- **Substitute-good supply.** Some affluent racket-sport customers split time across formats. Tennis club density and premium pickleball density should enter the supply-pressure signal at lower weight (0.2-0.3x of padel competitors). Not a pure substitute (padel converts retain at 92% per the briefing), but non-zero.

### v2 — refinements after operating data exists

- **Distance-decay capture weighting.** Current model is a binary step function: a member is captured at 100% if inside the competitor's 15-min ring, 0% if outside. Real choice probability decays smoothly with drive time (gravity model). Implement once we have NTRC's actual member origin data to fit decay parameters.
- **Membership cap / waitlist signals.** Scrape competitor reviews, sites, and social mentions for "waitlist" / "membership closed" language as evidence of unmet demand the catchment is hiding. Real signal: a saturated competitor in a candidate's overlap region is functionally less of a capturer than an under-utilized one.
- **New-supply detection.** Periodic re-scrape to flag markets where supply has materially changed (new club opens, existing one closes). Triggers re-scoring of affected candidates.
- **Cross-metro spillover.** Extend supply check beyond the 30-min radius for known commuting corridors. NYC suburbs should include Manhattan supply (Brooklyn-based padel facilities serve NYC-suburb members during workweek). SF Peninsula should include SF proper. Hard-coded corridor table per metro.

### Probably-never (documented as known limitations only)

- **Time-of-day and seasonality in supply.** Real capture rates vary by weekday vs weekend, season, and time block. Tracking this would require operational data from competitors (which we don't and won't have). Limitation, not a TODO.
- **Anchor-specific demographic-match weighting in catchment.** Different padel operators serve different sub-segments of the affluent target (Sensa's $349 tier vs NTRC's $159 tier). Conceptually a competitor at a higher price point captures less of a lower-price candidate's demand pool. Implementing this requires per-competitor pricing data + demand elasticity modeling — overkill for current scale.

## Change log

- Repo initialized. No methodology decisions yet.
- Dual-radius catchment scoring (7-min + 15-min) adopted as canonical methodology. Operator-driven hypothesis based on padel format properties (scheduled play, scarcity of substitutes) raising drive tolerance vs. boutique fitness baseline. Both demand scores reported per candidate; operator selects strategy per-site. Pending validation against operating data once 2-3 locations exist.
- Pop-weighted ZCTA centroid adopted as canonical isochrone origin (vs geographic centroid). Validated against 8 Phase 0 anchors: 2/8 trigger meaningful (>2 km) displacement, both rural/exurban PASS anchors (Roanoke AL 2.67 km, Winder GA 4.32 km). NTRC and other affluent-suburban BUILD anchors show <1.6 km displacement. Methodology adds rigor without changing BUILD-candidate outcomes; prevents false catchment readings on rural negative controls.
- Convex-hull isochrone construction documented as v0 known limitation: 1.5-2.5x overestimate in inland metros, ~true in water-bounded metros. Phase 2 alpha-shape upgrade pending first false-positive in BUILD ranking.
- Catchment population hard gate set to 100K (15-min isochrone). Anchor-derived from Phase 0 data: Roanoke AL PASS catchment 29K cleanly fails; Sensa urban BUILD floor 559K, NTRC suburban floor 892K, so 100K leaves >5x margin while excluding rural-pop case. Three of four PASS anchors clear 100K and are excluded by other mechanisms (supply policy, home-value gate, urban exclusion) — gate is intentionally narrow in scope.
- Position-in-metro effect documented: NTRC 75034 catchment 1.27M vs 75033 892K despite 5-mile separation, driven by 75034's more central DFW position. Per-capita signals will normalize this; catchment-pop should not be added as an additional composite-score weight (already serves as denominator + hard-gate floor).
- Demand-cluster-overlap supply methodology adopted as v0 canonical (CLAUDE.md anti-pattern #13; METHODOLOGY "Supply-overlap-with-demand methodology"). Operator-driven decision: facility count is a coarse proxy that ignores who competitors actually serve. Empirical basis: NTRC adjacency where 5 facilities-within-15km would say "supply saturated" but the overlap math may show meaningful uncaptured affluent demand. Must be implemented from the first scoring run; facility-count is explicitly wrong.
- Affluent-criteria-only demand catchment adopted as v0 canonical (CLAUDE.md anti-pattern #14; METHODOLOGY "Affluent-demand-only catchment"). Operator-driven decision: total catchment overstates addressable demand 10-50x in mixed-density urban-adjacent zips. Empirical basis: Brooklyn Heights's 4.7M total catchment vs NTRC 75033's 892K total catchment makes Brooklyn Heights look 5x stronger when in real-affluent terms it is likely smaller. Tract-level affluent filter (income ≥ $100K + age 25-49 ≥ 25% + ownership ≥ 50%) is the v0 starting criteria.
- v1/v2 methodology backlog locked in (METHODOLOGY "Methodology backlog — adjacent fixes prioritized as v1/v2"): capacity-weighted supply + substitute-good supply build before first capital decision; distance-decay capture, waitlist signals, new-supply re-scrape, cross-metro spillover deferred to v2 post-operating data; time-of-day / per-competitor demographic-match flagged as probably-never. Documented now so v0 implementations don't accidentally close off space for these refinements.
- Affluent-catchment empirical findings from 2026-04-28 anchor pipeline run added to METHODOLOGY "Affluent-demand-only catchment / Empirical findings". Key results: 100K affluent gate excludes 3 of 4 PASS anchors (vs 1 of 4 under 100K total); Sensa Germantown is tight-margin BUILD anchor at 112K affluent (12% above gate, destination-pull caveat); Brooklyn Heights 341K affluent exceeds 4 of 7 BUILD-class anchors confirming supply-overlap methodology is necessary not optional; 75034 NTRC retains highest catchment under affluent denominator (position-in-metro effect persists post-filter).
- Layered-gating methodology adopted (METHODOLOGY "Layered gating: candidate-site demographics AND catchment affluence"; CLAUDE.md anti-pattern #15). Decision: BUILD eligibility requires BOTH (a) candidate-zip clears demographic floors AND (b) catchment-affluent population ≥ 100K. Empirical motivation: Winder GA's 59K affluent catchment from neighboring zips would lift an unaffluent candidate site under catchment-only scoring; the candidate-zip filter prevents that failure mode. Either gate alone is insufficient.
- Google Places `locationBias` bleed fix corrected demand-signal counts. Pre-fix data overstated boutique fitness density by 2-4x in suburban anchors and produced false positives in rural anchors (Roanoke AL: 381 boutique → 0 after fix; all 381 were Atlanta/Birmingham facilities Google relaxed in when the local 15km circle was empty). Note: Google Places API New `locationRestriction.circle` is not valid for Text Search — only Search Nearby supports it. Fix is `locationBias.circle` + post-fetch client-side haversine 15km filter. All 10 non-75033 anchor caches refreshed. Empirical density baselines (METHODOLOGY "Empirical demand-density baselines") and DFW supply ground truth (1 padel facility, not 4) updated accordingly.
- Calibration boundary documented (METHODOLOGY "Calibration boundary: saturated markets"; CLAUDE.md anti-pattern #16). v0 engine cannot disambiguate "saturated and served-out" (Brooklyn Heights, capture ~0.83) from "saturated but operators at capacity" (Cresskill, capture ~1.0 but Padel United operates successfully). Both produce composite ≈ 0 in the multiplicative formulation. v2 capacity-data signals (waitlists, court-time scraping, member-cap closures) are required to disambiguate. Phase 0 handling: BUILD anchors with capture_share > 0.85 excluded from BUILD floor derivation (operator-set `SATURATED_CAPTURE_THRESHOLD` v0_provisional). Engine reliability domain: unsaturated candidates (capture < 0.50) scored well; saturated candidates (> 0.85) flagged as calibration boundary, not used for capital decisions until v2.
- Business climate tier (v0 categorical) adopted (METHODOLOGY "Business climate tier (v0 categorical, not quantitative)"; CLAUDE.md anti-pattern #17). 4-tier framework (FAVORABLE / NEUTRAL / PREMIUM / PROHIBITIVE) covers 50 states + DC + metro overrides (NYC-proper, Chicago-city, Seattle-proper, Austin-metro, Rural-VA-non-NOVA, Rural-PA-non-Philly). Tier is OUTPUT FLAG only — never composite-score input. Engine deliberately does NOT estimate construction costs / taxes / permitting numerically; categorical signal protects against false-precision underwriting from screening data. TIER_3 sub-flag for property-tax-extreme states (currently NJ at 2.08%) carries additional caveat. Refusal commitment: future schema changes wanting quantitative cost fields must be refused and surfaced to operator.
