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

## 2026-04-28 — M5 ORB port: session FSM reset orphaned live position management; M6 forensics

**Phase:** 1 (M5/M6)  
**Context:** M6 full-window Python ORB+Opt3 vs NT8 showed order-of-magnitude $/yr divergence plus multi-thousand-hour “ORB” holds and calendar years with zero exits despite RTH bars.  
**Finding:** The Python `OrbStrategy` tied **open-position management** to the **daily entry** state machine: on `cme_session_date` rollover it reset to **Idle** before handling `ctx.position_qty != 0`, so **`_manage_open`** (break-even, bracket refresh) could **drop out** across sessions. In C#, `ResetDaily` clears `ExecutionEngine._positionState`, but **NT8 protective orders remain on the instrument**; production ORB+Opt3 had not exposed this in live because broker-side exits still run. The Python simulator has **no** broker layer—management must stay on-strategy every bar while flat is false.  
**Implication:** M6 **validated the escalation path**: smoke bands + large divergence → investigation → **real** bug, not fill-model noise. **M7** can proceed once the operator accepts **M6 process** closure; **headline dollar parity** remains a stacked data/parity problem (plus residual bracket-queue hypotheses). Regression: `test_orb_cross_session_position_break_even_regression`.  
**Artifact:** Commit fixing `orb.py` + updated `m6-nt8-reproduction.md`.

## 2026-04-28 — Docs referenced artifact paths that were never committed (looked fine locally)

**Phase:** 1 (process / repo hygiene)  
**Context:** Validating methodology and smoke results that pointed at on-disk paths such as `docs/nt8-artifacts/` (or similar) while reviewing git history and clone-fresh behavior.  
**Finding:** Documentation and checklists referenced files that **existed only in the local working tree** (untracked or not yet pushed). On the author machine everything “resolved” because the files were present; another checkout or collaborator saw **broken references** until the artifacts were actually **committed** (or the doc was corrected).  
**Implication:** When docs instruct readers to open paths or rely on committed baselines, **prove availability from a clean clone** (or CI) — not from “I have the folder here.” Treat **“referenced in doc” ⇒ “in git”** as an explicit gate for artifact directories, CSV exports, and NT8 dumps. Same class of failure as assuming env state that isn’t in the repo.  
**Artifact:** `docs/lessons-log.md` (this entry); commits that added `docs/nt8-artifacts/` after methodology-only commits (see repo history / `SESSION_NOTES`).

## 2026-04-28 — M4 = correct engine; M6 = NT8 smoke test (not parity)

**Phase:** 1 (M4/M6 scope)
**Context:** Path A had already fixed M6 baseline to ORB+Opt3 only; methodology was PT3-Complete. Remaining drag was an implicit “forensic NT8 reproduction” bar that competed with reaching M7 (Phase 2 statistical leverage).
**Finding:** **M4** is explicitly **sound backtest engineering** (deterministic fills, auditable `PYTHON_ASSUMPTION`s, Flux-style OMAT/priority). **M6** is downgraded to a **smoke test** vs NT8: **±10% aggregate net P&L**, **±5% closed-trade count** for the ORB+Opt3 run; per-trade diff is diagnostic, not a gate, unless bands fail. PT3 remains a **reference**, not a byte-match spec.
**Implication:** `docs/m4-backtest-engine-design.md` signed **2026-04-28** with **§8 adopted defaults**; `docs/nt8-backtest-methodology.md` §10 references smoke bands. **`docs/phase-1-detailed-plan.md` M6** still states “every divergence >5% investigated” — **needs a planned doc pass** to align exit criteria with operator smoke framing **without** silently rewriting charter gates in this session.
**Artifact:** **`a303e0f`** — docs + `src/quant_research/backtest/`.

---

## 2026-04-30 — Phase 1b after Phase 1; Python-first port spec to Sierra

