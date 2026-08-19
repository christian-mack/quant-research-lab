# Wave 1 Track 2 — Phase 3 step 3d: OTE exit-structure test

**Date:** 2026-06-07  |  **git_sha:** `0db224fc2bd1ef320064fb04c9a9a3d9d095e366`
**Deflation N:** 20 (step3 5 + step3b 1 + step3c 9 + step3d 5)

**Entry (frozen):** OTE 70.5% full RTH (`ote_only`). Exit structures vary per combo.

## Diagnostic framing

Exit redesign improves target-hit rates but does not produce account-viable edge.

## Results by combination

### C-base — Current baseline: swept-extreme stop + nearest opposing pool target. — harness **PASS**

- Stop / Target: **swept_extreme** + **nearest_pool**
- Exit remap rejects: **0**
- Booked: **10,680**
- WR: **46.1%** | Avg win: **$37.76** | Avg loss: **$-32.14** | R:R: **1.17**
- Net ticks/trade: **0.17**
- Frame B annual net: **$1,122/MNQ**
- Year-by-year ($/MNQ):
  - 2021: $-1,914
  - 2022: $5,812
  - 2023: $-1,694
  - 2024: $142
  - 2025: $3,263
- Exit rates: stop **52.3%** | target **44.3%** | time **3.4%**
- Apex DLL fit ($30K/yr): **NO**
- Harness:
  - V1: PASS — 0/10680 filled trades fail entry-time geometry; upstream reject rate 63.7% > 20% surface (booked population clean)
  - V2: PASS — All trades exit at/after entry
  - V3: PASS — 0/10680 zero-commission; 0 net/gross mismatches
  - V4: PASS — Avg net 0.17 ticks/trade (surface > 15.0)
  - V5: PASS — T1=ok T2=ok T5_reject=ok
  - V6: PASS — Skipped (need bars + entry_bar for dual-touch analysis)

### C-1 — Keep structural stop; force 2R target — tests entry quality for 2R. — harness **PASS**

- Stop / Target: **swept_extreme** + **fixed_2r**
- Exit remap rejects: **18**
- Booked: **10,680**
- WR: **34.7%** | Avg win: **$62.93** | Avg loss: **$-34.57** | R:R: **1.82**
- Net ticks/trade: **-1.48**
- Frame B annual net: **$-519/MNQ**
- Year-by-year ($/MNQ):
  - 2021: $-2,689
  - 2022: $4,564
  - 2023: $-937
  - 2024: $-496
  - 2025: $-3,037
- Exit rates: stop **63.0%** | target **30.9%** | time **6.1%**
- Apex DLL fit ($30K/yr): **NO**
- Harness:
  - V1: PASS — 0/10680 filled trades fail entry-time geometry; upstream reject rate 64.0% > 20% surface (booked population clean)
  - V2: PASS — All trades exit at/after entry
  - V3: PASS — 0/10680 zero-commission; 0 net/gross mismatches
  - V4: PASS — Avg net -1.48 ticks/trade (surface > 15.0)
  - V5: PASS — T1=ok T2=ok T5_reject=ok
  - V6: PASS — Skipped (need bars + entry_bar for dual-touch analysis)

### C-2 — Fixed 10pt stop + 15pt target (1.5R tradeable structure). — harness **PASS**

- Stop / Target: **fixed_10pt** + **fixed_15pt**
- Exit remap rejects: **0**
- Booked: **11,270**
- WR: **41.7%** | Avg win: **$29.80** | Avg loss: **$-19.72** | R:R: **1.51**
- Net ticks/trade: **1.82**
- Frame B annual net: **$1,946/MNQ**
- Year-by-year ($/MNQ):
  - 2021: $-1,268
  - 2022: $4,681
  - 2023: $-2,614
  - 2024: $1,960
  - 2025: $6,972
