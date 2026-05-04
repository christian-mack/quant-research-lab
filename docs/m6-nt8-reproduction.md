# M6 — Python ORB+Opt3 vs NT8 reference (smoke, not parity)

**Protocol window:** 2020-01-01 through **2026-04-19** (inclusive calendar end date), matching the six-year NT8 study cited in the lessons log. **Python:** funded ORB+Opt3 parameters, **qty = 3** (`production_orb_opt3_funded_params()`). **Bars:** NT8 MNQ export, RTH only, continuous contract, `cme_session_date` assigned in Chicago. **Runs:** `uv run python scripts/run_m6_orb_baseline.py` — segments with `split_dataframe_at_operator_export_gaps` (fresh `OrbStrategy` + `BacktestEngine` per segment) so positions do not span operator-known export holes.

**Reference (lessons log — 2026-04-28, production simplification / six-year NT8):** ORB+Opt3 on the NT8 baseline was summarized as **~$10,885/yr per contract**, **63.8%** win rate, **7/7** positive calendar years, **max drawdown −$17,880** (instrument/account unit as recorded in NT8; not re-derived here).

---

## C# vs Python — session and open positions (why the bug happened)

In **FluxV1Strategy**, `CheckSessionReset` runs **before** `RunDecisionPipeline` on each bar. On a new `SessionDate` it calls `ExecutionEngine.ResetDaily()`, which sets **`_positionState = null`**, and `ORBModule.ResetSessionState()`, which returns the ORB FSM to **Idle** for **next** opening-range logic.

**Critical:** In NT8, **SetStopLoss** / **SetProfitTarget** are **broker-attached** to the instrument. `ManagePosition` reads/writes that state via managed orders; even when the C# engine’s RAM state is cleared, **working protective orders typically remain on the symbol**. Python has no separate broker layer: brackets only exist if `OrbStrategy` keeps emitting consistent exit instructions and the simulator’s `working` queue stays coherent.

The **M5** bug: on a new `cme_session_date`, `OrbStrategy` reset its **full** session FSM to **Idle** **before** consulting `ctx.position_qty`. With `TRIGGERED` cleared, the `on_bar` path fell through into **daily entry** states (`Idle` / `FormingRange` / `Watching`) while `position_qty != 0` was **disallowed** in several branches (`return []`), so **`_manage_open` stopped running** each bar. Break-even and bracket refresh **paused** across sessions even though C# keeps managing the live position.

**Fix (landed in tree):** After session rollover, if **`ctx.position_qty == 0`**, perform a **full** reset (entry machine only). If **non-zero**, **`_reset_session_for_new_day_with_open_position()`** clears only **entry** accumulation (range, VWAP numerators) and forces **`_state = TRIGGERED`**. **`on_bar`** then **returns `_manage_open`** whenever **`position_qty != 0`**, **before** any entry logic—mirroring the pipeline ordering where NT8 still holds stops while the ORB module’s **daily** state machine restarts.

Regression: `tests/backtest/test_orb_module.py::test_orb_cross_session_position_break_even_regression`.

---

## Python — pre-fix vs post-fix (same script, same data)

| Metric | **Pre-fix** Python | **Post-fix** Python |
|--------|-------------------|---------------------|
| Closed trades | 398 | 391 |
| Net P&amp;L total (3 lots) | +$41,878.50 | +$41,115.00 |
| Per-contract $ / yr | ~$2,216 | ~$2,175 |
| Win rate | 64.57% | 64.19% |
| Profit factor | 1.68 | 1.67 |
| Avg win / avg loss | +$403.20 / −$460.78 | +$408.75 / −$462.27 |
| Max drawdown (combined) | −$9,451.50 | −$9,451.50 |
| Max drawdown (÷ 3) | ~−$3,150.50 | ~−$3,150.50 |

Pre-fix row is the baseline recorded before the session/position fix (same `run_m6_orb_baseline.py`, operator MNQ export). Post-fix row is from the **2026-04-28** rerun after the fix.

