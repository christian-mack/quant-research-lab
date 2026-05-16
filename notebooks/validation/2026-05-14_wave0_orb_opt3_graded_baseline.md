# Wave 0 — ORB+Opt3 graded baseline

**Git SHA:** `3cb97cfbcb9df07474daa348634e2b12c08899ac`  
**Dirty tree:** True  
**Generated:** 2026-05-16T04:43:55.803825+00:00  

## Headline

- **Max sustainable qty (R(q)):** **0** (binding: no_positive_q; R at q_max: $0.00; headroom: $3,000.00 under $3,000 cap).
- **DD(1) magnitude:** $2,675.00 (max drawdown on cumulative closed-trade path, qty=1).
- **Avg annual P&L at q_max:** **$0.00**/yr (Phase 2 tier bucket: **below_floor** vs $36k / $60k / $100k).
- **Simulated eval pass rate (rolling 30 sessions, at q_max):** **0.00%** (0/1532 windows).

### Operator review flags

- **R(q) vs production:** With **DD(1)≈$2,675**, pre-registered **R(q)** yields **q_max=0** — no positive integer size satisfies the conservative cap. Production at **qty=3** therefore **exceeds** this formal sizing rule; see JSON `operator_flags`.
- **M6 reconciliation:** Wave 0 per-contract annual **$1,014.16** vs M6 anchor **~$1,014** → **0.02%** abs diff (within 5%: **True**).
- **Multi-entry `entry_cme_session_date`:** **4** days (max **6** closes). See JSON: sequential same-day round-trips (BE/target), not concurrent size. DD at qty 2/3 = **$5,350.00** / **$8,025.00** matches **q×DD(1)** (True).

## Per-contract (qty=1) economics

| Metric | Value |
|--------|-------|
| Trade count | 799 |
| Total P&L | $6,389.00 |
| Per-contract $/yr | $1,014.16 |
| Win rate | 62.95% |
| Breakeven WR (i.i.d. approx) | 60.84% |
| Edge over BE (pp) | 2.12 |
| Avg win / avg loss | $84.29 / $-130.95 |
| Max drawdown | $-2,675.00 |
| Profitable calendar years (2020–2026, qty=1) | 4 / 7 |

### Year-by-year P&L (qty=1, Chicago exit year)

| Year | Net P&L | Trades (exits) |
|------|---------|----------------|
| 2020 | $1,038.50 | 165 |
| 2021 | $0.00 | 0 |
| 2022 | $2,038.00 | 86 |
| 2023 | $-1,386.50 | 223 |
| 2024 | $1,375.00 | 166 |
| 2025 | $3,912.00 | 138 |
| 2026 | $-588.00 | 21 |

### Year-by-year max DD (within-year cumulative path)

| Year | Max DD |
|------|--------|
| 2020 | $-660.00 |
| 2021 | $0.00 |
| 2022 | $-484.00 |
| 2023 | $-2,675.00 |
| 2024 | $-902.00 |
| 2025 | $-1,502.50 |
| 2026 | $-816.50 |

**Global max DD** from **exit** `2023-11-16 15:09:00+00:00` (trough) vs peak before trough **exit** `2023-01-23 15:02:00+00:00`.

## Bootstrap 95% CI — annual P&L per contract

Low **$-362.24** — point **$1,014.16** — high **$2,766.52** (10000 resamples).

## Eval simulation detail

- Windows: **1532**, passes: **0**, fail trailing: **0**, fail DLL: **0**, fail no target: **1532**.
- No passing windows — time-to-pass and trailing-margin distributions are **N/A**.

Full machine-readable metrics: `2026-05-14_wave0_orb_opt3_graded_baseline.json`.
