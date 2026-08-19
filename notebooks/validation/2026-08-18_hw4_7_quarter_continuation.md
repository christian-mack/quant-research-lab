# H-W4-7 Quarterly Close-Location Continuation (MNQ) — harness report

**Date:** 2026-08-18  
**git_sha:** `efc119e11495666a6e73d4161e2dcab649f7e337`  
**git_dirty:** `True`  
**Fill path:** M4 `BacktestEngine` (V7 provenance)  
**Costs:** $1.98 RT + 1 tick stop/time / 0.5 tick target  
**MNQ running N (DSR):** **15**  
**Verdict:** not issued this session

## Repro check vs Session 1

| Metric | Session 1 | This rerun | Delta | OK |
|--------|-----------|------------|-------|----|
| trades | 6410 | 6410 | 0 | yes |
| win_rate_pct | 50.5 | 50.5 | 0.0 | yes |
| net_pnl | 1358.7 | 1358.6999999999757 | -2.432898327242583e-11 | yes |
| max_dd | 6769.84 | 6769.840000000014 | 1.3642420526593924e-11 | yes |

Trade log: `2026-08-18_hw4_7_primary_trades.parquet`

## W4 pre-conditions

| Gate | Status |
|------|--------|
| Clean clone | **MET** (worktree of ledger-correction SHA) |
| TDD $2K vs $3K | **RESOLVED** — $2,000 pre-lock trail |
| MES loader | N/A (MNQ-only) |

## Forced deviations from spec

