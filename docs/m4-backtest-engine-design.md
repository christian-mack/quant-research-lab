# M4 Backtest Engine — Design

**Status:** *Approved for implementation* — **2026-04-28** (Christian). M4 is **correct research backtest engineering** (auditable assumptions, deterministic execution, sane Flux-inspired constraints). **Not** a forensic NT8 replicator. **PT3 / methodology** remain a **reference** for defaults and sanity checks, not a byte-match specification.

**M6:** **Smoke validation** vs NT8 for the ORB+Opt3 baseline: **aggregate net P&L within ±10%**, **closed-trade count within ±5%**. Per-trade diff is diagnostic only unless it breaks those bands. (Operator framing **2026-04-28** — see `lessons-log.md`.)

**Related:** `docs/nt8-backtest-methodology.md` (PT3 reference), `docs/phase-1-detailed-plan.md` (M4/M5/M6 program text — M6 acceptance criteria **should be reconciled** to this smoke-test framing in a future doc pass).

---

## 1. Goals

1. Event-driven backtest over the existing **minute-bar** pipeline (polars), with optional **session** and **cme_session_date** from `quant_research.data.session`.
2. **Reproducible** execution: every assumption is a named configuration field traceable to **PT3 where helpful** or labeled `PYTHON_ASSUMPTION` — so future you (and M7+) know what was assumed, without implying NT8 parity.
3. Support Flux V1 constraints: **OneModuleAtATime**, **module priority**, single flat position per instrument (MNQ-scale quantity per program plan).
4. Output a **canonical trade log** (polars DataFrame) suitable for **M6 smoke metrics** (P&L and trade count bands) and Phase 2 research.

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

