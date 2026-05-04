# Current Working Plan: Next 30 Days

**Plan period:** Days 1-30 of Phase 1
**Phase:** 1 — Python Research Infrastructure
**Status:** Active
**Last updated:** April 30, 2026 — **Path A** (M6 = ORB+Opt3 only; §8.6 directional) recorded in `nt8-backtest-methodology.md` §12; **M4 design review** next (`m4-backtest-engine-design.md` §§1–8 / §9).
**Next review:** Weekly; full plan refresh at day 30
**Related documents:** `program-charter.md`, `phase-1-detailed-plan.md`, `ai-project-instructions.md`, `lessons-log.md`

---

## Purpose of This Document

This is the zoomed-in tactical plan for the next ~30 days of work. It covers a subset of Phase 1 milestones (approximately M1-M5 with M6 starting) plus all parallel tracks. When this 30-day window ends, this document is archived and replaced with the next 30-day working plan covering M6 completion through M9.

Update this document weekly. Add entries to the lessons log ad hoc. Refer to the charter and Phase 1 plan for context that doesn't belong here.

---

## 30-Day Scope

**Primary development goal:** Complete M1-M5 of Phase 1 (environment through module implementations) and begin M6 (NT8 validation). At 20 hours/week of focused development, this is 80 hours of capacity covering an estimated 57-85 hours of primary-path work with buffer for the start of M6.

**Parallel tracks:** PT1–PT4 active throughout. PT5 and PT6 fit in as time allows. **Phase 1b / Sierra Chart** porting is **not** in this 30-day window — it starts after the **Phase 1** milestone gate passes (see `program-charter.md` Phase 1b).

**Explicitly out of scope for this 30 days:**
- M6 completion (spans into next 30-day window)
- M7 statistical testing framework (next window)
- M8 multi-instrument infrastructure (next window)
- M9 regime scaffolding (next window)
- Any Flux V2 research (gated on Phase 1 completion)

---

## Week 1 — Environment + Data Pipeline Start

**Primary focus:** M1 complete, M2 begun

### Development tasks
- [x] M1: Cursor IDE in use on Windows (Python/Jupyter extensions); WSL2 deferred per lessons-log 2026-04-26
- [x] M1: Install uv; project repo already on GitHub (private)
- [x] M1: Initialize Python project with pyproject.toml; pin polars, numpy, scipy, matplotlib, plotly, pytest, jupyter, pandas-ta (for validation reference)
- [x] M1: Set up .gitignore for Python + Jupyter + data artifacts
- [x] M1: Smoke test — notebook runs, polars loads sample data, commit to git
- [x] M2: Begin data loader — read one MNQ .txt file, produce polars DataFrame with parsed timestamps (`src/quant_research/data/data_loader.py::load_contract_file`)
- [x] M2: Validate single-file load matches raw file contents (bar count, first/last timestamp) — see `tests/data/test_data_loader.py::test_real_mnq_03_26_*`

### Parallel tracks this week
- [ ] PT1: Monitor live Flux V1 accounts daily
- [ ] PT2: Track status of in-progress eval account; decide on next eval purchase timing
- [x] PT3: NT8 methodology **`docs/nt8-backtest-methodology.md`** — **Complete** 2026-04-30; operator **Path A** sign-off §12 (M6 ORB+Opt3 only).
- [ ] PT4: Acquire Lopez de Prado *Advances in Financial Machine Learning* (if not already owned)
### Week 1 success criteria
- Environment runs a Jupyter notebook with polars operations
- At least one MNQ contract file loaded and inspected in Python
- NT8 backtest methodology documentation started

### Estimated effort
12-18 hours (environment setup has known friction; budget accordingly)

---

## Week 2 — Data Pipeline + Indicators

**Primary focus:** M2 complete, M3 begun

