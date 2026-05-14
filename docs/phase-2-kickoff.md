# Phase 2 Kickoff — Flux V2 / Income-Gap Research

**Status:** Entry artifact for Phase 2 (fresh-chat startup)
**Date:** May 2026
**Owner:** Christian
**Related:** `docs/program-charter.md`, `docs/lessons-log.md`, `docs/current-working-plan.md`, `flux-v2-module-search-starter.md` (repo root), `docs/ai-project-instructions.md`

---

## Program state summary

**Phase 1 is complete** per the amended milestone gate (M1–M7 core path; M8/M9 minimal scope documented in `docs/phase-1-detailed-plan.md` and lessons log **2026-05-14**).

**Infrastructure in place:**

- Six-year MNQ stack: loader, continuous contract, session classification, gap/quality checks, indicators, custom event-driven backtest engine aligned with Flux V1 module constraints.
- Production research path validated: **ORB+Opt3** in Python vs NT8 on the agreed protocol (`docs/m6-nt8-reproduction.md`).
- Statistical layer operational: deflated Sharpe / multiple-trial correction, bootstrap confidence intervals, walk-forward scaffolding, purged K-fold with embargo, standardized trade-log reporting (`src/quant_research/statistics/` and tests).

**Phase 1 learnings that shape Phase 2:**

- Backtest parity is necessary but not sufficient: a strategy can show real edge in-sample and in static backtests yet **under-trade** relative to prop-firm drawdown window dynamics.
- Integrated multi-module stacks can **net-destroy** baseline edge after displacement (lessons log); any new signal must be tested **in context**, not only in isolation.
- Python is the primary research specification; NT8 remains execution until Phase 1b migration gates are met.

---

## Current empirical baseline

| Dimension | Summary |
|-----------|---------|
| **Economics (static backtest, pre-payout)** | **ORB+Opt3** at **qty = 3** (funded-scale) is on the order of **~$3,265/yr per account** (NT8 reference basis; ~$1,088.50/yr per contract × 3 — see `docs/program-charter.md` and lessons log **2026-05-13** correction). |
| **Python vs NT8** | Research rerun is within **~6.8%** of the NT8 reference on a **per-contract** basis (RTH-only protocol; `docs/m6-nt8-reproduction.md`). |
| **Live / operational** | Even when edge appears real in backtest, **trade frequency is structurally low** for the current ORB+Opt3 configuration: the strategy does not trade often enough to **reliably overcome variance** inside typical prop-firm drawdown windows. |

---

## Per-account income gap

- **Target:** **$65,000–$100,000/yr net per funded account** (after payout splits — charter-level engineering target).
- **Baseline (anchor above):** **~$3,265/yr** pre-payout static backtest at funded qty ≈ 3.
- **Gap scale:** Roughly **~20×** between baseline anchor and the per-account target.

Phase 2 must close **a meaningful fraction** of this gap — not merely ship marginal tweaks. Success is judged against **aggregate per-account economics**, not a single satisfying backtest curve.

---

## Phase 2 framing

Phase 2 is **ground-up pattern and configuration discovery** on **~6 years of MNQ** data using the Phase 1 environment. It is **not** “extend Flux with one more module by default” and **not** framed around **replacing AfternoonMR and Range** (that language is obsolete given production is **ORB+Opt3**-only).

The **V2 starter packet** mental model remains useful:

- **Phase 0 (done):** Data infrastructure and research platform.
- **Phase 1 (this program’s Phase 2 entry):** Pattern discovery and hypothesis testing.
- **Phase 2:** Strategy development from validated patterns.
- **Phase 3:** Integration and deployment planning.

**Updated mantra:** discover **any configurations** (sizing, filters, session/regime gates, new modules only if justified, or other structures) that **close the income gap** while surviving statistical gates and prop constraints.

Canonical research-process details and acceptable outcome families: **`flux-v2-module-search-starter.md`** (repo root).

---

## Minimum viable edge criteria (per-strategy)

