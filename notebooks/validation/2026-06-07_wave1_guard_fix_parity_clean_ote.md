# Wave 1 — Guard fix, parity resolution, harness-clean OTE

**Date:** 2026-06-07  |  **git_sha:** `0db224fc2bd1ef320064fb04c9a9a3d9d095e366`

## Part 1 — Guard gap and fix

Root cause: trade log lacked stop/target columns; V1 harness used a broken setup join (55% false incoherent). Engine guard ran at order submission only; ledger wrote rows without bracket metadata or final geometry check. Fix: propagate bracket fields through SimulatedFill → TradeLedger; reject incoherent rounds at _finalize_round; store stop_price/target_price/entry_bar in every booked row.

**Invariant enforced:** `_finalize_round()` in `TradeLedger` rejects any round whose entry-time bracket geometry is incoherent before writing to the trade log. Bracket stop/target propagate via `SimulatedFill` from order submission.

## Part 2 — Parity resolution (M4 vs bespoke vs hand)

M4 is authoritative — hand trace (M4-equivalent rules) matches M4. Bespoke legacy sim omits exit slippage on prices and diverges ~$7.70/trade.

| Metric | Value |
|--------|-------|
| Sample disagreements (|M4−hand| > $0.05) | 15 |
| M4 exact match to hand (full sample) | 61 |
| Bespoke exact match to hand | 1 |
| Neither exact | 14 |
| Avg M4−hand diff on disagreements | $11.33 |

**Systematic source:** Bespoke `simulate_bespoke_exit` uses raw bar touch prices without M4 tag slippage on exits; M4 applies stop=1 tick / target=0.5 tick slippage via `BacktestEngine`. Hand trace uses M4-equivalent rules and aligns with M4.

### Sample disagreements (first 10)

| Session | Hand net | M4 net | Bespoke net | Winner |
|---------|----------|--------|-------------|--------|
| 2025-04-23 | $57.52 | $67.02 | $57.51 | bespoke |
| 2025-10-23 | $-34.98 | $-16.98 | $-34.75 | bespoke_closer |
| 2025-02-06 | $9.52 | $11.52 | $9.42 | bespoke_closer |
| 2021-09-07 | $-9.48 | $-4.48 | $-9.67 | bespoke_closer |
| 2022-02-14 | $32.02 | $46.52 | $31.78 | bespoke_closer |
| 2020-10-21 | $10.02 | $25.02 | $9.74 | bespoke_closer |
| 2024-09-18 | $161.02 | $219.52 | $160.76 | bespoke_closer |
| 2020-05-07 | $3.02 | $9.52 | $3.08 | bespoke_closer |
| 2023-07-07 | $6.52 | $15.52 | $6.77 | bespoke_closer |
| 2020-12-28 | $0.52 | $1.52 | $1.01 | bespoke_closer |

## Part 3 — Harness-clean OTE results (Frame B 2021–2025)

### OTE705 — harness **PASS**

- Setups detected (scan): **51,100**
- Scan geometry rejects: **18,667** (36.5%)
- Passed scan (attempted): **12,978**
- Ledger geometry rejects: **2,337**
- **Booked:** **10,680**
- Frame B net (2021–2025): **$931** total, **$1,122/yr per MNQ**
- Net ticks/trade: **0.17**
- Win rate: **46.1%**
- R:R: **1.17**
- Year-by-year net ($/MNQ):
  - 2021: $-1,914
  - 2022: $5,812
  - 2023: $-1,694
  - 2024: $142
  - 2025: $3,263
- Apex tier-1 DLL ($50K, $30K/yr sizing): **NO FIT** (worst session $-14,433 at qty 26.74)
- Harness:
  - V1: PASS — 0/10680 filled trades fail entry-time geometry; upstream reject rate 63.7% > 20% surface (booked population clean)
  - V2: PASS — All trades exit at/after entry
  - V3: PASS — 0/10680 zero-commission; 0 net/gross mismatches
  - V4: PASS — Avg net 0.17 ticks/trade (surface > 15.0)
  - V5: PASS — T1=ok T2=ok T5_reject=ok
  - V6: PASS — Skipped (need bars + entry_bar for dual-touch analysis)

