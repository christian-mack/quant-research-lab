# Research log — Phase 2 pre-registration and results

**Purpose:** Append-only log of **hypotheses**, **specifications**, and **outcomes** for Flux V2 / Phase 2 work.

**Rules:**

- **Append only** — never delete or rewrite past entries; add a correction as a new note if something was wrong.
- **Pre-register before the run** that would decide pass/fail on the primary metric (except exploratory notes clearly labeled as such).
- **Waves:** Group hypotheses into **Wave 0**, **Wave 1**, … for **multiple-comparisons / deflated Sharpe** accounting: use **N = number of distinct hypotheses tested in that wave** (including any that were run after optional early stops, unless a sequential testing protocol was pre-registered).
- **Status line** must move forward: `PRE-REGISTERED` → `RUN-PENDING` → `RESULT-LOGGED` (or `ABANDONED` with reason).

**Related:** `docs/phase-2-kickoff.md`, `docs/current-working-plan.md`, `docs/lessons-log.md`, `docs/ai-project-instructions.md`

---

## Entries

*(No entries yet — Wave 0 and hypothesis waves append below.)*

---

## Entry template

Copy from `## YYYY-MM-DD` through **`Artifact:`** for each new hypothesis or baseline record.

```markdown
## YYYY-MM-DD — [Hypothesis short name] — [STATUS: PRE-REGISTERED | RUN-PENDING | RESULT-LOGGED]

**Wave:** [Wave N]
**Structural rationale:** [Why this pattern should exist in NQ microstructure, 1-2 sentences]
**Specification:**
  - Entry rule:
  - Exit rule:
  - Session window:
  - Position sizing convention for the test: 1 NQ (isolation screen) or max sustainable qty (graded)
  - IS/OOS split: [60/40 by trade count or alternative]
**Primary metric:** [Single metric for pass/fail]
**Secondary metrics:** [WR, edge over BE, trade count, year-by-year profitability, max DD]
**Pass/fail criteria:** [Specific thresholds before the run]
**Date pre-registered:**
**Date run completed:**
**Result:** [PASS / FAIL / INCONCLUSIVE — brief summary]
**Artifact:** [Path to notebook or backtest output, git SHA]
```
