# Phase 1 Detailed Plan: Python Research Infrastructure

**Phase:** 1 of program
**Scope:** Comprehensive Python research environment
**Status:** Not started
**Owner:** Christian
**Related documents:** `program-charter.md`, `current-working-plan.md`, `ai-project-instructions.md`

---

## Purpose of This Document

This document defines the full scope of Phase 1 — the comprehensive Python research infrastructure build. It is organized by milestones, not calendar dates. The 30-day working plan covers a subset of these milestones; when one 30-day plan completes, the next begins, covering the next set of milestones from this document.

Estimated total effort: 6-8 weeks at ~20 hours/week, with meaningful variance depending on how smoothly validation goes and whether Layer 4 NT8 comparison surfaces issues requiring investigation.

---

## Phase Objective

Build a comprehensive Python-based research environment that replaces NT8 as the primary research platform for all systematic trading strategy development. The environment must:

- Reproduce Flux V1 backtest results with documented divergence analysis
- Provide statistical testing appropriate for rigorous strategy research (deflated Sharpe, bootstrap CIs, walk-forward validation)
- Support multi-instrument research from day one (even if initially only MNQ is used)
- Scaffold regime detection capabilities for Flux V3 and beyond
- Operate locally on Windows development machine with WSL2 (Tier 0 deployment)

NT8 remains the execution platform. This phase does not change what runs in production — it changes where and how research happens.

---

## Exit Criteria (Milestone Gate — from Charter)

1. **Data integrity verified** against raw MNQ files (bar counts, session alignment, gap handling)
2. **Indicator correctness verified** against reference libraries within floating-point tolerance
3. **Unit tests pass** for each Flux V1 module's execution logic on hand-constructed scenarios
4. **Python vs. NT8 full backtests compared** for all four V1 modules; every divergence >5% investigated and documented
5. **Statistical testing framework operational:** deflated Sharpe, bootstrap CIs, walk-forward validation
6. **Multi-instrument data infrastructure in place**
7. **Regime detection framework scaffolded**

---

## Technology Stack

Confirmed decisions from program design:

| Layer | Choice | Rationale |
|---|---|---|
| Language | Python 3.11+ | Standard for quant research; ecosystem maturity |
| Data manipulation | polars | 5-10x faster than pandas at dataset size; cleaner API; better type safety |
| Numerical | numpy | Standard; required by almost every other library |
| Backtest engine | Custom event-driven loop | Flux's module priority and OneModuleAtATime constraints fight frameworks |
| Testing | pytest | Standard for Python testing |
| Visualization | matplotlib + plotly | matplotlib for static research plots; plotly for interactive exploration |
| Statistics | scipy.stats + arch + statsmodels | Core stats, financial econometrics, regression |
| Package management | uv | Fast, modern replacement for pip + venv |
| Version control | git + GitHub | Standard |
| IDE | Cursor (VS Code fork with agentic AI) on Windows | Standardized across the program; inherits VS Code extension ecosystem (Python, Jupyter) |
| Runtime host | Windows-native Python 3.13 (no WSL2) | Polars/uv/numpy/scipy ship native Windows wheels in 2026; original "WSL avoids Python pain" rationale no longer holds for this stack. See lessons-log 2026-04-26. |
| Research workflow | Jupyter notebooks for exploration; Python modules for production code | Notebooks rot; modules don't |

---

## Milestone Breakdown

Phase 1 is organized into nine milestones (M1-M9). Milestones are sequential in dependency order but can overlap in execution when one milestone's blocking subtask completes.

### M1: Development Environment Setup

**Goal:** Functional Python development environment with all tooling in place.

**Deliverables:**
- Cursor IDE configured with Python and Jupyter extensions on Windows
- uv installed and working (Windows-native)
- Git installed; GitHub repo created for the research project (private)
- Python 3.11+ available; project-local virtual environment created via uv
- Initial `pyproject.toml` with pinned dependency versions
- `.gitignore` appropriate for Python + Jupyter + data files
- `README.md` scaffold in the repo root

> Note: WSL2 was originally planned but deferred for Phase 1 (see lessons-log 2026-04-26). All Phase 1 development runs in Windows-native Python.

**Validation:** Able to create a test Jupyter notebook, run a polars operation on sample data, and commit the notebook to git. End-to-end smoke test.

**Estimated effort:** 4-8 hours

**Dependencies:** None. First milestone.

---

### M2: Data Pipeline — Loading and Session Alignment

**Goal:** Robust data loading from raw MNQ .txt files into a canonical in-memory representation.

