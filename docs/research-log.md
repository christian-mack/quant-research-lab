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

## 2026-05-14 — Wave 0 ORB+Opt3 graded baseline — PRE-REGISTERED

**Wave:** Wave 0

**Structural rationale:** ORB+Opt3 is the production Flux V1 configuration; Wave 0 establishes a **graded** economic and risk baseline (max sustainable qty under **R(q)**, simulated eval pass rate) so hypothesis waves compare to the **same** protocol and sizing rule—not ad hoc qty = 3 snapshots.

**Specification:**

- **Strategy / protocol:** ORB+Opt3 (`production_orb_opt3_funded_params()` with `latest_entry_hour_et=11`); **six-year MNQ** protocol **2020-01-01** through **2026-04-19** inclusive (Chicago); **RTH-only** bars; continuous contract; `split_dataframe_at_operator_export_gaps` with fresh engine per segment (same class as `scripts/run_m6_orb_baseline.py` / M6).
- **Per-contract run:** Backtest executed at **quantity = 1** so trade-level `net_pnl` and **DD(1)** are path-defined (not obtained by dividing a qty=3 run).
- **R(q) (sizing cap):** \(R(q) = \max(1.5 \times \mathrm{DD}(q), \mathrm{DD}(q) + \$500)\) with **DD(q)** in **dollars** (positive magnitude). **Max sustainable qty** = largest integer \(q \ge 0\) with \(R(q) \le \$3{,}000\) (Apex **$3K EOD trailing** research ceiling per `docs/phase-2-kickoff.md`).
- **DD scaling (pre-registered):** **Linear default:** \(\mathrm{DD}(q) \approx q \times \mathrm{DD}(1)\), consistent with \(\mathrm{DD}(1)\) from the qty=1 run. **Sanity check:** ORB+Opt3 is **≤ 1 position / day**; if the trade log shows **>1 entry per `cme_session_date`**, STOP and switch to path-dependent \(\mathrm{DD}(q)\) before reporting max sustainable qty.

**Rolling-window convention (eval pass simulation; inherited by later waves):**

| Choice | Decision |
|--------|-----------|
| **Window length** | **30 trading sessions** = 30 consecutive **`cme_session_date`** values from the RTH protocol dataframe (unique session dates in chronological order). *Rationale:* eval performance is defined over **sessions traded**, not calendar noise; aligns with CME session boundaries already used in the pipeline. |
| **Advance** | **1 session** (sliding start index by one `cme_session_date`). |
| **Partial windows** | **Drop:** require a full 30 session dates; no padding. |
| **Trades in window** | Closed trades whose **`cme_session_date` at exit** (from `exit_time` converted to Chicago + joined to session calendar) falls in the window’s 30 session dates. *Implementation:* `exit_time` → America/Chicago → assign the same **cme_session_date** logic as bars (`assign_cme_session_date` on a one-row frame) where possible; else Chicago **local date** as fallback documented in artifact. |
| **Starting balance** | **$50,000** (notional eval anchor per $50K Apex EOD class). |
| **Profit target** | Cumulative scaled closed P&L ≥ **$3,000** vs window start (realized-only). |
| **Trailing DD** | Track **equity** = starting balance + cumulative scaled realized P&L. **High water** = max equity after each closed trade. **Breach** if equity &lt; high_water − **$3,000** (EOD-style check evaluated **after each closed trade** as a conservative proxy; intraday path may differ). |
| **DLL** | **$1,000** max **realized** loss per **America/New_York** calendar day (sum of scaled `net_pnl` for exits on that date). *Limitation:* open-trade MTM not modeled. |
| **Scaling** | Trade `net_pnl` from qty=1 run × **`q_max`** (max sustainable qty). If `q_max = 0`, eval simulation is **degenerate** (no P&L); report **0%** pass and note constraint failure. |

**Primary metric (Wave 0):** Max sustainable qty **q_max** and **graded** annual P&L at **q_max** (if q_max &gt; 0).

**Secondary metrics:** Total and annual P&L per contract at qty=1; trade stats; year max-DD breakdown; simulated eval pass rate at **q_max**; bootstrap CI for per-contract **annualized** P&L (total/yfrac); reconcile to M6 (~$1,014/yr/contract Python).

**Pass/fail:** N/A (baseline establishment). **Deflated Sharpe:** **N/A** for Wave 0 — single pre-specified baseline, not a search over **N** hypotheses; documented here by policy.

**Date pre-registered:** 2026-05-14

**Date run completed:** *(pending — see RESULT-LOGGED follow-up entry)*

**Result:** *(pending)*

**Artifact:** *(pending)*

**Codebase SHA (pre–Wave 0 commit for this log appendix):** `3cb97cfbcb9df07474daa348634e2b12c08899ac`

**Note:** A follow-up **RESULT-LOGGED** entry will record the execution-time `git` SHA and outputs without altering this pre-registration block.

---

## 2026-05-14 — Wave 0 ORB+Opt3 graded baseline — RESULT-LOGGED

**Wave:** Wave 0 (implements pre-registration block above)

**Date run completed:** 2026-05-14

**Execution `git` metadata:** `git_sha` = `3cb97cfbcb9df07474daa348634e2b12c08899ac`, **`git_dirty`: true** (script + artifacts uncommitted at run time; see commit that adds this entry for clean-tree SHA).

**Result — headline:**

| Quantity | Value |
|----------|--------|
| **q_max (R(q) ≤ $3k)** | **0** (_BINDING:_ `no_positive_q`; R(1) would be **$4,012.50** vs **$3,000** cap — **1.5×DD** term binds at q=1) |
| **DD(1)** | **$2,675** (closed-trade path, qty=1) |
| **Per-contract $/yr** | **~$1,014.16** (matches M6 Python anchor within **0.016%**) |
| **Profitable calendar years (qty=1, 2020–2026)** | **4 / 7** |
| **Bootstrap 95% CI annual $/contract** | **[-362.24, 2766.52]** (point **1014.16**), 10k trade resamples, seed=42 |
| **Eval pass rate (30-session rolling, at q_max)** | **0%** (**0 / 1532** windows; degenerate: zero scaled P&L) |
| **Phase 2 P&L tier (at q_max)** | **below_floor** ($0/yr vs $36k / $60k / $100k) |

**Deflated Sharpe:** **N/A** — Wave 0 is a single pre-specified baseline, not a candidate from an **N**-trial search (**not** omitted by oversight).

**Multi-entry `entry_cme_session_date`:** **4** session dates with **&gt;1** closed trade (max **6** on 2025-11-06). Diagnostic: **sequential** same-day BE/target round-trips, not concurrent positions. Re-ran qty **2** and **3**: max DD **$5,350** / **$8,025** = exact **q×DD(1)** → **linear DD retained** for **R(q)** (no path-dependent DD re-fit).

**Artifacts:**
- `notebooks/validation/2026-05-14_wave0_orb_opt3_graded_baseline.md`
- `notebooks/validation/2026-05-14_wave0_orb_opt3_graded_baseline.json`
- Runner: `scripts/run_wave0_orb_opt3_baseline.py`

**Operator flags:** Pre-registered **R(q)** implies **no positive integer** contract count satisfies the conservative margin — **production qty=3** is **outside** this formal cap; methodology vs. live sizing needs explicit reconciliation before using **R(q)** as a hard gate. Not a lessons-log item per routine-completion rule — **judgment call**.

---

## 2026-05-16 — Wave 0b R(q) methodology investigation — PRE-REGISTERED

**Wave:** Wave 0b (methodology — not a strategy hypothesis)

**Structural rationale:** Wave 0’s **R(q)** used **closed-trade cumulative** max drawdown; it implied **q_max = 0** while **live** runs **qty=3**. This investigation tests whether **DD definition** (Apex **EOD trailing** + lock), the **1.5×** multiplier, or both misalign with firm-relevant risk — before Wave 1+ uses **R(q)** as a sizing gate.

**Deliverable 1 — EOD trailing DD simulation (6-year ORB+Opt3 trade log)**  
- **Account class:** **$50,000** starting balance (`docs/nt8-backtest-methodology.md` / `docs/ai-project-instructions.md` — $50K EOD context).  
- **Daily P&L:** Sum of scaled `net_pnl` for all trades whose **`exit_cme_session_date`** equals that session (Chicago / CME session key, same construction as Wave 0). Apply **after** each session in chronological order.  
- **Qty:** Run at **1, 2, 3** by scaling qty=1 trade `net_pnl` linearly (validated in Wave 0).  
- **Trailing rule (two documented variants):**
  - **A — Pure trailing:** after each session `hwm = max(hwm, equity)`; `allowed_min = hwm − $3,000`; breach if `equity < allowed_min`.
  - **B — Funded-style lock (primary report):** identical until `hwm ≥ starting_balance + $100`; at first crossing, set **`locked_floor = hwm − $3,000`**; thereafter **`allowed_min = locked_floor`** (floor does **not** rise with later highs — “drawdown stops moving up” per common Apex funded interpretation). *Operator may correct interpretation; variants labeled in artifact.*
- **DLL (flag only):** Count sessions where **daily scaled P&amp;L &lt; −$1,000**; **do not** alter equity path for DD (underlying profile).  
- **Outputs per qty:** path max **(allowed_min − equity)** margin stress; sessions with breach; binding session index/date; count of **liquidation/breach** sessions; **DLL-hit** session count; compare to **closed-trade cumulative** |max DD| from Wave 0 (**$2,675 @ qty=1**; **$8,025 @ qty=3**).

**Deliverable 2 — Block bootstrap of max DD (qty=1, closed-trade path)**  
- **Sequence:** 799 closed trades, `net_pnl` at qty=1, **exit-time order**.  
- **Block lengths:** **1, 5, 10** (non-overlapping blocks, concatenate resampled blocks, **truncate to 799** trades).  
- **Resamples:** **10,000**, seed **42**.  
- **Metric:** max drawdown on **closed-trade cumulative** path each resample.  
- **Percentiles:** mean, median, **75th / 90th / 95th / 99th**; full distribution stored in JSON (histogram or sample array summary).  
- **Purpose:** Ground a **percentile-based** margin to replace **1.5×** in a **proposed** (non-binding) revised **R(q)** for operator sign-off.

**Deliverable 3 — Live production audit**  
- **Source:** **Operator-supplied** funded-account data only (no live logs in repo per `docs/ai-project-instructions.md`).  
- **Required:** EOD equity or daily realized P&amp;L since ORB+Opt3 **qty=3** deployment; reconstruct **live EOD trailing** stress vs **Deliverable 1** at qty=3.  
- **STOP if:** any evidence **trailing breach**, **DLL breach**, or **margin within $500** of modeled liquidation — report immediately in artifact and summary.  
- **If no file provided:** document **cannot complete** live comparison; operator must supply or waive.

**Primary output:** `notebooks/validation/` dated markdown + JSON; **RESULT-LOGGED** entry; **proposal only** for revised **R(q)** (no kickoff/working-plan edit until operator accepts + lessons log).

**Date pre-registered:** 2026-05-16  

**Date run completed:** 2026-05-16  

**Result:** RESULT-LOGGED — see follow-up entry (EOD DD vs closed-trade; bootstrap tails; live CSV pending).  

**Artifact:** `notebooks/validation/2026-05-16_wave0b_rq_methodology.md`, `.json`; runner `scripts/run_wave0b_rq_methodology.py`; module `src/quant_research/statistics/apex_eod_trailing.py`  

---

## 2026-05-16 — Wave 0b R(q) methodology investigation — RESULT-LOGGED

**Wave:** Wave 0b (implements pre-registration block above)

**Date run completed:** 2026-05-16

**Execution `git` metadata:** implementation commit `f95fb9fc20ff94d9e941fb210d4970e56375a2ee`; artifact tip (JSON/MD `git_sha` pointer refresh) `3a6eccb` — JSON/Markdown **`git_sha`** field references the **implementation** commit.

**Deliverable 1 — EOD trailing on ORB+Opt3 (2020-01-01 — 2026-04-19, qty 1/2/3)**  
- **Account:** **$50,000** start (same $50K EOD class as Wave 0).  
- **Daily P&L:** Sum of `net_pnl` on **`exit_cme_session_date`**; **779** session rows (**799** closed trades).  
- **Peak-to-trough DD on equity (reported):** At **qty=1**, **$2,675** under both **pure_trailing** and **funded_lock** — matches **closed-trade DD(1)**. At **qty=3**, peak-to-trough remains **$8,025** = **3 × DD(1)** (same as Wave 0 linear scaled closed-trade DD).  
- **Pure vs funded_lock:** **Pure trailing** shows **trailing breach** sessions at qty 2–3 (**125** / **249** sessions); **funded_lock** shows **0** breach sessions at qty≤3 (floor locks early; **min margin to floor** stays positive on the unstopped path). **DLL** session hits (daily P&amp;L &lt; **−$1k**): **4** / **5** / **5** at qty 1/2/3 (path **not** censored for DD).  
- **Stop check (EOD ≪ closed×3):** **Not triggered** — EOD peak-to-trough at q=3 is **not** materially below **$8,025**.

**Deliverable 2 — Block bootstrap max DD (qty=1), 10,000 resamples, seed 42**  
- Block lengths **1, 5, 10**: see JSON percentiles + histograms. **Primary (block=5):** closed-trade max DD **p95 ≈ $4,815**, **p99 ≈ $6,162**; **EOD (funded_lock on collapsed bootstrap path)** matches these nearly exactly (same block construction).  
- **Implication for R(q):** Tail DD at **q=1** already exceeds **$3,000** at **p95** under percentile-style margins built from this strategy alone — **q_max** stays **0** for the illustrative **`max(p95×q, q×EOD_point+500)`** rule unless the percentile or ceiling is relaxed.

**Deliverable 3 — Live audit**  
- **Incomplete:** no operator **`data/wave0b_live_funded_daily.csv`** in-repo (expected path documented in artifact). **No live breach / near-miss assessment** possible without that file.

**Operator flags**  
- **Production vs formal R(q):** Wave 0 **q_max=0** is **not** resolved by switching DD metric to **EOD peak-to-trough** on this log — magnitudes **match** closed-trade scaling. **funded_lock** does change **breach-count semantics** vs a continuously rising trail.  
- **Next step for live:** Operator supplies daily realized P&amp;L (qty=3) CSV → re-run runner; **STOP** logic in script flags breach, DLL, or margin **&lt; $500**.

**Caveat (superseded by Wave 0c — 2026-05-16):** Wave 0b mechanics and Wave 0 eval/trailing text assumed **$3K** trail and **start+$100** lock. That parameterization was **wrong** for the **$50K EOD** class under research (see `docs/lessons-log.md`, **Wave 0c correction**). Do **not** use Wave 0b breach tables as firm-rule evidence; use **Wave 0c** two-gate artifacts instead.

**Artifacts:**  
- `notebooks/validation/2026-05-16_wave0b_rq_methodology.md`  
- `notebooks/validation/2026-05-16_wave0b_rq_methodology.json`  
- `scripts/run_wave0b_rq_methodology.py`  
- `src/quant_research/statistics/apex_eod_trailing.py`  

---

## 2026-05-16 — Wave 0c ORB+Opt3 two-gate re-baseline — PRE-REGISTERED

**Wave:** Wave 0c

**Structural rationale:** Wave 0 / 0b used **incorrect** Apex **$50K EOD** parameters ($3K trail, wrong lock story). Phase 2 must **separate funded survival** from **eval pass rate** and re-grade ORB+Opt3 under **$2K** pre-lock trail, **$52K** lock, **$50K** post-lock floor, **$53K** profit target, **$1K** DLL.

**Specification:**

- **Strategy / protocol:** ORB+Opt3 (same six-year MNQ window and pipeline as Wave 0).
- **Apex simulation (canonical):** `simulate_apex_50k_eod_two_phase` + `simulate_eval_window_50k_eod` in `src/quant_research/statistics/apex_eod_trailing.py`.
- **Deliverable 1 — Two gates:**  
  - **(a) Funded survival:** full-length **session-daily** scaled P&amp;L path; pass = no trailing/post-lock breach and no DLL fail. Report **funded q_max** for **q ∈ {1,2,3,4,5}**.  
  - **(b) Eval pass:** rolling **30-session** windows, advance **1**; trades in window by **exit `cme_session_date`**; **trade-by-trade** path; pass = reach **$53K** before breach/DLL. Report pass rate **per q**.
- **Deliverable 2 — Bootstrap:** **q ∈ {1..5}**, block lengths **5, 20, 50**, **10,000** resamples, RNG **seed = 42 + block_len + q×1000**; survival fraction; margin percentiles **pre-lock** and **post-lock** (post-lock NaN when lock never achieved in replicate).
- **Deliverable 3 — Eval at funded q_max:** pass rate at **funded q_max** only; grading pair **(funded_q_max, eval_pass_rate)**.
- **Deliverable 4 — Graded baseline:** economics at **funded q_max** (annual tier, year profile).
- **Stop:** funded fails **q=1**; eval **0%** all **q**; bootstrap survival **&lt; ~80%** at **funded_q_max**; verify two-phase code before trusting Wave 0b-style breach summaries.

**Date pre-registered:** 2026-05-16  
**Date run completed:** 2026-05-16  
**Result:** *(see RESULT-LOGGED below)*  
**Artifact:** `notebooks/validation/2026-05-17_wave0c_orb_opt3_two_gate_baseline.{md,json}`; `scripts/run_wave0c_orb_opt3_two_gate_baseline.py`

---

## 2026-05-16 — Wave 0c ORB+Opt3 two-gate re-baseline — RESULT-LOGGED

**Wave:** Wave 0c (implements pre-registration above)

**Date run completed:** 2026-05-16

**Verification:** `simulate_apex_50k_eod_two_phase` implements **pre-lock** ``HWM − $2K`` and **post-lock** static **$50K** once **HWM ≥ $52K**. Legacy `simulate_apex_eod_trailing` (**$3K** / **+$100** lock) retained **only** for Wave 0b reproduction.

**STOP / operator flags (this run):**

| Condition | Triggered |
|-----------|-----------|
| Funded survival fails **q=1** | **No** — **q=1** passes |
| Eval pass **0%** for **all** q | **No** |
| Bootstrap funded survival **&lt; ~80%** at **funded q_max** | **Yes** — at **q=1** survival frac **~0.58–0.61** across block lengths (see JSON) |

**Deliverable 1 — Headline**

- **Funded q_max:** **1**. **q ≥ 2** fail **DLL** on the **6y session-daily** path (scaled same-day loss), **not** trailing floor breach (**0** trail breach rows for all **q** in this artifact).  
- **Eval pass rates (30-session windows, 1532 windows):** e.g. **q=1:** **30 / 1532 ≈ 1.96%**; higher **q** yields higher pass rates but **do not** satisfy **Gate A** here.

**Grading conclusion:** **(funded_q_max, eval_pass_rate) = (1, ~1.96%)**.

**Deliverable 4 — Economics at funded q_max (q=1):** ~**$1,014/yr** per contract (same as Wave 0 per-contract totals); **tier:** **below_floor**; **4 / 7** profitable calendar years (2020–2026 slice).

**Caveat (Wave 0d — DLL semantics):** Wave 0c code treated **DLL as terminal** for funded survival and eval failure. Apex **EOD DLL** is a **session pause**, not account termination. The **“q ≥ 2 fail DLL”** headline in this block reflects **incorrect simulation**, not operational firm outcomes — see `docs/research-log.md` **Wave 0d** and `docs/lessons-log.md` (**2026-05-13**). Wave **0c** numeric **artifacts** remain in-repo as **historical** outputs under the bug.

**Artifacts:**  
- `notebooks/validation/2026-05-17_wave0c_orb_opt3_two_gate_baseline.md`  
- `notebooks/validation/2026-05-17_wave0c_orb_opt3_two_gate_baseline.json`  
- `scripts/run_wave0c_orb_opt3_two_gate_baseline.py`

