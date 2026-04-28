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
