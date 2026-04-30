# Flux V2 — Research Starter (configuration investigations)

**Location:** Repository root for now. **TODO:** Consider moving under `docs/` for consistency with other program docs (separate cleanup pass).

**Authority:** Phase scope and gates live in `docs/program-charter.md` (Phase 2). Baseline economics and production cut live in `docs/lessons-log.md` (2026-04-28 entries).

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
- **Improvement metric:** Charter Phase 2 uses **≥X% improvement vs. baseline** on KPIs agreed at Phase 2 kickoff; **X** is set only after the ORB+Opt3 reference is frozen in Python artifacts (**M6/M7-class** NT8 parity).

---

## Related

- `docs/program-charter.md` — Phase 2 entry/exit/stop conditions
- `docs/README.md` — program overview
- `docs/phase-1-detailed-plan.md` — Phase 1 handoff to Phase 2