**Phase:** 1 / program infrastructure  
**Context:** Production was cut to ORB+Opt3 with explicit validation and income-gap lessons (2026-04-28 entries); program docs were reframed around income as constraint and backtest-to-live alignment. That cascade raised how **execution migration** should relate to **research**: still necessary for NT8 feed integrity, but not in a way that competes with completing validated Python strategy logic first.  
**Finding:** **Sierra Chart migration remains the plan** — **not** deferred in the sense of "maybe later / maybe never" — but **sequenced after Phase 1 completes**, not **in parallel** with it. Phase 1 produces **validated Python strategy logic** (especially **M5** implementations and **M6** NT8 parity); that **Python is the primary specification** for ACSIL (or chosen platform) porting; **NT8 C# is secondary reference** for cross-check and implementation detail. **NT8 → Sierra directly** would skip the validated research chain and keep spec ambiguity in band. The **M1–M9 research track is the same** whether live runs on NT8 or eventually on Sierra; only **when Phase 1b port work begins** is gated on Phase 1 completion. **NT8 remains production** for all of Phase 1 and until Phase 1b passes **side-by-side SIM validation** against NT8. Separately, **Apex/Tradovate API** access for funded execution is **already understood to be restricted** — a dedicated "email Apex / PT7" task in the working plan was **redundant** and is removed.  
**Implication:** Charter **Phase 1** parallel tracks must **not** imply Phase 1b during Phase 1. **Phase 1b** entry is **Phase 1 milestone gate passed** plus trial access; scope encodes **Python-first** port, **chart/platform route** (not API-first), and **live deployment** continuity on NT8 until validation. **`current-working-plan.md`**: drop **PT7** lines; note Phase 1b sits after the 30-day Phase 1 window. **`phase-1-detailed-plan.md`** §PT7 aligned so "parallel PT7 weeks" don't reappear.  
**Artifact:** Pending commit (`program-charter.md`, `current-working-plan.md`, `phase-1-detailed-plan.md`); this entry pending approval.

---

## 2026-04-28 — Income target is the constraint; architecture is empirical

**Phase:** Program-wide (charter / roadmap framing)
**Context:** Reviewing program documentation after a production configuration change and clarifying what actually gates progress toward the stated financial goal.
**Finding:** The **$500K–$1M/yr net income target** is the hard constraint. **System shape** (single- vs multi-module, which execution stack, whether a regime overlay exists, Flux vs Onyx, etc.) is **means**, not **ends**. Strategy **generations** (Flux V1/V2/V3, Onyx V1, …) should be read as the **current best-understood path** to that income goal — a structured way to sequence **investigations** — not as a fixed ladder where each step is “the next architecture we must build.” Phase boundaries stay useful for scoping work, but their **justification** shifts from “predetermined next build” to **“next empirical investigation toward income.”** What advances the goal is decided by evidence, not by the table order in the charter.
**Implication:** Charter, roadmap exit criteria, and Phase 2 narrative should **not** treat multi-module expansion or specific follow-on generations as assumed successes. Documentation should describe phases as **hypothesis tests** toward income, with explicit room to prefer simpler live configurations if they perform better on **both** backtest-like metrics and **live correspondence**. Downstream edits: program charter (program structure + principles), Phase 2 scope/exit language, any “V2 starter” / README summaries that still frame Phase 2 only as “replace broken modules.”
**Artifact:** Operator decision (production config + program reframing); pending coordinated doc updates (`program-charter.md`, roadmap/README Phase 2 wording).

---

## 2026-04-28 — Backtest-to-live alignment is first-class validation

**Phase:** Program-wide (research and gates)
**Context:** Aligning research and phase gates with how live capital is actually risked: backtests are necessary but not sufficient when execution, feeds, and runtime behavior diverge from research assumptions.
**Finding:** **Backtest-to-live alignment** must be treated as a **first-class research goal**, not an afterthought or operational nicety. A configuration is **not** validated by **backtest performance alone**. Evidence needs **both** (a) acceptable risk-adjusted / income outcomes under the research backtest protocol and (b) **demonstrated correspondence** (or explainable, bounded gaps) between that backtest and live/SIM behavior over defined windows. Gates that only reference paper performance risk **overfitting the simulator** and shipping structure that fails under real constraints.
**Implication:** Phase milestone wording, working-plan checks, and future “minimum edge” definitions should explicitly require **live-alignment evidence** alongside backtest stats. Research prioritization may favor simpler systems that **calibrate cleanly** to live over complex stacks that **only** look good in backtest. Ties directly to NT8 methodology documentation, port-fidelity checks, and Phase 1b side-by-side validation themes.
**Artifact:** Charter principle (pending); existing/pending methodology artifacts (`nt8-backtest-methodology.md`, divergence analyses).

