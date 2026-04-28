# Anchor catchment summary
Dual-radius (7-min + 15-min) drive-time isochrones from population-weighted ZCTA centroids per CLAUDE.md. Zip-membership tested against per-metro candidate universes using pop centroids for both origin and membership probes.
Methodology notes:
- Isochrone polygon = convex hull of OSM nodes reachable within drive-time budget. Overestimates true reachable area by 1.5-2.5x. Phase 2 should swap to alpha-shape.
- Pop centroid = sum(tract_centroid × tract_population) / sum(tract_population) across tracts overlapping the ZCTA on land. Tract centroids from Census 2023 Gazetteer (which is itself pop-weighted internal point per tract). Tract population from ACS 2023 5-year B01003_001E.
- Displacement > 2.0 km between geo and pop centroid is flagged as **meaningful** — material difference between polygon center and where people actually live.

## Summary table
| location_id | zip | metro | label | geo centroid | pop centroid | Δ km | 7-min km² | 15-min km² | inside 7 | inside 15 |
|---|---|---|---|---|---|---|---|---|---|---|
| ntrc_frisco | 75033 | DFW | BUILD | 33.1807, -96.8470 | 33.1752, -96.8520 | 0.76 | 150.3 | 861.8 | 2 | 8 |
| ntrc_frisco_75034 | 75034 | DFW | BUILD | 33.1352, -96.8367 | 33.1240, -96.8315 | 1.33 | 168.0 | 997.1 | 3 | 9 |
| ntrc_frisco_75035 | 75035 | DFW | BUILD | 33.1435, -96.7771 | 33.1575, -96.7749 | 1.57 | 125.1 | 755.6 | 1 | 9 |
| sensa_germantown | 37208 | Nashville | BUILD_DESTINATION_URBAN | 36.1749, -86.8019 | 36.1777, -86.8079 | 0.63 | 119.8 | 954.1 | 4 | 7 |
| roanoke_al | 36272 | Rural_Alabama | PASS | 33.9308, -85.6248 | 33.9402, -85.6513 | 2.67⚠ | 110.3 | 702.7 | 1 | 1 |
| miami_beach | 33139 | South_Florida | PASS | 25.7851, -80.1411 | 25.7837, -80.1472 | 0.64 | 25.7 | 237.4 | 3 | 8 |
| winder_ga | 30680 | Atlanta_Outer | PASS | 33.9695, -83.6820 | 33.9944, -83.7181 | 4.32⚠ | 181.2 | 946.5 | 1 | 2 |
| brooklyn_heights | 11201 | NYC | PASS | 40.6927, -73.9916 | 40.6933, -73.9892 | 0.21 | 58.7 | 388.7 | 9 | 9 |
| padel_united_cresskill | 07626 | NYC_Suburbs | BUILD | 40.9410, -73.9649 | 40.9404, -73.9630 | 0.18 | 55.8 | 250.7 | 1 | 1 |
| padel_boston_dedham | 02026 | Boston_Suburbs | BUILD | 42.2455, -71.1714 | 42.2441, -71.1676 | 0.35 | 74.8 | 489.6 | 1 | 1 |
| racket_social_alpharetta | 30005 | Atlanta_Suburbs | BUILD_OUTDOOR_VARIANT | 34.0771, -84.2213 | 34.0836, -84.2152 | 0.92 | 58.7 | 540.8 | 1 | 1 |

## Per-anchor detail

### ntrc_frisco — NTRC Frisco (75033, BUILD)

- Metro: `DFW`
- Geo centroid: `33.1807, -96.8470`
- Pop-weighted centroid: `33.1752, -96.8520` (displacement 0.76 km)
- 7-min isochrone: **150.3 km²**, zips inside: `['75033', '75034']`
- 15-min isochrone: **861.8 km²**, zips inside: `['75033', '75034', '75035', '75024', '75025', '75093', '75070', '75056']`
### ntrc_frisco_75034 — NTRC Frisco (75034, BUILD)

- Metro: `DFW`
- Geo centroid: `33.1352, -96.8367`
- Pop-weighted centroid: `33.1240, -96.8315` (displacement 1.33 km)
- 7-min isochrone: **168.0 km²**, zips inside: `['75033', '75034', '75024']`
- 15-min isochrone: **997.1 km²**, zips inside: `['75033', '75034', '75035', '75024', '75025', '75093', '75070', '75056', '75057']`
### ntrc_frisco_75035 — NTRC Frisco (75035, BUILD)