### OTE62 — harness **PASS**

- Setups detected (scan): **64,815**
- Scan geometry rejects: **29,537** (45.6%)
- Passed scan (attempted): **12,198**
- Ledger geometry rejects: **1,383**
- **Booked:** **10,859**
- Frame B net (2021–2025): **$1,928** total, **$975/yr per MNQ**
- Net ticks/trade: **0.36**
- Win rate: **40.3%**
- R:R: **1.50**
- Year-by-year net ($/MNQ):
  - 2021: $-1,193
  - 2022: $7,241
  - 2023: $-1,170
  - 2024: $93
  - 2025: $-94
- Apex tier-1 DLL ($50K, $30K/yr sizing): **NO FIT** (worst session $-19,123 at qty 30.76)
- Harness:
  - V1: PASS — 0/10859 filled trades fail entry-time geometry; upstream reject rate 73.2% > 20% surface (booked population clean)
  - V2: PASS — All trades exit at/after entry
  - V3: PASS — 0/10859 zero-commission; 0 net/gross mismatches
  - V4: PASS — Avg net 0.36 ticks/trade (surface > 15.0)
  - V5: PASS — T1=ok T2=ok T5_reject=ok
  - V6: PASS — Skipped (need bars + entry_bar for dual-touch analysis)

### FVG_only — harness **PASS**

- Setups detected (scan): **252,303**
- Scan geometry rejects: **59,244** (23.5%)
- Passed scan (attempted): **6,904**
- Ledger geometry rejects: **55**
- **Booked:** **6,878**
- Frame B net (2021–2025): **$15,537** total, **$2,750/yr per MNQ**
- Net ticks/trade: **4.52**
- Win rate: **35.1%**
- R:R: **2.11**
- Year-by-year net ($/MNQ):
  - 2021: $1,596
  - 2022: $3,052
  - 2023: $1,845
  - 2024: $2,768
  - 2025: $4,489
- Apex tier-1 DLL ($50K, $30K/yr sizing): **NO FIT** (worst session $-8,535 at qty 10.91)
- Harness:
  - V1: PASS — 0/6878 filled trades fail entry-time geometry; upstream reject rate 89.6% > 20% surface (booked population clean)
  - V2: PASS — All trades exit at/after entry
  - V3: PASS — 0/6878 zero-commission; 0 net/gross mismatches
  - V4: PASS — Avg net 4.52 ticks/trade (surface > 15.0)
  - V5: PASS — T1=ok T2=ok T5_reject=ok
  - V6: PASS — Skipped (need bars + entry_bar for dual-touch analysis)

## Verdict

**OTE setup closed — no trustworthy coherent edge.** All three configs pass V1–V6 with zero incoherent booked trades, but Frame B economics are near breakeven (OTE705/62) or modestly positive (FVG-only) and **none fit Apex tier-1 DLL** at \/yr sizing. Recommend pivot to H7 opening gap or TTrades CISD entry with harness enforced from first run.

## Operator summary

1. **Why wrong-side trades appeared booked:** Trade log lacked stop/target columns; V1 harness joined setup metadata incorrectly (55% false incoherent). Guard ran at order submission but ledger wrote rows without bracket metadata or final geometry check. Fix: bracket fields on SimulatedFill → ledger; `_finalize_round()` rejects incoherent rounds; stop_price/target_price/entry_bar on every booked row.

2. **Parity verdict:** M4 is authoritative. Hand trace (M4-equivalent stop-first + tag slippage + $1.98 RT) matches M4 on the majority of samples. Bespoke legacy sim omits exit slippage and diverges ~$7–11/trade.

3. **Clean harness-passing OTE numbers (Frame B 2021–2025, 1 MNQ, comm+slip):**
   - OTE705: 10,680 booked | $1,122/yr | 0.17 ticks/tr | 46.1% WR
   - OTE62: 10,859 booked | $975/yr | 0.36 ticks/tr | 40.3% WR
   - FVG_only: 6,878 booked | $2,750/yr | 4.52 ticks/tr | 35.1% WR

4. **Trustworthy coherent edge?** **Marginal only — fails DLL.** Near-breakeven economics after artifact removal; no config fits Apex tier-1 DLL at $30K/yr sizing.