# M6 — Python ORB+Opt3 vs NT8 reference (smoke + forensic escalation)

**Protocol window:** 2020-01-01 through **2026-04-19** (inclusive calendar end date), matching the six-year NT8 study cited in the lessons log. **Python:** funded ORB+Opt3 parameters, **qty = 3** (`production_orb_opt3_funded_params()`). **Bars:** NT8 MNQ export, RTH only, continuous contract, `cme_session_date` assigned in Chicago. **Runs:** `uv run python scripts/run_m6_orb_baseline.py` — segments with `split_dataframe_at_operator_export_gaps` (fresh `OrbStrategy` + `BacktestEngine` per segment) so positions do not span operator-known export holes.

**Reference (lessons log — 2026-04-28, production simplification / six-year NT8):** ORB+Opt3 on the NT8 baseline was summarized as **~$10,885/yr per contract**, **63.8%** win rate, **7/7** positive calendar years, **max drawdown −$17,880** (instrument/account unit as recorded in NT8; not re-derived here).

---

## M6 escalations on this run

| Pass | What changed | Why |
|------|--------------|-----|
| **(A) Cross-session fix** | `on_bar` always routes through `_manage_open` while `position_qty != 0`; on `cme_session_date` rollover with an open position, **only** entry accumulators reset (FSM forced to `TRIGGERED`); BE flag and bracket fields persist. | Smoke ran with massive dollar divergence and multi-thousand-hour holds — trade FSM was orphaning the open position. |
| **(B) Defensive bracket re-arm** | `_manage_open` now **emits stop and target every bar** while open with `dedupe_tag`. Engine `working` queue idempotently replaces same-tag orders. BE evaluation runs first; the emitted stop is at entry once `_break_even_done`, otherwise at `entry ± stop_distance`. | Static audit could not isolate where brackets dropped, but the empirical delta (next table) shows the OLD path lost protective orders for a small number of trades that then ran for **calendar quarters** until segment-end flatten. |
| **(C) Session hygiene (engine)** | `BacktestEngine` + `SessionSpec.intraday_hygiene`: **16:59 ET** bar **close** `session_maintenance_flatten_et` when open; **[17:00, 18:00) ET** entry deadzone (`ctx.suppress_entry`, queued orders cleared at boundary). | NT8 **break at end of session** / Globex maintenance: Python had been able to **hold or queue fills across** the gap when post-RTH bars exist. Hoisted to the engine for all Phase 2 modules. |

---

## C# vs Python — bracket and management semantics

NT8 `SetStopLoss` / `SetProfitTarget` create **broker-attached** orders that persist on the instrument until filled, replaced, or cancelled. `FluxV1Strategy.CheckSessionReset` calls `ExecutionEngine.ResetDaily()` which sets `_positionState = null` (so `ManagePosition` returns early — **no** BE / trail update across sessions) **but the broker still has the protective orders** and they fire when price touches them.

Python has no broker layer. The engine `working` queue is the source of truth. Pass (B) makes `OrbStrategy` adhere to the **broker-bracket contract** by re-emitting every bar — same prices, idempotent through `dedupe_tag`. Pass (A) ensures `_manage_open` is actually *called* every bar while open. Together they reproduce the **persist-until-filled** behavior of `SetStopLoss` / `SetProfitTarget`.

---

## Python — four runs on the same data

| Metric | **Pre-fix** (M5 baseline) | **After (A) cross-session** | **After (B) re-arm** | **After (C) session hygiene** |
|--------|---------------------------|-----------------------------|----------------------|--------------------------------|
| Closed trades | 398 | 391 | **799** | **799** |
| Net P&amp;L total (3 lots) | +$41,878.50 | +$41,115.00 | **+$19,167.00** | **+$19,167.00** |
| Per-contract $ / yr | ~$2,216 | ~$2,175 | **~$1,014** | **~$1,014** |
| Win rate | 64.57% | 64.19% | **62.95%** | **62.95%** |
| Profit factor | 1.68 | 1.67 | **1.18** | **1.18** |
| Avg win / avg loss | +$403.20 / −$460.78 | +$408.75 / −$462.27 | **+$252.88 / −$392.84** | **+$252.88 / −$392.84** |
| Max drawdown (combined) | −$9,451.50 | −$9,451.50 | **−$8,025.00** | **−$8,025.00** |
| Multi-thousand-hour trades | several | 7 (incl. 14k h, 13k h) | reduced; long-hold flatten artifact gone | unchanged vs (B) |