---

## 2026-05-13 — Wave 0d DLL fix + Apex EOD account-class survey — PRE-REGISTERED

**Wave:** Wave 0d

**Structural rationale:** Correct **DLL = session pause** in `apex_eod_trailing.py`; generalize two-phase EOD simulators for all Apex **EOD account classes** in the operator parameter table; quantify whether **larger accounts + higher qty** can satisfy **funded survival**, **bootstrap path robustness**, and **operationally meaningful eval pass rate** jointly.

**Specification:**

- **DLL model:** same **America/New_York** day cumulative realized P&amp;L; on first cross **strictly below −DLL**, apply that fill to equity then **ignore** further same-day P&amp;L; count **DLL pause days**; **do not** fail funded path or eval window on DLL alone; **trailing / post-lock** still fails runs.
- **Generalized API:** `simulate_apex_eod_two_phase`, `simulate_eval_window_eod` with `(starting_balance, trailing_dd, profit_target, dll, lock = start+trail, post_lock_floor = start)`; `$50K` helpers retained.
- **Account rows (operator table — verify vs Apex Help Center):** $25K / $50K / $100K / $150K EOD with **PA max contracts** for funded grid; **eval max contracts** from secondary 4.0 summary for disclosure; eval pass rates computed for **q = 1..PA_cap** (counterfactual above eval cap flagged in JSON).
- **Per class, per q:** (a) funded survival on **6y** session-daily path; (b) **30-session** rolling eval pass (trade-by-trade); (c) block-bootstrap (length **20**, **10,000** reps) funded survival; (d) annual avg P&amp;L at q; (e) avg DLL pause days per year.
- **Summary:** `(funded_q_max, eval@q_max, bootstrap@q_max, annual$@q_max, dll pauses/yr, tier)`.
- **Joint criteria:** funded pass, bootstrap **≥ 80%**, eval **≥ 50%**, maximize avg annual $ — report best or closest misses.
- **Stops:** Wave 0c q=1 funded or eval rate moves **> ~20% relative** vs terminal-DLL baseline; no triple pass; no funded-passing qty reaches **80%** bootstrap in any class.

**Date pre-registered:** 2026-05-13  
**Date run completed:** 2026-05-13 *(see RESULT-LOGGED)*  
**Artifact:** `notebooks/validation/2026-05-13_wave0d_orb_opt3_account_class_survey.{md,json}`; `scripts/run_wave0d_orb_opt3_account_class_survey.py`; code **`77f35f0`** (DLL fix).

---

## 2026-05-13 — Wave 0d DLL fix + Apex EOD account-class survey — RESULT-LOGGED

**Status:** Numeric results **obsolete** for PA contract limits, TDD rows, and **tier-DLL** modeling — see **`docs/research-log.md` Wave 0e** (2026-05-17).

**Wave:** Wave 0d

**Date run completed:** 2026-05-13

**Execution `git` metadata:** Survey **run** captured ``git_sha`` = **`17dde52`** (tree before artifact commit). **Artifact files** committed as **`85d5cae`**; research-log pointers updated in **`df67b87`**.

