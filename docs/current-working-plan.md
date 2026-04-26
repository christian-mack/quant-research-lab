# Current Working Plan: Next 30 Days

**Plan period:** Days 1-30 of Phase 1
**Phase:** 1 — Python Research Infrastructure
**Status:** Active
**Last updated:** April 26, 2026
**Next review:** Weekly; full plan refresh at day 30
**Related documents:** `program-charter.md`, `phase-1-detailed-plan.md`, `ai-project-instructions.md`, `lessons-log.md`

---

## Purpose of This Document

This is the zoomed-in tactical plan for the next ~30 days of work. It covers a subset of Phase 1 milestones (approximately M1-M5 with M6 starting) plus all parallel tracks. When this 30-day window ends, this document is archived and replaced with the next 30-day working plan covering M6 completion through M9.

Update this document weekly. Add entries to the lessons log ad hoc. Refer to the charter and Phase 1 plan for context that doesn't belong here.

---

## 30-Day Scope

**Primary development goal:** Complete M1-M5 of Phase 1 (environment through module implementations) and begin M6 (NT8 validation). At 20 hours/week of focused development, this is 80 hours of capacity covering an estimated 57-85 hours of primary-path work with buffer for the start of M6.

**Parallel tracks:** PT1-PT4 active throughout. PT5 and PT6 fit in as time allows.

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
- [ ] M1: Install uv; project repo already on GitHub (private)
- [ ] M1: Initialize Python project with pyproject.toml; pin polars, numpy, scipy, matplotlib, plotly, pytest, jupyter, pandas-ta (for validation reference)
- [ ] M1: Set up .gitignore for Python + Jupyter + data artifacts
- [ ] M1: Smoke test — notebook runs, polars loads sample data, commit to git
- [x] M2: Begin data loader — read one MNQ .txt file, produce polars DataFrame with parsed timestamps (`src/quant_research/data/data_loader.py::load_contract_file`)
- [x] M2: Validate single-file load matches raw file contents (bar count, first/last timestamp) — see `tests/data/test_data_loader.py::test_real_mnq_03_26_*`

### Parallel tracks this week
- [ ] PT1: Monitor live Flux V1 accounts daily
- [ ] PT2: Track status of in-progress eval account; decide on next eval purchase timing
- [ ] PT3: Begin documenting current NT8 backtest methodology — which date ranges used, what configurations, what commission/fill settings
- [ ] PT4: Acquire Lopez de Prado *Advances in Financial Machine Learning* (if not already owned)
- [ ] PT7 (Phase 1b): Contact Apex support to confirm whether Tradovate API access is permitted for their funded accounts. One email or support ticket. Document the answer regardless of outcome.

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
- [x] M2: Extend loader to all 26 MNQ contract files (`load_contracts`, `load_all_contracts`); dataset = 2,196,750 bars (1 DST-gap drop on 2025-03-09; see lessons-log 2026-04-26)
- [ ] M2: Implement continuous contract construction with documented roll methodology
- [~] M2: Timezone normalization; verify session boundaries correct — DST gap/overlap handled in loader (`non_existent="null"`, `ambiguous="earliest"`); session-boundary validation pending
- [ ] M2: Session classification (RTH / ETH / Break / Holiday)
- [ ] M2: Known gap detection and flagging (Jun-Jul 2024, Feb-Mar 2026)
- [~] M2: Validation — total bar count ~2.1M ✓ (2.20M actual); trading days ~1,580 pending; OHLC spot-check vs TradingView for 5 random dates pending
- [ ] M3: Begin indicator library — ATR (1m, 15m, daily) first
- [ ] M3: Unit tests for ATR against pandas-ta reference

### Parallel tracks this week
- [ ] PT1: Continued live operation monitoring
- [ ] PT2: Log in-progress eval status; purchase next eval if appropriate per cadence
- [ ] PT3: Complete NT8 backtest methodology documentation
- [ ] PT4: Begin Lopez de Prado reading — start with chapters on backtest overfitting (likely Ch. 11) and deflated Sharpe (likely Ch. 14)
- [ ] PT7 (Phase 1b): Based on Apex response, commit to platform direction. If API route is available, begin API research. If not, start Sierra Chart trial (~$26/month rental). Install locally (not on VPS) for initial evaluation.

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
- [ ] M3: Implement remaining indicators — Williams %R, VWAP (session-anchored), EMA/SMA, opening range construction
- [ ] M3: Unit tests for each against reference implementations
- [ ] M3: Basic volume profile / volume-at-price for future use
- [ ] M4: Design backtest engine architecture — document design decisions before implementing
- [ ] M4: Implement core event loop — bar-by-bar iteration with strategy callbacks
- [ ] M4: Implement order management — market orders first, then limit and stop
- [ ] M4: Implement position tracking and P&L calculation

### Parallel tracks this week
- [ ] PT1: Continued live operation
- [ ] PT2: Review eval progress; note any pattern emerging in pass rate data
- [ ] PT4: Continue Lopez de Prado reading
- [ ] PT5: Scope instrumentation work for live Flux V1 (per-module trade frequency logging) — estimate effort
- [ ] PT7 (Phase 1b): Platform proof-of-concept. Port one Flux V1 module (start with simplest — likely Momentum or ORB) to the chosen platform. Assess development experience, toolchain quality, and stability during the port. This is a go/no-go decision point — if the platform feels wrong here, pivot before committing more time.

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
- [ ] M4: Complete execution engine — OneModuleAtATime constraint, module priority ordering
- [ ] M4: Trade log output with standardized columns
- [ ] M4: Configurable fill model, slippage, commissions (defaults to NT8-matching assumptions)
- [ ] M4: End-to-end validation — simple strategy produces clean trade log
- [ ] M5: Implement ORBModule.py with unit tests
- [ ] M5: Implement MomentumModule.py with 15m ATR gate and unit tests

### Parallel tracks this week
- [ ] PT1: Continued live operation
- [ ] PT2: Eval sample tracking
- [ ] PT4: Continue reading
- [ ] PT6: Begin investigation of data gap backfill sources — cost and feasibility
- [ ] PT7 (Phase 1b): Continue module porting. Target: two modules ported by end of Week 4. Begin planning side-by-side SIM validation setup (how to run both platforms concurrently, where, with what logging).

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
