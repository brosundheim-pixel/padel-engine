# Anchor scoring (v1: gates + self-exclusion)

**v1 changes vs v0**: (1) site-level demographic hard gate applied before composite scoring; GATE_FAIL anchors get composite=None and classify PASS by gate. (2) Self-exclusion: padel facilities inside the candidate's 7-min isochrone are dropped from the competitor set (co-located operator = BUILD signal, not competitor).

**Demographic gates**: home_value ≥ $500,000, income ≥ $100,000, affluent_catchment_15min ≥ 100,000

**Competitor cap**: top 10 per anchor by rating × reviews (v0_provisional)

BUILD threshold: **0.0262**  
PASS threshold:  **0.0000**  
Separation gap (BUILD − PASS): **+0.0262**  
Separation clean: **True**

## Per-anchor scoring table

| anchor | label | method | classification | composite | demand | padel raw | post-self-excl | capped | uncaptured | capture % | failed_gates |
|---|---|---|---|---|---|---|---|---|---|---|---|
| racket_social_alpharetta | BUILD_OUTDOOR_VARIANT | BUILD_OUTDOOR_VARIANT | BUILD | **0.0797** | 0.0797 | 2 | 0 | 0 | 298,694 | 0.0% | — |
| ntrc_frisco_75035 | BUILD | GATE_PASS | BUILD | **0.0477** | 0.0477 | 1 | 0 | 0 | 622,824 | 0.0% | — |
| ntrc_frisco_75034 | BUILD | GATE_PASS | BUILD | **0.0438** | 0.0438 | 1 | 0 | 0 | 710,578 | 0.0% | — |
| brooklyn_heights | PASS_SATURATED_URBAN | PASS_SATURATED_URBAN | BUILD | **0.0408** | 0.2409 | 31 | 20 | 10 | 57,712 | 83.1% | — |
| sensa_germantown | BUILD_DESTINATION_URBAN | BUILD_DESTINATION_URBAN | BUILD | **0.0405** | 0.2269 | 3 | 1 | 1 | 20,046 | 82.2% | — |
| ntrc_frisco | BUILD | GATE_PASS | BUILD | **0.0370** | 0.0370 | 1 | 0 | 0 | 627,073 | 0.0% | — |
| padel_boston_dedham | BUILD | GATE_PASS | BUILD | **0.0262** | 0.1066 | 7 | 5 | 5 | 74,566 | 75.4% | — |
| padel_united_cresskill | BUILD | GATE_PASS | PASS | **0.0000** | 0.1590 | 10 | 8 | 8 | 0 | 100.0% | — |
| roanoke_al | PASS | GATE_FAIL | PASS | **—** | — | 0 | 0 | 0 | — | — | home_value,income,affluent_catchment_15min |
| miami_beach | PASS | GATE_FAIL | PASS | **—** | — | 0 | 0 | 0 | — | — | home_value,income,affluent_catchment_15min |
| winder_ga | PASS | GATE_FAIL | PASS | **—** | — | 0 | 0 | 0 | — | — | home_value,income,affluent_catchment_15min |

## BUILD vs PASS composite distribution (gate-passers only)

BUILD anchors (n=5): 0.0000, 0.0262, 0.0370, 0.0438, 0.0477

PASS  anchors (n=0): 

Excluded from threshold derivation: sensa_germantown (0.0405), brooklyn_heights (0.0408), racket_social_alpharetta (0.0797)

