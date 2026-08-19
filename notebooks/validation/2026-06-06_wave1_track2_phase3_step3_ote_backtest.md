# Wave 1 Track 2 — Phase 3 step 3: Standalone OTE backtest

**Date run:** 2026-06-06  
**git_sha:** `0db224fc2bd1ef320064fb04c9a9a3d9d095e366`  
**Protocol:** 2020-01-01 → 2026-04-19  
**Mode:** Unconstrained RTH (no bias gate, multi-setup/session)  

## (a) Trade frequency

- Total setups (primary): **9,557**
- Trades/year: **1365.3**
- Sessions with ≥1 trade: **1,561** (100.0% of sessions)
- Sessions with multiple trades: **1,538** (98.5% of trading sessions)
- Max setups in one session: **14**

## (b) Headline economics (primary, qty=1 MNQ)

- Total P&L: **$14,648**
- Annual P&L: **$2,093**
- Win rate: **51.7%**
- Avg win / avg loss: **$30** / **$-29**
- Reward:Risk (avg win / |avg loss|): **1.04**
- Avg R: **0.04**

### Year-by-year P&L (primary)

- 2020: $2,712
- 2021: $871
- 2022: $2,335
- 2023: $3,718
- 2024: $3,631
- 2025: $1,852
- 2026: $-472

## (c) FVG/OTE conflict

- Conflict fraction (>4 ticks): **99.3%** (9,488 / 9,557)
- Total P&L OTE entry: $14,648; FVG-zone entry: $220,760 (delta $206,113)

## (d) Target fork preview

- Nearest (counterfactual on primary fills): WR 51.7%, annual $2,093
- Far (counterfactual on primary fills): WR 51.7%, annual $2,093
- Far (active variant log): WR 34.6%, annual $630

## (e) Bias overlap preview (C1)

- Fraction setups on bias-agreeing sessions: **9.2%**
- Agree subset annual P&L: **$340** (WR 52.6%)
- Disagree/no-bias subset annual P&L: **$1,752** (WR 51.6%)

## Stop conditions

- **low_frequency_STOP:** False
- **n_trades_primary:** 9557
- **high_conflict_SURFACE:** True
- **conflict_fraction:** 0.9928
- **all_variants_negative_SURFACE:** False
- **strong_positive_EDGE_SURFACE:** True
- **annual_pnl_primary:** 2092.53

## Variant economics (all 5 logs)

- **primary:** n=9,557, annual=$2,093, WR=51.7%
- **target_far:** n=9,557, annual=$630, WR=34.6%
- **stop_fvg_c2:** n=9,557, annual=$-21,798, WR=46.9%
- **entry_ote_62:** n=9,204, annual=$8,844, WR=57.4%
- **fvg_nearest_ote:** n=9,557, annual=$2,093, WR=51.7%

Trade logs: `C:\Users\chris\Documents\Trading\quant-research-lab\notebooks\validation\2026-06-06_wave1_track2_phase3_step3_ote_trades`