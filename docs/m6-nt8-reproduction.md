# M6 — Python ORB+Opt3 vs NT8 reference (smoke, not parity)

**Protocol window:** 2020-01-01 through **2026-04-19** (inclusive calendar end date), matching the six-year NT8 study cited in the lessons log. **Python:** funded ORB+Opt3 parameters, **qty = 3** (`production_orb_opt3_funded_params()`). **Bars:** NT8 MNQ export, RTH only, continuous contract, `cme_session_date` assigned in Chicago. **Runs:** `uv run python scripts/run_m6_orb_baseline.py` — segments with `split_dataframe_at_operator_export_gaps` (fresh `OrbStrategy` + `BacktestEngine` per segment) so positions do not span operator-known export holes.

**Reference (lessons log — 2026-04-28, production simplification / six-year NT8):** ORB+Opt3 on the NT8 baseline was summarized as **~$10,885/yr per contract**, **63.8%** win rate, **7/7** positive calendar years, **max drawdown −$17,880** (instrument/account unit as recorded in NT8; not re-derived here).

## Side-by-side aggregates

| Metric | NT8 (lessons log) | Python (this run) | Notes |
|--------|-------------------|-------------------|--------|
| Net P&amp;L (protocol total, **3 contracts**) | Not stated as a single total | **+$41,878.50** | NT8 headline is **per-contract annualized**, not window total. |
| **Per-contract $ / year** | **~$10,885** | **~$2,216** | Python: `net_pnl_total / 3 / protocol_year_fraction` (~6.298 calendar years). |
| Closed trades | Not in reference | **398** | No NT8 trade count in the lessons log → **±5% trade-count band not applicable**. |
| Win rate | **63.8%** | **64.57%** | Δ **0.77** percentage points. |
| Profit factor | Not stated | **1.68** | — |
| Avg win / avg loss | Not stated | **+$403.20** / **−$460.78** | Per round-trip, **3 MNQ** scale. |
| Max drawdown (cumulative net per closed trade, **combined**) | **−$17,880** | **−$9,451.50** | NT8 unit ambiguous (account vs per-contract); Python **per-contract** max DD ≈ **−$3,150.50**. |
| Positive calendar years (Chicago exit-year P&amp;L) | **7 / 7** | **4** years **> 0** in **2020–2026** slice | See annual table below. |

### Python — calendar-year net P&amp;L (Chicago `exit_time`, **closed trades only**)

| Year | Net P&amp;L (3 lots) |
|------|----------------------|
| 2020 | +$3,333.00 |
| 2021 | $0.00 |
| 2022 | +$1,960.50 |
| 2023 | $0.00 |
| 2024 | +$25,318.50 |
| 2025 | +$11,346.00 |
| 2026 | −$79.50 |

### Python — closed trades by **exit** year (Chicago)

| Year | Trades |
|------|--------|
| 2020 | 167 |
| 2021 | 0 |
| 2022 | 32 |
| 2023 | 0 |
| 2024 | 65 |
| 2025 | 123 |
| 2026 | 11 |

Run metadata: **5** segments, **599,533** RTH bars in the protocol window; `commission_total` in this engine run **0** (commission model unchanged vs lessons).

## Smoke bands (operator)

| Check | Target | Result |
|--------|--------|--------|
| Win rate | NT8 ± **2** percentage points | **Pass** (63.8% vs 64.57%). |
| Trade count | NT8 ± **5%** | **N/A** (no reference count). |
| Net P&amp;L | NT8 ± **10%** on comparable basis | **Fail on headline annual $/contract** (~$2.2k vs ~$10.9k). |

Interpreting the P&amp;L band requires a like-for-like basis. Lessons reference: **per-contract annual**; Python row matches that math. The gap is far wider than 10%, so the strict band is not met.

## Divergence assessment (brief, not exhaustive)

1. **Win rate alignment** — The Python engine reproduces NT8 **win-rate scale** (~64%). That supports the reframed M6 goal: the **trade outcome mix** is in-family; the problem is not “completely different strategy statistics on the same bar tape.”

2. **Dollar path and calendar structure** — **Per-contract annual P&amp;L** in Python is much lower than the NT8 summary. Investigation of the consolidated trade log shows **round-trips with multi-year holding horizons** (order of **10k+ hours**) and **calendar years with zero exits** despite full **RTH bar coverage** in 2021 and 2023. Intraday ORB with disabled max-hold should not accumulate multi-year holds when session-aware exits are correct.

3. **Probable engine/module coupling issue (not deep-forensics scope)** — `OrbStrategy` calls `_check_session_reset` at the start of each bar, which resets the FSM to **IDLE** on a new `cme_session_date` **without** flattening or re-entering **TRIGGERED** management when `ctx.position_qty != 0`. If working exits are not preserved exactly as NT8/C# across the session boundary, the strategy can **lose coherence** between open position and state machine, yielding **orphaned** or incorrectly managed positions. That pattern is consistent with **2021 / 2023** showing **no** exit-year trades while bars exist, and with **segment 0** spanning **2020-01-02 → 2024-03-28** in one backtest (420k+ bars).

4. **Drawdown** — Python max DD is **smaller in magnitude** than the NT8 −$17,880 figure; definitions may differ (equity curve sampling, contracts, intraday vs closed-trade), and the pathological holds distort both trade cadence and DD statistics.

## Milestone conclusion (reframed M6)

- **Strict smoke bands:** **not** met on **per-contract annual net P&amp;L** vs the lessons-log NT8 headline.
- **Engine reasonableness:** **partial** — **win rate** is reassuring; **dollar path and calendar-year trade distribution** indicate the **Python ORB + current session/position coupling** is **not** yet trustworthy for long-span “match NT8 economics” claims.
- **Recommendation:** Treat M7 work as unblocked **only if** the program accepts “M6 documented gap + fix queued” rather than “M6 pass.” Priority follow-up: **reconcile `OrbStrategy` session reset with non-zero `position_qty`** (and verify against C# `ORBModule` / session-end behavior), then **re-run** this script and revisit the bands.

Artifact: metrics JSON emitted by `scripts/run_m6_orb_baseline.py` on the operator MNQ export; this file **2026-04-28**.
