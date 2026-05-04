# M4 Backtest Engine — Design (pre-implementation)

**Status:** *Design for operator review (§§1–8).* **PT3 / methodology** accepted **2026-04-30** (operator **Path A** — M6 = ORB+Opt3 only; §8.6 directional). **No M4 implementation** until **§9** records **full design approval** after your section-by-section review.

**Related:** `docs/nt8-backtest-methodology.md` (PT3), `docs/phase-1-detailed-plan.md` (M4/M5/M6).

---

## 1. Goals

1. Event-driven backtest over the existing **minute-bar** pipeline (polars), with optional **session** and **cme_session_date** from `quant_research.data.session`.
2. **Reproducible** execution: every assumption is a named configuration field traceable to PT3 or labeled `PYTHON_ASSUMPTION`.
3. Support Flux V1 constraints: **OneModuleAtATime**, **module priority**, single flat position per instrument (scalp of MNQ-scale quantity as in plan).
4. Output a **canonical trade log** (polars DataFrame) suitable for M6 comparison to NT8 exports.

**Non-goals (initial implementation scope, subject to revision after review)**

- Multi-instrument portfolio (M8).
- Options, spreads, position netting across products.
- Sub-minute queue simulation or full L2 replay.
- Live / paper trading connectivity.

---

## 2. Traceability: PT3 → configuration knobs

Each subsection here maps to tables or checklist items in `docs/nt8-backtest-methodology.md`. Fields below are the **M4 public configuration surface** (names indicative; final names follow `quant_research` snake_case).

| PT3 area | M4 config grouping (proposed) |
|----------|-------------------------------|
| Date range, capital | `BacktestRunSpec`: `start`, `end`, `initial_cash`; optional `timezone` display (data remain tz-aware). |
| Instrument / tick | `InstrumentSpec`: `symbol`, `tick_size`, `tick_value`, `currency`; `min_lot`; validates prices snap to tick when optional strict mode on. |
| Session | `SessionSpec`: `calendar_name` (default `CME_Equity`), `classify_sessions` on/off, optional “trade only RTH.” |
| Commissions | `CommissionSpec`: `per_contract_per_fill`, `currency`, `round_turn_mode` (enum: one_way_credits_both_legs vs explicit entry+exit), optional flat per trade. |
| Slippage | `SlippageSpec`: `mode` (none / fixed_ticks / fixed_points / optional future ATR-scaled), `ticks` or `points`, `side` (symmetric / adverse_only). |
| Fill model | `FillModelSpec`: market at **open_of_next_bar** / **close_of_signal_bar** / other enum; stop/limit intrabar policy (first_touch_ohlc_order, pessimistic, optimistic); gap policy. |
| Partial fills | `PartialFillSpec`: `enabled` (bool), `min_fill_fraction` optional; if disabled, fills always full size. |
| TIF | `TimeInForceSpec`: default for market / limit / stop (DAY / GTC enum); M4 v1 may only implement DAY semantics. |
| Module orchestration | `OrchestrationSpec`: ordered module ids, `one_position_at_a_time`, optional per-module enable flags. |

**Rule:** Default values for a “**NT8 parity run**” must match **`docs/nt8-backtest-methodology.md`** (PT3 **Complete**). Any deliberate delta is a named `PYTHON_ASSUMPTION` with a pointer to methodology § or this doc.

---

## 3. Core architecture

### 3.1 Event loop

- Single-threaded **bar iterator** sorted by `timestamp`.
- Per bar: update **bar context** (OHLCV, optional precomputed indicators injected or lazily computed outside engine).
- Strategies receive: `on_bar(ctx)` or equivalent; engine owns **order queue** and **fill simulator** applying `FillModelSpec` when bars advance.

### 3.2 Time semantics

- **Decision clock:** strategy logic observes bar *t* after bar *t* is complete (closed bar), unless a reviewed design explicitly uses “intrabar signal” (discouraged for v1).
- **Fill clock:** fills occur at simulated times determined by `FillModelSpec` (e.g. next bar’s open timestamp) for logging and P&L.

### 3.3 Position and P&amp;L

- **Position state:** quantity (signed integer contracts), average entry price, unrealized on mark (optional), realized via closing trades.
- **Marking:** use **trade price** from fill model; no separate MTM unless needed for reporting.
- **Account:** `cash`, `equity = cash + open position MTM` if MTM enabled (optional flag).

---

## 4. Order and execution API (strategy-facing)

Minimal types (conceptual):