When the winning path includes a **new module**, the charter’s **minimum viable edge** thresholds remain in force (see `docs/program-charter.md`):

- OOS win rate **≥ 57%**
- Edge over breakeven **≥ +3 percentage points**
- P&L **≥ $5K/yr** at **1 NQ**
- Trades **≥ 80/yr**
- Profitable in **≥ 4 of 6** years

**Important:** These are **individual-strategy / module** criteria. **Program success** is **closing the per-account income gap**, which may require **multiple strategies**, **sizing increases** within risk limits, **portfolio diversification**, or **other leverage** — not a single new module clearing MV edge in isolation.

---

## Research methodology principles

All of the following are **defaults** unless the operator explicitly approves an exception (documented in the lessons log):

1. **Pre-registration:** Hypotheses and primary metrics are stated **before** the backtest run that tests them.
2. **IS / OOS:** **60/40 split by trade count** (or charter-aligned variant if superseded — document if changed).
3. **Multiple testing:** **Deflated Sharpe** (or equivalent Bailey–López de Prado–style correction) across the **set of hypotheses tested** in a research wave.
4. **Uncertainty:** **Bootstrap confidence intervals** on key metrics where applicable.
5. **Temporal robustness:** **Walk-forward** validation for candidates that survive initial screens.
6. **Structural rationale:** Patterns must have a **structural / behavioral reason**, not only favorable equity curves.

---

## Trade frequency as a first-class constraint

Phase 1 showed that **low trade count** can make a **real edge** **operationally unusable** under prop DD windows: variance dominates short horizons, and pass/fail becomes a sampling lottery.

Phase 2 should treat **trade frequency** as a **constraint alongside** edge magnitude — not only “more P&L per trade.” **Higher frequency with smaller per-trade edge** may **dominate** **rare, high-edge** patterns for **funded** survival and payout realization.

---

## Role specialization (Phase 2)

| Role | Actor | Responsibility |
|------|--------|----------------|
| **Operator** | Christian | **Conductor:** chooses which hypotheses enter the queue, resolves tradeoffs at decision points, validates findings against market intuition and live constraints. |
| **Strategy partner** | Claude app | Hypothesis generation, methodology review, ranking and briefing on candidate directions, statistical interpretation. |
| **Implementation agent** | Cursor | Code execution, data analysis, backtest runs, document maintenance, lessons log entries per `docs/ai-project-instructions.md`. |

---

## Reference documents for fresh-chat startup

Read these **in order** when opening a new Phase 2 session:

1. `docs/program-charter.md` — program structure, Phase 2 gates, MV edge language.
2. `docs/lessons-log.md` — decisions, failures, baseline corrections, multi-module findings.
3. **`docs/phase-2-kickoff.md`** (this document) — intent, gap math, methodology, roles.
4. **`flux-v2-module-search-starter.md`** — reframed Phase 2 objective and acceptable outcome families.
5. `docs/ai-project-instructions.md` — agent and documentation conventions.

Supporting: `docs/phase-1-detailed-plan.md` (what was built), `docs/m6-nt8-reproduction.md` (parity anchor), `docs/nt8-backtest-methodology.md` (NT8 reference protocol).

---

## First-session priorities (Phase 2)

1. Re-read **`flux-v2-module-search-starter.md`** and the charter Phase 2 section for **any remaining stale framing**; align language with **income-gap discovery** (not “replace named legacy modules”).
2. **Confirm** research methodology and **where pre-registered hypotheses are recorded** (e.g. lessons log, dedicated research log, or ticket list — pick one convention and stick to it).
3. Identify the **first batch** of **5–10** hypotheses to investigate and **pre-register** them before running tests.
4. Agree how **findings** are **documented and surfaced** (summary format, pass/fail, links to artifacts, operator sign-off checkpoints).

---

## Closure

When this document and the Phase 2 **`docs/current-working-plan.md`** are committed to **main**, Phase 1 closure is **administratively complete** and Phase 2 work may proceed in dedicated chats with clean context.