- Metro: `DFW`
- Geo centroid: `33.1435, -96.7771`
- Pop-weighted centroid: `33.1575, -96.7749` (displacement 1.57 km)
- 7-min isochrone: **125.1 km²**, zips inside: `['75035']`
- 15-min isochrone: **755.6 km²**, zips inside: `['75033', '75034', '75035', '75024', '75025', '75093', '75070', '75071', '75056']`
### sensa_germantown — Sensa Padel Nashville (37208, BUILD_DESTINATION_URBAN)

- Metro: `Nashville`
- Geo centroid: `36.1749, -86.8019`
- Pop-weighted centroid: `36.1777, -86.8079` (displacement 0.63 km)
- 7-min isochrone: **119.8 km²**, zips inside: `['37208', '37203', '37210', '37212']`
- 15-min isochrone: **954.1 km²**, zips inside: `['37208', '37203', '37206', '37210', '37212', '37215', '37205']`
### roanoke_al — Roanoke AL (36272, PASS)

- Metro: `Rural_Alabama`
- Geo centroid: `33.9308, -85.6248`
- Pop-weighted centroid: `33.9402, -85.6513` — **displacement 2.67 km ⚠ meaningful**
- 7-min isochrone: **110.3 km²**, zips inside: `['36272']`
- 15-min isochrone: **702.7 km²**, zips inside: `['36272']`
### miami_beach — Miami Beach FL (33139, PASS)

- Metro: `South_Florida`
- Geo centroid: `25.7851, -80.1411`
- Pop-weighted centroid: `25.7837, -80.1472` (displacement 0.64 km)
- 7-min isochrone: **25.7 km²**, zips inside: `['33139', '33140', '33132']`
- 15-min isochrone: **237.4 km²**, zips inside: `['33139', '33140', '33141', '33154', '33129', '33131', '33132', '33134']`
### winder_ga — Winder GA (30680, PASS)

- Metro: `Atlanta_Outer`
- Geo centroid: `33.9695, -83.6820`
- Pop-weighted centroid: `33.9944, -83.7181` — **displacement 4.32 km ⚠ meaningful**
- 7-min isochrone: **181.2 km²**, zips inside: `['30680']`
- 15-min isochrone: **946.5 km²**, zips inside: `['30680', '30620']`
### brooklyn_heights — Brooklyn Heights NY (11201, PASS)

- Metro: `NYC`
- Geo centroid: `40.6927, -73.9916`
- Pop-weighted centroid: `40.6933, -73.9892` (displacement 0.21 km)
- 7-min isochrone: **58.7 km²**, zips inside: `['11201', '11215', '11217', '11231', '11211', '11205', '10004', '10038', '10002']`
- 15-min isochrone: **388.7 km²**, zips inside: `['11201', '11215', '11217', '11231', '11211', '11205', '10004', '10038', '10002']`
### padel_united_cresskill — Padel United Sports Club (07626, BUILD)

- Metro: `NYC_Suburbs`
- Geo centroid: `40.9410, -73.9649`
- Pop-weighted centroid: `40.9404, -73.9630` (displacement 0.18 km)
- 7-min isochrone: **55.8 km²**, zips inside: `['07626']`
- 15-min isochrone: **250.7 km²**, zips inside: `['07626']`
### padel_boston_dedham — Padel Boston (02026, BUILD)

- Metro: `Boston_Suburbs`
- Geo centroid: `42.2455, -71.1714`
- Pop-weighted centroid: `42.2441, -71.1676` (displacement 0.35 km)
- 7-min isochrone: **74.8 km²**, zips inside: `['02026']`
- 15-min isochrone: **489.6 km²**, zips inside: `['02026']`
### racket_social_alpharetta — Racket Social Club Alpharetta (30005, BUILD_OUTDOOR_VARIANT)

- Metro: `Atlanta_Suburbs`
- Geo centroid: `34.0771, -84.2213`
- Pop-weighted centroid: `34.0836, -84.2152` (displacement 0.92 km)
- 7-min isochrone: **58.7 km²**, zips inside: `['30005']`
- 15-min isochrone: **540.8 km²**, zips inside: `['30005']`
