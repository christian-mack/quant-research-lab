# Wave 1 Track 2 — Phase 2: daily bias module (assembly) diagnostics

**Date run:** 2026-06-05  
**git_sha:** `0db224fc2bd1ef320064fb04c9a9a3d9d095e366`  
**Protocol window:** 2020-01-01 → 2026-06-30  
**Bars:** MNQ 599,533, MES 629,048, MYM 632,947 (RTH)  
**Configs:** C1=5m/SMT-optional (**PRIMARY**), C2=5m/SMT-required, C3=15m/SMT-optional, C4=15m/SMT-required.
**Structural constants:** opening_range_minutes=30, penetration_ticks=1, close_back_within_bars=3, tick_size=0.25, SMT=MNQ/MES/MYM.

## Summary (operator)

- **Bias distribution (C1 primary):** long 14.0% / short 10.6% / no-clear-bias 75.5% of 1561 sessions. **383** clear-bias sessions over 6 years.
- **Frequency finding (SURFACE, not a stop):** no-clear-bias dominates at 75.5% (>70%). The module stands down on ~3 of 4 sessions; weigh this against downstream trade frequency / eval pass-rate.
- **Where the chain breaks:** of 1333 sessions that start a path (sweep), 817 reach CISD, 383 reach EQ-respect, 169 reach SMT. The binding filters are **CISD confirmation** (sweep→CISD loses 516) and **EQ-respect** (CISD→EQ loses 434).
- **SMT cost:** requiring SMT flips 214 of 383 clear sessions (55.9%) to no-clear-bias — roughly halving frequency.
- **Year stability:** long-share of clear sessions stays ~45–64% across full years (2026 partial) — balanced, not a one-directional trend artifact.
- **Worked examples:** all classified correctly (all_correct=True) — assembly logic is self-consistent with the transcript day-types; **no STOP**.

_Reproduce:_ `uv run python scripts/run_wave1_track2_phase2_bias_module.py`. Caveat: prior-day levels for the first session after each operator MNQ export gap are stale (last available session); ~2 sessions in 6 years — negligible.

## (a) Bias distribution by config

| Config | TF | SMT req | n | long | short | no-clear-bias |
|---|---|---|---|---|---|---|
| C1 | 5m | False | 1561 | 218 (14.0%) | 165 (10.6%) | 1178 (75.5%) |
| C2 | 5m | True | 1561 | 96 (6.1%) | 73 (4.7%) | 1392 (89.2%) |
| C3 | 15m | False | 1561 | 240 (15.4%) | 159 (10.2%) | 1162 (74.4%) |
| C4 | 15m | True | 1561 | 89 (5.7%) | 57 (3.7%) | 1415 (90.6%) |

## (b) Bias distribution by year — primary (C1)

| Year | n | long | short | no-clear-bias | long-share of clear |
|---|---|---|---|---|---|
| 2020 | 258 | 36 (14.0%) | 26 (10.1%) | 196 (76.0%) | 58.1% |
| 2021 | 258 | 30 (11.6%) | 25 (9.7%) | 203 (78.7%) | 54.5% |
| 2022 | 258 | 30 (11.6%) | 36 (14.0%) | 192 (74.4%) | 45.5% |
| 2023 | 257 | 38 (14.8%) | 29 (11.3%) | 190 (73.9%) | 56.7% |
| 2024 | 226 | 35 (15.5%) | 23 (10.2%) | 168 (74.3%) | 60.3% |
| 2025 | 257 | 39 (15.2%) | 22 (8.6%) | 196 (76.3%) | 63.9% |
| 2026 | 47 | 10 (21.3%) | 4 (8.5%) | 33 (70.2%) | 71.4% |

## (c) Confirmation-chain attrition — primary (C1, combined best-path funnel)

- Sessions: **1561**
- Started a directional path (sweep): **1333**
- Reached CISD: **817**
- Reached EQ-respect: **383**
- Reached SMT: **169**

| Stage transition | sessions lost |
|---|---|
| sweep → CISD | 516 |
| CISD → EQ-respect | 434 |
| EQ-respect → SMT | 214 |

## (d) SMT impact — primary TF (5m)

- Clear-bias sessions (SMT optional): **383**
- Winning path SMT evaluable: **374**
- Winning path SMT present: **169**
- Flip to no-clear-bias if SMT required: **214** (55.9% of clear sessions)

## (e) TTrades worked-example validation

| Day type | expected | got | correct |
|---|---|---|---|
| continuation_bullish | long | long | True |
| reversal_bearish | short | short | True |
| consolidation_range | no-clear-bias | no-clear-bias | True |

**All worked examples correct:** True (synthetic day-types faithful to the transcript geometry; no real-MNQ ground-truth labels exist in the corpus).

## Stop conditions

- Worked example misclassified (STOP): **False**
- No-clear-bias dominates >70% (surface): **True** (no-clear-bias = 75.5%)
- <50 clear-bias sessions (surface): **False** (clear sessions = 383)
