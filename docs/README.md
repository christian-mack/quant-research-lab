# Systematic Trading Development Program

**Owner:** Christian
**Status:** Phase 1 — Python Research Infrastructure

---

## What This Is

A multi-year program to build a portfolio of systematic trading strategies, progressing from retail-level systematic trading to quant-level edge sources. The program spans multiple strategy generations:

- **Flux V1** (deployed) — NT8 intraday NQ/MNQ; **live: ORB+Opt3** (see `lessons-log.md`; historical quad-module stack for repro only)
- **Flux V2** (planned) — Python research: **configuration investigations** vs ORB+Opt3 baseline (modules optional; see `flux-v2-module-search-starter.md`)
- **Flux V3** (leading candidate) — Regime-overlay / meta-gating **if** Phase 2 warrants
- **Onyx-class V1** (leading candidate) — Multi-instrument systematic **if** economics justify after Flux phases; not “next” by default
- **Future generations** (placeholder) — Leading candidates only after major-phase evidence

Long-term income target: $500K-$1M/year net across multiple funded prop firm accounts.

---

## How to Navigate This Project

Documents in the `docs/` directory are organized by purpose:

### Strategic Documents (stable, rarely change)

- **`program-charter.md`** — The umbrella document. Phase definitions, income gates, skills ladder, stop conditions, operational framework. Read this first for context on the whole program.

### Tactical Documents (active, updated often)

- **`phase-1-detailed-plan.md`** — The full scope of Phase 1 (Python research infrastructure). Milestone breakdown with effort estimates.
- **`current-working-plan.md`** — The zoomed-in next-30-days plan. What's actively being worked on this week. Updated weekly.

### Reference Documents

- **`lessons-log.md`** — Append-only record of findings, surprises, invalidated assumptions, and post-mortems. Read this before starting major work to benefit from prior learnings.
- **`ai-project-instructions.md`** — Rules and conventions for AI coding agents and human collaborators working in this project. Code style, correctness requirements, research methodology, lessons log rules.
- **`nt8-backtest-methodology.md`** — NinjaTrader 8 backtest settings baseline for Flux V1 (commissions, slippage, fills, sessions). **Operator-maintained** checklist; required input for M4 defaults and M6 NT8 comparison. Supporting screenshots: **`nt8-screenshots/README.md`**.
- **`m4-backtest-engine-design.md`** — Pre-implementation design for the Python backtest engine: configuration knobs (mapped from PT3), event loop, and trade log schema. **Operator approval required** before M4 coding starts.

---

## Reading Order for New Context

If you're an AI agent, new collaborator, or future-self returning to this project after time away, read in this order:

1. **This README** (you're here)
2. **Program Charter** — understand the program structure and current phase
3. **Current Working Plan** — understand what's happening right now
4. **AI Project Instructions** — understand the conventions
5. **Lessons Log** — skim recent entries for relevant findings
6. **Phase Plan** — reference when working on specific milestones
7. **NT8 methodology** (`nt8-backtest-methodology.md`) and **M4 engine design** (`m4-backtest-engine-design.md`) — when working on backtest / execution assumptions

---

## Current State Snapshot

**Active phase:** Phase 1 — Python Research Infrastructure

**What's being built:** Python-based research environment using polars, numpy, custom event-driven backtest engine. Replaces NT8 as research platform. NT8 remains the execution platform.

**What's running live:** Flux V1 on Apex — **ORB+Opt3** (LatestEntryHourET=11). **Eval:** qty 10 on $50K EOD. **Funded:** qty 3 on $50K PA (see `lessons-log.md` for economics and validation).

**What's next after Phase 1:** Phase 2 — **investigate configurations that improve income vs ORB+Opt3** (6-year protocol, statistical rigor, **backtest-to-live** alignment). New modules are optional; sizing, filters, and other approaches are in scope.

---

## Repository Structure

```
repo_root/
├── README.md                  # Repo entry; links to docs/
├── flux-v2-module-search-starter.md  # Phase 2 scope primer (TODO: consider moving under docs/)
├── docs/
│   ├── README.md              # Program overview (this file)
│   └── …
├── src/                       # Production Python modules
├── tests/                     # Unit tests (pytest)
├── notebooks/                 # Jupyter notebooks for research
├── data/                      # Market data (gitignored)
├── results/                   # Backtest outputs (gitignored)
├── pyproject.toml             # Python project configuration
└── uv.lock                    # Locked dependencies
```

See `ai-project-instructions.md` for full conventions on file organization, naming, and code style.

---

## Key Principles

These principles guide all work in this project:

1. **Edge creation over edge multiplication** — New strategies create edge; sizing and overlays multiply it. Create first.
2. **Structural reasoning over curve-fitting** — Every decision must be justifiable on market microstructure grounds, not just backtested P&L.
3. **Statistical rigor is mandatory** — IS/OOS splits, walk-forward validation, deflated Sharpe ratio after multiple-comparisons correction.
4. **Ship incrementally** — Each phase produces a deployable system.
5. **Infrastructure investments compound** — Build research infrastructure properly once; it serves every subsequent strategy.
6. **Document as a habit** — Weekly working plan updates, ad hoc lessons log entries. Documentation decay is silent and costly.
7. **Prop firm compliance is non-negotiable** — All strategies must respect Apex constraints.
8. **Backtest-to-live alignment** — Configurations are validated by research backtests **and** demonstrated live/SIM correspondence, not paper metrics alone.

---

## Quick Links by Task

Starting a new development session? Read `current-working-plan.md`.

Designing a new module or strategy? Read the relevant phase plan and `ai-project-instructions.md` sections on statistical rigor.

Found something surprising in research? Add it to `lessons-log.md`.

Questioning whether to continue a phase? Check stop conditions in the phase plan and program-level stops in the charter.

Wondering why a decision was made? Check the charter's revision log and the lessons log.

---

## Program Revision Log

| Date | Event |
|---|---|
| 2026-04-20 | Program formalized. Charter, Phase 1 plan, first working plan, AI instructions, and lessons log template created. |