**Rule:** **Starting defaults** should align with **`docs/nt8-backtest-methodology.md`** where it saves ambiguity (session, $0 commission baseline, tick sizing). Deliberate or unknown deltas are **`PYTHON_ASSUMPTION`** with a short rationale. **M6 does not require** resetting defaults until NT8 matches — only the **smoke bands** in the header.

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
- **OneModuleAtATime:** if flat, any module may arm entries; if in position, only **exit logic** for the **owning** module runs until flat — implement to match **documented Flux behavior** (`docs/nt8-backtest-methodology.md` §8 + C# reference). **First delivery:** ORB+Opt3 as **one coherent strategy surface** (Opt3 as sub-logic); general multi-module host can **follow** once M5/M6 smoke is green.
- **Priority:** on simultaneous signals, higher-priority module wins; ties broken by deterministic tie-break (declared in code + doc).

**Implemented in** ``quant_research.backtest.omat`` (**``StrategyModule``**, **``collect_orders_for_bar``**): flat bar → all modules’ ``on_bar`` run; if more than one submits orders under OMAT, **only** the highest-priority module’s list is kept (**``OrchestrationSpec.module_ids``** — earlier id wins; must match the set of ``StrategyModule.module_id``). In position → **only** ``position_owner`` runs. Each **``OrderRequest.module_id``** must match its strategy module.

**End of series:** ``BacktestEngine`` **drops** unfilled pending/working orders (**``UserWarning``**). Any open position is **auto-flattened** at the **last bar’s close** (``PYTHON_ASSUMPTION``: not next open). Synthetic fill tag **``end_of_series_flatten``**; trade log **``exit_reason``** **``flatten``**. Optional env **``MFA_GIT_SHA``** populates **``mfa_git_sha``**.

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
- **Unit / golden tests:** synthetic bar streams with **hand-computed fills** — prove the **engine**, not NT8 parity.
- **M6:** instrument-level **smoke** only (see header): P&L and trade-count bands vs NT8 export; investigate only if **out of band** or blocking Phase 2 confidence.

---

## 8. Adopted defaults (implementation starting positions)

Locked **2026-04-28**; consistent with §§1–7 and the **speed-to-M7** goal.

| # | Topic | Default |
|---|--------|---------|
| 1 | **Decision clock** | **Closed bar** — strategies observe bar *t* only after it closes (**§3.2**). Stop/limit **fills** use `FillModelSpec` (intrabar path on bar *t+1* OHLC or later bar per policy), not “extra” intrabar signal clock. |
| 2 | **OMAT + first delivery** | **OMAT** per §5. **Implementation order:** ORB+Opt3 as **one strategy module** (Opt3 inside); generic **multi-module registry** after smoke pass unless trivial. |
| 3 | **Order types (v1)** | **Market, limit, stop** supported (**§4**); resolution rules live in `FillModelSpec` (first-touch OHLC ordering documented in code). |
| 4 | **Tick grid** | Fills snap to **`InstrumentSpec.tick_size`**; optional **non-strict** debug mode allowed but **off** for M6 runs. |
| 5 | **TIF** | **`PYTHON_ASSUMPTION`:** treat **`DAY`** as *valid for entire backtest window* (backtest-local stand-in for GTC). Upgrade to full GTC semantics later if research needs it. |
| 6 | **Market fill timing (baseline)** | **Next bar open** for unrestricted market orders unless `FillModelSpec` selects otherwise — matches `phase-1-detailed-plan` M4 wording and keeps bars coherent for minute data. |

---

## 9. Approval gate

- [x] Operator: design intent — **M4 = correct engine**; **M6 = smoke bands** (±10% P&L, ±5% trade count); **optimize for M7 / Phase 2**. **2026-04-28** (Christian).
- [x] **`docs/nt8-backtest-methodology.md`** accepted **2026-04-30** (Christian). **Path A:** M6 reference baseline = **ORB+Opt3**; multi-module / §8.6 = **directional**.
- [x] PT3 **Complete** for reference purposes; **§11.6** NT8 version etc. **non-blocking**.

**Approved for M4 implementation (design):** **2026-04-28**, Christian.

---

## 10. Known deferrals (Python vs NT8 ``ExecutionEngine`` / data feed)

Items **intentionally absent** until a Phase 2 hypothesis or M6+ work needs them. Production ORB+Opt3 does **not** rely on these today.

| Topic | NT8 location | Python status |
|--------|----------------|---------------|
| **ORB time flatten** | ``ExecutionEngine.ManagePosition``: ``ORBMaxHoldMinutes`` → ``FlattenForRisk`` | **Deferred** at **engine** level (not in ``OrbStrategy``). Production CSV has **0** (disabled). |
| **15m ATR series** | ``FluxV1Strategy.SetPriceData`` → ``ORBModule._atr15m`` | **Deferred.** ``OrbParams.atr15m_series`` stays **0**; production ``ORBMaxATR15m == 0`` and ATR filters off. When enabled, re‑examine Flux strategy code for **15m bar ATR vs 1m projection**. |
| **Entry hour gates** | ``ORBModule``: ``TimeSpan.Hours`` / hour compares | **Matched:** Python uses **ET hour only** (quirky but same as C#). |

---

## Revision history

| Date | Change |
|------|--------|
| 2026-04-28 | Initial design draft; PT3 traceability table; no code. |
| 2026-04-30 | PT3 / Path A in §9; §8 as operator questions; status updated. |
| 2026-04-28 | **Velocity reframe (post Path A):** M4 = correct engine, not NT8 forensic parity; M6 = smoke bands; §8 adopted defaults; §9 signed; `quant_research.backtest` scaffold. |
| 2026-05-04 | **OMAT + priority + trade log:** ``StrategyModule`` / ``omat.py``; ``TradeLedger`` round-trips; engine end-of-series flatten + warnings; ``OrderRequest.module_id`` / ``SimulatedFill.module_id``. |
| 2026-05-04 | **M5 post:** §10 **known deferrals** (``ORBMaxHoldMinutes``, ``atr15m`` feed, hour-gate parity); engine docstring points to §10. |