---

## 2026-04-28 — Production cut to ORB+Opt3; tri-module economics invalidated on 6-year data

**Phase:** Live operations / research framing
**Context:** Extended 6-year backtest validation and Apex eval pass-rate testing drove a production configuration decision; tri-module ROI projections in the charter were tied to an obsolete baseline.
**Finding:** Production was changed from the quad-module config (Momentum/ORB/Range/AfternoonMR) at Config E sizing (0/16/16/20) to ORB-only with the LatestEntryHourET=11 optimization (referred to as ORB+Opt3 in operator notes). Current sizing: qty=10 for $50K EOD eval phase, qty=3 for funded phase (currently running on a $50K PA at $49,418 balance, $1,418 from liquidation). Decision was driven by 6-year backtest results (2020-2026) showing:
- ORB+Opt3 alone: $10,885/yr per contract, 63.8% WR, 7/7 positive years, MaxDD -$17,880
- V1 production tri-module (no Opt3): $3,060/yr, 58.5% WR, 5/7 positive years, MaxDD -$44,490
The non-ORB modules collectively destroyed ~$45K of ORB's value across the 6-year period. Momentum specifically was net-negative through displacement — its presence cost ORB more in lost trades than Momentum produced from its own entries. The earlier 18-month analysis that concluded the tri-module config was profitable was invalidated by extended validation, providing concrete evidence for the broader meta-lesson about validation methodology (entry 2 above).

For prop firm scenarios specifically, ORB+Opt3 at qty=10 produced the best Apex 4.0 eval pass rate (~35.5% in ~9 days average) of all configurations tested. Multi-module configs at meaningful sizing blew more often than they passed. The slower trade frequency of ORB-only is a feature for prop firm survival, not a bug.

**Implication:** ROI projections in the charter and roadmap based on tri-module baseline P&L (~$32K/yr) are obsolete. New baseline for improvement targets is ORB+Opt3 performance. Per-account funded income realistic projection (~$8K/yr at qty=3 funded sizing) significantly trails the program's $65K-$100K per-account target — this gap is now an explicit research priority, not an assumption. The charter's program structure should reframe phase justifications toward "investigations that close the per-account income gap" rather than "predetermined architectural progressions." Production code now has ORBLatestEntryHourET=11 set; this configuration value should be captured in nt8-backtest-methodology.md when PT3 completes.

**Artifact:** Six-year NT8 backtest comparison (2020–2026); Apex 4.0 eval pass-rate study; live PA snapshot at decision; production `ORBLatestEntryHourET=11`.

---

## 2026-04-27 — Source NT8 export timestamps are UTC, not CME local time

**Phase:** 1
**Context:** Starting M2 session classification. Before writing the
classifier I applied the process lesson from the 2026-04-26 NT8-export-shape
entry — inspect the data shape before designing a data-shape-dependent
algorithm. Specifically, I dumped hour-of-day distributions of the
CT-labeled timestamps and looked at where the CME daily maintenance break
falls.

**Finding:** The data is **not** in `America/Chicago` despite the
documentation (and the loader, until now) treating it as such. Three
independent observations all reconcile only under the hypothesis that
the source timestamps are UTC:

1. **Daily maintenance gap location.** CME Globex closes daily for
   maintenance at 16:00-17:00 CT. Under the old "source is CT"
   assumption the gap landed at 21:00-22:00 in the labeled CT data —
   five hours late. Under "source is UTC, convert to CT" the gap lands
   at exactly 16:00-17:00 CT.