### Development tasks
- [x] M2: Extend loader to all 26 MNQ contract files (`load_contracts`, `load_all_contracts`); dataset = 2,196,751 bars (no rows dropped after UTC discovery + load-time conversion to CT; see lessons-log 2026-04-27 entries on UTC discovery and DST correction)
- [x] M2: Continuous contract construction with documented roll methodology (`continuous_contract.build_continuous_contract`); volume-crossover with `data_boundary` fallback. Empirical: NT8 export gives ~5-day overlap with current contract dominant through day 4 → all 25 rolls fall through to data-boundary. See lessons-log 2026-04-26 (NT8 export shape).
- [x] M2: Timezone normalization — source confirmed UTC by inspection (Friday close, daily maintenance gap, DST shifts all consistent only with UTC); loader now does `replace_time_zone("UTC").convert_time_zone("America/Chicago")`. Last bar of dataset lands at 16:00 CT, matching CME's daily maintenance-break boundary.
- [x] M2: Session classification (`src/quant_research/data/session.py::classify_sessions`) — RTH / ETH / BREAK / WEEKEND / HOLIDAY, backed by `pandas_market_calendars` `CME_Equity` for holiday and early-close lookup. Half-open `[market_open, market_close)` convention; BREAK is Mon-Thu only.
- [x] M2: Known gap detection and flagging (`src/quant_research/data/quality.py`) — `KNOWN_GAPS` registry (4 entries: Good Friday 2024, Jun-Jul 2024, Good Friday 2025, Feb-Mar 2026; 61 missing trading days total). `find_unexpected_missing_days` returns `[]` on the current dataset.
- [x] M2: Validation — total bar count 2,196,751 raw / 2,140,532 continuous ✓ (phase plan ~2.1M); 1,630 PMC trading days in range (phase plan ~1,580 was an estimate, PMC is exact); coarse price-level cross-check on 2024-04-04 vs `/NQM4` daily wrap (~18,173) passes (our RTH range 18,201-18,505). Tick-perfect TradingView OHLC comparison deferred — TV's free product can't render RTH-session daily candles cleanly enough to compare; internal validations (bar count, PMC days, known-gap coverage, tz boundaries) are strong enough. Decision documented in `SESSION_NOTES`. **M2 closed.**
- [x] M3: Indicator library scaffolded with ATR (`src/quant_research/indicators/atr.py`); `true_range_expr`, `atr_expr`, `add_true_range`, `add_atr` with Wilder-default + SMA/EMA modes. Pandas-ta-equivalent seeding (TR pre-seeded with SMA at index `length-1`).
- [x] M3: Unit tests for ATR against pandas-ta reference (`tests/indicators/test_atr.py`); 26 tests covering hand-computed primitive, three smoothing modes vs pandas-ta within 1e-6 relative error, edge cases, error paths, and real-data smoke. Indicator-API conventions documented in `atr.py` module docstring as the template for remaining M3 indicators.

### Parallel tracks this week
- [ ] PT1: Continued live operation monitoring
- [ ] PT2: Log in-progress eval status; purchase next eval if appropriate per cadence
- [x] PT3: **M4 gate —** NT8 methodology **Complete** + **Path A** sign-off; **M4 design** review in progress (`m4-backtest-engine-design.md` §9).
- [ ] PT4: Begin Lopez de Prado reading — start with chapters on backtest overfitting (likely Ch. 11) and deflated Sharpe (likely Ch. 14)
### Week 2 success criteria
- Full 6-year MNQ dataset loaded into polars with validated bar count and session labels
- ATR indicator implemented and passing unit tests
- NT8 methodology documentation complete

### Estimated effort
18-22 hours

---

## Week 3 — Indicators + Backtest Engine Start

**Primary focus:** M3 complete, M4 begun

### Development tasks
- [x] M3: Williams %R (`indicators/williams_r.py`), EMA/SMA (`indicators/moving_average.py`), session-anchored VWAP (`indicators/vwap.py` + `session.assign_cme_session_date`), opening range (`indicators/opening_range.py`), basic volume profile (`indicators/volume_profile.py`). Session cumulative / grouped outputs document template deviations in-module (see `vwap.py`, `opening_range.py`, `volume_profile.py`).
- [x] M3: Unit tests for each (`tests/indicators/`); pandas-ta cross-checks where applicable (Williams %R ``talib=False``, SMA/EMA ``talib=False``); VWAP vs hand arithmetic + per-session numpy cumsum on real data.

