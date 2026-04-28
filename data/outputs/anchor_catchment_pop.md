# Anchor catchment population — total + affluent

**Total catchment** = sum of population across Census tracts whose centroid (Census 2023 Gazetteer internal point) falls inside the drive-time isochrone polygon.

**Affluent catchment** = same set, filtered by tract-level affluent gate (median household income ≥ $100K AND pct_age_25_49 ≥ 25% AND ownership rate ≥ 50%). Per METHODOLOGY.md "Affluent-demand-only catchment" — this is the v0-canonical demand signal feeding scoring; total is reported only for visibility.

**affluent/total ratio** = how much of the total catchment passes the tract-level affluent filter. High ratio = surroundings are uniformly affluent. Low ratio = isochrone sweeps through mixed-density geography.

## Per-anchor table

| location_id | zip | label | total 7-min | total 15-min | affluent 7-min | affluent 15-min | affluent/total 15-min |
|---|---|---|---|---|---|---|---|
| ntrc_frisco | 75033 | BUILD | 168,871 | 891,607 | 131,904 | 627,073 | 70.3% |
| ntrc_frisco_75034 | 75034 | BUILD | 208,151 | 1,272,386 | 132,544 | 710,578 | 55.8% |
| ntrc_frisco_75035 | 75035 | BUILD | 193,518 | 922,750 | 153,372 | 622,824 | 67.5% |
| sensa_germantown | 37208 | BUILD_DESTINATION_URBAN | 154,279 | 558,744 | 31,476 | 112,370 | 20.1% |
| roanoke_al | 36272 | PASS | 3,775 | 29,312 | 0 | 0 | 0.0% |
| miami_beach | 33139 | PASS | 48,568 | 652,189 | 11,748 | 38,599 | 5.9% |
| winder_ga | 30680 | PASS | 43,761 | 177,085 | 0 | 59,016 | 33.3% |
| brooklyn_heights | 11201 | PASS | 983,355 | 4,696,986 | 70,564 | 340,769 | 7.3% |
| padel_united_cresskill | 07626 | BUILD | 93,113 | 469,836 | 68,719 | 201,301 | 42.8% |
| padel_boston_dedham | 02026 | BUILD | 88,515 | 604,503 | 58,326 | 303,071 | 50.1% |
| racket_social_alpharetta | 30005 | BUILD_OUTDOOR_VARIANT | 69,355 | 437,145 | 58,871 | 298,694 | 68.3% |