2. **Seasonal shift in gap location.** Across a fixed-tz interpretation
   the gap's wall-clock position shifts by exactly one hour between
   DST-on (CDT, UTC-5) and DST-off (CST, UTC-6) months — exactly what
   you'd expect if the underlying timestamps are UTC and being viewed
   in a DST-observing zone, and exactly *not* what you'd expect if the
   source were already CT.
3. **Friday weekly close and Sunday weekly open.** CME's weekly close
   is Friday 16:00 CT and the weekly reopen is Sunday 17:00 CT. The
   raw labels show Friday close at 21:00 (DST-on) or 22:00 (DST-off)
   and Sunday open at 22:00/23:00 — again, off by 5 or 6 hours
   depending on season, exactly the UTC↔CT offset.

The "1 phantom bar at 02:14 on 2025-03-09 in the DST gap" finding from
the prior DST entry is now explainable: 02:14 in the source file is
02:14 UTC = 20:14 CST on 2025-03-08 (Saturday evening, well before
Sunday's CME reopen). It's a stray pre-open tick, not a real DST
artifact at all.

**Implication:**
1. **Loader fix (Path A — convert at load time).** Source treated as
   UTC and converted to CT inside `load_contract_file`:
   `replace_time_zone("UTC").convert_time_zone("America/Chicago")`.
   Downstream code keeps reasoning in CT wall-clock as before. New
   constant `SOURCE_TIMEZONE = "UTC"` documents the actual source
   timezone alongside the existing `CME_TIMEZONE`. Reasons for Path A
   over Path B (carry UTC end-to-end): operator mental model is CT,
   downstream code (session classification, RTH/ETH boundaries,
   indicators with daily timeframes) expects CT, and a single
   conversion at the data boundary eliminates per-call conversion
   risk in dozens of downstream call sites.
2. **No rows dropped now.** The previous DST-gap drop was based on a
   wrong premise. With the source correctly tagged as UTC, every UTC
   instant has exactly one CT representation, so no row is non-existent
   under the conversion. Raw rows = 2,196,751, all retained. Continuous
   contract = 2,140,532 (was 2,140,530 — the +2 is from previously-
   dropped phantom bars now correctly included, plus a small change
   in the data-boundary roll instant for one pair where the boundary
   shifted by an integer-microsecond amount).
3. **Tests updated.**
   - `test_load_contract_file_converts_utc_source_to_ct` (replaces
     the deleted DST-gap-drop test): asserts the loader converts
     UTC source to CT correctly across a former-DST-gap window.
   - `test_real_load_all_contracts_total_bar_count_matches_raw_files`:
     now asserts exact equality (`loaded_height == raw_count`),
     no DST-tolerance window.
   - `test_real_mnq_03_26_endpoints_match_raw_file_after_utc_round_trip`:
     compares the loaded CT timestamp converted *back* to UTC against
     the raw file's UTC string, verifying instant-in-time preservation
     across the conversion.
   - 43/43 tests pass.
4. **Documentation correction-by-append.** Per the append-only
   lessons-log rule, the prior DST entry stays as committed. A
   correction entry (next in this file) references it explicitly,
   preserving the historical record.
5. **Process amendment.** The 2026-04-26 process lesson said "inspect
   data shape before designing data-shape-dependent algorithms." A
   companion entry (also in this file) adds **timezone and time-of-day
   sanity checks** to the list of things that "data-shape inspection"
   covers. The current finding is the canonical example: had I run a
   maintenance-gap-by-hour query on day 1 of M2, I would have spotted
   the 21:00 vs 16:00 CT discrepancy immediately and avoided this
   sequence of fix-then-rediscover.

**Artifact:** This commit ("M2(fix): UTC source timezone for NT8
export; convert to CT at load time"). Module:
`src/quant_research/data/data_loader.py`. Empirical verification:
post-fix, last bar of dataset lands at 16:00 CT — exactly the CME
daily-maintenance-break boundary.

## 2026-04-27 — Correction to the 2026-04-26 DST entry: rationale was wrong

**Phase:** 1
**Context:** Append-only correction (per the lessons-log convention) of
the 2026-04-26 entry "NT8 export contains DST-gap timestamps; loader
must handle gracefully."

**Finding:** That entry's *result* — drop the 2025-03-09 02:14 phantom
bar — was the right action, but its *rationale* was wrong. The rationale
asserted "Source data IS in `America/Chicago` as documented; NT8 does
not insulate against DST and the responsibility falls on the loader."
This is incorrect. The source data is in **UTC**, not `America/Chicago`
(see the 2026-04-27 UTC discovery entry above for the full investigation).
Once the source is correctly treated as UTC and converted to CT, the
"phantom bar" is not in any DST gap at all — `2025-03-09 02:14 UTC`
becomes `2025-03-08 20:14 CST`, a Saturday-evening pre-open tick that
the loader retains rather than drops.

**Implication:**
1. The original entry's items 1 ("Source data IS in America/Chicago"),
   2 (the row-drop count), 3 (DST-tolerance test), and 4 (the
   `test_load_contract_file_drops_dst_gap_phantom_bars` test name)
   are all superseded.
2. Replacement state, post-2026-04-27 fix:
   - Loader: `replace_time_zone("UTC").convert_time_zone("America/Chicago")`,
     no `non_existent`/`ambiguous` flags needed (UTC is unambiguous).
   - Row count: 2,196,751 raw, 0 dropped (was 2,196,750 with 1 dropped).
   - Test assertion: exact equality between loader rows and raw line
     count, no tolerance window.
   - DST-gap synthetic test replaced with a UTC→CT conversion test
     covering the same date.
3. Item 5 of the original entry — "session classification must
   understand DST, since RTH/ETH boundaries shift wall-clock time
   twice a year" — remains correct and still applies. RTH wall-clock
   times are stable (08:30-15:00 CT) but the underlying UTC offset
   shifts twice a year, which the polars-attached `America/Chicago`
   tz handles automatically.
4. The original entry stays as committed; this correction does not
   edit it. Future readers should follow this entry up to find the
   current state.

**Artifact:** Same commit as the 2026-04-27 UTC discovery entry above.
The original DST entry references commit `7ec8e35`; this correction
supersedes that commit's loader logic.

## 2026-04-27 — Amendment to the 2026-04-26 process-lesson: data-shape inspection includes timezone

**Phase:** 1 (process)
**Context:** Append-only amendment (per the lessons-log convention) of
item 4 ("Process lesson") of the 2026-04-26 entry "NT8 export shape
forced data-boundary fallback for continuous contract."

**Finding:** That process lesson said: "Run a daily-aggregate inspection
of the relevant data before writing the algorithm, not after." The
intent was correct but the scope was incomplete. The 2026-04-27 UTC
discovery (above) is a case where the algorithm being written was
*timezone handling itself*, and the inspection that would have caught
the bug was a different shape of inspection — hour-of-day distributions
across DST-on and DST-off months, not daily aggregates.

**Implication:** The "inspect data shape before designing
data-shape-dependent algorithms" lesson should be read as covering at
least these three sub-checks, applied to *any* dataset entering the
pipeline:

1. **Distributional shape (the original intent).** Daily aggregates,
   per-contract overlap windows, gap patterns, holiday behavior — what
   the 2026-04-26 lesson originally addressed.
2. **Timezone and time-of-day sanity checks (new).** Hour-of-day
   distributions; location of known reference events (daily maintenance
   break, weekly open/close, RTH boundaries) under the assumed
   timezone; comparison across DST-on and DST-off months to detect
   misinterpreted-as-fixed-offset data.
3. **Calendar-and-DST sanity checks (implied by 2 but worth calling out).**
   Verify the dataset behaves as expected across at least one DST
   spring-forward, one fall-back, and one major US holiday before
   trusting the loader output for downstream code.

**Implication for future work:** Apply this expanded checklist when
loading any new dataset (M3 alternative-instrument data, M5 module
ports, M6 NT8 backtest comparisons, future Onyx data sources). The
hour-of-day check is the single highest-leverage item — five minutes
of wall-clock time saved hours of fix-then-rediscover here.

**Artifact:** Same commit as the 2026-04-27 UTC discovery and DST
correction entries above.

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