- M4 implements OPEN_OF_NEXT_BAR only: entry order is submitted on the closed first 15-min bar of the following quarter and fills at the **open of the next** 15-min bar (~15 min after the spec's 'close of first bar'). No CLOSE_OF_SIGNAL_BAR; no bespoke walker.
- V4 implausible-tick surface raised 15 → 250 because the pre-registered 50-pt target is 200 MNQ ticks gross (default 15 is ORB-scale and would false-fail).
- 15-min left-labeled bars never timestamp at 16:59 ET, so engine hygiene flatten does not fire on this grid; holds may cross the 17:00 ET maintenance break (counted below). Deadzone [17:00, 18:00) still suppresses entries if those bars exist.
- DLL spec text said '$200/contract per loss' for a 50-pt MNQ stop; 50×$2/pt=$100. Binding q uses $100; the $200 figure is reported as a side calculation.
- Committed MNQ running N: Track 1 + W2 = 13, W3 H-7 = 14, H-W4-7 primary = **15**. H-W4-1…6 were never registered and are not invented. Session 1 DSR used N=19; this rerun uses N=15.
- Session 3 execution is from a clean worktree of the ledger-correction SHA (H-W4-7 module + N-correction committed). Per-trade log is written (Session 1 aggregates-only JSON was a hygiene miss).
- V5 `validation_spot_checks.py` was imported by committed `validation.py` since fb264ac but the module itself was never on main (only in the dirty tree / now WIP). Restored onto this worktree so V1–V7 can run; fills/P&L path unchanged.
- Full-protocol graded path (not 60/40 IS as the pass/fail split). 60/40 is not the primary metric for this spec.

## DST spot-check

Spring reopen 2020-03-08 18:00 ET: **True**; fall reopen 2020-11-01 18:00 ET: **True**; weekday overnight DST-on/off: **True**.

## Quarter-range distribution (points)

| Year | n | p10 | p25 | median | p75 | p90 | % range < 50 | 50 / median |
|------|---|-----|-----|--------|-----|-----|--------------|-------------|
| 2020 | 1540 | 34.8 | 53.2 | 83.5 | 128.8 | 206.8 | 22.3% | 0.60 |
| 2021 | 1545 | 30.0 | 46.5 | 71.5 | 115.8 | 169.9 | 28.7% | 0.70 |
| 2022 | 1539 | 48.0 | 72.2 | 120.5 | 180.8 | 253.8 | 10.9% | 0.41 |
| 2023 | 1537 | 27.8 | 43.2 | 71.5 | 116.5 | 161.4 | 31.2% | 0.70 |
| 2024 | 1350 | 34.2 | 54.5 | 86.8 | 140.5 | 210.1 | 21.3% | 0.58 |
| 2025 | 1530 | 50.0 | 72.6 | 117.6 | 194.7 | 291.8 | 9.9% | 0.43 |
| 2026 | 286 | 65.1 | 102.8 | 153.0 | 213.2 | 297.5 | 2.4% | 0.33 |

Chart: `2026-08-18_hw4_7_quarter_continuation.png`

## Frequency screen (signal counts, no P&L)

- Quarters classified: **9330**
- Signals (not 0.50 / not degenerate): **9309** (**1477.7**/yr, **5.94**/session)
- No-trade quarters: **21**
- Clears ~200/yr floor: **True**
- Extreme tiers (>=0.75 or <=0.25): **4987** (53.6% of signals; ~3.18/session if gated, not graded).

### By block

| Block | n |
|-------|---|
| 18:00-22:00 | 1560 |
| 22:00-02:00 | 1559 |
| 02:00-06:00 | 1559 |
| 06:00-10:00 | 1564 |
| 10:00-14:00 | 1559 |
| 14:00-17:00 | 1508 |

### By tier

| Tier | n |
|------|---|
| ge_0.75 | 2966 |
| 0.50_to_0.75 | 2190 |
| 0.25_to_0.50 | 2132 |
| le_0.25 | 2021 |
| eq_0.50 | 0 |

## VALIDATION REPORT (V1–V7)

**Overall:** PASS

- **V1 Geometry coherence:** PASS — 0/6410 filled trades fail entry-time geometry
- **V2 Causal sequencing:** PASS — All trades exit at/after entry
- **V3 Cost application:** PASS — 0/6410 zero-commission; 0 net/gross mismatches
- **V4 Magnitude sanity:** PASS — Avg net 0.42 ticks/trade (surface > 250.0)
- **V5 Hand-computation spot check:** PASS — T1=ok T2=ok T5_reject=ok
- **V6 Dual-touch exposure:** PASS — 0.4% dual-touch on 6408 bracket exits
- **V7 Engine provenance:** PASS — All 6410 trades carry M4 engine provenance

## Headline economics (qty=1, net of costs)

| Metric | Value |
|--------|-------|
| Trades | 6410 |
| Trades/yr | 1017.5 |
| Win rate | 50.5% |
| Profit factor | 1.004 |
| Net P&L | $1,358.70 |
| $/yr | $215.67 |
| Max DD (closed path) | $6,769.84 |
| MAR qty=1 | 0.032 |

### Year-by-year net P&L (qty=1)

| Year | Net P&L |
|------|---------|
| 2020 | $-2,660.54 |
| 2021 | $2,757.40 |
| 2022 | $-314.10 |
| 2023 | $-3,126.32 |
| 2024 | $4,574.46 |
| 2025 | $-289.36 |
| 2026 | $417.16 |

## Skips / maintenance

- Engine signals: **9304**
- Skipped (position still open): **2894**
- Skipped (deadzone suppress): **0**
- Hygiene flatten exits (`session_maintenance_flatten_et`): **0**
- Holds crossing 17:00 ET close: **405**

## Max sustainable qty

- DD(1): **$6,769.84**
- R(q) ceiling: **$2,000** TDD (Wave 0c-corrected)
- q_max R(q): **0** (R(q)=10,154.76)
- DLL two-loss (correct 50×$2=**$100**/contract + friction $2.48): **q=4**
- DLL two-loss if spec's $200/contract figure were used: **q=2** (flagged as arithmetic slip; 50×$2=$100)
- **Binding q_max:** **0** (R(q) (no positive q))

### Graded at q=0

| Metric | Value | Floor $36k | Target $60k | Stretch $100k |
|--------|-------|------------|-------------|---------------|
| $/yr | $0.00 | no | no | no |
| MAR | n/a | — | — | — |
| Eval pass (30-session) | 0.00% (0/1538) | no | no | no |

Qty=1 eval diagnostic (not graded): 1.04% (16/1538).

## Deflated Sharpe (N=15)

- Observed trade-series Sharpe: **0.1644**
- PSR vs E[max SR] null: **1.0000**
- E[max SR] (N=15, var from this SR + 14 zeros): **0.0752**
- n_trades (observations): **6410**

Variance-across-trials uses this hypothesis's Sharpe plus 14 zeros (committed ledger: Track 1 + W2 = 13, W3 H-7 = 14, H-W4-7 primary = **15**; H-W4-1…6 were never registered). **PSR near 1 here is an artifact of that zero-fill shrinking E[max SR]; it is not evidence of edge.** Trade-series Sharpe ~0.16 with PF 1.00 is noise-scale.

## Kill/promote

Not issued. Operator verdict in a fresh context.
