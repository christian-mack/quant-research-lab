# Lessons Log

**Purpose:** Append-only record of findings, surprises, invalidated assumptions, and post-mortems across the systematic trading development program.

**Rules for what goes here:** See `ai-project-instructions.md` for the full rules. Summary: significant findings, decision points, and invalidated assumptions — not routine completions.

**Format:** Newest entries at the top. Each entry dated, with a one-line summary, the context, the finding, and the implication.

---

## Entry Template

```
## YYYY-MM-DD — [One-line summary]

**Phase:** [1/2/3/4 or parallel track ID]
**Context:** [What was being done when this was discovered]
**Finding:** [What was learned]
**Implication:** [What changes because of this — plans, assumptions, architecture, approach]
**Artifact:** [Link to code commit, backtest result, research notebook, or other supporting evidence]
```

---

## Entries

## 2026-04-26 — Deferred WSL2 in favor of Windows-native Python for Phase 1

**Phase:** 1
**Context:** M1 development environment setup. Phase 1 plan specified WSL2 with rationale "avoids Windows-specific Python headaches."
**Finding:** As of April 2026, the Windows-Python friction the original rationale assumed is largely gone for this project's stack: polars, numpy, scipy, pandas-ta, and uv all ship native Windows binaries with no compilation step. Python 3.13.9 was already installed and functional on the dev machine. WSL2 was installed but only with a `docker-desktop` distribution; setting up a usable Ubuntu environment plus crossing the WSL filesystem boundary for the local `data/` directory was judged to add more friction than it removed.
**Implication:** Proceeding with Windows-native Python 3.13 + uv for Phase 1. WSL2 remains available if a future need (e.g., a Linux-only library, container-based reproducibility) emerges. `docs/phase-1-detailed-plan.md` tech stack table updated to reflect this.
**Artifact:** This M1 setup session; commit "M1 setup: switch to Cursor + Windows-native Python; scaffold project".

## 2026-04-26 — Switched IDE from VS Code to Cursor

**Phase:** 1
**Context:** Phase 1 plan and Week 1 working plan were drafted on April 20 specifying "VS Code + WSL2 on Windows" as the development environment. At session start on April 26, the project workspace rule (`.cursor/rules/project.mdc`) and the operator confirmed Cursor is the IDE for this project.
**Finding:** Cursor (a VS Code fork with built-in agentic AI) is preferred over stock VS Code. The "Python/Jupyter/Remote-WSL extensions" referenced in the M1 deliverables remain available in Cursor since it inherits the VS Code extension marketplace; no functional capability is lost.
**Implication:** `docs/phase-1-detailed-plan.md` tech stack table and M1 deliverable list updated to reference Cursor. `docs/current-working-plan.md` Week 1 task and risks table updated. `docs/ai-project-instructions.md` amended with explicit "IDE: Cursor" convention so future agent sessions inherit the choice without rediscovery.
**Artifact:** Commit "M1 setup: switch to Cursor + Windows-native Python; scaffold project".