- `OrderRequest`: `side`, `quantity`, `order_type` (MARKET, LIMIT, STOP), `limit_price`, `stop_price`, `tif`, `tag` (module id + reason).
- `Fill`: `timestamp`, `price`, `quantity`, `commission`, `slippage_applied`, `order_id`.

Engine responsibilities:

- Accept orders from strategies; **collide** with risk rules (max size, flattened end of session if configured).
- Resolve working orders against next bar’s OHLC (or current per fill model) deterministically.
- Emit fills and update position.

---

## 5. Module host (Flux V1)

- **Registry:** ordered list of strategy modules implementing a small interface, e.g. `on_bar`, `on_fill`, optional `on_start`/`on_end`.
- **OneModuleAtATime:** if flat, any module may arm entries; if in position, only **exit logic** for the **owning** module runs until flat — behavior must trace to **C# aggregator** + `docs/nt8-backtest-methodology.md` §8; lock details during M4 review (**§8** open questions).
- **Priority:** on simultaneous signals, higher-priority module wins; ties broken by deterministic tie-break (declared in code + doc).

---

## 6. Trade log schema (canonical, M6-ready)

Proposed columns (extend after review):

| Column | Description |
|--------|-------------|
| `trade_id` | Stable id |
| `module_id` | ORB / Momentum / … |
| `entry_time`, `exit_time` | tz-aware |
| `direction` | long / short |
| `quantity` | contracts |
| `entry_price`, `exit_price` | after slippage |
| `gross_pnl`, `commission`, `net_pnl` | currency |
| `exit_reason` | stop, target, flatten, time, reverse |
| `bars_held` | optional |
| `mfa_git_sha` | repo revision |

---

## 7. Testing strategy (design-level)

- **Cash accounting:** sum of `net_pnl` + `initial_cash` equals final equity for deterministic runs.
- **Invariants:** no overlapping positions under OMAT; order log replayable from trade log.
- **Golden tests:** once PT3 filled, small **synthetic bar streams** with hand-computed fills v.s. engine.

---

## 8. Open questions for operator review

Cross-reference **`docs/nt8-backtest-methodology.md`** §§3–7 (Analyzer execution), **§8** (strategy params), **§13** (known ambiguities **not** blocking ORB+Opt3 M6).

1. **Closed-bar vs intrabar signals** — M4 §3.1 uses **closed bar** by default. Confirm this matches Flux **Calculate.OnBarClose** + your intended **first meaningful fill** semantics (vs any NT8 “intrabar” stop/target touch you rely on — **PT3 §4** Standard fill + **§6** stops).
2. **OMAT** — **§5** here defers to PT3 §8 / C# aggregator. Confirm Python mirrors **OneModuleAtATime / exit-only for owning module** exactly **before** any multi-module host work; for **ORB+Opt3-only** baseline, orchestration may be **single active module** until Opt3 is modeled as sub-logic inside the same host.
3. **Order types for M4 v1** — ORB+Opt3 likely needs **market + stop + limit** for entries/exits per C#. Is **market-only** acceptable for a **thin vertical slice**, or must v1 ship **stop/limit** resolution ( **first-touch on OHLC, pessimistic/optimistic** per **FillModelSpec** )?
4. **Tick grid** — Snap simulated fills to **0.25** MNQ tick (strict parity) always, vs optional **debug fractional** mode?
5. **TIF** — PT3 shows **GTC** for managed types; M4 §2 says v1 may implement **DAY** only. Accept **`PYTHON_ASSUMPTION`** for DAY-equivalent **within backtest window**, or implement **GTC** semantics in v1?
6. **Scope vs Path A** — First implementation milestone: **full engine shell + ORB+Opt3 strategy path only**, or **generic module host** from day one? (Both can satisfy M6; second is more code before first green run.)

---

## 9. Approval gate

- [ ] Operator: review **this document §§1–8** (section-by-section).
- [x] Operator: **`docs/nt8-backtest-methodology.md`** accepted **as-is** — **2026-04-30** (Christian). **Path A:** M6 strict scope = **ORB+Opt3**; **§8.6** / multi-module = **directional**, not reproducible.
- [x] PT3 **Complete**; remaining methodology follow-ups (**§11.6** NT8 version string, optional archived export) **explicitly non-blocking** for M4.

**Approved for M4 implementation (design):** *[date, initials — when §§1–8 review complete]*

---

## Revision history

| Date | Change |
|------|--------|
| 2026-04-28 | Initial design draft; PT3 traceability table; no code. |
| 2026-04-30 | PT3 / Path A recorded in §9; §8 expanded with PT3 cross-refs + scope; status line updated. |
