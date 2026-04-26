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

## 2026-04-26 — NT8 export shape forced data-boundary fallback for continuous contract

**Phase:** 1
**Context:** M2 continuous-contract construction. Planned roll methodology was
volume crossover (next-contract daily volume > current contract for N=3 consecutive
days within the overlap window, then roll the next calendar day). This is the
standard convention in futures research and matches NT8's default.

**Finding:** The methodology never triggers on the present NT8 MNQ dataset,
because the export's data shape doesn't carry the signal:

- 2020 - mid-2024 contracts: each adjacent pair has exactly 5 calendar days of
  overlap. During those 5 days the current contract still dominates by 50-1000x
  for days 1-4, then crashes ~90% on day 5 (the unwind day) while the next
  contract's volume picks up. So next-contract dominance occurs at most for the
  single last day of overlap, never for 3 consecutive days.
- Mid-2024 onward: contracts are 0- or 1-day-contiguous (no overlap). Plus two
  documented gaps: Jun 18 - Jul 31 2024 (-44 days) and Feb 3 - Mar 11 2026
  (-37 days), where adjacent contracts don't even touch.
- Net: zero of the 25 inter-contract rolls trigger volume crossover; all fall
  through to the implemented data-boundary fallback (roll at current.last_ts +
  1 microsecond).

The fallback isn't a degraded answer — the data boundary is exactly where NT8
chose to stop one contract and start the next, which is itself a roll
heuristic baked into the export.

**Implication:**
1. **Methodology decision**: continuous-contract module supports both methods.
   Default behavior on this dataset is data_boundary; the volume_crossover code
   path is preserved and tested for the case where we acquire fuller data
   (institutional vendors typically export each contract over its full
   lifecycle, not just its dominant period).
2. **Diagnostic**: a real-data test (`test_real_continuous_contract_methods_breakdown`)
   asserts `n_data_boundary >= 20` so that a future data-source upgrade
   producing real volume_crossover rolls is visible (good signal — more
   information for indicator/regime work).
3. **Back-adjustment deferred**: continuous output keeps raw prices. Roll-day
   discontinuities are visible via the `contract_symbol` column. M4 backtest
   engine will handle position rolls explicitly; if research downstream needs
   a back-adjusted series for indicator computation, add as a separate
   transform.
4. **Process lesson** (operator-flagged as the most valuable part of this entry
   for future work): I committed to the volume-crossover methodology before
   inspecting the data shape. A 5-minute exploratory query before designing
   the core algorithm would have surfaced this earlier. **Apply going forward
   for any data-shape-dependent algorithm — particularly relevant during M3
   indicator design and M5 module ports, where indicator/strategy assumptions
   can collide with the actual data shape (session boundaries, gap patterns,
   roll discontinuities, holiday handling). Run a daily-aggregate inspection
   of the relevant data before writing the algorithm, not after.**

**Artifact:** Commit `ce56bd6` ("M2(continue): continuous contract construction
with documented roll methodology"). Module: `src/quant_research/data/continuous_contract.py`.

## 2026-04-26 — NT8 export contains DST-gap timestamps; loader must handle gracefully

**Phase:** 1
**Context:** M2 multi-file loader. Initial `load_contract_file` localized timestamps with `pl.Expr.dt.replace_time_zone("America/Chicago")` using polars defaults (`non_existent="raise"`, `ambiguous="raise"`). Real-data load of the full 26-contract MNQ dataset crashed.
**Finding:** The dataset contains a single bar at `2025-03-09 02:14:00` — a wall-clock time that does not exist in `America/Chicago` because of the spring-forward DST gap (clocks jumped 02:00 → 03:00 that morning). The bar has `volume=1`, almost certainly a stray adjustment or NT8 export artifact: CME Globex is closed Sunday early morning (the trading session reopens 17:00 CT Sunday), so no bona fide bars are expected in the gap. The fall-back analog (1:00-1:59 CT occurring twice on November 3, 2024) shows zero bars in the dataset. This single phantom bar is the only DST-gap row across the full 6-year dataset.
**Implication:**
1. Source data IS in `America/Chicago` as documented; NT8 does not insulate against DST and the responsibility falls on the loader.
2. Loader updated to `replace_time_zone(non_existent="null", ambiguous="earliest")` + filter null timestamps. Net: 1 row dropped from 2,196,751 raw rows. Result: 2,196,750 canonical bars.
3. Multi-file real-data test asserts `loaded_count == raw_count` modulo a 50-row DST tolerance, so the test stays meaningful as data is added without re-implementing DST logic.
4. Synthetic DST-gap regression test (`test_load_contract_file_drops_dst_gap_phantom_bars`) added.
5. Same caution applies to forthcoming M2 work: session classification must understand DST, since RTH/ETH boundaries shift wall-clock time twice a year. Continuous contract construction is unaffected (it operates on already-localized timestamps).
**Artifact:** Commit `7ec8e35` ("M2(continue): multi-file loader + DST-gap handling").

## 2026-04-26 — Renamed Python package: flux_research → quant_research

**Phase:** 1
**Context:** M1 environment scaffold was committed earlier in the day with the Python package named `flux_research` (after the Flux strategy generation). On review before starting M2, decided the package should match the repo (`quant-research-lab`) and reflect the durable cross-generation scope of the research infrastructure rather than a single strategy family.
**Finding:** Naming the research package after one strategy generation is short-sighted given the program's multi-generation scope per the charter (Flux V1/V2/V3, Onyx V1, future generations). The Python import package and PEP 503 distribution name should both reflect the long-term scope of the infrastructure, not the first strategy that uses it.
**Implication:** Renamed `src/flux_research/` to `src/quant_research/` via `git mv` (preserves history). Distribution name in `pyproject.toml` also changed from `flux-research` to `quant-research` for consistency between import name and dist name. All doc references updated. Done while the package was still effectively empty (only `__init__.py` files) — zero import-refactoring cost. Lesson for future: name infrastructure assets after the program scope they serve, not the first consumer.
**Artifact:** Commit "refactor(M1): rename package flux_research → quant_research; relocate raw data".

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