**Why (C) matches (B) on this row:** The M6 protocol filters to **`SESSION_RTH`**, which in `session.classify_sessions` is **Mon–Fri `08:30 ≤ time < 15:00` Chicago** — i.e. the last RTH bar is **before 16:59 ET** maintenance. Hygiene is **load-bearing** for ETH / full-session bars and is **regression-tested** (`tests/backtest/test_session_hygiene.py`); it does **not** intersect the current RTH-only bar set.

The **−$22k** drop in net P&amp;L from (A) to (B) traces to a single +$32,443 segment-flatten on the **2022-08-26 → 2024-03-28** trade — pre-(B), this position rode unmanaged for **~580 days** and crystallized at the segment boundary. That windfall was simulator artifact, not strategy edge: with proper bracket persistence, the trade exits on a normal stop or target far earlier.

### Post-(B) — calendar-year net P&amp;L (Chicago `exit_time`)

| Year | Net P&amp;L (3 lots) |
|------|----------------------|
| 2020 | +$3,115.50 |
| 2021 | $0.00 |
| 2022 | +$6,114.00 |
| 2023 | −$4,159.50 |
| 2024 | +$4,125.00 |
| 2025 | +$11,736.00 |
| 2026 | −$1,764.00 |

### Post-(B) — closed trades by **exit** year (Chicago)

| Year | Pre-(B) | Post-(B) |
|------|---------|----------|
| 2020 | 165 | 165 |
| 2021 | 0 | 0 |
| 2022 | 31 | 86 |
| 2023 | 0 | **223** |
| 2024 | 65 | 166 |
| 2025 | 119 | 138 |
| 2026 | 11 | 21 |

Run metadata: **5** segments, **599,533** RTH bars; `commission_total` **0** (commission model unchanged).

---

## Smoke bands (operator) — current

| Check | Target | Result |
|--------|--------|--------|
| Win rate | NT8 ± **2** pp | **Pass** (63.8% vs 62.95%; Δ 0.85 pp). |
| Trade count | NT8 ± **5%** | **N/A** (no NT8 trade count). |
| Net P&amp;L | NT8 ± **10%** on per-contract $/yr | **Not met** (~$1.0k vs ~$10.9k). Gap **widened** vs (A) — but (B) is honest accounting; (A) banked a flatten artifact. |

## Why the dollar gap is *bigger* after a real fix

Pass (B) is the **correct** bracket contract. The pre-(B) dollar total included an unmanaged **multi-quarter** drift on a single trade. Removing that artifact uncovers the **structural** divergence vs the NT8 lessons-log headline:

- 2021 still shows **zero exit-year trades**: the **2020-11 → 2022-08** trade armed BE, then sat at entry while MNQ ran from **$11k → $16k → back to $11k** before BE filled. With BE enabled (production setting), that is the strategy's actual behavior. Production NT8 reportedly does not produce those holds at the same scale; possible bases for the divergence (not investigated):
  - **Different bar resolution** at NT8 (tick-level vs minute), so brackets fire on intrabar noise we don't see.
  - **Different protocol window or roll calendar** behind the lessons-log $10,885 number.
  - **Different ORB params** in the reference vs the funded CSV row (e.g., a non-zero `ORBMaxHoldMinutes` or ATR filters).
  - **Live management** (operator-side flatten) that's not modeled in any backtest.

## Milestone status — **M6 stays open**

- **Engine reasonableness:** Cross-session management (A), broker-style bracket re-arm (B), and **session hygiene** (C) are now encoded; (C) is NT8 **break-at-end-of-session** parity for bar sets that reach **16:59 ET**.
- **Win-rate band:** Pass.
- **Dollar headline:** **Far** outside ±10%. Per the operator directive ("don't close M6 with the dollar gap unresolved"), **M6 is not closed** by this rerun.

### Next concrete investigations (not done here)
1. **Reconcile the lessons-log NT8 reference** — pin down its data, time-period, and parameter basis. The $10,885/yr/contract figure may not be a like-for-like backtest.
2. **Try `max_hold_minutes`** (Opt 5 in C#) on a sweep — does production-equivalent NT8 also run with it disabled?
3. **Disable BE** on a pass: BE-armed-and-camp-at-entry is a known quirk for trending instruments; a no-BE run would isolate that effect.

Artifact: `scripts/run_m6_orb_baseline.py` JSON on operator MNQ export; doc revised **2026-05-04** (post-(C) four-run table; (C) ≠ (B) only on feeds that include **≥ 16:59 ET** bars).