**Deliverable 1 — Parameter verification:** JSON `verification` records operator simulation row + **deltas vs third-party 4.0 blog tables** (trailing DD and PA contract caps **disagree** on several tiers — **requires** confirmation on [Apex Help Center](https://apextraderfunding.com/help-center/)).

**Deliverable 2 — Code:** `simulate_apex_eod_two_phase`, `simulate_eval_window_eod`, tests in `tests/test_apex_eod_trailing.py`; `dll_terminates_run` preserves pre-fix behavior for regression.

**Wave 0c regression ($50K, q=1, historical path):** **Terminal vs pause:** both **funded survive**; eval passes **30 / 1532** both — **no** **>20%** eval rate change (**STOP** not triggered for magnitude).

**Headline survey (ORB+Opt3, DLL pause, operator PA caps):**

| Class | funded_q_max | eval @ q_max | bootstrap @ q_max | ~$/yr @ q_max | DLL pauses/yr @ q_max | tier @ q_max |
|-------|-------------|--------------|-------------------|---------------|------------------------|--------------|
| $25K | 4 | ~32.8% | ~0.18 | ~$4,057 | ~24.8 | below_floor |
| $50K | 7 | ~24.2% | ~0.17 | ~$7,099 | ~20.2 | below_floor |
| $100K | 9 | ~14.8% | ~0.17 | ~$9,127 | ~1.0 | below_floor |
| $150K | 11 | ~8.2% | ~0.15 | ~$11,156 | ~1.0 | below_floor |

**Joint criteria (funded + bootstrap ≥ 80% + eval ≥ 50%):** **No** **(class, qty)** pair satisfied all three gates in this run.

**STOP flags:** **Triple gate:** no pass; **Bootstrap ≥ 80%:** no funded-passing qty in any class met **80%** block-20 survival; **Wave 0c material regression:** **false** on headline q=1 check.

**Artifacts:**  
- `notebooks/validation/2026-05-13_wave0d_orb_opt3_account_class_survey.{md,json}`  
- `notebooks/validation/2026-05-13_wave0d_account_class_survey.ipynb`  
- `scripts/run_wave0d_orb_opt3_account_class_survey.py`

**Caveat (Wave 0e — 2026-05-17):** Wave **0d** numeric survey and parameter rows are **obsolete** for firm-rule conclusions. Operator confirmed **May 2026** Apex tables: **correct TDD / eval+PA contract limits**, **PA tiers** = **maximum** mini contracts and **tiered DLL** from **prior session EOD** equity (strategy target qty capped per tier; **1 mini = 10 MNQ** in ORB+Opt3 research convention). Re-stated survey: **`docs/research-log.md` Wave 0e** + `notebooks/validation/2026-05-17_wave0e_orb_opt3_survey.{md,json}`.

---

## 2026-05-17 — Wave 0e — Tiered PA rules + bootstrap diagnosis + survey — PRE-REGISTERED

**Wave:** Wave 0e

**Structural rationale:** Wave **0d** combined **DLL session-pause** with an **incorrect** static PA parameterization (wrong PA/eval caps and TDD on several classes) and **no** modeling of **PA balance-tier** DLL / effective contract caps. Wave **0e** corrects the **two-phase simulator** (`lock = start + TDD`, post-lock floor = start), adds **tier-aware** effective MNQ qty (Apex **max mini × 10** vs target MNQ), **tiered DLL**, **demotion** on lower EOD tier, tracking of tier transitions and DLL pauses per tier; keeps `simulate_apex_50k_eod_two_phase` for flat replay. **Diagnoses** Wave **0d** block-20 **~17–18%** bootstrap survival on $50K q=1 (2023 trade-count conditional rates, block-1 vs block-20 gap). **Re-runs** account-class survey on verified tier tables with operator target/sweep MNQ grids; **joint gates**: funded 6y survival, bootstrap **≥ 80%** (block 20, 10k), eval **≥ 50%** (30 **calendar-day** windows), annual P&L vs **$36K / $60K / $100K** tiers.

**Specification (summary):**

- **Deliverable 1 — Simulator:** `simulate_apex_eod_two_phase` tiered mode: `balance_tiers` list `{min_balance, max_balance, max_contracts_mini, dll}`; `effective_mnq = min(target_qty_mnq, max_contracts_mini × mnq_per_mini)`; lock at **`lock_equity_threshold`** = start + TDD (no +$100); DLL pause (default); tier from **prior EOD** before each session; **tier_summary** in result.
- **Deliverable 2 — Bootstrap diagnosis:** $50K **flat** `simulate_apex_50k_eod_two_phase` at **q=1 MNQ**, `block_length=20` vs **1**, **10,000** resamples; per replicate: 2023 trade count, survival, max DD proxy, annual P&L; compare count distribution to expectation; conditional survival when |2023 count − expected| ≤ **10%**; classify **(i)** fragility vs **(ii)** resampling artifact; **proposed** stratified / no-replacement revision **not** implemented pending operator approval.
- **Deliverable 3 — Survey:** Four EOD classes; target MNQ grids: 25K **10,15,20**; 50K **20–40** sweep; 100K **30–60**; 150K **40–100**; funded tier sim on 6y ORB+Opt3; eval qty = min(target, eval mini cap × 10); eval DLL from tier at **starting** equity; bootstrap tiered `block_bootstrap_apex_eod_tiered_funded`.
- **Deliverable 4 — Joint gates:** As in Wave 0d triple gate + economics; best passing combo by annual P&L or closest misses.
- **Stops:** If diagnosis **(ii)** with strong bias → pause survey (not triggered by pre-defined flag alone); if **no** funded survival on 6y for any pair → escalate **strategy vs Apex EOD** framing; if **no** triple pass → primary Wave 1 finding.

**Date pre-registered:** 2026-05-17  

**Date run completed:** *(see RESULT-LOGGED below)*  

**Artifact:** *(pending in PRE block)*  

---

## 2026-05-17 — Wave 0e — Tiered PA rules + bootstrap diagnosis + survey — RESULT-LOGGED

**Wave:** Wave 0e (implements pre-registration above)

**Date run completed:** 2026-05-17

**Execution `git` metadata:** artifact `git_sha` = **`75c84e5ae8ce1edc1d19e4c0788144dc5f6dff7d`** (**`git_dirty`: true** at write).

**Deliverable 1 — Code:** `simulate_apex_eod_two_phase` tiered path; `apex_tier_index_for_equity` handles equity **below** bottom published band and **gaps** between bands (conservative lower band); `block_bootstrap_apex_eod_tiered_funded`; `eval_pass_rate_calendar_days`; `diagnose_block_bootstrap_flat_funded_path`; tests in `tests/test_apex_eod_trailing.py`.

**Deliverable 2 — Bootstrap diagnosis ($50K flat q=1, ORB+Opt3 799 trades, seed 42 / 43):**

| Metric | Block 20 | Block 1 (iid trades) |
|--------|----------|----------------------|
| Unconditional funded survival | **0.5791** | **0.5878** |
| Conditional survival (\|2023 count − expected\| ≤ 10%) | **~0.5818** | **~0.5901** |
| 2023 trade-count mean (expected **223**) | **223.0** (sd **55.7**) | **222.8** (sd **12.5**) |

**Gap (20 − 1):** **−0.0087** — block-20 **does not** raise survival vs iid; **low** Wave 0d **~17–18%** headline is **not reproduced** here under corrected flat $50K sim — this run’s **~58%** reflects **updated trail/TDD** and/or path definition vs the obsolete 0d parameter mix. **`methodology_bias_flag`:** **false** (conditional ≈ unconditional; no strong 2023-overweight artifact by pre-specified rule).

**Diagnosis (pre-specified labels):** Primarily **(i) path / rule fragility signal** at **~58%** survival under current bootstrap — **not** **(ii)** resampling bias per coarse flags. (Wave 0d’s lower number is **not comparable** — obsolete parameters.)

**Deliverable 3–4 — Survey (tiered PA, May 2026 operator tables):**

- **Funded survival (6y tiered sim):** **no** **(account_class, target_qty_mnq)** pair **survived** (`stop_conditions.funded_survival_any_pair`: **false**) — **severity upgrade** vs Wave 0d headline “high q_max”; **tier caps + corrected rules** eliminate naive high-q funded survival on this log.
- **Joint gates (funded + bootstrap ≥ 80% + eval ≥ 50%):** **none**.
- **Operator STOP (survey):** Not triggered — diagnosis did **not** mandate pause before survey on methodology-artifact rule.

**Mechanism vs Wave 0d (explicit):** Wave **0d** **inflated** funded `q_max` by **wrong PA/DLL/TDD** and treating **tier ceilings** as compatible with **static high DLL** assumptions. Wave **0e** ties **DLL and qty cap** to **tier from EOD equity** and **start + TDD lock** — historical ORB+Opt3 path **fails** funded survival for **all** surveyed sizes.

**Artifacts:**  
- `notebooks/validation/2026-05-17_wave0e_orb_opt3_survey.{md,json}`  
- `notebooks/validation/2026-05-17_wave0e_orb_opt3_survey.ipynb`  
- `scripts/run_wave0e_orb_opt3_survey.py`

---

## 2026-05-17 — Wave 0f — ORB+Opt3 failure profile + low-qty sweep — PRE-REGISTERED

**Wave:** Wave 0f

**Structural rationale:** Wave **0e** showed **no** funded survival at tier-ceiling-and-above target MNQ under corrected Apex tier rules. Before Wave **1** “strategy repairs,” pre-register **failure profiling** (which sessions/modes/year concentration) and a **sub–tier-1-ceiling** MNQ sweep to map the **lower** survivability surface against joint gates.

**Specification (summary):**

- **D1 — Failure enumeration:** For each **Wave 0e** **(account_class, target_qty_mnq)** pair, session-level tiered trace: first trailing-breach session, pre- vs post-lock, margins, tier, single-day vs DLL-heavy erosion heuristic, DLL pauses before breach.
- **D2 — Loss distribution:** Per pair, full-session P&L distribution, worst 10/25/50 sessions, DLL-pause counts **by tier index**.
- **D3 — Year attribution:** P&L, DLL pauses, tier time, failure year, demotion years; concentration vs spread across years.
- **D4 — Low-qty sweep:** Per class, MNQ grid from **1** (or **5** / **10** min where stated) up to **tier-1 ceiling**: 25K **1,2,3,5,7,10**; 50K **1,2,5,10,15,20**; 100K **5,10,…,30**; 150K **10,…,40**. Each row: tiered funded sim, **30d** calendar eval, block-20 bootstrap **10k**, annual P&L, triple gate. Report lowest qty with funded pass; lowest with **all** gates; best economics among triple passes; gate failure histogram; gap to **$36K/yr** among near-misses.
- **D5 — Diagnosis:** Binding mode, year concentration, min survivable qty + $/yr, likely repair lever.
- **Stops:** $50K **q=1** funded fail → incompatible at any size; survivable qty with **&lt;$5K/yr** everywhere → operationally negligible; bootstrap **&lt;80%** when funded passes → fragility.

**Date pre-registered:** 2026-05-17  

**Date run completed:** 2026-05-17  

**Artifact:** `notebooks/validation/2026-05-17_wave0f_orb_opt3_failure_profile.{md,json}`; `scripts/run_wave0f_orb_opt3_failure_profile.py`  

---

## 2026-05-17 — Wave 0f — ORB+Opt3 failure profile + low-qty sweep — RESULT-LOGGED

**Wave:** Wave 0f (implements pre-registration above)

**Date run completed:** 2026-05-17

**Execution `git` metadata:** `git_sha` = **`75c84e5ae8ce1edc1d19e4c0788144dc5f6dff7d`** (**dirty** at artifact write).

**Deliverable 1–3 (Wave 0e 19 pairs):**

- **Primary failure mode (first breach):** **trailing_breach_pre_lock** on **all 19** pairs (post-lock not the first hit at these sizes).
- **Heuristic tail shape:** **`lean_single_catastrophic_session`** on **all 19** (first breach session loss large vs class **TDD**; DLL pauses before breach typically small — see JSON per pair).
- **Year concentration:** **First breach calendar year** — **2020** for **all 19** (early-window concentration **not** 2023-driven for this qty grid).

**Deliverable 4 (low-qty sweep, 25 configurations):**

- **$50K @ 1 MNQ funded survival:** **True** → **STOP “incompatible at any size”** is **false**.
- **Lowest qty with funded survival:** **25K & 50K — 1 MNQ** (~**$1,014/yr** est.); **100K — 5 MNQ** (~**$5,071/yr**); **150K — 10 MNQ** (~**$10,142/yr**).
- **Triple gate (funded + bootstrap ≥ 80% + eval ≥ 50%):** **none** in sweep.
- **Gate histogram (first failing gate among funded-pass vs not):** **funded** failures **15**; among **10** funded-pass rows, **all** fail **bootstrap** next (**10**); **eval** **0** as first fail among rows that passed funded + bootstrap (**none** passed both).
- **Operator STOP (~$5K/yr):** **25K / 50K** lowest survivable tier ≈ **$1K/yr** — **“survival possible but economically negligible”** at min size **without** strategy change; **100K/150K** min survivable **above** **$5K** but still **far** below **$36K** floor tier.

**Deliverable 5 — Synthesis:**

- **(a) Binding failure mode (high Wave 0e qty):** **Pre-lock trailing breach**, dominated by **large single-session loss** relative to trail in the profiled window (not DLL-cumulative-dominant by heuristic).
- **(b) Regime concentration:** **2020** first-breach year for **all** Wave 0e pairs — failures **not** “all 2023” on this diagnostic.
- **(c) Min survivable qty:** See Deliverable 4 table; **$50K** survives at **q=1**.
- **(d) Repair levers:** **Sub-ceiling qty** restores **funded** survival but **bootstrap** stays **&lt;80%** here → **path hardening** (stops / tail / regime filter) before sizing up; year concentration in **2020** supports **evaluating regime gating** but **not** as a 2023-only narrative.

**Artifacts:**  
- `notebooks/validation/2026-05-17_wave0f_orb_opt3_failure_profile.{md,json}`  
- `scripts/run_wave0f_orb_opt3_failure_profile.py`  
- `simulate_apex_eod_two_phase_tiered_with_trace` in `src/quant_research/statistics/apex_eod_trailing.py`  

---

## 2026-05-17 — Wave 0g — 2020 data sanity + breach-session characterization + 2020-excluded survival re-grade — PRE-REGISTERED

**Wave:** Wave 0g

**Structural rationale:** Wave **0f** showed all **19** Wave **0e** funded-survival failures are **lean single catastrophic session, pre-lock breach**, with **first breach year = 2020** (not 2023-centric). Before Phase **3** regime-overlay design, **isolate whether 2020 is a data artifact**, **characterize the breaching sessions** for later overlay features, and **re-grade** ORB+Opt3 on a **2020-excluded** trade log to test viability under **non-COVID** conditions. **Phase 2 discipline:** diagnostics + re-grade only — **no** regime filter implementation and **no** strategy changes.

**Specification:**

- **Protocol / log:** Same six-year ORB+Opt3 MNQ trade log construction as Waves **0e** / **0f** (qty=1 path, `LatestEntryHourET=11`, continuous contract, segment split at operator export gaps).
- **Deliverable 1 — Trade log sanity vs raw MNQ:**
  - (a) Trades per **calendar year** (reporting key aligned to implementation: **`exit_cme_session_date` year**).
  - (b) **Unique `count(cme_session_date)`** per calendar year from **RTH** bars in the protocol window.
  - (c) Ratio **trades / sessions** per year; compare **2020** to other years (expected ballpark **~0.3–0.7** for this filter); flag **material mismatch** vs peer years.
  - (d) **Unexpected** missing **RTH** session days in **2020** via continuous-contract calendar classification; **known** gaps (**2024-06-18–2024-07-31**, **2026-02-03–2026-03-11**) must **not** spuriously implicate **2020** undocumentedly.
  - (e) **2020 monthly** trade count distribution; note **Feb–Apr** anomalies if present.
  - **STOP:** If **2020** shows undocumented gaps, implausible trade counts, or ratio mismatch indicating incomplete **2020** data, **do not** proceed to D2–D4 — “2020 drives failures” may be artifact.
- **Deliverable 2 — 2020 failure-session characterization:** For each of the **19** Wave **0e** pairs, take **first pre-lock breach session** (Wave **0f** enumeration); **de-duplicate** by calendar date. For each unique session, join bars and report: session / CME dates, session P&amp;L (per-MNQ), prior EOD balance / HWM, **margin to floor** at session open, trade count, stop type, stop time vs session open, ORB H/L and range ($), prior **ATR14** (RTH), overnight gap, full-session range, **range/ATR**, DOW, DOY. **Aggregate:** month/week concentration within **2020** vs Feb–Apr COVID window; common **signature** (ATR, gap, range/ATR) for Phase **3** framing — **2020 exclusion semantics** documented for operators.
- **Deliverable 3 — 2020-excluded survival re-grade:** Remove trades with **`exit_ny_date` calendar year == 2020**. Confirm count drop ~proportional to **2020** share of six-year total. For **each** **(account_class, target_qty_mnq)** in Wave **0e** grid **and** Wave **0f** D4 low-qty sweep (**dedupe** `(class, qty)`):
  - Tiered Apex **funded** survival on excluded log.
  - **Bootstrap** funded survival (**block length 20**, **10000** resamples) on **2020-excluded** population only.
  - **Eval** pass rate (rolling-window sim, inherited convention).
  - **Annual P&amp;L** estimate (protocol year-fraction on excluded window).
  - **Joint gates:** funded **pass** + bootstrap **≥ 80%** + eval **≥ 50%**.
  - Compare to **six-year** Wave **0e** rows: configs moving **fail → pass**; for passes report **$/yr** and tier vs **$36K / $60K / $100K**; for failures report **binding** gate.
- **Deliverable 4 — Operator diagnosis:** (a) **2020** log integrity yes/no. (b) **Regime signature** of breach sessions and realtime-identifiability (ATR, gap, range/ATR). (c–e) **2020-excluded** joint pass and best config / economics, or dominant failure mode if none.
- **Additional STOP / surface rules (post-run):** If **every** configuration **fails funded** on excluded log → surface **fragility beyond 2020**. If joint pass but best **$/yr** **≪** Phase **2** economics floor → surface. If joint pass with **meaningful $/yr** (e.g. **&gt;~$20K/yr** on some row) → document as candidate Wave **1** baseline under Frame **B**.

**Date pre-registered:** 2026-05-17

**Date run completed:** 2026-05-17  

**Artifact:** `notebooks/validation/2026-05-17_wave0g_orb_opt3_2020_exclusion.{md,json}`; `scripts/run_wave0g_orb_opt3_2020_exclusion.py`  

---

## 2026-05-17 — Wave 0g — 2020 data sanity + breach-session characterization + 2020-excluded survival re-grade — RESULT-LOGGED

**Wave:** Wave 0g (implements pre-registration above)

**Date run completed:** 2026-05-17

**Execution `git` metadata:** `git_sha` = **`75c84e5ae8ce1edc1d19e4c0788144dc5f6dff7d`** (**dirty** at artifact write).

**Deliverable 1 (sanity):**

- **STOP (skip D2–D4):** **False** — proceed.
- **2020** trades (exit **`cme_session_date`** year): **165**; RTH **sessions** in **2020:** **258**; **ratio ≈ 0.64** vs **median ~0.49** other years (excl. **2021** — see note) → **not** flagged as ratio anomaly vs peers.
- **Unexpected missing RTH days in 2020:** **0**; **known** gaps ∩ **2020** calendar: **empty**.
- **2021** shows **0** closed trades in this log while RTH bars exist — documented as **strategy / filter** behavior, not a raw **2020** integrity issue.
- **2020** monthly trade counts (exit **NY** date) are **roughly uniform (~15–21/mo)** in JSON — **no** single-month **“few or many”** spike tied to Feb–Apr in this aggregation key.

**Deliverable 2 (breach characterization):**

- **Unique first-breach NY dates (Wave 0e × Wave 0f enumeration):** **2** — **2020-01-14**, **2020-01-15** (early January, **not** Feb–Apr COVID cluster).
- **Coarse signature (from bar-backed diagnostics in artifact):** **orb_exit_stop** exits; intraday **range / prior ATR** **≈ 0.6–0.9** (not **range ≫ ATR** outliers on sampled days); **Phase 3** regime overlay still **deferred**.

**Deliverable 3 (2020-excluded re-grade):**

- **Exclusion:** drop **`exit_ny_date.year == 2020`**; **799 → 634** trades (**~20.7%** removed), in line with **2020** share.
- **Configs swept:** **40** (**19** Wave **0e** + **21** additional low-qty Wave **0f** rows, deduped).
- **Funded survival (2020-excluded):** **0 / 40** — **`any_funded_survival_excl`: false** (`stop_every_configuration_fails_funded_survival`: **true** per pre-registered surface rule).
- **First-failing gate histogram (2020-excluded sweep):** **`funded`: 40** (all fail before bootstrap/eval binding).
- **Joint triple-pass (funded + bootstrap ≥ 80% + eval ≥ 50%):** **none** (`joint_gate_passing_configs`: **[]**); **no** configs **newly** passing joint vs six-year Wave **0e** comparison.

**Deliverable 4 (operator framing):**

- **(a)** Six-year log **2020** integrity: **confirmed** under scripted checks — failures on **2020** dates are **not** attributed here to undocumented **2020** bar gaps.
- **(b)** Breach sessions: **early Jan 2020**, **stop-out** profile; **range/ATR** **moderate** on sampled days — **not** a simple “only gap/ATR monsters” story from these two days alone; realtime overlay **TBD** Phase **3**.
- **(c–e)** **No** configuration passes **joint gates** on the **2020-excluded** log; **funded** fails **universally** on the **2021–2026** subset — fragility is **not** explained away by dropping **2020**. ORB+Opt3 **Phase 2** effort should assume **path / tail** work remains **binding** unless strategy or rules change; **Frame B** “Wave **1** baseline from joint-pass **2020-excluded**” is **not** supported by this run.

**Artifacts:**  
- `notebooks/validation/2026-05-17_wave0g_orb_opt3_2020_exclusion.{md,json}`  
- `scripts/run_wave0g_orb_opt3_2020_exclusion.py`  

---

## 2026-05-17 — Wave 0h — ORB+Opt3 chapter close-out + Phase 2 reframe (new-strategy search) — PRE-REGISTERED

**Wave:** Wave 0h

**Structural rationale:** Waves **0a–0g** establish that **ORB+Opt3** does **not** clear **joint** Apex EOD gates at sizes tested; failure mode is **pre-lock** single-session loss at scale and **bootstrap** fragility even when **funded** survives at small qty. **Operator decision:** close **ORB+Opt3 repair** within Phase **2**; reframe active work as **new-strategy search** per `docs/program-charter.md` (acceptable outcomes include **other approaches** discovered during research). This wave documents that decision with a **per-session loss tail** diagnostic vs class **TDD**, consolidated close-out prose, and kickoff / working-plan updates.

**Specification:**

- **D1 — Per-session loss distribution (qty=1 MNQ, six-year protocol trade log):**
  - (a) Aggregate **realized** P&amp;L by **`exit_ny_date`** (sum `net_pnl`).
  - (b) On **losing** sessions: count; mean/median loss; **75/90/95/99** percentiles of **absolute** loss; maximum single-session loss; **40-bin** histogram.
  - (c) **Tail multiples** (e.g. p99 \|loss\| / median \|loss\| among losers).
  - (d) **Apex comparison:** per account class (**25k / 50k / 100k / 150k**), report **TDD** (pre-lock trailing), **profit target** dollars, **margin to trailing floor** at open / textbook pre-lock peak (both = **TDD** under two-phase rules), percentiles of **absolute** session loss as **% of TDD**; repeat for illustrative **qty** **2, 5, 10** under linear scaling of the per-MNQ loss distribution.
  - (e) **Back-of-envelope** proportional **stop** narrowing to bring **p99** **absolute** loss ≤ **50% TDD** at qty=1 (**no** WR/path model); report implied **%** stop reduction when factor **&lt; 1**.
  - **STOP surface:** If **p99** abs loss at **MNQ=1** **≤** half **$50K** TDD, **document** — suggests unit-scale tail is **not** extreme vs that buffer (possible **stop-distance** revisit nuance) even if prior waves failed **joint** gates at higher qty.
- **D2 — Close-out doc:** `docs/orb_opt3_phase2_closeout.md` (waves 0a–0h summary, structural conclusion, ruled out / not explored, production status).
- **D3 — Phase 2 reframe:** Update **`docs/phase-2-kickoff.md`** and **`docs/current-working-plan.md`**: baseline is **not** “ORB must survive”; success = **at least one** strategy passing **funded + bootstrap ≥ 80% + eval ≥ 50%** + **≥ $36K/yr** (floor tier); Wave **0** graded ORB remains implicit **$0** joint-pass floor.
- **D4 — Wave 1 operator agenda** in artifact JSON (strategy families, Apex screens, frequency floor, instruments) — **not** answered by implementation.

**Date pre-registered:** 2026-05-17  

**Date run completed:** 2026-05-17  

**Artifact:** `notebooks/validation/2026-05-17_wave0h_orb_opt3_chapter_closeout.{md,json}`; `scripts/run_wave0h_orb_opt3_chapter_closeout.py`; `docs/orb_opt3_phase2_closeout.md`  

---

## 2026-05-17 — Wave 0h — ORB+Opt3 chapter close-out + Phase 2 reframe — RESULT-LOGGED

**Wave:** Wave 0h (implements pre-registration above)

**Date run completed:** 2026-05-17

**Execution `git` metadata:** `git_sha` = **`75c84e5ae8ce1edc1d19e4c0788144dc5f6dff7d`** (**dirty** at artifact write).

**Deliverable 1 (session loss tail, MNQ=1):**

- **Unique `exit_ny_date` with trades:** **779**; **losing sessions:** **272**; **max trades / NY day:** **6** (**15** NY days multi-trade).
- **Median** session P&amp;L (losers): **−$136.50**; **median \|loss\|:** **$136.50**; **p99 \|loss\|:** **~$520**; **worst** session: **−$789.50**; **p99 / median \|loss\|:** **~3.8×**.
- **$50K TDD** = **$2,000** → **p99** abs loss **~26%** of TDD at **MNQ=1**; at **10 MNQ** linear scaling → **p99 ~$5,198** (**~260%** of TDD).
- **STOP surface (pre-registered):** **True** — **p99 ≤** half **$50K** TDD (**$1,000**). **Interpretation:** unit-scale **percentile** tail is **moderate** vs **$50K** buffer; **joint-gate** failure remains explained by **qty**, **worst-day** mass (max **−$790** at qty=1), **path/bootstrap**, and **eval** — not by p99 alone. **Operator still closes** ORB repair; nuance **on record** for **Wave 1** screening.
- **$25K:** p99 **~52%** of **$1K** TDD — **above** half-TDD; back-of-envelope **~3.8%** linear stop tighten to hit **50% TDD** cap on p99.

**Deliverable 2–4:** See **`docs/orb_opt3_phase2_closeout.md`** (narrative), JSON **`deliverable_4_wave1_operator_agenda`**, and updates to **`docs/phase-2-kickoff.md`** / **`docs/current-working-plan.md`**.

**Artifacts:**  
- `notebooks/validation/2026-05-17_wave0h_orb_opt3_chapter_closeout.{md,json}`  
- `scripts/run_wave0h_orb_opt3_chapter_closeout.py`  
- `docs/orb_opt3_phase2_closeout.md`  

---

## 2026-05-26 — Wave 1 Stage 1 Track 1 — quant hypotheses (N=7) — PRE-REGISTERED

**Wave:** Wave 1  
**Status:** PRE-REGISTERED (spec fixed before screening code run; **Track 2** ICT batch is separate / later).  
**Structural bundle:** First **quant-derived** coarse screen under Phase 2 joint-gate *discipline* adapted to a **fast kill** layer (DLL-style per-session cap + frequency + WR + R:R + year stability), **not** full funded + bootstrap + eval until Stage 2+.  

**Protocol / data**

- **Execution instrument:** **MNQ** only (Phase 2 **M8** MNQ scope); **cross-features** from **ES** and **RTY** permitted for **H8**, **H9**, **H10** when tape exists.  
- **Loader extension:** `quant_research.data.data_loader` exposes `ES_CONTRACT_GLOB` / `RTY_CONTRACT_GLOB`; `quant_research.research_wave1.instrument_pipeline.load_continuous_rth_mnq_style` stitches **any** `*.Last.txt` band to RTH + `cme_session_date` like MNQ.  
- **Evaluation window:** calendar **2021-01-01** – **2025-12-31** (Frame B: **2020 excluded**); gates use exit-date year in **America/New_York** where daily attribution applies.  
- **Segmentation:** `split_dataframe_at_operator_export_gaps` on MNQ (fresh path per segment — no positions across known export holes).  
- **Simplifications (Stage 1 coarse):** **$0** commission/slippage; minute-bar **pessimistic** stop vs target when both touch; **H8** macro calendar filter omitted if no calendar data (**documented**).  

**Hypotheses (operational specs — summary; full detail in operator charter for this track)**

| ID | Idea (short) | Parameter sweep |
|----|----------------|-----------------|
| **H1** | Opening-drive exhaustion after large normalized OR; fade; stop extreme+2; target 50% retrace; time exit RTH; 1 trade/session | **X** ∈ {8, 10, 12} pts |
| **H2** | Lunch (11:30–13:30 **ET**) VWAP ± 1.5× morning ATR fade; target VWAP; time 13:30 | stop **8 / 10 / 12** pts |
| **H8** | ES–NQ % divergence &gt; **0.3%** &gt; **15** min; fade leader on **MNQ**; stop **8–10**; target ½ gap closure; ≤2 trades/session | stop **8 / 10** |
| **H9** | NQ flat 20m (**0.2%** range); RTY impulse **&gt;0.3%** → directional MNQ entry; stop NQ flat range opp side; tgt **1.5×** range; 30m time | — |
| **H10** | ES level touch + 5m rejection; MNQ direction with ES; stop NQ 30m extreme; tgt prior NQ swing; ≤2/session; ES 10pt “clean” filter | — |
| **H11** | 15m OR (**09:30–09:45 ET**) + 5m close breakout **09:45–10:30**; tgt **1×** range; time **11:00** | — |
| **H12** | Weekly midpoint (**Mon–Thu** path); Wed/Thu only; **&gt;20** pts + **30** min extension + **5m** rejection **&gt;30%** retracement toward mid | — |

**Screening gates (binary; SURVIVE = all pass)**

1. **Per-session worst loss (DLL-style screening):** `qty_design = round( $30k / avg_annual_pnl_usd @ MNQ=1 )` (min **1** if positive annual); if **avg annual ≤ 0** → **fail**. **Pass** if worst CME-session sum of scaled `net_pnl` at `qty_design` is **&gt; −$1,000** (strictly better than **−$1k** one-session loss).  
2. **Frequency:** average **closed trades / calendar week** over **2021–2025** ≥ **3**.  
3. **Win rate:** ≥ **60%** on non-zero closed trades (years filter).  
4. **R:R:** `avg_win / avg_loss` ∈ **[0.8, 1.5]** (loss as positive magnitude).  
5. **Years:** **&gt;0** P&amp;L in **≥4** of **2021–2025** (strictly profitable years).  

**Statistics (pre-registered for this track)**

- **Sharpe (reporting):** **daily** realized USD P&amp;L at **qty=1**, **sqrt(252)** — document trade-level alternative in artifact.  
- **Deflated Sharpe:** **N = 7** hypotheses; trial SR vector uses **0** substitution **only** for Var(SR̂) across trials when a trial SR is undefined; per-hypothesis **PSR/DSR** omitted if no daily series.  
- **Bootstrap:** **circular block** length **20** sessions on session P&amp;L sums; **1000** resamples; **95% CI** on **mean annual** P&amp;L proxy (total / 5); **flag** if CI crosses **0** for any **SURVIVE**.  

**Date pre-registered:** 2026-05-26  

---

## 2026-05-26 — Wave 1 Stage 1 Track 1 — RESULT-LOGGED

**Wave:** Wave 1 (implements PRE-REGISTERED block above)  
**Date run completed:** 2026-05-26  

**Execution `git` metadata:** `git_sha` = **`75c84e5ae8ce1edc1d19e4c0788144dc5f6dff7d`** (workspace **dirty** at run — see local `git status` for tip commit at archival time).  

**Data / pipeline**

- **MNQ:** loaded; **4** gap-split segments in **2021–2025** window.  
- **ES / RTY:** **0** files matching `ES *.Last.txt` and `RTY *.Last.txt` under `data/raw/` → **H8** (needs ES), **H9** (needs RTY), **H10** (needs ES) **blocked** (no cross-instrument sim). Economic-calendar filter for **H8** **not** applied (pre-registered fallback).  

**Survivors (all 5 gates):** **NONE**  

**Per-hypothesis (best sweep where applicable)**

| ID | Selected variant | Outcome | Primary gate failure(s) |
|----|------------------|---------|-------------------------|
| H1 | **X=12** | KILLED | **G1** (negative mean annual @ qty=1); **G2**; **G3**; **G4**; **G5** |
| H2 | **stop=12** | KILLED | **G1**; **G3**; **G4**; **G5** (**G2** pass) |
| H8 | — | KILLED / **BLOCKED** | No ES tape (+ **G1–G5** degenerate on empty log) |
| H9 | — | KILLED / **BLOCKED** | No RTY tape |
| H10 | — | KILLED / **BLOCKED** | No ES tape |
| H11 | — | KILLED | **G1** only — passes **G2–G5** (notable: **~62%** WR, R:R in band, **5/5** profitable years at qty=1; **worst session ~−$1,272** at **qty=3** $30K/yr heuristic vs **$1k** screen) |
| H12 | — | KILLED | **G1** (tail at sized qty), **G2**, **G3**, **G4** (**G5** pass) |

**Deflated Sharpe (N=7):** Large across-trial SR variance (negative H1/H2 vs positive H11/H12); **expected_max_SR** under null ≈ **3.92**; **H11/H12** PSR vs that benchmark **≈1** — multiple-testing mass is **material**, but **does not rescue** **H11** because **Gate 1** fails on session tail at economics.  

**Bootstrap (mean annual, qty=1):** **H11** / **H12** CIs **exclude 0** (edge **not** weak on this axis); still **killed** on other gates / **G1**.  

**STOP surfaces (pre-registered)**

- **All seven killed** at Stage 1 coarse screen → Phase 2 search leans on **Track 2 (ICT)** and/or **new quant families** until one clears gates.  
- **ES/RTY export** required to **unblock** **H8–H10** re-runs.  

**Artifacts:**  
- `notebooks/validation/2026-05-26_wave1_stage1_track1_quant_screen.md`  
- `notebooks/validation/2026-05-26_wave1_stage1_track1_quant_screen.json`  
- `scripts/run_wave1_stage1_track1_screening.py`  
- Code: `src/quant_research/research_wave1/` (sims + metrics + instrument pipeline), `src/quant_research/data/data_loader.py` (ES/RTY globs)  

---

## 2026-05-29 — Wave 1 Stage 1 Track 1b — H8b MES–MNQ divergence — PRE-REGISTERED

**Wave:** Wave 1 (Track **1b** extension — cross-instrument batch)  
**Status:** PRE-REGISTERED (spec fixed before screening run; **H9/H10 deferred** until RTY export).  
**Supersedes:** Track 1 **H8** (“fade the leader”) — **not executed**; replaced by **H8b** below.

**Protocol / data**

- **Execution instrument:** **MNQ**; cross-feature **MES** (micro ES — operator export under `data/raw/mes/`).  
- **Loader:** `MES_CONTRACT_GLOB = "mes/MES *.Last.txt"`, `MNQ_CONTRACT_GLOB = "mnq/MNQ *.Last.txt"`; continuous contract + RTH + `cme_session_date` via `instrument_pipeline.load_continuous_rth_mnq_style`.  
- **Evaluation window:** calendar **2021-01-01** – **2025-12-31** (Frame B: **2020 excluded**); exit **America/New_York** date convention (same as Track 1).  
- **Segmentation:** MNQ `split_dataframe_at_operator_export_gaps`; MES filtered to segment session dates; **inner join** on timestamp (sessions without aligned MES bars excluded).  
- **Macro calendar filter:** omitted (no FOMC/NFP/CPI calendar — same fallback as Track 1).  
- **Data coverage (pre-run inventory):** MES **26** contract files; RTH first bar **2020-01-02** CT (not materially post-2020); last bar **2026-05-26**. MES **covers** operator-known MNQ export holes **Jun–Jul 2024** and **Feb–Mar 2026** but MNQ execution still absent on those days. **MES-only unexpected missing days in 2021–2025 eval window** surfaced (Apr 2023 cluster, Nov 2023, Feb/Jul/Aug 2025) — **STOP surface** documented; screen proceeds on overlap-only bars.

**H8b operational specification — MES–MNQ divergence, trade WITH leader**

- **Monitoring:** MNQ % and MES % change from respective **09:30 ET** RTH opens each session.  
- **Divergence:** `|MNQ% − MES%| > 0.3%` sustained **≥ 15** consecutive minutes.  
- **Leader:** larger signed % change (MES or MNQ).  
- **Direction (H8b — catch-up, not fade):**  
  - MES% **>** MNQ% → **MNQ LONG** (MNQ catches up to higher MES).  
  - MES% **<** MNQ% → **MNQ SHORT** (MNQ catches down to lower MES).  
- **Entry:** MNQ close when divergence first sustained 15 minutes.  
- **Stop sweep:** **8 / 10** MNQ points against trade direction.  
- **Target:** signed gap `MNQ% − MES%` narrows by **≥ 50%** vs entry gap.  
- **Time exit:** RTH end (**16:00 ET**); **≤ 2** trades/session.

**Screening gates (identical to Track 1)**

1. Per-session worst loss **< $1,000** at qty for **$30K/yr** design (fail if avg annual ≤ 0 @ qty=1).  
2. Frequency **≥ 3** trades/week (2021–2025).  
3. Win rate **≥ 60%**.  
4. R:R **∈ [0.8, 1.5]**.  
5. Profitable (**> 0**) in **≥ 4 of 5** years **2021–2025**.

**Statistics**

- Daily Sharpe @ qty=1, **√252**; bootstrap **block 20**, **1000** resamples on session P&amp;L.  
- **Joint deflated Sharpe @ N=5** after run: **H1, H2, H8b, H11, H12** (excludes never-run H8 fade, blocked H9/H10). Compare **H11 PSR** vs Track 1 **N=7**.

**Deferred:** **H9** (RTY lead), **H10** (ES/MES S/R) until RTY data added.

**Date pre-registered:** 2026-05-29  

---

## 2026-05-29 — Wave 1 Stage 1 Track 1b — H8b — RESULT-LOGGED

**Wave:** Wave 1 Track **1b** (implements PRE-REGISTERED block above)  
**Date run completed:** 2026-05-29  

**Data / pipeline**

- **MES:** **26** files (`mes/MES *.Last.txt`); RTH **629,048** bars; **2020-01-02** – **2026-05-26** CT.  
- **MNQ:** **26** files (`mnq/MNQ *.Last.txt`); **4** gap-split segments in eval window; **1,551** overlapping CME session dates with MES.  
- **Coverage asymmetry (STOP surfaced):** MES has **10** unexpected missing days in **2021–2025** not present in MNQ (Apr 2023 cluster, Nov 2023, Feb/Jul/Aug 2025). MES **fills** MNQ export holes **Jun–Jul 2024** and **Feb–Mar 2026** but MNQ cannot execute on those days. Screen ran on **inner-joined** overlap only.  
- **Macro filter:** not applied (no calendar). **H9/H10:** deferred (RTY pending).

**H8b outcome:** **KILLED** (best sweep **stop=10**; **stop=8** also killed)

| Gate | Result | Gap |
|------|--------|-----|
| G1 | **FAIL** | avg annual **−$1,744** @ qty=1 (non-positive → fail by spec) |
| G2 | **PASS** | **~5.8** trades/week |
| G3 | **FAIL** | win rate **~9.1%** (need ≥60%) |
| G4 | **FAIL** | R:R **~6.83** (need 0.8–1.5) |
| G5 | **FAIL** | **1/5** profitable years (need ≥4) |

**Notable:** H8b “trade with divergence” produces **strongly negative** edge (opposite of catch-up hypothesis). **~1,501** trades in gate years; bootstrap mean-annual CI **excludes zero** on the loss side (**−$2,530** to **−$843**). **Not** a conditional Stage-2 candidate (fails G3–G5, not just G1).

**Sharpe / bootstrap (H8b, stop=10):** daily SR **≈ −2.38**; bootstrap mean annual **−$1,744** (CI95 excludes 0).

**Joint deflated Sharpe @ N=5** (H1, H2, H8b, H11, H12 — actually-run hypotheses):

- Var(trial SR) **≈ 13.95** (vs **≈ 8.00** at N=7 with three zero-blocked slots)  
- E[max SR \| null] **≈ 4.45** (vs **≈ 3.92** at N=7)  
- **H11 PSR demoted:** **≈ 0.685 @ N=5** vs **≈ 1.000 @ N=7** — prior “clean PSR” for H11 was **partially an artifact** of N=7 including three never-run zero-SR slots  
- **H12 PSR:** **≈ 0.774 @ N=5** vs **≈ 0.999 @ N=7**

**Survivors (Track 1 + 1b):** still **NONE** (0/5 run hypotheses clear all five gates).

**Artifacts:**  
- `notebooks/validation/2026-05-29_wave1_stage1_track1b_h8b_screen.{md,json}`  
- `scripts/run_wave1_stage1_track1b_h8b_screening.py`  
- Code: `simulate_h8b` in `track1_hypothesis_sims.py`; `MES_CONTRACT_GLOB` / `MNQ_CONTRACT_GLOB` in `data_loader.py`; `deflated_sharpe_joint_from_trial_stats` in `track1_metrics.py`

---

## 2026-06-01 — ICT daily-bias corpus ingested (JadeCap primary, TTrades supplement) — PROVENANCE / RESULT-LOGGED

**Wave:** Parallel track — ICT source-material ingestion (NOT a Phase 2 quant hypothesis; no edge claim, no backtest).

**Structural rationale:** A SEPARATE daily-bias corpus (two teaching videos) is ingested so a human (the ICT strategy chat) can build a daily-bias spec downstream from raw timestamped wording. This corpus is kept **distinct** from the 2022 mentorship midnight-open / Power 3 maps — no merge, no cross-reference, no reconciliation between the two creators.

**Specification (ingestion only):**
- **Sources (`data/raw/ict_sources/bias_manifest.csv`, tracked via `git add -f` since `/data/` is gitignored):**
  - `x4FJVEZUXhc` — JadeCap, "The Only ICT Daily Bias Video You'll Ever Need" — **primary** (`primary: true`). Title verified against the live video and corrected from the provisional hand-off title.
  - `-KKuZb5Z5aU` — TTrades, "Easy Daily Bias - Mechanical Framework" — **supplement** (`primary: false`). Title verified/corrected. Leading-hyphen id handled as a manifest VALUE (never a bare CLI flag).
- **Retrieval:** `youtube-transcript-api` (auto-generated EN captions for both; no manual captions). `yt-dlp` fallback not needed; **whisper not used / not approved**. Both deps were approved+installed in Phase A — none reinstalled.
- **Normalization (LOCAL / gitignored):** `data/processed/transcripts/bias/<video_id>.json` — full third-party content, not committed (JadeCap 383 segments, TTrades 490 segments).
- **Concept maps (TRACKED):** pure case-insensitive, alphanumeric-boundary keyword windowing (`±2` context segments) over the 8-group `BIAS_LEXICON`, one map PER video, never merged.

**Tracked-path choice (flagged):** Concept maps are placed under **`docs/ict_bias_concept_maps/`** (option (a) from the hand-off) rather than a `results/` `.gitignore` negation, since `docs/` is already tracked and resolves cleanly from a fresh clone. Map files:
- `docs/ict_bias_concept_maps/jadecap_primary.json` — 91 hits across 8 concept groups.
- `docs/ict_bias_concept_maps/ttrades_supplement.json` — 69 hits across 8 concept groups.

**Provenance:** Maps generated from the working tree atop commit `75c84e5`; each map's metadata carries `creator`, `role`, `video_id`, `primary`, and `git_sha` (the 2022 maps embed no SHA, so this is an added-provenance improvement, not a parity requirement). Both maps' `structure` group is legitimately empty — neither transcript uses "structure"/"shift"/"displacement"/"bos"/"mss" (verified against raw text), not a matching bug.

**Reuse / module change:** Reused `src/quant_research/utils/transcript_ingest.py` (Phase A). Added backward-compatibly (no fork): `BIAS_LEXICON`, `BiasManifestRow`, `read_bias_manifest`, `normalize_bias_transcript`, `build_bias_concept_map`. The custom-lexicon path on `build_*` already existed; per-video creator/role metadata is the only new emission. Tests extended in `tests/utils/test_transcript_ingest.py` (word-boundary: "consequent encroachment" matches; short tokens "bos"/"mss" do not match inside "embossed"/"dismiss"; bare "ce" omitted) — all 231 pass.

**Out of scope (not done):** no bias-rule synthesis, no JadeCap-vs-TTrades reconciliation, no 2022 midnight-open / Power 3 folding, no strategy/backtest/NT8 code.

**Artifact:** `notebooks/exploration/2026-06-01_ict_daily_bias_extraction.ipynb`; `docs/ict_bias_concept_maps/{jadecap_primary,ttrades_supplement}.json`; `data/raw/ict_sources/bias_manifest.csv`; `src/quant_research/utils/transcript_ingest.py`; `tests/utils/test_transcript_ingest.py`. Commit SHA recorded in the commit that adds these maps.

---

## 2026-06-02 — Bias corpus re-scanned with TTrades mechanical lexicon; TTrades set as mechanical spec primary — PROVENANCE / DECISION

**Wave:** Parallel track — ICT source-material ingestion (NOT a Phase 2 quant hypothesis; no edge claim, no backtest).

**Context:** The first bias scan (commit `6848990`) used ICT-standard terms and under-collected TTrades' own mechanical vocabulary (TTrades only 69 hits, with delivery / candle-mechanics / day-type empty). Re-scanned the EXISTING local transcripts (NO re-fetch, no network) with an additive `BIAS_LEXICON_EXTENSION` (delivery, smt, candle_mechanics, day_type, protected_swing, eq_targets, power_of_three). Base `BIAS_LEXICON` groups left untouched.

**Result (ingestion only):** New groups merged into the committed maps under `concepts` (existing groups byte-unchanged). **TTrades 69 → 206 hits** — delivery 15, smt 6, candle_mechanics 43, day_type 52, protected_swing 6, eq_targets 15, power_of_three 0; the under-collection is resolved. **JadeCap 91 → 97** (ICT-standard vocabulary; only power_of_three 6 from the new groups). Maps: `docs/ict_bias_concept_maps/{jadecap_primary,ttrades_supplement}.json`, `git_sha` stamped to the feature commit `15c31fd`. Guard tests extended (cisd/smt token-boundary, "wick" not in "wicked", "body of the candle" phrase, reversal/continuation) — all 46 pass.

**Operator decision (SPEC-level, not extraction):** For building the daily-bias SPEC, **TTrades is the mechanical PRIMARY** and **JadeCap the supplement** — TTrades teaches a mechanical, rule-based framework better suited to mechanization. This is a spec-precedence decision recorded here only; it does **not** rewrite extraction provenance. The artifact role/primary flags are **UNCHANGED**: `ttrades_supplement.json` keeps `role="supplement"` / `primary=false` and `jadecap_primary.json` keeps `primary=true`; filenames unchanged. No merge / reconciliation / synthesis across creators was performed.

**Out of scope:** no bias-rule synthesis, no JadeCap-vs-TTrades reconciliation, no 2022 midnight-open / Power 3 folding, no strategy/backtest/NT8 code.

**Artifact:** `src/quant_research/utils/transcript_ingest.py` (`BIAS_LEXICON_EXTENSION`); `tests/utils/test_transcript_ingest.py`; `docs/ict_bias_concept_maps/{jadecap_primary,ttrades_supplement}.json`; feature commit `15c31fd`; git_sha stamp commit `8112098`.

---

## 2026-06-02 — TTrades CISD + SMT confirmation primitives ingested (distinct `cisd_smt` mini-corpus) — PROVENANCE / RESULT-LOGGED

**Wave:** Parallel track — ICT source-material ingestion (NOT a Phase 2 quant hypothesis; no edge claim, no backtest).

**Context:** The daily-bias module depends on two TTrades confirmation-primitive sub-specs — Change in State of Delivery (CISD) and SMT Divergence. Extracted both as a NEW, distinct `cisd_smt` mini-corpus, kept SEPARATE from the 2022 mentorship corpus and the daily-bias corpus (never merged/cross-referenced). Manifest `data/raw/ict_sources/cisd_smt_manifest.csv` (titles verified against the live videos and corrected from provisional). Transcripts fetched via `youtube-transcript-api` (auto_subs) on the pinned `.venv` (`quant-venv`) kernel — see lessons-log 2026-06-01 nbconvert silent-failure entry; no whisper, no re-fetch beyond the two videos, no network beyond transcript fetch.

**Result (ingestion only):** One concept map PER VIDEO using a new additive `CISD_SMT_LEXICON` (groups: cisd_core, cisd_mechanics, smt_core, smt_mechanics, instruments, shared_confirm); existing lexicons untouched. Per-group hit counts — `ttrades_cisd.json` (`CHIK5oBRKiw`, 369 segments): cisd_core 19, cisd_mechanics 14, smt_core 0, smt_mechanics 0, instruments 0, shared_confirm 23 (total 56); `ttrades_smt.json` (`q1NmxUTm4n4`, 200 segments): cisd_core 0, cisd_mechanics 0, smt_core 24, smt_mechanics 12, instruments 14, shared_confirm 5 (total 55). Clean per-video separation (the CISD video has zero SMT/instrument hits and vice versa). Guard tests extended (cisd/smt token boundaries; "dow" not inside "down"; "euro" not inside "european"; displacement/divergence and "higher high" phrase matches) — all 55 pass.

**Out of scope:** no CISD/SMT definition synthesis, no cross-video reconciliation, no folding into the bias or 2022 corpora, no strategy/backtest/NT8 code. Raw transcripts stay LOCAL/gitignored under `data/processed/transcripts/cisd_smt/`.

**Artifact:** `data/raw/ict_sources/cisd_smt_manifest.csv`; `src/quant_research/utils/transcript_ingest.py` (`CISD_SMT_LEXICON`); `tests/utils/test_transcript_ingest.py`; `docs/ict_bias_concept_maps/{ttrades_cisd,ttrades_smt}.json`; `notebooks/exploration/2026-06-02_ict_cisd_smt_extraction.ipynb` (local orchestration); feature commit `9ad932e`; git_sha stamp commit `ad42034`.

---

## 2026-06-04 — Wave 1 Track 2 — Phase 1 ICT primitives + MYM data prep — PRE-REGISTERED

**Wave:** Wave 1, Track 2 (ICT-derived hypotheses)
**Status:** PRE-REGISTERED (scope fixed before build). **NOT** a backtest/edge claim — this is infrastructure: five standalone, unit-tested ICT **primitives** built before the daily-bias module (Phase 2) or the Spec A liquidity-sweep reversal strategy (Phase 3), per the strategy-chat "primitives first" review.

**Structural rationale:** Track 1 (quant hypotheses) produced **0 survivors** (research-log 2026-05-26 / 2026-05-29). Track 2 operationalizes ICT-derived hypotheses. The flagship is **Spec A** (sweep → MSS → displacement/FVG → OTE entry), gated by a daily **bias module** derived from TTrades' mechanical framework (CISD, SMT, EQ-respect; TTrades = mechanical primary per 2026-06-02 decision). Each primitive is unit-tested in isolation against the worked examples cited in the source specs before any module/strategy depends on it.

**Scope (Phase 1 only):**

- **Data prep:** Process **MYM** (Micro Dow) raw exports through the MNQ-style pipeline (UTC→CT, continuous contract via data-boundary fallback, session classification). Verify coverage, gaps, and MNQ/MES/MYM overlap. SMT can fall back to MES-vs-MNQ only if MYM is short/gappy.
- **Five primitives** under `src/quant_research/ict/`, each with pytest coverage incl. boundary conditions (first/last bar, session transitions, missing data) per ai-project-instructions Section 4:
  1. **PD-array / level marking** — PDH, PDL, prior-day EQ `(PDH+PDL)/2` per session, daily TF.
  2. **FVG detection + midpoint** — 3-candle imbalance, both directions, top/bottom/midpoint, parameterized TF.
  3. **CISD detection** (load-bearing) — opening price of the FIRST opposing-close candle in the run; fires on close beyond it; exposes the order-block zone.
  4. **SMT detection** — cross-instrument divergence at swing points (MNQ vs MES vs MYM).
  5. **Liquidity sweep** — trades through a level by `>=` configurable ticks then closes back inside within N bars; tick threshold and N are **[MANUAL OBS]** config (no source value), not hardcoded.

**Stop conditions (pre-registered):** MYM coverage/quality issues → surface MES-only vs wait; any primitive not validatable against source-cited worked examples → STOP at that primitive; CISD ambiguity against transcript examples → surface (load-bearing); FVG count implausible on a sanity slice → surface.

**Date pre-registered:** 2026-06-04

---

## 2026-06-04 — Wave 1 Track 2 — Phase 1 ICT primitives + MYM data prep — RESULT-LOGGED

**Wave:** Wave 1, Track 2 (implements PRE-REGISTERED block above)
**Date run completed:** 2026-06-04

**MYM data prep:** `MYM_CONTRACT_GLOB` added to `data_loader`; 26 quarterly files (03-20…06-26) run through the same pipeline as MES. MYM RTH coverage **632,947 bars / 1,650 session dates / 2020-01-02 → 2026-06-04** — materially the same length as MNQ (1,561; ends 2026-04-17) and MES (1,639; ends 2026-05-26), in fact longer. MYM's **only** >4-day session gap is **2023-04-05→04-17** (6 sessions), the *same* Apr-2023 cluster MES has (research-log Track 1b) — **not** MYM-specific. MYM does **not** have the MNQ export holes (2024-06/07, 2026-02/03) and covers them. Overlap **MNQ∩MES∩MYM = 1,551 = MNQ∩MES (1,551)** → MYM adds zero session loss. **Decision: full three-instrument SMT (MNQ/MES/MYM); MES-only fallback not needed.** No surprise in processing (parallel to MES) → no lessons-log entry per Section 6.

**Primitives — all five VALIDATED CLEANLY** (no stop condition fired):

| # | Primitive | Module | Tests | Validation |
|---|-----------|--------|-------|------------|
| 1 | PD-arrays (PDH/PDL/EQ) | `ict/pd_arrays.py` | 6 | hand-built sequences; first-day null; null-session-date exclusion |
| 2 | FVG + midpoint | `ict/fvg.py` | 11 | hand-built bull/bear zones; no-gap/touch reject; **real MNQ Mar-2024 counts plausible** (81/16/5.4 per session at 1m/5m/15m) |
| 3 | CISD (load-bearing) | `ict/cisd.py` | 13 | transcript @47/49/61/80/163s; **first-candle-of-series** rule; sweep-wick fallback; strict close-beyond. **Unambiguous** |
| 4 | SMT | `ict/smt.py` | 13 | bull/bear divergence; aligned→none; equal-low→none; 3-instrument; **"8:35 NASDAQ takes the lows" (@312s)** |
| 5 | Liquidity sweep | `ict/liquidity_sweep.py` | 15 | single/multi-bar sweep; continuation→none; N-window boundary; tick-threshold filter; [MANUAL OBS] config |

**Suite at completion:** **305 passed, 31 skipped** (skips pre-existing real-data tests on flat `data/raw/MNQ 03-26.Last.txt` path); ruff clean.

**Next (not in this phase):** Phase 2 assembles the bias module from primitives 1/3/4 (+EQ respect); Phase 3 assembles Spec A from primitives 2/5 (+MSS, OTE). Both remain separate operator-gated prompts.

**Artifacts:** `notebooks/validation/2026-06-04_wave1_track2_phase1_ict_primitives.md`; `src/quant_research/ict/`; `tests/ict/`; `scripts/verify_mym_coverage.py` + `scripts/_mym_coverage_report.json`; `src/quant_research/data/data_loader.py` (`MYM_CONTRACT_GLOB`).

---

## 2026-06-05 — Wave 1 Track 2 — Phase 2 daily bias module (assembly) — PRE-REGISTERED

**Wave:** Wave 1, Track 2 (ICT-derived hypotheses) — Phase 2 (bias module assembly).
**Status:** PRE-REGISTERED (logic + diagnostics + variants fixed before building/running).
**NOT** a backtest / edge claim. This assembles the five Phase-1 primitives
(research-log 2026-06-04) into a daily bias **state machine** that emits
`long` / `short` / `no-clear-bias` per session, and reports diagnostics on the
assembled module's behavior. No strategy P&L is computed here (that is Phase 3,
Spec A).

**Source precedence:** TTrades mechanical framework is canonical
(`docs/ict/bias_module_spec.md`; TTrades = mechanical primary per 2026-06-02
decision). JadeCap premium/discount + PO3 are NOT built into this module.

**Strategy-chat decisions encoded (fixed, not free parameters):**

1. **Direction is confirmed, not seeded.** No ex-ante continuation-vs-reversal
   prediction. **Both** directions are armed each session; whichever path
   completes its confirmation chain via CISD dictates the bias. The
   continuation-vs-reversal seed proxy is **DEFERRED** (optional later
   experiment), not built now.
2. **EQ-respect is canonical** = closure past 50% of the **prior-day** range
   against bias = invalidation. The operator's FVG-midpoint variant is a
   separately-tested Phase-3 extension, **NOT** in this module.
3. **No-clear-bias day → emit `no-clear-bias`** (strategy stands down).

**State machine (per session, no look-ahead; uses only session-N intraday bars +
prior-day levels):**

1. **Mark reference levels** (Primitive 1, `pd_arrays`): PDH, PDL, prior-day EQ
   `(PDH+PDL)/2` from the prior RTH session. First session of data → no prior
   levels → `no-clear-bias`.
2. **Pairing timeframe (parameterized):** session 1m RTH bars are resampled
   (Primitive 2 `resample_ohlc`) to the pairing TF on which CISD is detected.
   **Primary = 5m** (per spec "5m into NY"); **one variant = 15m**. No broad TF
   sweep (would inflate deflated-Sharpe N).
3. **Arm both directions** on the pairing-TF bars:
   - **Bullish path:** (a) **sweep** of a downside reference — PDL or the
     opening-range low (min low of the first `OPENING_RANGE_MINUTES`=30 of RTH,
     scanned after the OR forms) — via Primitive 5 `detect_sweep(side="low")`;
     then (b) **bullish CISD** fires after the sweep on the pairing TF (Primitive
     3, anchored at the swing low) — closes above the first down-close candle's
     open; then (c) **EQ respected** (operationalized below); then (d) **SMT**
     bullish divergence at the low (Primitive 4, MNQ vs MES/MYM).
   - **Bearish path:** symmetric (sweep PDH / OR-high → bearish CISD → EQ
     respected → bearish SMT at the high).
4. **EQ-respect (operationalization — modeling choice, flagged):** for the
   bullish path it holds iff, **at/after the CISD fire bar**, some bar **closes
   at/above** prior-day EQ (price reclaims/holds the prior-day midpoint) **and**
   from that first reclaim through session end **no bar closes strictly below**
   prior-day EQ (an opposing EQ closure = invalidation). Bearish is the mirror
   (reclaim = close at/below EQ; invalidation = close strictly above EQ). This is
   the canonical "closure-past-50%-against-bias = invalidation" rule made causal;
   it is a modeling decision (the spec gives the rule, not the exact reclaim
   sequencing).
5. **Emit bias:** `long` iff the bullish path completes and the bearish does not;
   `short` iff bearish completes and bullish does not; **`no-clear-bias`**
   otherwise — i.e. neither completes (incl. consolidation/range, which produces
   no clean sweep→CISD→EQ chain), **both** complete (ambiguous), or an opposing
   EQ closure invalidates a forming path. No separate range detector is added
   (would be an extra free parameter); range = chain-incompletion.
6. **SMT as a configurable confirmation tier (the pre-registered VARIANT axis):**
   - `smt_required=False` (**PRIMARY**): bias fires on sweep+CISD+EQ; SMT is
     computed and logged present/absent but does **not** gate.
   - `smt_required=True` (**VARIANT**): bias fires only with SMT confirmation on
     the winning path.
   SMT uses pairing-TF MNQ/MES/MYM aligned bars: prior window = session open to
   the sweep bar; current window = sweep bar to the CISD fire. Sessions without
   aligned MES/MYM bars → SMT not evaluable (absent); under `smt_required=True`
   those cannot fire.

**Pre-registered configs (the ONLY ones run; no other free parameters):**

| Config | pairing TF | smt_required | Role |
|---|---|---|---|
| **C1** | **5m** | **False** | **PRIMARY** |
| C2 | 5m | True | SMT-tier variant |
| C3 | 15m | False | TF variant |
| C4 | 15m | True | TF × SMT variant |

Structural (non-swept, documented) constants: `OPENING_RANGE_MINUTES=30`,
sweep `penetration_ticks=1`, sweep `close_back_within_bars=3` (Primitive 5
[MANUAL OBS] defaults), MNQ `tick_size=0.25`, SMT instruments = MNQ/MES/MYM.

**Diagnostic outputs (the Phase-2 deliverable), over the full 6-year MNQ set
(MES/MYM for SMT):**

- (a) **Bias distribution** overall (fraction long/short/no-clear-bias).
- (b) **Bias distribution by year** (2020–2026); stability vs regime-dependence.
- (c) **Confirmation-chain attrition:** of sessions that start a directional path
  (a sweep occurs), how many reach CISD, EQ-respect, SMT; where the chain most
  often breaks (the binding filter).
- (d) **SMT impact:** how many clear-bias sessions (under `smt_required=False`)
  flip to no-clear-bias under `smt_required=True`.
- (e) **TTrades worked-example validation:** the spec's worked examples are
  transcript-described day **types** (continuation @193/258s; reversal
  @45/64s), not labeled real-MNQ dates, so they are reproduced as **synthetic**
  sessions faithful to the described geometry and the module must classify them
  as the transcript describes. (Honest limitation: no real-MNQ ground-truth
  labels exist in the corpus.)

**Unit tests (pre-registered):** synthetic continuation day → expected bias;
synthetic reversal day → expected bias; consolidation/range day → no-clear-bias;
opposing EQ closure invalidates a forming bias; `smt_required` True-vs-False
toggle behaves correctly; no look-ahead (session-N bias unchanged by presence of
session N+1 bars).

**Stop conditions (pre-registered):**

- Any TTrades worked example **misclassified** by the assembled module → **STOP,
  surface** (interaction logic wrong; primitives validated individually).
- No-clear-bias **dominates (>70%)** under the PRIMARY config (C1) → **surface
  (do not stop)** — frequency finding for strategy-chat.
- Bias distribution **wildly unstable** across years (e.g. ~90% one direction in
  one year, ~90% the other in another) → **surface** (possible trend artifact).
- Confirmation chain attrites to **<50 clear-bias sessions** in the 6-year set
  under C1 → **surface** (insufficient for downstream statistical test).

**Date pre-registered:** 2026-06-05

---

## 2026-06-05 — Wave 1 Track 2 — Phase 2 daily bias module (assembly) — RESULT-LOGGED

**Wave:** Wave 1, Track 2 (implements the PRE-REGISTERED block above).
**Date run completed:** 2026-06-05
**Execution `git` metadata:** `git_sha` = `0db224fc2bd1ef320064fb04c9a9a3d9d095e366` (workspace
dirty at run; clean-tree SHA in the commit that adds this entry).

**Build:** `src/quant_research/ict/bias_module.py` — daily state machine assembling
Primitives 1/2/3/4/5. `BiasConfig` exposes only the two pre-registered axes
(`pairing_timeframe`, `smt_required`); all else structural. 13 unit tests
(`tests/ict/test_bias_module.py`): continuation→long, reversal→short, range→no-clear,
opposing-EQ-closure invalidation, OR-low reference, SMT required/optional toggle,
no-look-ahead (session-N bias unchanged by N+1 bars), pure combinators. Full suite
**318 passed, 31 skipped** (same data-keyed skips as Phase 1); ruff clean.

**Data:** MNQ 599,533 / MES 629,048 / MYM 632,947 RTH bars (2020-01-01→2026-06-30);
**1,561** MNQ sessions classified. SMT three-instrument (MNQ/MES/MYM).

**(a) Bias distribution (overall):**

| Config | TF | SMT req | long | short | no-clear-bias |
|---|---|---|---|---|---|
| **C1 (PRIMARY)** | 5m | False | 218 (14.0%) | 165 (10.6%) | **1,178 (75.5%)** |
| C2 | 5m | True | 96 (6.1%) | 73 (4.7%) | 1,392 (89.2%) |
| C3 | 15m | False | 240 (15.4%) | 159 (10.2%) | 1,162 (74.4%) |
| C4 | 15m | True | 89 (5.7%) | 57 (3.7%) | 1,415 (90.6%) |

**383** clear-bias sessions over 6 years under C1 (well above the 50-session floor).

**(b) By year (C1):** no-clear-bias 70–79% every year; long-share of clear sessions
**45–64%** across full years (2026 partial, n=47, 71%). Balanced, not a one-direction
trend artifact.

**(c) Confirmation-chain attrition (C1):** 1,561 sessions → **sweep 1,333** →
**CISD 817** → **EQ-respect 383** → **SMT 169**. Largest losses: **sweep→CISD −516**
and **CISD→EQ −434**. The binding filters are **CISD confirmation** and **EQ-respect**
(roughly halves at each); the initial sweep is common (85% of sessions).

**(d) SMT impact (5m):** of 383 clear sessions, winning-path SMT present on only **169**;
requiring SMT flips **214 (55.9%)** to no-clear-bias — roughly halving frequency.

**(e) Worked examples:** continuation→long, reversal→short, consolidation→no-clear all
**classified correctly** — assembly logic self-consistent with the transcript day-types.
(Honest limit: synthetic day-types faithful to transcript geometry; no real-MNQ
ground-truth labels exist.)

**Stop conditions:**
- Worked example misclassified (STOP): **NO** — all correct, Phase 3 may proceed.
- No-clear-bias dominates >70% (**SURFACE, not stop**): **YES (75.5%)** — the module
  stands down on ~3 of 4 sessions; weigh downstream trade frequency / eval pass-rate
  in strategy chat.
- Year instability: **NO** (long-share 45–64%, no ~90% flips).
- <50 clear-bias sessions: **NO** (383 — sufficient for downstream tests).

**Operator decision still open (for strategy chat):** SMT tier (C1 vs C2). Optional
SMT gives 383 clear sessions (~64/yr); required SMT gives 169 (~28/yr). Pairing TF
5m vs 15m barely moves the distribution (15m slightly more long-biased).

**Artifacts:**
- `notebooks/validation/2026-06-05_wave1_track2_phase2_bias_module.{md,json}`
- `src/quant_research/ict/bias_module.py`; `tests/ict/test_bias_module.py`
- `scripts/run_wave1_track2_phase2_bias_module.py`

---

## 2026-06-06 — Wave 1 Track 2 — Phase 3a bias/entry architecture diagnostic — RESULT-LOGGED

**Wave:** Wave 1, Track 2 — Phase 3a (source-material diagnostic only; **no strategy code**).
**Status:** RESULT-LOGGED
**Purpose:** Resolve structural ambiguity between Phase 2 bias (TTrades: sweep → CISD →
EQ → SMT) and Spec A setup (2022: sweep → MSS → FVG → OTE) before Phase 3 assembly.

**Method:** Direct transcript extraction at cited timestamps from processed JSON
(TTrades CISD + daily bias; 2022 Ep 6/12/25/38/41). Term cross-search: **zero**
"state of delivery" in 2022 sample; **zero** "market structure shift" in TTrades bias
supplement.

**Findings (Q1–Q4):**

| Q | Result | Confidence |
|---|---|---|
| **Q1 MSS vs CISD** | **Distinct** computable mechanics (swing break vs close beyond first opposing candle open). Same narrative role; may co-occur; not interchangeable. | High |
| **Q2 Bias/entry** | **Corpora split:** 2022 Spec A ≈ **Architecture A** (one manipulation leg → MSS → FVG → OTE). TTrades daily bias ≈ **Architecture C** (pairing-TF CISD confirms bias; entry via candle 2/3 or lower-TF CISD/OB). @622 shows possible **later sub-leg** entry within bias. **Plug-in unresolved in source.** | Medium |
| **Q3 Timeframes** | TTrades: hourly/30m early → 15m/5m NY for CISD; 5m for entry. 2022: 15m/50m FVG context, 5m OTE execution (Ep 41). Bias TF ≠ entry TF in both. | High (TTrades); Medium (2022) |
| **Q4 Corpora differ** | **Yes** — different confirmation terms, entry mechanics, bias framing. Two-corpus build is valid per operator precedence but **must not conflate CISD with MSS**. | High |

**Stop conditions:**
- MSS ≠ CISD for Spec A entry → **SURFACED** (Phase 3 needs MSS primitive; do not relabel CISD). Phase 2 bias module **not invalidated** for TTrades gate purpose.
- Q2 ambiguous → **SURFACED** for operator: same manipulation leg vs later same-session setup after bias time.
- Phase 2 rework → **Not required** unless operator pivots to TTrades-only entry (drops Spec A OTE flagship).

**Recommendation for Phase 3 (operator sign-off):** **Two-layer model** — (1) Phase 2 bias
gate unchanged; (2) Spec A entry detector uses **MSS + FVG + OTE** per 2022, in bias
direction only. Pre-register **conservative** default: entry setup begins **at or after**
bias emission time. Do **not** use Phase 2 CISD fire as MSS substitute.

**Artifact:** `notebooks/validation/2026-06-06_wave1_track2_phase3a_architecture.md`

---

## 2026-06-06 — Wave 1 Track 2 — Phase 3 steps 0–1 (definitions + MSS) — PRE-REGISTERED

**Wave:** Wave 1, Track 2 — Phase 3 steps 0–1
**Status:** PRE-REGISTERED
**Purpose:** Resolve six Spec A underspecifications from 2022 mentorship source (step 0),
then build unit-tested MSS primitive (step 1) for standalone OTE strategy assembly (step 2).

**Scope:**
- **Step 0:** Extract precise definitions D0.1–D0.6 from Ep 6/12/25/38/41; deliver
  definitions report; STOP if D0.1, D0.3, or D0.6 unresolvable even provisionally.
- **Step 1:** `src/quant_research/ict/mss.py` + `tests/ict/test_mss.py` using D0.4
  lookback default; validate against Ep 6/12 worked geometries; MSS ≠ CISD test required.

**Pre-registered mechanical defaults (summary):**
- D0.1 OTE leg: displacement leg low→high (long) / high→low (short).
- D0.2 Entry FVG: first in-leg FVG on correct PD side (`[MANUAL OBS]` tie-break).
- D0.3 Displacement extreme: running min/max sweep-penetration → MSS bar.
- D0.4 MSS swing lookback: penetration-anchored, max 100-bar fallback (`[MANUAL OBS]`).
- D0.5 Stop buffer: 1 tick (2-tick FVG-arm variant); swept arm `[MANUAL OBS]`.
- D0.6 Target: nearest unbroken opposing liquidity pool (fractal + PDH/PDL) (`[MANUAL OBS]`).

**Pass/fail (step 1):** MSS primitive unit tests pass; Ep 6 @1416/@1110 and Ep 12 @2247
geometries reproduce; MSS and CISD independence demonstrated; no look-ahead in
displacement leg.

**Date pre-registered:** 2026-06-06

---

## 2026-06-06 — Wave 1 Track 2 — Phase 3 steps 0–1 (definitions + MSS) — RESULT-LOGGED

**Wave:** Wave 1, Track 2 — Phase 3 steps 0–1 (implements pre-registration above)
**Status:** RESULT-LOGGED
**Date run completed:** 2026-06-06

**Step 0 — Definitions:** **COMPLETE.** All six items resolved with mechanical defaults.
Stop condition **not triggered** (D0.1, D0.3, D0.6 provisionally specified).

| ID | Default | `[MANUAL OBS]` |
|---|---|---|
| D0.1 OTE leg | Displacement leg endpoints | — |
| D0.2 Entry FVG | First in-leg FVG, correct PD side; nearest-OTE tie-break | tie-break |
| D0.3 Displacement extreme | Running extreme `[penetration, MSS bar]` | — |
| D0.4 MSS lookback | `max(0, penetration − 100 bars)` through MSS candidate | fallback cap |
| D0.5 Stop buffer | 1 tick beyond reference (FVG c2 / swept extreme) | swept-arm ticks |
| D0.6 Target | Nearest unbroken opposing fractal swing or PDH/PDL | pool ranking |

**Step 1 — MSS primitive:** **COMPLETE.** `11/11` tests pass (`tests/ict/test_mss.py`).
Ep 6 bullish/bearish and Ep 12 short-term-low-broken geometries validated. MSS vs CISD
independence tests pass. Displacement leg causal at MSS bar close (no look-ahead).

**Artifacts:**
- `notebooks/validation/2026-06-06_wave1_track2_phase3_step0_definitions.md`
- `src/quant_research/ict/mss.py`
- `tests/ict/test_mss.py`

**Next:** Phase 3 step 2 — standalone OTE strategy assembly (operator-gated).

---

## 2026-06-06 — Wave 1 Track 2 — Phase 3 step 2 (standalone OTE assembly) — PRE-REGISTERED

**Wave:** Wave 1, Track 2 — Phase 3 step 2
**Status:** PRE-REGISTERED
**Purpose:** Assemble self-contained Spec A OTE strategy (sweep → MSS → FVG → OTE) with
no bias gate; unconstrained RTH collection for step-3 backtest and step-4 constraint/overlap
analysis.

**Strategy logic (structural chain):**
1. Sweep reference levels: PDL, PDH, recent swing high/low (`penetration_ticks=1`,
   `close_back_within_bars=3`).
2. MSS in sweep reversal direction (3-bar fractal; D0.4 lookback).
3. Displacement leg `[penetration, MSS bar]` (D0.3).
4. FVG: earliest in-leg gap on correct PD side (D0.2); tie-break nearest-OTE (variant).
5. OTE limit at 70.5% of displacement leg (D0.1); 62% first-touch (variant).
6. Stop A/B graded separately: swept extreme (primary) vs FVG c2 ± 1 tick (variant).
7. Target fork: nearest pool (primary) vs far PDH/PDL/fractal pool (variant); time exit
   16:00 ET if open.
8. **No** bias gate; **no** session-window cap; **no** one-setup-per-session limit.

**Pre-registered variants (deflation N = 4 axes, not swept beyond):**

| Axis | Primary | Variant |
|---|---|---|
| Target | `nearest` | `far` |
| Stop arm | `swept_extreme` (A) | `fvg_c2` (B) |
| OTE entry | `ote_705` | `ote_62` |
| FVG tie-break | `earliest` | `nearest_ote` |

**Structural constants (fixed):** OTE band 62–79%, 3-bar fractal, 100-bar MSS fallback,
`penetration_ticks=1`, `close_back_within_bars=3`.

**Pass/fail:** `ote_strategy.py` unit tests pass; long/short E2E; no-setup guards;
direction from sweep/MSS only; no look-ahead; target fork wired; multiple setups/session.

**Date pre-registered:** 2026-06-06

---

## 2026-06-06 — Wave 1 Track 2 — Phase 3 step 2 (standalone OTE assembly) — RESULT-LOGGED

**Wave:** Wave 1, Track 2 — Phase 3 step 2 (implements pre-registration above)
**Status:** RESULT-LOGGED
**Date run completed:** 2026-06-06

**Result:** **COMPLETE.** Standalone OTE strategy assembled and unit-tested.

| Check | Outcome |
|---|---|
| Step-0 definitions implementable | **Yes** — no stop condition |
| `tests/ict/test_ote_strategy.py` | **12/12 pass** (94/94 ICT suite) |
| Long / short E2E | **Pass** — entry, stop A, both targets |
| No-setup guards | **Pass** — no MSS, no FVG, no fill |
| Direction self-contained | **Pass** — from sweep/MSS only |
| Target fork | **Pass** — nearest ≠ far on test geometry |
| Multi-setup / session | **Pass** — `scan_setups` unconstrained |

**Implementation judgment calls (surfaced):**
1. **FVG confirmation timing:** eligible when `c3_index <= mss_index + 1` (FVG may
   confirm one bar after MSS when c2 is the MSS candle) — causal, not look-ahead.
2. **Target pool “unbroken”:** fractal pool taken if `max(high)` / `min(low)` **after
   swing confirmation** through signal has not traded through the level (not full-session
   max, which over-disqualifies pools touched before confirmation).
3. **D0.1/D0.2 interaction:** `fvg_ote_conflict` flag when OTE limit lies >4 ticks outside
   selected FVG zone — observed on test geometry (common; logged, not blocking).

**Artifacts:**
- `src/quant_research/ict/ote_strategy.py`
- `tests/ict/test_ote_strategy.py`

**Next:** Phase 3 step 3 — 6-year backtest with rich tagging (no constraints applied at
collection; variants tagged for step-4 analysis).

---

## 2026-06-06 — Wave 1 Track 2 — Phase 3 step 3 (standalone OTE backtest) — PRE-REGISTERED

**Wave:** Wave 1, Track 2 — Phase 3 step 3
**Status:** PRE-REGISTERED
**Purpose:** Run unconstrained 6-year MNQ RTH backtest of standalone OTE (no bias gate) with
rich per-trade tagging so step 4 can apply pre-registered constraints and bias-overlap analysis
without re-running the backtest.

**Data scope:**
- MNQ RTH continuous, protocol window 2020-01-01 → 2026-04-19 (Wave 0 MNQ protocol end)
- MES/MYM loaded for bias-module SMT tagging only
- P&L denominated per MNQ contract (qty=1; sizing in step 4)

**Collection mode:** UNCONSTRAINED — all valid setups, all RTH times, multiple setups per
session; no bias gate, no time window beyond RTH, no one-setup-per-session cap.

**Trade logs (5):** primary + four single-axis flips (not full grid):
1. **primary:** target=nearest, stop=swept_extreme, entry=ote_705, fvg_tiebreak=earliest
2. **target_far:** primary with target=far
3. **stop_fvg_c2:** primary with stop=fvg_c2
4. **entry_ote_62:** primary with entry=ote_62
5. **fvg_nearest_ote:** primary with fvg_tiebreak=nearest_ote

**Per-trade tags (required):** entry/exit timestamps, direction, prices, exit reason,
session date, entry time-of-day, setup-number-in-session, bias C1/C2 verdict + agree flag,
both stop arms + R, both target levels + counterfactual outcomes, fvg_ote_conflict + dual
entry prices, displacement leg size, sweep depth, FVG size.

**Diagnostics:** (a) frequency, (b) headline economics primary, (c) fvg_ote_conflict on real
data, (d) target fork preview, (e) bias overlap preview, (f) time-of-day preview.

**Stop conditions:**
- Total setups < ~100 → surface (too infrequent)
- fvg_ote_conflict > ~30% → surface (entry ambiguous)
- Primary + all variant flips strongly negative → surface (no edge)
- Annual P&L > $2K/MNQ → surface (strong positive signal)

**Date pre-registered:** 2026-06-06

---

## 2026-06-06 — Wave 1 Track 2 — Phase 3 step 3 (standalone OTE backtest) — RESULT-LOGGED

**Wave:** Wave 1, Track 2 — Phase 3 step 3 (implements pre-registration above)
**Status:** RESULT-LOGGED
**Date run completed:** 2026-06-06
**git_sha:** `0db224fc2bd1ef320064fb04c9a9a3d9d095e366`

**Result:** **COMPLETE.** Unconstrained 6-year MNQ RTH backtest executed; 5 trade logs
written with full per-trade tagging for step-4 constraint/overlap analysis.

### Stop-condition assessment

| Condition | Triggered? | Finding |
|---|---|---|
| Setups < ~100 | **No** | 9,557 primary setups (~1,365/year) — strategy is **not** rare unconstrained |
| fvg_ote_conflict > ~30% | **Yes** | **99.3%** of setups — entry definition ambiguous on nearly all trades |
| All variants negative | **No** | Primary + target_far + entry_ote_62 positive; stop_fvg_c2 strongly negative |
| Annual P&L > $2K/MNQ | **Yes** | Primary **$2,093/MNQ/yr** — first material standalone edge signal |

### (a) Frequency

- **9,557** primary setups over protocol window; **1,365/year**
- **1,561** sessions with ≥1 trade (**100%** of sessions in data)
- **98.5%** of trading sessions have multiple setups (avg **6.1**/session; max **14**)

### (b) Headline economics (primary, qty=1 MNQ)

- Total P&L **+$14,648**; annual **+$2,093**; WR **51.7%**; avg R **0.04**
- Year-by-year: 2020 +$2,712; 2021 +$871; 2022 +$2,335; 2023 +$3,718; 2024 +$3,631;
  2025 +$1,852; 2026 −$472 (partial year)

### (c) FVG/OTE conflict (SURFACED)

- **99.3%** of setups have OTE limit >4 ticks outside selected FVG zone
- Counterfactual P&L on same stops/targets: OTE-entry total **+$14,648** vs FVG-zone entry
  **+$220,760** (8,592 fills) — entry-price choice dominates economics; **must resolve
  D0.1/D0.2 before step-4 screening**

### (d) Target fork preview

- **Nearest (primary):** WR 51.7%, annual +$2,093 — eval-relevant profile (higher WR, ~1R)
- **Far (active log):** WR 34.6%, annual +$630, R:R ~1.9 — funded-relevant hypothesis weak
  on raw P&L (2024–2026 negative)

### (e) Bias overlap preview (C1)

- Only **9.2%** of setups occur on bias-agreeing sessions
- Agree subset: annual +$340 (WR 52.6%); disagree/no-bias: annual +$1,752 (WR 51.6%)
- Standalone OTE edge does **not** require bias agreement in this preview

### (f) Time-of-day preview

- Best hours: **15:00 ET** (+$7,176 total, 55.2% WR), **12:00 ET** (+$4,004)
- Weakest: **09:00 ET** (−$2,417, 39.3% WR) — morning window constraint worth testing in step 4

### Variant economics (5 logs)

| Variant | n | Annual P&L | WR |
|---|---|---|---|
| primary | 9,557 | +$2,093 | 51.7% |
| target_far | 9,557 | +$630 | 34.6% |
| stop_fvg_c2 | 9,557 | −$21,798 | 46.9% |
| entry_ote_62 | 9,204 | +$8,844 | 57.4% |
| fvg_nearest_ote | 9,557 | +$2,093 | 51.7% |

Note: `fvg_nearest_ote` identical to primary on real data (tie-break did not change FVG selection).

**Artifacts:**
- `scripts/run_wave1_track2_phase3_step3_ote_backtest.py`
- `notebooks/validation/2026-06-06_wave1_track2_phase3_step3_ote_backtest.{md,json}`
- `notebooks/validation/2026-06-06_wave1_track2_phase3_step3_ote_trades/{primary,target_far,stop_fvg_c2,entry_ote_62,fvg_nearest_ote}.json`

**Next:** Phase 3 step 3b — entry-coherence forensic diagnostic (step 4 blocked until resolved).
**Blocker surfaced:** resolve D0.1/D0.2 entry ambiguity (99% conflict) before interpreting
screening results.

---

## 2026-06-06 — Wave 1 Track 2 — Phase 3 step 3b (entry-coherence diagnostic) — PRE-REGISTERED

**Wave:** Wave 1, Track 2 — Phase 3 step 3b
**Status:** PRE-REGISTERED
**Purpose:** Forensic audit of step-3 standalone OTE economics. NOT screening. Determine
whether any cost-surviving, artifact-free edge exists once entry is coherent. **Blocks step 4.**

**Diagnostics:**
1. Why D0.1 (OTE 70.5%) and D0.2 (FVG) disagree (median ~46 ticks) — trace 50 setups
2. Audit FVG-zone $220k counterfactual for look-ahead / fill timing artifact
3. Audit entry_ote_62 4× outperformance for fill artifact
4. Re-evaluate all 5 configs net of commission ($1.98 RT) and 1-tick slippage model
5. If fixable: re-run coherent entry alternatives cost-inclusive

**Stop conditions:**
- No config survives realistic costs with coherent entry → surface; pivot ICT track
- Incoherence is definitional (operator decision) → surface; do not guess
- Config survives costs with verified no-look-ahead → surface as real candidate for step 4

**Date pre-registered:** 2026-06-06

---

## 2026-06-06 — Wave 1 Track 2 — Phase 3 step 3b (entry-coherence diagnostic) — RESULT-LOGGED

**Wave:** Wave 1, Track 2 — Phase 3 step 3b (implements pre-registration above)
**Status:** RESULT-LOGGED
**Date run completed:** 2026-06-06
**git_sha:** `0db224fc2bd1ef320064fb04c9a9a3d9d095e366`

**Result:** **COMPLETE.** Forensic diagnostic confirms step-3 standalone OTE economics are
**not trustworthy** for screening. **Step 4 blocked.**

### Verdicts

| Diagnostic | Finding |
|---|---|
| **D1 — Entry incoherence** | **Definitional, not a code bug.** 99.3% conflict; median 46 ticks (mean 71). On 50/50 traced setups: OTE 70.5% sits in **premium** half, earliest eligible FVG in **discount** half — opposite PD sides by construction (Ep 38: OTE vs FVG are **alternative** entry styles). Not fixable by window tweak; **operator must choose** entry mode. |
| **D2 — FVG-zone $220k** | **Artifact (price substitution, not look-ahead).** 30/30 top trades bar-valid. Fair-timing re-sim $220,575 vs $220,760 — timing is not the driver. Inflation from ~46-tick-different entry with fixed stop/target. **Discard.** |
| **D3 — entry_ote_62** | **Partially real** (bar-valid fills, better entry geometry). 13.5 vs 3.1 gross ticks/trade. Still incoherent FVG+OTE assembly — not cleared. |
| **D4 — Costs** | Primary: **−$1,186/MNQ/yr** (−1.74 net ticks/trade) comm+slip. Gross +3.1 ticks/trade cannot cover $1.98 RT. target_far −$2,735/yr; stop_fvg_c2 −$25,029/yr. entry_ote_62 +$5,673/yr but incoherent. |
| **D5 — Coherent re-run** | OTE-only (70.5%, no FVG gate): **−$1,186/yr** cost-inclusive. FVG-only: +$28,549/yr but **untrusted** (targets resolved at OTE entry price). |

### Stop conditions

- **No cost-surviving coherent edge:** **TRIGGERED**
- **Definitional decision required:** **TRIGGERED** (OTE-only vs FVG-only vs unified rule)
- **Proceed to step 4:** **NO**

**Artifacts:**
- `scripts/run_wave1_track2_phase3_step3b_diagnostic.py`
- `notebooks/validation/2026-06-06_wave1_track2_phase3_step3b_diagnostic.{md,json}`

**Next:** Phase 3 step 3c — coherent cost-inclusive entry rebuilds (OTE-only, windowed OTE,
FVG-only with correct target pairing).

---

## 2026-06-06 — Wave 1 Track 2 — Phase 3 step 3c (coherent entry rebuilds) — PRE-REGISTERED

**Wave:** Wave 1, Track 2 — Phase 3 step 3c
**Status:** PRE-REGISTERED
**Purpose:** Clean test of whether any **coherent** ICT entry has cost-surviving edge on MNQ.
NOT step-4 screening. Targets/stops resolved from **actual** entry price (fixes step-3b
artifact).

**Running configuration count (deflation N):**
- Step 3: **5** (primary + 4 single-flip incoherent logs)
- Step 3b: **+1** unique (FVG-only mis-paired; OTE-only duplicates 3c C1)
- Step 3c: **+9** (C1×2 + C2 windows×2 bands + C3×1)
- **Total N after 3c: 15**

**Configs (all cost-inclusive primary):**
1. **C1 OTE-only** full RTH: 70.5% and 62% (anchor reproduces 3b −$1,186/yr)
2. **C2 OTE-only** session windows W1/W2/W3 × 70.5% and 62% (report all, no cherry-pick)
3. **C3 FVG-only** full RTH: zone touch; targets/stops from FVG entry

**Costs:** $1.98 RT commission; 1-tick slip stop/time; half-tick target.

**Stop conditions:**
- C3 >10 net ticks/trade → audit 30 trades before reporting edge
- Any config cost-surviving + DLL-fit → step-4 candidate
- All negative/marginal → ICT track reassessment

**Date pre-registered:** 2026-06-06

---

## 2026-06-06 — Wave 1 Track 2 — Phase 3 step 3c (coherent entry rebuilds) — RESULT-LOGGED

**Wave:** Wave 1, Track 2 — Phase 3 step 3c (implements pre-registration above)
**Status:** RESULT-LOGGED
**Date run completed:** 2026-06-06
**git_sha:** `0db224fc2bd1ef320064fb04c9a9a3d9d095e366`

**Deflation N (standalone OTE search):** step 3 **5** + step 3b **1** + step 3c **9** = **15 total**

**Result:** **COMPLETE.** No configuration cleared for step-4 screening.

### Cost-inclusive headline (comm+slippage, qty=1 MNQ)

| Config | n | Annual net | Net ticks/trade | DLL @ $30K/yr |
|---|---:|---:|---:|---|
| C1 OTE 70.5% full | 13,012 | **−$2,410** | −2.59 | No |
| C1 OTE 62% full | 12,491 | **+$5,099** | +5.71 | No |
| C2 W1 OTE 62% | 2,776 | +$609 | +3.07 | No |
| C2 W2 OTE 62% | 8,601 | +$4,355 | +7.09 | No |
| C2 W3 OTE 62% | 6,503 | +$2,763 | +5.95 | No |
| C2 W1 OTE 70.5% | 2,914 | −$1,776 | −8.53 | No |
| C2 W2 OTE 70.5% | 8,886 | −$1,334 | −2.10 | No |
| C2 W3 OTE 70.5% | 6,756 | −$189 | −0.39 | No |
| C3 FVG-only full | 8,080 | **+$26,185** | **+45.37** | **Yes** |

### Key findings

1. **C1 OTE 70.5%** does not reproduce step-3b −$1,186 anchor: true OTE-only scan finds **13,012** setups (vs 9,557
   combined-with-FVG gate). Extra marginal setups worsen economics to −$2,410/yr.
2. **OTE 62%** is the only OTE-band mode with sustained positive net P&L (+$5,099/yr full; +$4,355 W2), but
   **fails Apex tier-1 DLL** at $30K/yr sizing (max session loss −$3,409 at qty 5.88).
3. **Session windows** do not rescue OTE 70.5% (all negative). OTE 62% positive in all three windows but
   marginal in W1 (+$609/yr).
4. **C3 FVG-only** with correct target pairing: **+$26,185/yr**, 45.4 net ticks/trade — barely changed from
   step-3b mis-paired FVG-only ($28,549). Step-3 counterfactual inflation was on **combined** logs, not FVG-only
   pairing error. **30/30** top-trade bar audit passed; median target distance 89 ticks. Magnitude still
   implausible for intraday MNQ — **not authorized for step 4** without independent validation.

### Stop conditions

- C3 >10 net ticks/trade: **TRIGGERED** (45.4); audit 30/30 bar-reachable — magnitude still suspect
- Cost-surviving artifact-free candidate for step 4: **NOT MET**
- All OTE 70.5% configs negative: **YES**

**Artifacts:**
- `scripts/run_wave1_track2_phase3_step3c_coherent_rebuild.py`
- `notebooks/validation/2026-06-06_wave1_track2_phase3_step3c_coherent_rebuild.{md,json}`
- `src/quant_research/ict/ote_strategy.py` (`entry_style`: `ote_only` / `fvg_only`)

**Next:** Operator decision — (a) independent validation of FVG-only magnitude, (b) pursue OTE 62% with DLL-
constrained sizing, (c) pivot to bias-gated two-layer path, or (d) ICT track reassessment. Step 4 **not authorized**.

---

## 2026-06-07 — Wave 1 engine topology + integrity audit — RESULT-LOGGED

**Wave:** Wave 1 (cross-track infrastructure)
**Type:** Read-only investigation (no code changes)
**Trigger:** Step 3 FVG/OTE artifacts ($220k counterfactual, $26k FVG-only) from incoherent entry-stop-target
geometry; concern that fill engine may also silently deflate strategies with real edge (Track 1 KILLED
hypotheses, OTE 70.5% net-negative).

**Questions addressed:** Engine topology (Q1), blast radius (Q2), geometry invariants (Q3), intrabar
stop-vs-target (Q4), bar sequencing (Q5), hand-computed ground truth (Q6), cost application (Q7).

**Findings:**

1. **Three fill paradigms** — not one engine:
   - **M4 `BacktestEngine`** → Wave 0 ORB+Opt3 only (`engine.py`, `fill_resolution.py`, `trade_ledger.py`).
   - **Track 1 bespoke** → H1/H2/H8b/H11/H12 (`track1_hypothesis_sims.simulate_trade_intraday`).
   - **OTE bespoke** → Track 2 step 3/3b/3c (`ote_strategy._find_entry_fill` + step3 `_simulate_exit`).
   - **Bias module:** no fill engine.

2. **Blast radius:** All listed backtest results map to one of the three paradigms above. Track 1 KILLED
   results do **not** share code with OTE or M4, but share the **stop-first dual-touch** simplification class
   with OTE. FVG-specific geometry bug (45.7% wrong-side stop) does **not** apply to Track 1 at that rate.

3. **Geometry guard:** **Absent.** 45.7% of FVG-only setups (2021–2025, n=6,474) have stop on wrong side of
   entry; engine books them. Confirms step 3 artifact root.

4. **Intrabar pessimism:** OTE/Track1 use stop-first when both touched (~4.9% of FVG sample trades).
   Portfolio deflation ~1–2 ticks/trade (borderline vs materiality threshold). H11: 0% dual-hit. M4 ORB uses
   path-based pivot resolution (different rule).

5. **Hand computation:** 11/11 synthetic + real MNQ traces match engine **to the tick** — no arithmetic bugs;
   issues are specification/design.

6. **Costs:** M4 per-fill (default $0); Track 1 $0 coarse; OTE gross in step 3, costs post-hoc in 3b/3c.

**Verdict:** Implementations are internally consistent but **not trustworthy for research pass/fail** until
P0 geometry invariant and fill-paradigm consolidation. Inflation (unguarded geometry) primary; deflation
(stop-first dual-touch) secondary.

**Stop conditions:**
- Hand P&L mismatch: **NOT triggered**
- Intrabar deflation >2 ticks/trade: **BORDERLINE**
- Incoherent geometry unprevented: **TRIGGERED**

**Artifact:** `notebooks/validation/2026-06-07_wave1_engine_integrity_audit.md` (git_sha
`0db224fc2bd1ef320064fb04c9a9a3d9d095e366`)

**Next:** Operator review → P0 geometry guard + fill-engine unification scope (fixes **not** started this pass).

---

## 2026-06-07 — Wave 1 engine remediation (P0 geometry + P1 OTE→M4) — PRE-REGISTERED

**Wave:** Wave 1 (cross-track infrastructure)
**Type:** Engine fix + validation re-run
**Trigger:** Engine integrity audit (2026-06-07): 45.7% FVG-only wrong-side stops booked;
OTE fill logic in untested run-script; three fill paradigms.

**Scope:**
- **P0:** Structural geometry invariant — reject if long stop ≥ entry or target ≤ entry
  (mirror for short). Enforce in M4 bracket validation + OTE setup assembly; count rejects.
- **P1:** Consolidate OTE execution onto M4 BacktestEngine; unified cost model ($1.98 RT,
  tag slippage: 0 entry, 1 tick stop/time, ½ tick target). Signal logic unchanged in
  `ote_strategy.py`; fills in tested `ote_execution.py`.
- **P2 DEFERRED:** Dual-touch stop-first rule not recalibrated.

**Validation re-run (post-fix):**
- OTE 62% full RTH, OTE 70.5% full, FVG-only full — 2020–2026 protocol; Frame B eval
  2021–2025 (2020/2026 partial).
- Compare to step 3c baselines (+$5,099 OTE 62%, −$2,410 OTE 70.5%, +$26,185 FVG-only).

**Stop conditions:**
- OTE 62% geometry reject rate >30%
- Clean OTE 62% Frame B flips negative
- FVG-only does not collapse post-guard
- M4 vs hand-trace P&L mismatch on traced trades

**Date pre-registered:** 2026-06-07

---

## 2026-06-07 — Wave 1 engine remediation (P0 geometry + P1 OTE→M4) — RESULT-LOGGED

**Wave:** Wave 1 (cross-track infrastructure)
**Type:** Engine fix + validation re-run
**Result:** P0/P1 implemented; clean re-run complete. FVG artifact diagnosis **confirmed**.
Geometry guard rejects **45.6%** of OTE 62% sweep-chain attempts (>30% stop — surfaced).

**Clean numbers (Frame B 2021–2025, comm+slip, M4 engine):**
| Config | Step 3c | Clean M4 | Δ |
|--------|--------:|---------:|--:|
| OTE 62% | $5,099/yr | **$4,629/yr** | −$469 |
| OTE 70.5% | −$2,410/yr | **$11,155/yr** | +$13,565 ⚠ |
| FVG-only | $26,185/yr | **$2,798/yr** | −$23,386 |

**Key findings:**
1. FVG-only collapsed from +$26k to +$2.8k — confirms geometry inflation was primary artifact.
2. OTE 62% remains **positive** but lower (−9%); still fails Apex tier-1 DLL at $30K/yr sizing
   (max session loss −$3,855 at qty 6.48).
3. OTE 62% geometry reject rate **45.6%** — economics were partly geometry-inflated; clean number
   still positive.
4. OTE 70.5% **flipped strongly positive** vs step 3c — **requires operator review** (M4 fill path
   vs step 3c bespoke sim divergence, not just geometry guard).
5. P2 dual-touch unchanged.

**Stop conditions:**
- OTE 62% reject >30%: **TRIGGERED** (45.6%)
- OTE 62% Frame B negative: **NOT triggered** ($4,629)
- FVG collapse: **NOT triggered** (artifact confirmed)
- Hand-trace mismatch: **NOT tested in this re-run** (unit tests pass)

**Artifact:** `notebooks/validation/2026-06-07_wave1_engine_remediation_and_ote_rerun.{md,json}`

**Next:** Operator decision on OTE 70.5% parity anomaly; whether OTE 62% ($4.6K Frame B) warrants
account-class survey given DLL breach; P2 only if within ~1 tick/trade of threshold.

---

## 2026-06-07 — Wave 1 geometry-guard causality + validation harness — PRE-REGISTERED

**Wave:** Wave 1 (cross-track infrastructure)
**Type:** Guard verification (A) + standing harness (B)
**Trigger:** OTE 70.5% +$13,565/yr swing post-remediation with 36.5% geometry rejects;
need causality proof before trusting as DLL-fitting candidate.

**Deliverable A:** Guard causality (A1), rejected vs kept characterization (A2),
wrong-side mechanism (A3), OTE 70.5% verdict (A4).

**Deliverable B:** `validation.py` V1–V6 harness wired into M4 BacktestEngine;
convention in ai-project-instructions.

**Stop conditions:** Guard peek; rejected population winning; stop logic bug; harness fail on clean log.

**Date pre-registered:** 2026-06-07

---

## 2026-06-07 — Wave 1 geometry-guard causality + validation harness — RESULT-LOGGED

**Wave:** Wave 1 (cross-track infrastructure)
**Result:** Harness operational (159 tests pass; V1–V6 wired into M4). OTE 70.5% **SUSPECT**
— do not proceed to account-class survey until M4/bespoke parity resolved.

**A1 Causality:** PASS — `check_trade_geometry` uses entry/stop/target only; unit test confirms
same decision regardless of post-entry path.

**A2 Selection bias:** Rejected wrong-side (n=18,667) hypothetical avg net **+$19.48/trade**
(90.3% WR) — guard excludes artifact-class “stop on profit side” winners. Kept (n=12,978)
bespoke-sim avg net **-$3.99/trade**. Structural: rejected entry-vs-stop **-43.9 ticks** vs
kept **+62.4 ticks** (known at entry).

**A3 Mechanism:** 20/20 traces = **shallow_retracement_vs_swept_stop** (not stop-placement bug).

**M4 vs bespoke parity (500 kept sample):** **0/500** exact matches; avg net diff **+$7.70**;
max **$218.44**. +$11,155 Frame B likely M4 fill-path divergence from step 3c, not geometry
selection alone.

**Harness on OTE 70.5% log:** FAIL (V1 — trade-log bracket join incomplete for subset; V2–V5 pass).

**Stop conditions triggered:** rejected_winning (artifact exclusion, expected); harness_fail (V1);
guard_peek NOT triggered; stop_logic_bug NOT triggered.

**Artifact:** `notebooks/validation/2026-06-07_wave1_guard_verification_and_harness.{md,json}`

**Date pre-registered:** 2026-06-07

---

## 2026-06-07 — Wave 1 guard fix + parity + harness-clean OTE — PRE-REGISTERED

**Wave:** Wave 1 (cross-track infrastructure)
**Type:** Guard correctness fix + M4/bespoke parity + clean OTE re-run
**Trigger:** V1 harness FAIL (55% false incoherent on bad trade-log join); kept OTE 70.5%
population loses -$51,793; M4/bespoke 0/500 parity.

**Parts:** (1) Ledger-boundary geometry guard, stop/target in trade log, V1 must pass.
(2) Hand-trace parity resolution (~30 trades). (3) OTE 70.5%, 62%, FVG-only re-run with
passing harness only.

**Stop conditions:** V1 still fails post-fix; hand matches neither engine; any genuine edge.

**Date pre-registered:** 2026-06-07

---

## 2026-06-07 — Wave 1 guard fix + parity + harness-clean OTE — RESULT-LOGGED

**Wave:** Wave 1 (cross-track infrastructure)
**Status:** RESULT-LOGGED
**git_sha:** `0db224fc2bd1ef320064fb04c9a9a3d9d095e366`
**Artifact:** `notebooks/validation/2026-06-07_wave1_guard_fix_parity_clean_ote.md` (+ `.json`)

**Part 1 — Guard fix:** Root cause was trade log missing stop/target columns (V1 used broken setup join → 55% false incoherent). Fix: bracket fields on `SimulatedFill` → `TradeLedger._finalize_round()` rejects incoherent geometry before booking; stop/target/entry_bar on every row. **V1 now passes: 0 incoherent fills in all three configs.**

**Part 2 — Parity:** M4 authoritative. Hand trace (M4-equivalent stop-first + tag slippage + $1.98 RT) matches M4 on 61/90 sampled trades; bespoke legacy sim matches 1/90 (omits exit slippage, ~$7–11/trade divergence).

**Part 3 — Harness-clean OTE (Frame B 2021–2025, 1 MNQ, comm+slip, V1–V6 PASS):**

| Config | Booked | Annual net/MNQ | Ticks/tr | WR | DLL fit |
|--------|--------|----------------|----------|-----|---------|
| OTE 70.5% | 10,680 | +$1,122 | +0.17 | 46.1% | NO (−$14,433 worst session) |
| OTE 62% | 10,859 | +$975 | +0.36 | 40.3% | NO (−$19,123 worst session) |
| FVG-only | 6,878 | +$2,750 | +4.52 | 35.1% | NO (−$8,535 worst session) |

**Verdict:** OTE setup **closed — no trustworthy coherent edge**. Prior +$11,155 OTE 70.5% and FVG-only artifact were wrong-side-stop / harness-join artifacts. Clean booked populations are near breakeven or modestly positive but **fail Apex tier-1 DLL** at $30K/yr sizing. **Pivot:** H7 opening gap or TTrades CISD entry with harness enforced from first run.

**Date run completed:** 2026-06-07

---

## 2026-06-07 — Wave 1 Track 2 — Phase 3 step 3d (realistic exit-structure test) — PRE-REGISTERED

**Wave:** Wave 1, Track 2 — Phase 3 step 3d
**Type:** Pre-registered exit-structure variant test (harness-enforced)
**Trigger:** Clean harness-passing OTE re-run closed strategy as no-edge as built (OTE705
+$1,122/yr, 0.17 ticks/tr). Operator hypothesis: exit structure (swept-extreme stop +
nearest-pool target ≈ 1:1) masks entry edge; 62.7% of coherent trades have stop > 10 pts.

**Entry (frozen):** OTE 70.5% full RTH — same sweep → MSS → displacement → OTE entry as
clean baseline. OTE 62% deferred until 70.5% results logged.

**Pre-registered combinations (5 — bounded, not grid):**
- **C-base:** S1 swept extreme + T1 nearest pool (reference)
- **C-1:** S1 + T4 fixed 2R (structural stop, forced 2:1)
- **C-2:** S2 fixed 10pt + T2 fixed 15pt (1.5R tradeable)
- **C-3:** S3 1.0×ATR(14) + T3 2.0×ATR(14) (regime-adaptive 2:1)
- **C-4:** S2 fixed 10pt + T4 fixed 2R (= 20pt target)

**Running configuration count (deflation N):**
- Step 3: **5** | Step 3b: **+1** → 6 | Step 3c: **+9** → 15 | Step 3d: **+5** → **20 total**

**Gate:** M4 engine, comm+slip, harness V1–V6 must pass before reporting economics.
Frame B 2021–2025 primary; full protocol + 2020/2026 partial separate.

**Stop conditions:** Harness-clean multi-year edge + DLL fit → survey candidate; all combos
near-zero despite reachable targets → OTE entry closed definitively; 2022-only edge → regime
kill; V4 tripwire on >15 ticks/tr → audit before believing.

**Date pre-registered:** 2026-06-07

---

## 2026-06-07 — Wave 1 Track 2 — Phase 3 step 3d (realistic exit-structure test) — RESULT-LOGGED

**Wave:** Wave 1, Track 2 — Phase 3 step 3d (implements pre-registration above)
**Status:** RESULT-LOGGED
**git_sha:** `0db224fc2bd1ef320064fb04c9a9a3d9d095e366`
**Artifact:** `notebooks/validation/2026-06-07_wave1_track2_phase3_step3d_exit_structure.{md,json}`
**Deflation N:** **20** (step3 5 + step3b 1 + step3c 9 + step3d 5)

**Entry frozen:** OTE 70.5% `ote_only` — 12,978 setups passed scan. All 5 combos: harness V1–V6 PASS, 0 incoherent booked trades.

| Combo | Stop + Target | Booked | WR | Ticks/tr | Annual/MNQ | Target hit | DLL |
|-------|---------------|--------|-----|----------|------------|------------|-----|
| C-base | S1 + T1 | 10,680 | 46.1% | +0.17 | +$1,122 | 44.3% | NO |
| C-1 | S1 + T4 (2R) | 10,680 | 34.7% | −1.48 | −$519 | 30.9% | NO |
| C-2 | S2 10pt + T2 15pt | 11,270 | 41.7% | +1.82 | +$1,946 | 40.2% | NO |
| C-3 | S3 ATR + T3 2×ATR | 11,277 | 30.7% | −4.90 | −$4,033 | 29.4% | NO |
| C-4 | S2 10pt + T4 2R | 11,270 | 33.5% | −1.02 | −$732 | 31.2% | NO |

**Diagnostic answers:**
1. **Exit recover edge?** **No.** Best combo C-2 (+$1,946/yr, 1.82 ticks/tr) fails Apex tier-1 DLL; three of five combos are Frame-B losers.
2. **Target-hit vs baseline:** Baseline already hit targets 44% of the time — problem was ~1:1 R:R (median stop ≈ target distance), not unreachable targets. Forced 2R (C-1/C-4) *lowers* target-hit to ~31% and worsens net.
3. **Year concentration:** Not a pure 2022 artifact — C-2 spreads across years but remains too small for account viability.

**Verdict:** OTE **entry has no persistent account-viable edge** independent of exit structure. OTE closes definitively; pivot to H7 opening gap or TTrades CISD. OTE 62% secondary deferred (not run — 70.5% sufficient to kill).

**Date run completed:** 2026-06-07

---

## 2026-06-08 — ORB+Opt3 account-class survey ($50K / $100K / $150K floor-income) — PRE-REGISTERED

**Wave:** Account-class survey (post–Wave 0h; not a new edge hypothesis)
**Structural rationale:** ORB+Opt3 edge is **settled** (~$1,014/yr/MNQ Python M6). Production cut on **$50K** was a **loss-tail vs DLL/TDD** sizing problem, not an edge problem. Larger Apex EOD classes raise trailing DD and profit targets; this survey tests whether the **validated Wave 0 trade log**, sized into larger DD room, clears **$36K/yr floor** net of eval economics at **max sustainable qty** under **R(q)** + **DLL** + **consistency** + **contract-cap** constraints.
**Specification:**
- **Input log:** Wave 0 graded ORB+Opt3 qty=1 trade log (six-year MNQ protocol 2020-01-01 → 2026-04-19); re-run M4 engine only if log diverges **>10%** from ~$1,014/yr/MNQ anchor.
- **Account classes (operator May 2026):** **$50K** TDD **$2K**, target **$3K**, tier-1 DLL **$1K**; **$100K** TDD **$3K**, target **$6K**, tier-1 DLL **$1,750**; **$150K** TDD **$4K**, target **$9K**, tier-1 DLL **$2,500**. PA tier tables from Wave **0e** (`run_wave0e_orb_opt3_survey.py`); eval caps **6 / 8 / 12** mini.
- **Max sustainable qty:** For each class, largest integer **MNQ** such that **R(q) = max(1.5×DD(q), DD(q)+$500) ≤ class TDD** using path **EOD peak-to-trough DD(q)** (flag if ≠ linear **q×DD(1)**); also bound by **worst-session loss ≤ tier-1 DLL**, **consistency** (max NY-day profit ≤ 30% of total backtest profit at q), **PA contract cap** (bottom-tier max mini × 10), and **Gate A** tiered funded survival — report binding constraint; take **MIN**.
- **Funded economics at q_max:** gross and net-of-payout (first **$25K** at 100%, remainder **90%** per annual payout simplification); year-by-year calendar P&amp;L.
- **Eval:** rolling **30 trading-session** windows (Gate B default); pass rate to class profit target without TDD/DLL breach; **eval fee / pass rate** = expected cost per funded account (fees: operator table **$167 / $207 / $297** for 50K/100K/150K — flagged if not on help center).
- **Floor gate:** net funded **≥ $36K/yr** AND eval pass rate **≥ 50%**.
- **Harness:** validation report on any fresh backtest run.
**Primary metric:** Cross-class table — q_max, binding constraint, net $/yr, eval pass rate, eval cost/funded acct, clears floor?, tier reached.
**Pass/fail:** Deployable if **any** class clears floor + eval ≥ 50%; structural wall if **none** and DLL/TDD binds across classes.
**Date pre-registered:** 2026-06-08

---

## 2026-06-08 — ORB+Opt3 account-class survey ($50K / $100K / $150K floor-income) — RESULT-LOGGED

**Wave:** Account-class survey (implements pre-registration above)
**Input:** **Fresh backtest** from `data/raw/mnq/` (26 NT8 exports via `MNQ_CONTRACT_GLOB`); qty=1 ORB+Opt3, 799 trades, **$1,014.16/yr/MNQ** (0% anchor divergence). Eval: **30 trading-session** rolling windows (Gate B default).
**Harness:** **FAIL V1** geometry on all 5 segments (528/528 etc. filled trades flagged — ORB bracket/geometry vs harness V1; V2–V6 pass). Trade log economics match Wave 0; harness fail noted, not a reproduction divergence.
**Consistency (new vs artifact run):** Best NY session **+$3,896** = **61%** of six-year total profit → **strict max sust qty = 0** all classes under 30% consistency rule at mnq=1. Ex-consistency qty (DLL × Gate A): **1 / 2 / 3 MNQ**.
**Cross-class headline:**

| Class | strict q_max | binding | net $/yr (ex-consistency qty) | eval pass (30 sess) | Clears floor? |
|-------|-------------|---------|------------------------------|---------------------|---------------|
| $50K | **0** | **consistency** | **$1,014** @ 1 MNQ | **2.0%** | **NO** |
| $100K | **0** | **consistency** | **$2,028** @ 2 MNQ | **2.0%** | **NO** |
| $150K | **0** | **consistency** | **$3,042** @ 3 MNQ | **2.0%** | **NO** |

**Gate A funded q_max:** $50K **7** MNQ (~$7,099/yr), $100K **11** (~$11,156/yr), $150K **15** (~$15,212/yr) — all **&lt; $36K floor** (gaps **$21K–$29K**).
**Verdict:** **NO** class clears **$36K/yr net + eval ≥ 50%**. Structural wall confirmed on fresh log: **consistency + DLL + low edge density**; larger classes raise Gate A ceiling but **cannot close income gap**.
**Artifact:** `notebooks/validation/2026-06-08_orb_account_class_survey.{md,json}`; `scripts/run_orb_account_class_survey.py`
**Date run completed:** 2026-06-08 (re-run with `data/raw/mnq`)

---

## 2026-06-08 — P2-W2 — tight-loss-tail / arbitrage-resistant hypotheses (N=6) — PRE-REGISTERED

**Wave:** P2-W2  
**Status:** PRE-REGISTERED (no backtest run; spec fixed before screening code).  
**Baseline:** Wave 0 graded ORB+Opt3 (max sustainable qty). ORB is reference, not an income path — closed at **~2%** eval pass at income size; loss tail caps sustainable qty at **5–15 MNQ**.

**Structural rationale:** Tight uniform per-trade loss tail (sizes toward **30+ MNQ** within the **$1K DLL**) → arbitrage-resistant (capacity-constrained / operationally messy / impact-bound) → sufficient frequency for eval-window survival. The **loss-tail-to-edge ratio** against the DD/DLL envelope is the binding constraint, not edge existence alone.

**Protocol / data**

- **Costs (every trade):** **$1.98** RT commission + slippage **1 tick** on stop/time exits, **0.5 tick** on target. Per-MNQ, **$2/pt**. No cost-free numbers.  
- **Apex $50K EOD (corrected):** TDD **$2K** (not $3K), target **$3K**, DLL **$1K** (session-pause). **R(q)** sizing against the **$2K** TDD ceiling per kickoff.  
- **Sizing:** max sustainable qty per kickoff methodology — stop-after-first-loss bound for single-trade-session configs; path-dependent DD sim for multi-trade configs.  
- **Partition:** IS/OOS **60/40** by trade count, chronological. Gate **#1** and sizing run on **IS only**; OOS sealed until a candidate clears all IS gates.  
- **Harness:** **V1–V6** mandatory and passing on every run (mechanical trust only).  
- **Data precondition (blocks first backtest):** confirm raw MNQ loader resolves to the real six-year dataset — ORB survey silently fell back. **H-5** additionally **BLOCKED** pending economic-calendar data (not in repo).

**Hypotheses (operational specs — summary)**

| ID | Idea (short) | Stop / session rule | Target qty | Frequency | Risk / notes |
|----|----------------|---------------------|------------|-----------|--------------|
| **H-1** | Trend micro-pullback continuation; minutes-scale, impact-bound (not daily momentum) | stop **≤ 8–9 pt** vol-gated; stop-after-first-loss | **~30 MNQ** | **300–500/yr** | regime-dependent (needs trend day); cost drag is kill risk |
| **H-2** | Liquidity-vacuum reversion **~11:30–13:30 ET**; thin pocket can't absorb size | stop **6–8 pt**; **1–2** trades/window | **~25–30 MNQ** | **200–350/yr** | is reversion — justify via thin-liquidity structure, not curve fit |
| **H-3** | Failed-breakout fast reclaim; trapped breakout stops fuel reversal | stop **≤ 8–10 pt**; stop-after-first-loss | **~25–30 MNQ** | **250–400/yr** | ≈OTE — tight-reclaim vs swept-extreme stop distinction must hold or it fails identically |
| **H-4** | Opening-auction imbalance reversion (RTH first **5–15 min**) | stop **8–10 pt**; single trade/session | **~33–40 MNQ** | **~250/yr** | ≈ORB — best tail but **1** window/session = eval variance lottery |
| **H-5** | Post-event vol-collapse drift | tight stop; **1** trade/event | **~30 MNQ** | **&lt; 150/yr** | **BLOCKED** (no calendar data); freq too low standalone — portfolio supplement only |
| **H-6** | Prior-session level first-test rejection (PDH/PDL/settle) | tight stop; **1–2** trades/session | **~20–30 MNQ** | **250–400/yr** | weakest moat — most-watched, closest to a clean known pattern |

**Screening gates and decision rules (IS)**

1. **Per-trade expectancy:** net-of-cost per-trade expectancy **&gt; 0** at stop cap → **DEAD** if **≤ 0** (no further budget).  
2. **Max sustainable qty** at stop cap under **R(q)** / DLL / kickoff sizing rule.  
3. **Floor economics:** **≥ $36K/yr** at that qty; profitable **≥ 4/6** yrs.  
4. **OOS + deflated Sharpe + bootstrap CI + walk-forward** — survivors only.

**Primary metric:** net-of-cost graded annual P&amp;L at max sustainable qty (all hypotheses).

**Secondary metrics:** eval pass rate (rolling **30-day** sim), trades/yr, deflated Sharpe (running **N = 13**).

**Statistics (pre-registered for this wave)**

- **Deflated Sharpe:** wave-local **N = 6**; running quant-search **N = Track 1 (7) + W2 (6) = 13**. ICT/OTE configs (**20**) excluded — separate search family (transcript-derived primitives), does not inflate this family's FDR. ORB survey configs excluded — characterization of a known edge, not novel-edge search. Correction applied against running **N = 13**; wave-local **N = 6** reported alongside.

**Correlation accounting:** **H-2 / H-3 / H-4 / H-6** are an overshoot-fade/reversion cluster and will correlate. A single survivor must be shown **not** to be the cluster's shared edge relabeled (variant-multiplicity lesson). **H-1** (continuation) is the only structurally orthogonal entry.

**Date pre-registered:** 2026-06-08

---

## 2026-06-08 — P2-W2 Gate #1 mortality screen (IS partition) — RESULT-LOGGED

**Wave:** P2-W2 (implements pre-registration block above)

**Date run completed:** 2026-06-08

**Scope:** Gate **#1** only — net-of-cost per-trade expectancy on **IS (60%)**; **H-5** skipped (BLOCKED). **OOS 40% sealed.** No sizing / deflated Sharpe / walk-forward.

**Data precondition:** **PASS** — `data/raw/mnq/MNQ *.Last.txt`, **26** contract files, **599,533** RTH bars, **1,561** session dates, **2020-01-02 → 2026-04-17** CT. No Wave-0-artifact fallback.

**Harness:** V1–V6 **PASS** all five configs (V4 threshold **50** ticks — accommodates pre-registered **10pt** stop cap).

**Gate #1 survivors:** **NONE** (0/5)

| ID | IS trades | Net $/trade | Gross $/trade | Cost $/trade | WR (net) | Verdict |
|----|-----------|-------------|---------------|--------------|----------|---------|
| **H-1** | 7 | **−$17.69** | −$15.71 | $1.98 | 0.0% | **DEAD** |
| **H-2** | 726 | **−$5.34** | −$3.36 | $1.98 | 23.1% | **DEAD** |
| **H-3** | 738 | **−$19.61** | −$17.63 | $1.98 | 4.6% | **DEAD** |
| **H-4** | 46 | **−$3.34** | −$1.36 | $1.98 | 21.7% | **DEAD** |
| **H-6** | 282 | **−$12.79** | −$10.81 | $1.98 | 4.3% | **DEAD** |

**IS/OOS boundaries (last IS exit):** H-1 **2024-03-01**; H-2 **2023-06-15**; H-3 **2023-08-17**; H-4 **2023-06-26**; H-6 **2023-05-31** (America/Chicago offset timestamps in artifact).

**Operator flags:** **H-1** frequency **12** total trades over six years — below pre-registered **300–500/yr** band even if edge existed; gate #1 kill is moot for sizing. **H-2** least-negative net (**−$5.34**) but still **DEAD**; reversion cluster (**H-2/H-3/H-4/H-6**) uniformly net-negative on IS. **No survivor** → wave **Gate #2–#4 not authorized** on these specs without operator redesign.

**Artifacts:** `notebooks/validation/2026-06-08_p2w2_gate1_mortality_screen.{md,json}`; `scripts/run_p2w2_gate1_mortality_screen.py`; `src/quant_research/research_p2w2/`

---

## 2026-06-08 — P2-W3 — OR-extreme reclaim continuation (N=1) — PRE-REGISTERED

**Wave:** P2-W3  
**Hypothesis:** **H-7** (single-hypothesis wave; canonical id — no prior **H-7** in this log)  
**Status:** PRE-REGISTERED (no backtest run; spec fixed before screening code).  
**Baseline:** Wave 0 graded ORB+Opt3 (max sustainable qty), unchanged.

**Structural rationale:** When price breaks an opening-range extreme, reverses back through it intrabar, and a **5m** bar closes back across the extreme, that reclaim marks **CONTINUATION** in the breakout direction — not reversion back into the range. Enter in the breakout direction on the reclaim; stop tight on the reclaim level (the failed-reversal pivot). W2 **H-3** registered the opposite thesis (failed-breakout reclaim → fade into range) and produced **95%** stop-out / **4.6%** win rate on **738** IS trades — sign audit confirmed entries were on the reversion side as designed (forensic **2026-06-08**, git **`b833904`**). The uniformity of the stop-out is the signature of trading the wrong side of a real directional tendency: the reclaim resolves **as continuation**. The broader W2 reversion/fade cluster (**H-2**, **H-3**, **H-6**) was also negative, consistent with fade being structurally dead on MNQ intraday at realistic cost. **H-7** tests the inverse directly and cleanly.

**Motivation note (not a pre-registered metric):** An arithmetic direction-flip of H-3's IS trades showed **+$15.65/trade**. This is **UPPER-BIASED** and not tradable — it negates gross P&amp;L on the original entry/exit prices without re-walking bars, so stops and targets do not swap correctly. It motivates **H-7**; it does **not** set its expected edge. **H-7**'s edge must come from a real IS run with exits walked on the continuation geometry.

**Design-brief alignment:** Tight uniform loss tail (stop on reclaim level, **~8–10 pt** cap, stop-after-first-loss session) → sizes toward **30+ MNQ** within **$1K DLL**; continuation-after-failed-counter is impact-bound / turnover-driven, not a clean scalable factor (arbitrage-resistant); frequency depends on reclaim event rate — **report trades/yr explicitly** (first-class constraint); W2 **H-3** fired **1,230** times over six years so frequency is expected adequate.

**Relationship to prior hypotheses:** **H-7** supersedes W2 **H-1** (continuation thesis whose trend-day gate was too strict — **12** fires / 6yr, closed). **H-7** uses **H-3**'s reclaim trigger with **inverted direction** rather than **H-1**'s trend-gate trigger. **H-1** is **not** carried forward.

**Protocol / data**

- **Costs (every trade):** **$1.98** RT commission + slippage **1 tick** on stop/time exits, **0.5 tick** on target. Per-MNQ, **$2/pt**. No cost-free numbers.  
- **Apex $50K EOD (corrected):** TDD **$2K**, target **$3K**, DLL **$1K** (session-pause). **R(q)** sizing against **$2K** TDD ceiling per kickoff.  
- **Sizing:** max sustainable qty per kickoff methodology — stop-after-first-loss bound.  
- **Partition:** IS/OOS **60/40** by trade count, chronological. Gate **#1** and sizing run on **IS only**; OOS sealed until **H-7** clears all IS gates.  
- **Harness:** **V1–V6** mandatory and passing on every run (mechanical trust only).  
- **Data precondition (blocks first backtest):** confirm raw MNQ loader resolves to the real six-year dataset (print path, bar count, range) — do not run on fallback.

**H-7 operational specification — OR-extreme reclaim continuation**

| Field | Spec |
|-------|------|
| **Trigger** | Price breaks **09:30–10:00 ET** OR high or low; later **5m** close reclaims back across the broken extreme (same bar construction as W2 **H-3**, **opposite** direction) |
| **Direction** | **WITH** the original breakout (continuation), not fade into range |
| **Entry** | On reclaim **5m** close, in breakout direction |
| **Stop** | Tight on reclaim level / failed-reversal pivot; cap **~8–10 pt** |
| **Target** | Continuation geometry TBD at implementation — must be locked before Gate **#1** run |
| **Session rule** | Stop-after-first-loss; **≤ 1** trade/session |
| **Frequency (report)** | Trades/yr is a **first-class** reported constraint (H-3 analog **~205/yr** over six years) |

**Screening gates and decision rules (IS)**

1. **Per-trade expectancy:** net-of-cost per-trade expectancy **&gt; 0** at stop cap → **DEAD** if **≤ 0** (no further budget).  
2. **Max sustainable qty** at stop cap under **R(q)** / DLL / kickoff sizing rule.  
3. **Floor economics:** **≥ $36K/yr** at that qty; profitable **≥ 4/6** yrs.  
4. **OOS + deflated Sharpe + bootstrap CI + walk-forward** — only if IS gates clear.

**Primary metric:** net-of-cost graded annual P&amp;L at max sustainable qty.

**Secondary metrics:** eval pass rate (rolling **30-day** sim), trades/yr, deflated Sharpe (running **N = 14**).

**Statistics (pre-registered for this wave)**

- **Deflated Sharpe:** wave-local **N = 1**; running quant-search **N = Track 1 (7) + W2 (6) + W3 (1) = 14**. **H-7** increments **N** as a **new** structural thesis (continuation), **not** a free rerun of **H-3** — a sign-corrected rerun of a registered hypothesis would not increment, but this is a distinct thesis on the opposite side of the market and is counted. ICT/OTE configs (**20**) and ORB survey configs remain excluded per W2 rationale (separate search family / known-edge characterization). Correction applied against running **N = 14**; wave-local **N = 1** reported alongside.

**Date pre-registered:** 2026-06-08

---

## 2026-06-08 — M4 validation harness V7 engine provenance guard — RESULT-LOGGED

**Wave:** Cross-track infrastructure (Wave 1 harness extension; closes P2-W2/W3 bypass class)

**Date run completed:** 2026-06-08

**Trigger:** P2-W3 H-7 forensic (`021d430`) — bespoke `simulate_p2_trade` passed V1–V6 while carrying entry-bar look-ahead; third script-local fill bypass after OTE and Track 1 (lessons-log 2026-06-08).

**Implementation:**

- `src/quant_research/backtest/provenance.py` — `M4_ENGINE_PROVENANCE_MARKER` + engine-issued ledger seal (singleton identity).
- `TradeLedger` stamps `mfa_engine_provenance` on every finalized row when constructed with the engine seal.
- `BacktestEngine` passes `engine_ledger_seal()` at ledger construction (sole producer path).
- `validation.py` **V7** — fails logs missing column or foreign marker; reports offending `trade_id` indices.
- Schema: `mfa_engine_provenance` column added to canonical trade log.

**Tests:** M4 engine run → V7 PASS; fabricated / mixed / missing-marker logs → V7 FAIL with indices; V1–V6 regression green.

**Convention:** `docs/ai-project-instructions.md` updated — trustworthy results require passing **V1–V7**; strategy modules supply signal logic only; fills route through `engine.py`.

**Implication:** P2-W2/W3 harness PASS status downgraded to "coherent bespoke walker" — V7 would fail those runs by construction. No P2 quant result trusted until re-run on M4 engine.

**Artifact:** `src/quant_research/backtest/{provenance,validation,trade_ledger,schema,engine}.py`; `tests/backtest/test_validation.py`; `docs/ai-project-instructions.md`; draft lessons note `docs/drafts/2026-06-08_lessons-log-v7-provenance-draft.md` (approval pending)

---

## 2026-06-08 — P2-W3 / H-7 Gate #1 mortality screen (IS partition) — RESULT-LOGGED

**Wave:** P2-W3 (implements pre-registration block above)

**Date run completed:** 2026-06-08

**Scope:** Gate **#1** only — net-of-cost per-trade expectancy on **IS (60%)**; **OOS 40% sealed.** No sizing / deflated Sharpe / walk-forward.

**Data precondition:** **PASS** — `data/raw/mnq/MNQ *.Last.txt`, **26** contract files, **599,533** RTH bars, **1,561** session dates, **2020-01-02 → 2026-04-17** CT.

**Harness:** V1–V6 **PASS** on H-7 run.

**H-3 trigger parity:** **PASS** — **1,253** shared reclaim triggers (identical detection); H-3 maps **1,230** trades (**23** structural geometry rejects); H-7 maps all **1,253** (fixed **10/20** pt bracket). Inversion proof on five forensic dates: all **True** (opposite direction, same reclaim bar close).

**Gate #1 verdict:** **SURVIVOR** — net **+$20.85/trade** on **751** IS trades.

| Metric | Value |
|--------|-------|
| Total / IS / OOS (sealed) | **1,253** / **751** / **502** |
| IS/OOS boundary (last IS exit) | **2023-08-28** 11:00 CT |
| Gross expectancy/trade | **+$22.83** |
| Cost/trade | **$1.98** |
| **Net expectancy/trade** | **+$20.85** |
| Win rate (net) | **74.8%** |
| Avg win / avg loss (net) | **+$34.87** / **−$20.84** |
| Max / P95 single-trade loss (net) | **$22.48** / **$22.48** |
| Trades/yr (protocol) | **198.9** |

**Stop / target / time:** fixed **10 pt** stop, **20 pt** (2R) target; **12:00 ET** time stop (same as H-3).

**Flip motivation cross-check:** H-3 arithmetic flip (upper-biased) **+$15.65/trade** IS vs H-7 walked continuation **+$20.85/trade** IS (gap **+$5.20**). Result **above** the flip warrants skeptical exit-walk review per pre-registration note; not treated as confirmation of flip arithmetic.

**Next authorized step:** Gate **#2** (max sustainable qty at **10 pt** stop) on IS — only because Gate **#1** cleared.

**Artifacts:** `notebooks/validation/2026-06-08_p2w3_h7_gate1_mortality_screen.{md,json}`; `scripts/run_p2w3_h7_gate1_mortality_screen.py`; `src/quant_research/research_p2w2/hypothesis_sims.py`

**Status note (2026-06-08):** Gate #1 **SURVIVOR** **VOID** — bespoke `simulate_p2_trade` entry-bar look-ahead (forensic `955dcbb`); see M4 re-run entry below.

---

## 2026-06-08 — P2-W2/W3 M4 engine migration + Gate #1 re-run (IS) — RESULT-LOGGED

**Wave:** P2-W2 (H-1..H-6) + P2-W3 (H-7)

**Date run completed:** 2026-06-08

**Trigger:** V7 provenance guard (`fb264ac`) — trustworthy quant results require M4 `BacktestEngine` fill path; bespoke `simulate_p2_trade` deleted.

**Migration:**

- Signal logic unchanged in `research_p2w2/hypothesis_sims.py` (`scan_h*` → `P2Setup`).
- Fills routed through `p2_execution.py` (`P2SetupRunner` + `BacktestEngine`); entry on reclaim 5m close; brackets arm entry+1.
- Single cost model: **$1.98 RT** + slippage (1 tick stop/time, 0.5 tick target) via `P2_W2_BACKTEST_CONFIG`.
- `simulate_p2_trade`, `P2Trade`, `trades_to_harness_log`, `run_hypothesis` walker **removed**; legacy gate1/forensic scripts **RETIRED** (loud exit → `run_p2_m4_gate1_rerun.py`).

**Harness:** **V1–V7 PASS** on all six hypotheses (IS partition).

**Gate #1 — M4 engine (IS 60%) vs bespoke walker anchor:**

| ID | Walker net/tr | M4 net/tr | M4 WR | M4 IS trades | Verdict | V7 |
|----|---------------|-----------|-------|--------------|---------|-----|
| H-1 | −$17.69 | +$24.81 | 57.1% | 7 | SURVIVOR | PASS |
| H-2 | −$5.34 | −$1.06 | 45.9% | 726 | DEAD | PASS |
| H-3 | −$19.61 | −$1.00 | 48.0% | 735 | DEAD | PASS |
| H-4 | −$3.34 | +$23.92 | 58.7% | 46 | SURVIVOR | PASS |
| H-6 | −$12.79 | −$20.32 | 43.3% | 282 | DEAD | PASS |
| H-7 | +$20.85 *(void)* | −$4.01 | 45.9% | 750 | DEAD | PASS |

**H-7 proof-of-migration:** M4 **−$4.01/tr** ≠ walker **+$20.85/tr**; aligns with forensic corrected **−$2.41/tr** (next-bar bracket), not inflated gate.

**REVIEW flags (not hard-stop):** H-1 and H-4 flipped negative→positive on M4 — low IS trade counts (7 / 46); do **not** treat as trusted edge without further validation.

**W2/W3 corrected verdicts on trusted path:** H-2, H-3, H-6, H-7 **DEAD**; H-1/H-4 **SURVIVOR** on M4 but flagged for partition noise review. OOS **sealed**.

**Artifacts:** `notebooks/validation/2026-06-08_p2_m4_gate1_rerun.{md,json}`; `scripts/run_p2_m4_gate1_rerun.py`; `src/quant_research/research_p2w2/{hypothesis_sims,p2_execution,p2_setup,metrics,costs}.py`

**Execution `git` SHA:** `1fe521b`

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