**Deliverables:**
- Data loader module: reads all 24 MNQ contract files (`MNQ_03-20_Last.txt` through `MNQ_03-26_Last.txt` etc.)
- Continuous contract construction: handles quarterly roll logic (document the methodology chosen — likely volume-based rollover to match NT8's approach)
- Timezone handling: source data timestamps normalized to a single canonical timezone (likely America/Chicago to match CME native timing)
- Session classification: each bar labeled as RTH / ETH / Maintenance Break / Holiday
- Gap handling: known gaps (Jun-Jul 2024, Feb-Mar 2026) detected and flagged, not silently bridged
- Output: polars LazyFrame with columns for timestamp, OHLCV, session_type, contract_symbol, days_to_expiry

**Validation:**
- Total bar count matches expectation (~2.1M bars)
- Trading day count matches expectation (~1,580 days)
- Daily OHLC spot-checked against a known reference source (e.g., TradingView) for 5 random dates
- Session labels correct for a sampled week (no RTH bars outside 9:30-16:00 ET, for example)
- Gaps appear where expected; no unexpected gaps

**Estimated effort:** 8-12 hours

**Dependencies:** M1

---

### M3: Indicator Library

**Goal:** Library of technical indicators needed by Flux V1 modules, validated against reference implementations.

**Deliverables:**
- ATR (multiple timeframes: 1m, 15m, daily)
- Williams %R
- VWAP (session-anchored and rolling variants as needed)
- EMA and SMA
- Opening range construction (per-day)
- Volume profile / Volume-at-price (basic version for future use)
- All indicators implemented as polars expressions where possible (vectorized, performant)
- Each indicator has unit tests

**Validation:**
- Each indicator's output compared against pandas-ta or talib reference on a 1000-bar sample; match within floating-point tolerance (1e-6 relative error acceptable)
- Unit tests cover edge cases: first N bars, session boundaries, missing data

**Estimated effort:** 10-15 hours

**Dependencies:** M2

---

### M4: Core Backtest Engine

**Goal:** Event-driven backtest loop that can execute strategy logic against the historical data pipeline.

**Deliverables:**
- Bar-by-bar event loop with strategy callbacks
- Order management: market, limit, stop orders
- Position tracking with P&L calculation
- Execution assumptions documented explicitly: fill model (next-bar open assumed for market orders, unless otherwise configured), slippage assumptions (configurable, start with zero for baseline comparison to NT8), commissions (configurable, start with zero for baseline)
- Trade log output: per-trade entry time, exit time, direction, quantity, entry price, exit price, P&L, reason for exit
- Supports OneModuleAtATime constraint (only one strategy position open at a time)
- Supports module priority ordering
- Outputs standardized trade log format (polars DataFrame with canonical columns)

**Validation:**
- Engine runs a trivial "buy every Monday, sell every Friday" strategy without crashing
- P&L accounting reconciles: sum of per-trade P&L equals final equity change
- OneModuleAtATime constraint verifiable via inspection of trade log (no overlapping positions)

**Estimated effort:** 15-20 hours

**Dependencies:** M2, M3

---

### M5: Flux V1 Module Implementations

**Goal:** Each Flux V1 module (ORB, Momentum, Range, AfternoonMR) implemented as Python strategy logic against the backtest engine.

**Deliverables:**
- ORBModule.py: Python implementation of Opening Range Breakout logic
- MomentumModule.py: Python implementation of Williams %R momentum logic with 15m ATR gate (per the recent enhancement)
- RangeModule.py: Python implementation of compression breakout logic
- AfternoonMRModule.py: Python implementation of VWAP fade logic
- Each module has unit tests against hand-constructed scenarios validating entry/exit logic
- Each module documented with the same parameters exposed in the NT8 version

**Validation:**
- Unit tests pass for each module: "Given this 10-bar sequence with these indicator values, does the module enter/exit at the correct bar with the correct P&L?"
- Module behavior matches documented Flux specification (not NT8 implementation — specification)

**Estimated effort:** 20-30 hours (5-7 hours per module including tests)

**Dependencies:** M4

---

### M6: NT8 Baseline Reproduction and Divergence Analysis

**Goal:** Run each module in Python against the 6-year dataset; compare against NT8 backtest results for the same period and configuration; explain every divergence >5%.

**Deliverables:**
- Python backtests run for all four modules at baseline configurations (matching the NT8 backtests referenced in the project docs)
- Side-by-side comparison report: trade count, win rate, total P&L, PF, max DD
- Divergence investigation log: for each metric divergence >5%, documented root cause (fill model difference, indicator calculation difference, data boundary difference, NT8 bug, etc.)
- Decision log: for each divergence, whether to align Python to NT8 or accept Python as correct (with rationale)

**Validation:**
- This is the Phase 1 "moment of truth." Expected outcome: most divergences are small and explicable; some may reveal that NT8 backtests had subtle issues; at least one should be a Python bug to fix.
- Acceptance: every divergence has a documented explanation. Not every divergence must be resolved — some are accepted as legitimate differences in modeling assumptions.

**Estimated effort:** 15-25 hours (highly variable depending on what's found)

**Dependencies:** M5

**Risk:** If Layer 4 validation reveals a major NT8 backtest issue (>20% unexplained P&L divergence), this milestone may extend significantly. Stop condition from charter applies.

---

### M7: Statistical Testing Framework

**Goal:** Library of statistical tests and validation methods required for rigorous strategy research.

**Deliverables:**
- Bootstrap confidence intervals for: P&L, Sharpe ratio, win rate, max drawdown
- Deflated Sharpe ratio implementation (per Lopez de Prado; handles multiple-comparisons inflation)
- Walk-forward validation framework: configurable window sizes, step sizes, anchored vs. rolling
- Purged and embargoed cross-validation for time series
- IS/OOS split utilities with configurable split points
- White's Reality Check or SPA test implementation for strategy selection bias
- Results reporting: standardized format for presenting backtest results with all statistical qualifications

**Validation:**
- Bootstrap CIs validated against known analytical result on synthetic data
- Deflated Sharpe validated against hand-calculated example from Lopez de Prado text
- Walk-forward framework tested on a synthetic strategy with known structure

**Estimated effort:** 15-20 hours

**Dependencies:** M6 (conceptually independent but best built once the framework has real strategy results to apply to)

**Preparatory reading:** Lopez de Prado *Advances in Financial Machine Learning*, chapters 7-8 (cross-validation, feature importance) and chapters 11-12 (backtest statistics, deflated Sharpe). This reading should ideally be completed before or during this milestone.

---

### M8: Multi-Instrument Data Infrastructure

**Goal:** Data pipeline extended to support multiple instruments, even if only MNQ is actively loaded at this stage.

**Deliverables:**
- Data loader generalized to support arbitrary futures symbols
- Canonical data schema supports instrument_id and contract metadata
- Directory structure and naming convention for multi-instrument data storage
- Configuration system for registering new instruments
- Example: load MNQ + at least one additional symbol (even a small sample) to prove the multi-instrument path works

**Validation:**
- Loading two instruments simultaneously produces correctly aligned timestamp-indexed data
- Backtest engine can operate on multi-instrument data (even if no multi-instrument strategies exist yet)

**Estimated effort:** 8-12 hours

**Dependencies:** M2

---

### M9: Regime Detection Framework Scaffolding

**Goal:** Framework for regime feature engineering and classification, ready for Flux V3 use. Does not need to include a production regime model — just the scaffolding so V3 can build on it without rework.

**Deliverables:**
- Regime feature module: library of functions producing features like realized volatility (multiple windows), trend strength (e.g., ADX), range-bound vs. trending classifier inputs, session-type one-hot encoding
- Regime state tracking: ability to label each bar with regime state based on features
- Simple baseline regime classifier: rule-based (e.g., high/medium/low volatility tercile on rolling RV). Not optimized, just functional.
- Integration point with backtest engine: strategies can query current regime state

**Validation:**
- Features compute without error on full 6-year dataset
- Regime state transitions look reasonable on spot-checked dates (e.g., March 2020 should be flagged high-vol)

**Estimated effort:** 10-15 hours

**Dependencies:** M3, M4

---

## Milestone Dependency Graph

```
M1 (Environment)
 └─> M2 (Data Pipeline) ─┬─> M3 (Indicators) ─┬─> M4 (Backtest Engine) ─> M5 (Modules) ─> M6 (NT8 Validation)
                         │                     │                                              │
                         │                     └─> M9 (Regime Framework) <───────────────────┘
                         │
                         └─> M8 (Multi-Instrument)

M7 (Statistical Framework) — independent, runnable after M6 or in parallel with M8/M9
```

Critical path: M1 → M2 → M3 → M4 → M5 → M6. This is the reproduction path. Everything else branches off.

---

## Effort Summary

| Milestone | Estimate (hours) | Cumulative |
|---|---|---|
| M1: Environment | 4-8 | 4-8 |
| M2: Data Pipeline | 8-12 | 12-20 |
| M3: Indicators | 10-15 | 22-35 |
| M4: Backtest Engine | 15-20 | 37-55 |
| M5: Module Implementations | 20-30 | 57-85 |
| M6: NT8 Validation | 15-25 | 72-110 |
| M7: Statistical Framework | 15-20 | 87-130 |
| M8: Multi-Instrument | 8-12 | 95-142 |
| M9: Regime Scaffolding | 10-15 | 105-157 |
| **Total** | **105-157 hours** | |

At 20 hours/week of focused development, this is 5-8 weeks of work, not counting interruptions from live operation, parallel tracks, or investigations extending M6.

---

## Parallel Tracks (run concurrently with Phase 1)

These items do not block Phase 1 milestones but should progress alongside them:

### PT1: Continued Flux V1 Live Operation
- Monitor live accounts daily
- Respond to eval completions (passes, fails, timeouts)
- Maintain watchdog scripts and VPS environment
- Log any operational anomalies to the lessons log

### PT2: Eval Pass-Rate Sample Building
- Goal: reach 8-10 completed eval attempts to establish live pass-rate confidence interval
- Current: 2 complete (1 pass with nudge, 1 timeout), 1 in progress
- Stagger new eval purchases per current weekly cadence
- Log each eval's outcome with full context (market regime notes, module activity, anomalies)

### PT3: NT8 Backtest Methodology Documentation
- Document exactly how current NT8 backtests are run: data range, configuration per module, fill assumptions, commission settings
- This becomes the reference for M6 validation
- Should be complete before M6 starts (ideally during M2-M4)

### PT4: Preparatory Reading
- Lopez de Prado *Advances in Financial Machine Learning* — chapters on backtest overfitting, deflated Sharpe, cross-validation
- Should be complete before or during M7
- Lessons log entries for key insights and how they affect the infrastructure

### PT5: Live System Instrumentation
- Add logging to live Flux V1 for per-module trade frequency per day
- Goal: data to inform Flux V2 regime analysis ("when does ORB get suppressed, and how often historically?")
- Low-priority but valuable; fit in around other work

### PT6: Data Gap Backfill (Optional, High-ROI)
- Investigate sources for Jun-Jul 2024 and Feb-Mar 2026 gap data
- Budget: $200-500
- Priority: Jun-Jul 2024 first (falls in likely OOS windows)
- Not a blocker for Phase 1 — gaps are documented and handled — but preferred completed before M6 runs

### PT7: Execution Platform Migration (Phase 1b) — **after Phase 1**
- **Timing:** Phase 1b **begins after** the Phase 1 milestone gate passes — **not** in parallel with M1–M9. Full scope: `program-charter.md` Phase 1b.
- **Rationale:** Validated **Python** module logic (M5, M6 parity) is the **primary specification** for the port; NT8 C# is **secondary**. Sierra Chart (ACSIL) remains the leading target.
- **Research path:** M1–M9 proceed **identically** regardless of live execution stack; only the **start** of porting work waits on Phase 1 completion.
- **Milestones within Phase 1b (high level):**
  - Sierra Chart (or selected alternative) trial / setup **after** Phase 1 gate
  - Proof-of-concept port from **Python spec** (production path e.g. ORB+Opt3 first)
  - Remaining module port scope per live/research needs
  - Side-by-side SIM validation vs. NT8 (30+ trading days)
  - Funded account migration plan (draft before migration begins)
- **Apex / Tradovate API** for funded execution — **not** pursued as a gate; treated as restricted / non-viable for this program’s live path (no redundant “confirm API” task).
- Estimated effort: 60–100 hours in a **post–Phase 1** block (not overlapping primary Phase 1 research capacity).

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| NT8 validation (M6) reveals major backtest errors | Medium | High | Budget extra time in M6; accept that this finding is valuable even if disruptive |
| WSL2 + polars + Jupyter environment has setup issues | Medium | Low | Known-good recipes exist; community support available |
| Polars learning curve is steeper than anticipated | Low | Medium | pandas fallback always available; can migrate later |
| Flux V1 live operation demands spike during Phase 1 | Medium | High | Charter's 50% operational load stop condition applies |
| Hypothesis creep: scope expands mid-phase | Medium | Medium | Working plan discipline: no scope additions without explicit charter-level decision |
| Preparatory reading (Lopez de Prado) takes longer than expected | High | Low | Reading is continuous; M7 can start with partial knowledge and complete as reading progresses |
| Selected execution platform has comparable stability issues to NT8 | Medium | High | Trial extensively before committing; Phase 1b stop condition covers this |
| Port of Flux V1 modules reveals specification gaps that were implicit in NT8 code | High | Medium | Expected — document findings in lessons log; treat as benefit (forces clean specification) rather than cost |
| VPS insufficient to run NT8 + new platform concurrently during validation | Medium | Low | Run new platform locally on dev machine during validation window |

---

## Phase 1 Completion Artifact

When Phase 1 completes, the following artifacts exist and are committed to the research repo:

- Working Python research environment, reproducible via `uv sync` on a new machine
- Full Flux V1 module implementations with unit tests
- NT8 validation report (side-by-side comparison + divergence explanations)
- Statistical testing framework with examples
- Multi-instrument data infrastructure with at least one additional instrument loaded
- Regime detection scaffolding with basic rule-based classifier
- Lessons log entries for all significant findings and decisions

Exit gate review: confirm each of the seven milestone gate criteria is met with supporting artifact evidence. If yes, Phase 1 closes and Phase 2 begins — **Flux V2 configuration research** vs. the **ORB+Opt3** frozen baseline (new modules optional; see charter and `flux-v2-module-search-starter.md`).
