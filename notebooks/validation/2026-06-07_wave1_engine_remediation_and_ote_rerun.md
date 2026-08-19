# Wave 1 — Engine remediation + clean OTE re-run

**Date:** 2026-06-07  
**git_sha:** `0db224fc2bd1ef320064fb04c9a9a3d9d095e366`  
**Protocol:** 2020-01-01 → 2026-04-19  

## Scope

- **P0:** Structural geometry guard (stop on loss side, target on profit side) — enforced in M4 bracket validation + OTE setup assembly.
- **P1:** OTE fills consolidated onto M4 BacktestEngine with unified cost model ($1.98 RT, 1 tick stop/time slip, ½ tick target, no entry slip).
- **P2:** Dual-touch calibration **deferred** — stop-first rule retained.

## Cost model (engine-native)

Commission $0.99/fill ($1.98 RT) in BacktestEngine; slippage 1 tick default (stop/time), 0 entry (limit touch), 0.5 tick target — applied once per fill in engine.

## Comparison to step 3c (pre-remediation, comm+slip)

| Config | Step 3c annual (full) | Clean M4 Frame B | Δ Frame B |
|--------|----------------------:|-----------------:|----------:|
| OTE62 | $5,099 | $4,629 | $-469 |
| OTE705 | $-2,410 | $11,155 | $+13,565 |
| FVG_only | $26,185 | $2,798 | $-23,386 |

## Results by config

### OTE 70.5% full RTH

- Setups detected: **51,100**
- Geometry rejects: **18,667** (36.5%) — {'stop_wrong_side': 18667}
- Setups filled: **12,978**
- Trades: **12,978**

**Full protocol (comm+slip, engine-native):**
- Annual net: **$8,683/MNQ**
- Net ticks/trade: **9.37**
- WR: **54.0%** | R:R **1.13**

**Frame B (2021–2025 eval years):**
- Annual net: **$11,155/MNQ**
- Net ticks/trade: **9.37**

**Year-by-year net (comm+slip):**
- 2020: $2,750 *(partial)*
- 2021: $5,296
- 2022: $19,170
- 2023: $6,327
- 2024: $9,561
- 2025: $15,422
- 2026: $2,252 *(partial)*
- Apex DLL ($30K/yr sizing, Frame B): qty=2.69, max session loss=$-990.31, fits tier-1=True, worst=2022-05-11

### OTE 62% full RTH

- Setups detected: **64,815**
- Geometry rejects: **29,537** (45.6%) — {'stop_wrong_side': 29537}
- Setups filled: **12,198**
- Trades: **12,198**

**Full protocol (comm+slip, engine-native):**
- Annual net: **$3,375/MNQ**
- Net ticks/trade: **3.87**
- WR: **45.1%** | R:R **1.38**

**Frame B (2021–2025 eval years):**
- Annual net: **$4,629/MNQ**
- Net ticks/trade: **3.87**

**Year-by-year net (comm+slip):**
- 2020: $135 *(partial)*
- 2021: $1,943
- 2022: $12,055
- 2023: $2,075
- 2024: $2,894
- 2025: $4,181
- 2026: $342 *(partial)*
- Apex DLL ($30K/yr sizing, Frame B): qty=6.48, max session loss=$-3854.57, fits tier-1=False, worst=2025-11-21

### FVG-only full RTH

- Setups detected: **252,303**
- Geometry rejects: **59,244** (23.5%) — {'stop_wrong_side': 59244}
- Setups filled: **6,904**
- Trades: **6,904**

**Full protocol (comm+slip, engine-native):**
- Annual net: **$2,256/MNQ**
- Net ticks/trade: **4.57**
- WR: **35.2%** | R:R **2.10**

**Frame B (2021–2025 eval years):**
- Annual net: **$2,798/MNQ**
- Net ticks/trade: **4.57**

**Year-by-year net (comm+slip):**
- 2020: $601 *(partial)*
- 2021: $1,611
- 2022: $3,080
- 2023: $1,845
- 2024: $2,770
- 2025: $4,685
- 2026: $1,197 *(partial)*
- Apex DLL ($30K/yr sizing, Frame B): qty=10.72, max session loss=$-8388.06, fits tier-1=False, worst=2025-04-07

## Stop conditions

- **ote62_geometry_reject_gt_30pct:** TRIGGERED — 45.6% of OTE 62% setups rejected (>30% threshold)
- **ote62_frame_b_negative:** NOT triggered — Frame B annual net $4,629/MNQ
- **fvg_artifact_not_collapsed:** NOT triggered — FVG-only $2,798/yr, 4.6 ticks/trade (artifact collapsed)
- **dual_touch_p2:** DEFERRED — stop-first rule unchanged; uncalibrated

## Operator summary

P0 geometry guard + P1 M4 consolidation complete. Clean OTE 62% Frame B: $4,629/MNQ/yr (step 3c was $5,099). FVG-only collapsed to $2,798/yr (was $26,185 artifact). Geometry reject rate OTE 62%: 45.6%. Dual-touch (P2) unchanged.