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

**Execution `git` metadata:** `git_sha` = `03df8667945f942786b8ffbc32c20f6c703a3bf2` (amended commit incl. artifacts); **`git_dirty`:** see JSON — may read **true** if unrelated untracked files exist in the workspace.

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

**Artifacts:**  
- `notebooks/validation/2026-05-16_wave0b_rq_methodology.md`  
- `notebooks/validation/2026-05-16_wave0b_rq_methodology.json`  
- `scripts/run_wave0b_rq_methodology.py`  
- `src/quant_research/statistics/apex_eod_trailing.py`  

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
