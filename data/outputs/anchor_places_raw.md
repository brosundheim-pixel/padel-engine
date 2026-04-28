# Anchor Google Places raw fetch — non-NTRC-75033 batch

Run on 2026-04-28. Each anchor's pop-weighted centroid → 4 fetchers (tennis Search Nearby+Text, boutique fitness 14-brand Text, golf Search Nearby+Text, padel 3 Text queries) at radius 15000m. All counts post-proximity-dedupe (≤50m). All paid calls through `cached_api_call`; cache hits return free.

Total spend (this run): $6.0480

## Per-anchor summary

| location_id | zip | label | centroid | tennis | boutique | golf | padel | wall (s) | cum spend |
|---|---|---|---|---|---|---|---|---|---|
| ntrc_frisco_75034 | 75034 | BUILD | 33.1240, -96.8315 | 35 | 68 | 23 | 1 | 0.0 | $0.0000 |
| ntrc_frisco_75035 | 75035 | BUILD | 33.1575, -96.7749 | 36 | 65 | 24 | 1 | 0.0 | $0.0000 |
| sensa_germantown | 37208 | BUILD_DESTINATION_URBAN | 36.1777, -86.8079 | 38 | 77 | 20 | 3 | 0.0 | $0.0000 |
| roanoke_al | 36272 | PASS | 33.9402, -85.6513 | 0 | 0 | 0 | 0 | 0.0 | $0.0000 |
| miami_beach | 33139 | PASS | 25.7837, -80.1472 | 40 | 67 | 24 | 27 | 30.0 | $0.9280 |
| winder_ga | 30680 | PASS | 33.9944, -83.7181 | 11 | 4 | 8 | 0 | 39.9 | $1.9840 |
| brooklyn_heights | 11201 | PASS | 40.6933, -73.9892 | 44 | 238 | 23 | 31 | 45.9 | $3.1040 |
| padel_united_cresskill | 07626 | BUILD | 40.9404, -73.9630 | 40 | 49 | 34 | 10 | 44.0 | $4.2240 |
| padel_boston_dedham | 02026 | BUILD | 42.2441, -71.1676 | 45 | 90 | 32 | 7 | 29.4 | $5.1520 |
| racket_social_alpharetta | 30005 | BUILD_OUTDOOR_VARIANT | 34.0836, -84.2152 | 44 | 56 | 30 | 2 | 26.4 | $6.0480 |
