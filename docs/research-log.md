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