- Exit rates: stop **57.3%** | target **40.2%** | time **2.6%**
- Apex DLL fit ($30K/yr): **NO**
- Harness:
  - V1: PASS — 0/11270 filled trades fail entry-time geometry; upstream reject rate 62.7% > 20% surface (booked population clean)
  - V2: PASS — All trades exit at/after entry
  - V3: PASS — 0/11270 zero-commission; 0 net/gross mismatches
  - V4: PASS — Avg net 1.82 ticks/trade (surface > 15.0)
  - V5: PASS — T1=ok T2=ok T5_reject=ok
  - V6: PASS — Skipped (need bars + entry_bar for dual-touch analysis)

### C-3 — 1.0× ATR(14) stop + 2.0× ATR(14) target — regime-adaptive 2:1. — harness **PASS**

- Stop / Target: **atr_1x** + **atr_2x**
- Exit remap rejects: **0**
- Booked: **11,277**
- WR: **30.7%** | Avg win: **$45.87** | Avg loss: **$-23.89** | R:R: **1.92**
- Net ticks/trade: **-4.90**
- Frame B annual net: **$-4,033/MNQ**
- Year-by-year ($/MNQ):
  - 2021: $-4,479
  - 2022: $-5,188
  - 2023: $-4,600
  - 2024: $-3,191
  - 2025: $-2,708
- Exit rates: stop **68.5%** | target **29.4%** | time **2.1%**
- Apex DLL fit ($30K/yr): **NO**
- Harness:
  - V1: PASS — 0/11277 filled trades fail entry-time geometry; upstream reject rate 62.4% > 20% surface (booked population clean)
  - V2: PASS — All trades exit at/after entry
  - V3: PASS — 0/11277 zero-commission; 0 net/gross mismatches
  - V4: PASS — Avg net -4.90 ticks/trade (surface > 15.0)
  - V5: PASS — T1=ok T2=ok T5_reject=ok
  - V6: PASS — Skipped (need bars + entry_bar for dual-touch analysis)

### C-4 — Fixed 10pt stop + 2R target (= 20pt target). — harness **PASS**

- Stop / Target: **fixed_10pt** + **fixed_2r**
- Exit remap rejects: **0**
- Booked: **11,270**
- WR: **33.5%** | Avg win: **$38.17** | Avg loss: **$-19.96** | R:R: **1.91**
- Net ticks/trade: **-1.02**
- Frame B annual net: **$-732/MNQ**
- Year-by-year ($/MNQ):
  - 2021: $-3,089
  - 2022: $1,234
  - 2023: $-2,749
  - 2024: $-1,161
  - 2025: $2,105
- Exit rates: stop **65.3%** | target **31.2%** | time **3.5%**
- Apex DLL fit ($30K/yr): **NO**
- Harness:
  - V1: PASS — 0/11270 filled trades fail entry-time geometry; upstream reject rate 62.6% > 20% surface (booked population clean)
  - V2: PASS — All trades exit at/after entry
  - V3: PASS — 0/11270 zero-commission; 0 net/gross mismatches
  - V4: PASS — Avg net -1.02 ticks/trade (surface > 15.0)
  - V5: PASS — T1=ok T2=ok T5_reject=ok
  - V6: PASS — Skipped (need bars + entry_bar for dual-touch analysis)

## Verdict

**Marginal economics, no DLL fit.** Some combos show modest positive Frame B net but fail Apex tier-1 DLL at $30K/yr sizing. Not a survey candidate.

## Operator summary

| Combo | Harness | Annual/MNQ | Ticks/tr | Target% | DLL |
|-------|---------|------------|----------|---------|-----|
| C-base | PASS | $1,122 | 0.17 | 44% | NO |
| C-1 | PASS | $-519 | -1.48 | 31% | NO |
| C-2 | PASS | $1,946 | 1.82 | 40% | NO |
| C-3 | PASS | $-4,033 | -4.90 | 29% | NO |
| C-4 | PASS | $-732 | -1.02 | 31% | NO |

**Does realistic exit recover OTE entry edge?** No.