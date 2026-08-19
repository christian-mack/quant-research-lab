# Wave 1 Track 2 — Phase 3 step 3b: Entry-coherence diagnostic

**Date:** 2026-06-06  
**git_sha:** `0db224fc2bd1ef320064fb04c9a9a3d9d095e366`  
**Purpose:** Forensic audit of step-3 standalone OTE economics. NOT screening.

## Executive verdict

**No configuration shows verified, artifact-free, cost-surviving edge.** Step 4 remains blocked.

| Question | Verdict |
|---|---|
| (1) Entry incoherence | **Definitional** — OTE 70.5% (premium half) vs earliest discount FVG (opposite PD half) on 100% of traced setups. Operator must choose OTE-only, FVG-only, or unified rule. |
| (2) FVG-zone $220k | **Artifact (not look-ahead)** — fills are bar-valid; restricting fill timing barely changes total ($220,760 → $220,575). Inflated by substituting a ~46-tick-different entry price with fixed stop/target. **Discard.** |
| (3) entry_ote_62 4× gap | **Partially real geometry** — fills bar-valid; better price when 62% fills. Still incoherent assembly; not cleared for screening. |
| (4) Costs | **Primary net-negative:** −$1,186/MNQ/yr (−1.74 ticks/trade) comm+slip. Only entry_ote_62 positive (+$5,673/yr) but incoherent. |
| (5) Coherent re-run | **OTE-only:** −$1,186/yr. **FVG-only:** +$28,549/yr but **untrusted** — targets resolved at OTE entry price, flattering FVG entry. |

**Pivot:** bias-gated path, operator entry decision, or ICT track reassessment. Do not proceed to step 4 on step-3 numbers.

---

## Diagnostic 1 — Why D0.1 and D0.2 disagree

- Conflict rate: **99.3%**
- Distance (ticks): median **46**, mean **71**, max **1505**

**Root cause:** DEFINITIONAL_NOT_BUG: D0.1 (70.5% OTE fib) and D0.2 (earliest discount/premium FVG) are alternative entry styles per Ep 38. Earliest eligible FVG sits near displacement start (discount for longs); 70.5% OTE sits in premium half (~70% up the leg). Opposite PD halves + leg-scale mismatch explain ~100% conflict. NOT fixable by window tweak alone — requires operator choice: OTE-only, FVG-only, or unified rule (e.g. FVG nearest OTE / FVG containing OTE).

**Hypothesis counts (50-trade sample):**
- opposite_PD_halves_by_design: 50/50
- large_displacement_leg: 50/50
- earliest_fvg_at_leg_start_vs_deep_ote: 37/50
- micro_fvg_vs_leg_fib: 19/50

**Sample traces (first 5):**

- 2021-02-12 short: leg=59.0 ticks, OTE@70.5% of leg (premium), FVG entry 13745.5 (discount), gap=20.6 ticks — opposite_PD_halves_by_design, large_displacement_leg, earliest_fvg_at_leg_start_vs_deep_ote
- 2020-03-27 short: leg=205.0 ticks, OTE@70.5% of leg (premium), FVG entry 7744.25 (discount), gap=47.5 ticks — opposite_PD_halves_by_design, large_displacement_leg
- 2022-10-20 long: leg=86.0 ticks, OTE@70.5% of leg (premium), FVG entry 11064.5 (discount), gap=18.6 ticks — opposite_PD_halves_by_design, large_displacement_leg, micro_fvg_vs_leg_fib
- 2022-07-05 short: leg=374.0 ticks, OTE@70.5% of leg (premium), FVG entry 11684.5 (discount), gap=189.7 ticks — opposite_PD_halves_by_design, large_displacement_leg, earliest_fvg_at_leg_start_vs_deep_ote
- 2022-04-12 long: leg=327.0 ticks, OTE@70.5% of leg (premium), FVG entry 14148.0 (discount), gap=90.5 ticks — opposite_PD_halves_by_design, large_displacement_leg, earliest_fvg_at_leg_start_vs_deep_ote

## Diagnostic 2 — FVG-zone $220k audit

**PRICE-SUBSTITUTION ARTIFACT (not look-ahead):** FVG-zone fills are bar-reachable (30/30 top trades audited; no peeking). Restricting FVG fill to the OTE fill bar barely changes aggregate P&L ($220,760 → $220,575). The inflation comes from entering at the FVG-zone price (~46 ticks from OTE on median) while holding stop/target fixed — an apples-to-oranges counterfactual, not a tradeable alternate entry. **Discard** step-3 FVG-zone headline.

- Step-3 FVG counterfactual total: **$220,760**
- Re-sim same early timing: **$220,760**
- Fair timing (fill only from OTE bar): **$220,575**
- Median FVG fill lead vs OTE: **-1.0** bars

## Diagnostic 3 — entry_ote_62 audit

PARTIALLY_REAL_TIMING: ote_62 fills are bar-valid (no look-ahead). 62% is deeper retracement → fills median 0.0 bars later than 70.5% with better entry price when filled. Outperformance is partly real (better entry geometry) but still uses incoherent FVG+OTE assembly. Economics remain suspect until entry mode is chosen.

- Avg gross/trade: primary **3.07** ticks, ote_62 **13.45** ticks
- Median fill delay (62 vs 70.5): **0.0** bars

## Diagnostic 4 — Cost-realistic economics

| Config | Comm-only annual | Comm+slip annual | Avg net ticks/trade |
|---|---:|---:|---:|
| primary | $-611 | $-1,186 | -1.74 |
| target_far | $-2,074 | $-2,735 | -4.01 |
| stop_fvg_c2 | $-24,502 | $-25,029 | -36.66 |
| entry_ote_62 | $6,241 | $5,673 | 8.63 |
| fvg_nearest_ote | $-611 | $-1,186 | -1.74 |

Commission: $1.98/RT. Slippage: 1 tick ($0.5) on stop/time exits; half-tick on target.

## Diagnostic 5 — Coherent entry re-run (cost-inclusive)

Coherent alternatives: (A) OTE-70.5% limit after MSS, no FVG gate; (B) FVG-zone touch from mss+1 (Ep 38 alt entry). Both cost-inclusive (commission + 1-tick slip model).

- **OTE-only (70.5%):** n=9557, annual net **$-1,186**, avg **-1.74** ticks/trade
- **FVG-only (zone touch):** n=8592, annual net **$28,549**, avg **46.52** ticks/trade — **untrusted** (nearest targets resolved at OTE entry price; re-run needed with targets at FVG entry before treating as edge)

## Stop conditions

- **no_cost_surviving_coherent_edge:** True
- **entry_definitional_decision_required:** True
- **proceed_to_step4:** False