### Post-fix — calendar-year net P&amp;L (Chicago `exit_time`)

| Year | Net P&amp;L (3 lots) |
|------|----------------------|
| 2020 | +$3,115.50 |
| 2021 | $0.00 |
| 2022 | +$1,914.00 |
| 2023 | $0.00 |
| 2024 | +$25,318.50 |
| 2025 | +$10,846.50 |
| 2026 | −$79.50 |

### Post-fix — closed trades by **exit** year (Chicago)

| Year | Trades |
|------|--------|
| 2020 | 165 |
| 2021 | 0 |
| 2022 | 31 |
| 2023 | 0 |
| 2024 | 65 |
| 2025 | 119 |
| 2026 | 11 |

Run metadata: **5** segments, **599,533** RTH bars; `commission_total` **0** in this run.

---

## Side-by-side: NT8 reference vs **post-fix** Python

| Metric | NT8 (lessons log) | Python **post-fix** | Notes |
|--------|-------------------|---------------------|--------|
| **Per-contract $ / year** | **~$10,885** | **~$2,175** | Same formula: `net_pnl_total / 3 / protocol_year_fraction`. |
| Closed trades | Not stated | **391** | ±5% band N/A. |
| Win rate | **63.8%** | **64.19%** | Δ **0.39** pp → within **±2** pp smoke band. |
| Profit factor | Not stated | **1.67** | — |
| Max drawdown | **−$17,880** | **−$9,451.50** (≈ **−$3,150.50**/contract) | Definitions differ; NT8 unit not pinned. |
| Positive exit years (2020–2026 window) | **7 / 7** | **4** / 7 with **P&amp;L ≠ 0**; **5** years with **≥1** exit | 2021/2023 still **zero** exits (see below). |

## Smoke bands (operator)

| Check | Result (post-fix) |
|--------|-------------------|
| Win rate ±2 pp vs NT8 | **Pass** |
| Trade count ±5% | **N/A** |
| Net P&amp;L ±10% vs headline $/yr/contract | **Not met** (~$2.2k vs ~$10.9k) |

The **dollar** gap vs the lessons-log NT8 **headline** is **not** closed by the session fix alone. M6 **does** close on its **process** mandate: large divergence triggered **forensics**, a **real** port bug was found and fixed, and the baseline was **re-run**.

---

## Residual divergences (brief; not exhaustive)

1. **Calendar exit years 2021 / 2023** still show **no** closed trades while **RTH bar counts exist** for those years. The session fix **reduced** cross-session management gaps but did not eliminate **all** multi-thousand-hour `entry_time`→`exit_time` spans. A **small** set of trades still ends at **segment** `flatten` after **very long** holds (`reason=flatten`), consistent with **working** bracket lifecycle differences vs a **broker-backed** host (e.g. need to **re-arm** stops/limits when the simulator queue is empty even though `position_qty ≠ 0`). Treat as **next** hypothesis—not re-litigated here.

2. **Per-contract economics** vs **~$10,885/yr** remain far apart: likely **stacked** causes (local export vs **full** NT8 6-year tape, roll/fill microstructure already documented in `orb.py`, residual bracket behavior above—not **one** knob).

3. **Max drawdown** magnitude vs NT8 still not aligned; measurement units differ.

---

## Milestone conclusion

- **M6 (reframed):** **Complete** for this phase — **smoke bands** surfaced a **genuine** defect; **fix + regression test + rebaseline** are delivered; **win rate** remains in-family.
- **NT8 headline dollars:** **not** matched; treat as **Phase 1 carryover research**, not an M6 block on **M7** if the operator accepts **process** closure.
- **Follow-up (engineering):** Consider **idempotent bracket refresh** each bar while open (or engine-level guarantee that working exits survive like NT8’s), then rerun this script.

Artifact: `scripts/run_m6_orb_baseline.py` JSON on operator MNQ export; doc revised **2026-04-28** (post-fix).
