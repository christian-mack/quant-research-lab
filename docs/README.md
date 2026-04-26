# Systematic Trading Development Program

**Owner:** Christian
**Status:** Phase 1 — Python Research Infrastructure

---

## What This Is

A multi-year program to build a portfolio of systematic trading strategies, progressing from retail-level systematic trading to quant-level edge sources. The program spans multiple strategy generations:

- **Flux V1** (deployed) — NT8-based intraday NQ/MNQ module system
- **Flux V2** (planned) — Data-informed systematic with Python research environment
- **Flux V3** (planned) — Regime-overlay meta-strategy with ML components
- **Onyx V1** (planned) — Multi-instrument systematic (first bonafide quant-level system)
- **Future generations** (placeholder) — Direction determined by what earlier generations teach

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

---

## Reading Order for New Context

If you're an AI agent, new collaborator, or future-self returning to this project after time away, read in this order:

1. **This README** (you're here)
2. **Program Charter** — understand the program structure and current phase
3. **Current Working Plan** — understand what's happening right now
4. **AI Project Instructions** — understand the conventions
5. **Lessons Log** — skim recent entries for relevant findings
6. **Phase Plan** — reference when working on specific milestones

---

## Current State Snapshot

**Active phase:** Phase 1 — Python Research Infrastructure

**What's being built:** Python-based research environment using polars, numpy, custom event-driven backtest engine. Replaces NT8 as research platform. NT8 remains the execution platform.

**What's running live:** Flux V1 on Apex EOD eval accounts. Quad-module architecture (Momentum, ORB, Range, AfternoonMR) with Config E (0/16/16/20) tri-module sizing in production.

**What's next after Phase 1:** Phase 2 — Flux V2 module research and deployment. Replacing AfternoonMR and Range with new modules validated on 6-year data with proper statistical rigor.

---

## Repository Structure

```
repo_root/
├── README.md                  # This file
├── docs/                      # All project documentation
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
