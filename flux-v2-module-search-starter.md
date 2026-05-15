> **DEPRECATED FRAMING (2026-05).** This document predates Phase 2 production simplification. **Current framing:** `docs/phase-2-kickoff.md` and `docs/program-charter.md`. The starter packet’s **module-replacement** language (replace AfternoonMR and Range) is **obsolete** — production is **ORB+Opt3** only and Phase 2 is **income-gap discovery**, not module replacement. The content below remains useful for research-process detail and process guardrails.
>
> **Apex rule hygiene:** Program convention documents Apex **$3,000 EOD trailing drawdown** and **$1,000 Daily Loss Limit (DLL)** per day on EOD accounts (`docs/ai-project-instructions.md`). The **+$500** term in the **`R(q)`** formula in `docs/phase-2-kickoff.md` is an **internal safety margin on trailing-DD sizing**, **not** the DLL. Do not confuse the two.
>
> **Phase numbering:** This packet’s internal Phase 0 / 1 / 2 / 3 **stages** map to the program’s **single Phase 2**. Specifically: starter **Phase 1** (pattern discovery) and starter **Phase 2** (strategy development) are **sub-stages of program Phase 2**.

# Flux V2 — Research Starter (configuration investigations)

**Location:** Repository root for now. **TODO:** Consider moving under `docs/` for consistency with other program docs (separate cleanup pass).

**Authority:** Phase scope and gates live in `docs/program-charter.md` (Phase 2). Baseline economics and production cut live in `docs/lessons-log.md` (2026-04-28 entries). **Graded baselines** follow **`docs/phase-2-kickoff.md`** (Wave 0, **R(q)**, max sustainable qty).

---

## Phase 2 objective (reframed)

Phase 2 is **not** defined as “replace failed modules” or “add complementary modules” only. It is the research phase to **investigate configurations that improve income trajectory vs. the frozen ORB+Opt3 baseline**, including but **not limited to** additional modules.

**Acceptable outcomes** include, among others:

- Higher-sized **single-module** (ORB+Opt3) variants that survive prop constraints
- **New modules** — only if **integrated** P&L after displacement is positive (tri-module harm on 6-year data is a verified failure mode)
- **Regime gating** or time/session filters on ORB
- **Other approaches** discovered during research (document each hypothesis family)

Every candidate must clear **statistical rigor** (IS/OOS, multiple-comparisons correction, etc. per charter) **and** **backtest-to-live alignment** as a first-class gate — not backtest-only validation.

---

## Baseline reference

- **ORB+Opt3:** ORB with `LatestEntryHourET=11` (operator naming). Capture precisely in `docs/nt8-backtest-methodology.md` when PT3 completes.
- **Improvement metric:** Charter Phase 2 uses **≥X% improvement vs. baseline** on KPIs agreed at Phase 2 kickoff; **X** is set only after the ORB+Opt3 reference is frozen in Python artifacts (**M6/M7-class** NT8 parity). **Graded** baseline economics use **Wave 0** (**max sustainable qty**, **`docs/phase-2-kickoff.md`**).

---

## Related

- `docs/program-charter.md` — Phase 2 entry/exit/stop conditions
- `docs/phase-2-kickoff.md` — grading, Wave 0, **R(q)**, eval simulation
- `docs/research-log.md` — pre-registration and wave-level accounting
- `docs/README.md` — program overview
- `docs/phase-1-detailed-plan.md` — Phase 1 handoff to Phase 2