### M3 closeout / M4 gate (before starting the backtest engine)
- [~] **PT3: NT8 backtest methodology** — **Complete** 2026-04-30; **Path A** (§12): M6 strict = **ORB+Opt3**; multi-module / §8.6 = **directional** only.
- [x] **M4: Backtest engine design** — **Approved 2026-04-28** — `docs/m4-backtest-engine-design.md` (smoke M6, §8 defaults); **scaffold** in `src/quant_research/backtest/`.
- [x] M4: Implement core event loop — bar-by-bar iteration with strategy callbacks (``StrategyModule`` list + OMAT routing).
- [x] M4: Implement order management — market next open; stop/limit first-touch; end-series flatten.
- [x] M4: Implement position tracking and P&L calculation — ``Account`` + ``TradeLedger`` round-trip rows.

### Parallel tracks this week
- [ ] PT1: Continued live operation
- [ ] PT2: Review eval progress; note any pattern emerging in pass rate data
- [ ] PT4: Continue Lopez de Prado reading
- [ ] PT5: Scope instrumentation work for live Flux V1 (per-module trade frequency logging) — estimate effort
### Week 3 success criteria
- All required indicators implemented and validated
- Backtest engine can run a trivial strategy end-to-end without crashing
- P&L accounting reconciles correctly

### Estimated effort
20-25 hours

---

## Week 4 — Backtest Engine Completion + Module Implementations Start

**Primary focus:** M4 complete, M5 begun (ORB and Momentum modules)

### Development tasks
- [x] M4: Complete execution engine — OneModuleAtATime constraint, module priority ordering
- [x] M4: Trade log output with standardized columns
- [x] M4: Configurable fill model, slippage, commissions (defaults to NT8-matching assumptions)
- [x] M4: End-to-end validation — MNQ RTH slice smoke + ORB+Opt3 (`modules/orb.py`)
- [x] M5: ORB strategy module (**Opt3** = params incl. `latest_entry_hour_et=11`) + unit tests (`src/quant_research/modules/orb.py`)
- [ ] M5: Implement MomentumModule.py with 15m ATR gate and unit tests

### Parallel tracks this week
- [ ] PT1: Continued live operation
- [ ] PT2: Eval sample tracking
- [ ] PT4: Continue reading
- [ ] PT6: Begin investigation of data gap backfill sources — cost and feasibility
### Week 4 success criteria
- Backtest engine complete and validated
- ORB and Momentum modules implemented with passing unit tests
- Data gap backfill path identified (even if not yet purchased)

### Estimated effort
20-25 hours

---

## End of 30-Day Review

At day 30, review the following:

### Development progress
- Which Phase 1 milestones are complete?
- Which are in progress and what's their state?
- Are any taking significantly longer than estimated? Why?

### Parallel track progress
- Flux V1 live pass rate data: what does the sample show?
- Any operational anomalies worth investigating?
- How much reading completed? What are the key takeaways?

### Lessons log
- Review entries added during the 30 days
- Are there patterns? Anything that changes the Phase 1 plan or charter?

### Next 30-day plan
- Scope next 30 days covering M5 completion, M6, M7, and likely M8-M9
- Update this document (archive current version, draft replacement)

---

## Risks in This 30-Day Window

| Risk | Watch for | Response |
|---|---|---|
| Environment setup takes >1 week | Cursor/uv/polars friction on Windows | Budget extra time in Week 2; don't push to Week 3 if Week 1 slipping badly |
| Data pipeline edge cases emerge | Unexpected bar count discrepancies, timezone issues | Log findings in lessons log; investigate before proceeding to indicators |
| Backtest engine design takes multiple iterations | Unsure about best architecture | Document design decisions as they're made; M4 is the foundation for everything after |
| Live Flux operational issues | Account requires attention beyond daily monitoring | Pause development; charter's operational load principles apply |
| Lopez de Prado reading pace slow | Dense material, limited time | Focus on the key chapters (11, 14, 7-8); other chapters can wait for M7 |

---

## Working Plan Discipline

This document is updated weekly at minimum. The review cadence:

- **Daily:** Mental check on current task; update in-progress checkboxes
- **Weekly:** Review week's completions, update next week's tasks based on what actually happened, add entries to lessons log if anything significant emerged
- **At day 30:** Full review, archive this document, draft next 30-day plan

Add entries to the lessons log when:
- A decision was made that wasn't in the plan
- Something was harder or easier than expected in a way that might affect future planning
- An assumption turned out to be wrong
- A finding changes the approach to a future phase

Do not add entries for routine completions or non-surprising progress.
