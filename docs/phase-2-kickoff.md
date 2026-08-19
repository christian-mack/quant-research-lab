# Phase 2 Kickoff — Flux V2 / Income-Gap Research

**Status:** Entry artifact for Phase 2 (fresh-chat startup)
**Date:** May 2026
**Owner:** Christian
**Related:** `docs/program-charter.md`, `docs/lessons-log.md`, `docs/current-working-plan.md`, `docs/research-log.md`, `docs/orb_opt3_phase2_closeout.md`, `docs/ai-project-instructions.md`

---

## Program state summary

**Phase 1 is complete** per the amended milestone gate (M1–M7 core path; M8/M9 minimal scope documented in `docs/phase-1-detailed-plan.md` and lessons log **2026-05-14**).

**Wave 0h (2026-05-17):** **ORB+Opt3 repair** within Phase **2** is **closed** by operator decision (see `docs/orb_opt3_phase2_closeout.md`, `docs/research-log.md` Wave **0h**, `docs/lessons-log.md`). **Active Phase 2 work** is **new-strategy search** under the same Apex EOD research stack: candidates must clear **joint gates** (funded survival + block bootstrap ≥ **80%** + eval ≥ **50%**) and meet the **floor economics** tier (≥ **$36K/yr** funded P&amp;L at sized quantity) unless the operator registers an exception. The **Wave 0** graded ORB+Opt3 artifact remains the **implicit economic floor** (**no joint pass** / **~$0** relative to that bar for replacement economics).

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
| **ORB+Opt3 (Wave 0 graded, six-year MNQ protocol)** | Under tiered PA + two-gate methodology (**Waves 0c–0g**), **no** configuration clears **joint gates** (funded + bootstrap + eval) at meaningful size; **2020 exclusion** does **not** restore **funded** survival (**Wave 0g**). **ORB+Opt3 repair** is **closed** within Phase **2** (**Wave 0h**); live production may still run ORB+Opt3 until a **replacement** is validated. See `docs/orb_opt3_phase2_closeout.md`. |
| **Economics (static backtest, pre-payout)** | Historical **qty = 3** production snapshot (~**$3K/yr/account** class backtest economics) is **not** the Phase **2** target object — it is **continuity context** only (see `docs/program-charter.md`, lessons log **2026-05-13**). |
| **Python vs NT8** | Research rerun is within **~6.8%** of the NT8 reference on a **per-contract** basis (RTH-only protocol; `docs/m6-nt8-reproduction.md`). Per-contract behavior remains the input to **sizing-scaled** grading for **any** strategy. |
| **Live / operational** | **Trade frequency** and **pre-lock tail** at **sized qty** remain first-class risks for **new** hypotheses (`docs/orb_opt3_phase2_closeout.md`, Wave **0h** session-loss diagnostic). |

---

## Per-account income gap

- **Charter engineering target:** **$65,000–$100,000/yr net per funded account** (after payout splits).
- **Phase 2 compares apples to apples:** Each **candidate strategy** is evaluated at its **funded q_max (Gate A)** under the relevant Apex class rules, with **eval pass rate (Gate B)** and **bootstrap** where pre-registered — not at an arbitrary fixed qty.
- **Phase 2 primary success definition (reframed post–Wave 0h):** Identify **at least one** strategy configuration that **passes all joint research gates** (**funded survival** + **bootstrap ≥ 80%** + **eval ≥ 50%** on the rolling-window spec) **and** achieves **average funded P&amp;L ≥ floor tier ($36K/yr)** at the sized quantity, on the standard six-year MNQ protocol (unless a narrower window is pre-registered). **Target ($60K/yr)** and **stretch ($100K/yr)** tiers remain aspirational comparables.
- **Implicit floor vs Wave 0:** The **Wave 0** graded **ORB+Opt3** baseline clears **none** of the joint gates at useful economics — treat that as the **“better than nothing”** research floor for **replacement** strategies.
- **Charter alignment:** `docs/program-charter.md` Phase **2** still lists an **≥ X% improvement vs ORB+Opt3** milestone gate; **numeric X** and formal charter text should be **reconciled** with this **joint-gate + $36K/yr** operational definition on the next operator pass (**lessons log** **2026-05-17** Wave **0h**).

**Gap:** Closing a **meaningful fraction** of the distance from **successful joint-gate candidate → charter $65K–$100K/yr** remains the program burden. Success is judged against **aggregate per-account economics at sustainable sizing**, not a single satisfying backtest curve at a hand-picked qty.

Phase 2 must close **a meaningful fraction** of this gap — not merely ship marginal tweaks. **ORB+Opt3 repair** is **not** the active Phase **2** thread (**Wave 0h**).

---

## Phase 2 grading framework (two gates — funded survival vs eval)

**Principle:** **Quantity is a consequence of path-dependent firm rules, not an arbitrary input.** Phase 2 distinguishes **(A) funded-account survival** on the full backtest path from **(B) eval-style pass rate** in rolling windows. They use the **same** Apex $50K EOD rule class documented in `docs/ai-project-instructions.md` but answer **different questions** — do **not** conflate them into a single **R(q)** DD-margin formula for grading.

### Apex $50K EOD parameters (research default)

| Rule | Value |
|------|--------|
| Starting balance | **$50,000** |
| Pre-lock trailing | Floor **trails $1-for-$1** with equity high water: **allowed minimum = HWM − $2,000** (initial floor **$48,000**) |
| Lock | When **HWM ≥ $52,000**, floor **locks permanently at $50,000** |
| Breach | Pre-lock: **equity &lt; HWM − $2,000**; post-lock: **equity &lt; $50,000** |
| Profit target (eval) | Account reaches **$53,000** (**+$3,000** vs start) |
| DLL | **$1,000** max realized loss per **America/New_York** calendar day |

Simulations must enforce **both** pre-lock and post-lock failure modes and **DLL** where applicable.

### Gate A — Funded survival (six-year path)

On the **full** standard-protocol backtest, at integer quantity **q**: apply scaled realized P&amp;L **in time order** (session-close / daily aggregation is acceptable if documented; trade-by-trade is stricter for intraday path — match the research artifact). **Pass** if the account **never** breaches trailing/post-lock rules and (when modeled) **never** fails **DLL**. Report **funded q_max** = largest **q** that passes (or **none**).

Optional **internal** sizing margins (e.g. legacy **R(q) = max(1.5×DD, DD+$500)** against a notional ceiling) may still be used for **internal** stress screens — they are **not** substitutes for **Gate A** unless explicitly pre-registered.

### Gate B — Eval pass rate (rolling windows)

**Rolling windows** (default: **30 trading sessions**, advance **1 session**, drop partial tails; pre-register changes in `docs/research-log.md`). **Pass** a window if the simulated account reaches the **$3,000** profit target (**$53,000** equity) **without** trailing/post-lock breach and **without** **DLL** failure, under the same Apex rules. Report **passing windows / total** at each **q** of interest.

At the graded quantity, report **eval pass rate at funded q_max** as the headline operating statistic alongside **Gate A**.

### Legacy Wave 0 **R(q)** (DD margin) — optional screen only

The expression **R(q) = max(1.5 × DD(q), DD(q) + $500)** compared to a notional drawdown **ceiling** was a **Wave 0 research convenience** using **incorrect** Apex trail assumptions in early artifacts. It remains an **optional** crude screen against backtested **DD(q)**; **graded** sizing for Phase 2 baseline work should use **Gate A / Gate B** with the **$2K / $52K lock / $50K floor** rules above.

**DD scaling:** **DD(q) ≈ q × DD(1)** remains the default *economic* linearity check; **Gate A** is authoritative for firm-rule survival.

**Wave 0 (mandatory before hypothesis waves — superseded by Waves 0c–0h):**

Graded **ORB+Opt3** under **Gate A** / **Gate B** + **tiered PA** + **bootstrap** is **documented** in **`docs/research-log.md`** (**Waves 0c–0h**) and summarized in **`docs/orb_opt3_phase2_closeout.md`**. **ORB+Opt3 repair** within Phase **2** is **closed**; **Wave 1+** hypotheses compare against this artifact as the **reference** and **implicit floor**, not as a configuration that must be “fixed forward.”

Tight stops and high win rates can support **higher** sustainable qty than wide-stop, lower-win-rate structures — **both** are legitimate; each graded strategy is scored at **its** sustainable size.

| Tier | Criteria (all at **funded q_max** unless noted) |
|------|--------------------------------------------------------|
| **Floor** (acceptable minimum) | **Joint gates:** funded survival + **bootstrap ≥ 80%** + **eval ≥ 50%** (rolling **30-session** windows unless pre-registered). **Economics:** average funded P&amp;L **≥ $36K/yr** (~**$3K/month**); profitable **≥ 4 of 6** years; edge survives **deflated Sharpe** (or agreed multiple-comparisons correction). |
| **Target** (genuinely good) | Eval pass rate **≥ 70%**; average funded P&L **≥ $60K/yr**; profitable **≥ 5 of 6** years; **low correlation** with existing **portfolio** strategies. |
| **Stretch** (transformative) | Eval pass rate **≥ 80%**; average funded P&L **≥ $100K/yr**; profitable **all 6** years; **stacks** with portfolio strategies (combined / displaced economics documented). |

**Eval pass rate column:** Use **live/eval** sample when sufficient; otherwise the **rolling 30-session backtest simulation** at **funded q_max** (and optionally other **q** for diagnostics). The “30 days” floor wording aligns with that window length (sessions, not calendar days).

**Live vs backtest:** Backtest establishes **funded q_max** and long-horizon economics; **eval pass rate** and **funded P&L** come from **live/eval** when the sample is large enough — otherwise use the **rolling 30-session backtest simulation** rule above (pre-registered window spec).

---

## Phase 2 framing

Phase 2 is **ground-up pattern and configuration discovery** on **~6 years of MNQ** data using the Phase 1 environment — **not** “extend Flux with one more module by default.” **After Wave 0h,** the **center of gravity** is **new-strategy search**: any **evidence-backed** approach (new logic, modules only if justified, risk shaping, frequency redesign, filters) that clears **`program-charter.md`**-aligned acceptance and the **joint gates + floor economics** definition above. **ORB+Opt3** remains **live Flux V1** and a **frozen research reference** until replaced in production.

The **V2 starter packet** mental model remains useful:

- **Phase 0 (done):** Data infrastructure and research platform.
- **Phase 1 (this program’s Phase 2 entry):** Pattern discovery and hypothesis testing.
- **Phase 2:** Strategy development from validated patterns.
- **Phase 3:** Integration and deployment planning.

**Updated mantra:** discover **any configurations** that **pass joint Apex EOD research gates** and **meet floor economics**, closing income gap toward charter targets — with **sizing** set by **funded survival (Gate A)** and **eval / bootstrap** (as pre-registered), not by fixing qty a priori.

The self-deprecated `flux-v2-module-search-starter.md` primer that previously held supplemental research-process detail was **removed from the repo** in `ae2fa83` (2026-07-29). **This document is authoritative** on Phase 2 framing; `docs/orb_opt3_phase2_closeout.md` is authoritative on the ORB chapter boundary.

---

## Charter minimum viable edge (new modules, normalized)

When the winning path includes a **new module**, `docs/program-charter.md` still specifies **minimum viable edge** for **go/no-go on that module** (OOS WR **≥ 57%**, edge over BE **≥ +3pp**, P&L **≥ $5K/yr** at **1 NQ**, trades **≥ 80/yr**, profitable **≥ 4 of 6** years). Treat that block as a **normalized isolation screen** at **one contract** (or per-contract analog) before integration and **displacement** tests — **not** a substitute for the **Phase 2 grading table** above, which always applies at **funded q_max**.

**Program success** remains **closing the income gap** under the **floor / target / stretch** framework; that may require **multiple strategies** and **portfolio** construction, not a single module clearing MV edge in isolation.

---

## Research methodology principles

All of the following are **defaults** unless the operator explicitly approves an exception (documented in the lessons log):

1. **Pre-registration:** Hypotheses and primary metrics are stated **before** the backtest run that tests them.
2. **IS / OOS:** **60/40 split by trade count** (or charter-aligned variant if superseded — document if changed).
3. **Multiple testing:** **Deflated Sharpe** (or equivalent Bailey–López de Prado–style correction) across the **set of hypotheses tested** in a research **wave**, with **N = wave size** (see `docs/research-log.md`). **Per-instrument N:** MNQ and MES each maintain a **separate** running quant-search count — see **MNQ + MES dual-instrument search** below.
4. **Uncertainty:** **Bootstrap confidence intervals** on key metrics where applicable.
5. **Temporal robustness:** **Walk-forward** validation for candidates that survive initial screens.
6. **Structural rationale:** Patterns must have a **structural / behavioral reason**, not only favorable equity curves.
7. **Sustainable sizing:** Every graded run reports **funded q_max (Gate A)** and **eval pass rate at that qty (Gate B)** under the Apex EOD rules for the **account class** under test (`docs/ai-project-instructions.md` for **$50K** shorthand; **tiered PA** per **Wave 0e+** when surveying **25K–150K**); include **bootstrap** when pre-registered. Headline P&amp;L targets assume that pair unless pre-registered otherwise.

### MNQ + MES dual-instrument search (parallel discovery surfaces)

**Default from 2026-06-08** unless the operator pre-registers an exception:

- **MNQ** and **MES** are treated as **two independent search surfaces**, each with its own **running quant-search N** for deflated-Sharpe correction.
- A survivor is deflated against the count of hypotheses tried on **its instrument only** — **not** a pooled MNQ+MES total. *Rationale:* deflated Sharpe corrects for trials in the search family that produced the result; the MNQ search space and the MES search space are separate families.
- Each hypothesis is **pre-registered per instrument** it is tried on. An idea that fails on one instrument and is subsequently tried on the other **increments the other instrument's running N** (no cross-instrument salvage / no peeking).
- **Goal framing:** MES is a **genuine parallel discovery surface** — find edge that may exist on MES and not MNQ via their **~5–15% structural residual** — **not** a robustness check on MNQ.
- **Caution:** MES starts at **N = 0**, so identical ideas receive **lighter deflation** on MES than MNQ. An MES-only survivor may be partly a lighter-correction artifact; require **walk-forward + structural rationale** before trusting an MES-only result.

**Per-instrument economics (mandatory in every graded run):**

| Instrument | Point value | Tick value |
|------------|-------------|------------|
| **MNQ** | **$2/pt** | **$0.50/tick** |
| **MES** | **$5/pt** | **$1.25/tick** |

- **Cost convention unchanged:** **$1.98 RT** + slippage **1 tick** stop/time, **0.5 tick** target — slippage expressed in **ticks** so it scales to each instrument's tick value automatically (**do not** hardcode a dollar slippage).
- **max sustainable qty** computed **per instrument** against that instrument's **DLL/TDD** headroom. The same stop in **points** is a larger dollar risk on MES, so MES sustainable qty will generally be **lower** for the same strategy.

**Dual-instrument run preconditions (hard-stop):**

- Every dual-instrument run **hard-stops** unless **both** loaders resolve to real datasets (print path, contract file count, bar count, date range, session alignment for each).
- MES point value (**$5/pt**) and tick value (**$1.25**) must be **verified in the engine cost config** before any MES economic number is trusted — a wrong **$/pt** silently corrupts all MES P&amp;L. Print the configured values in the precondition block.

**Running N state:** recorded in **`docs/research-log.md`** dated convention entry (updated when a wave completes on either instrument).

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
3. **`docs/phase-2-kickoff.md`** (this document) — intent, **two-gate** grading, methodology, roles, **Wave 0 / 0c** baseline.
4. **`docs/research-log.md`** — append-only pre-registration and results (**wave** = deflated Sharpe **N**).
5. **`docs/orb_opt3_phase2_closeout.md`** — ORB+Opt3 chapter boundary: what was ruled out, what was never explored, production status.
6. `docs/ai-project-instructions.md` — agent and documentation conventions (incl. Apex **$50K EOD**: **$2K** trailing pre-lock, **$52K** lock, **$50K** static floor, **$3K** profit target, **$1K** DLL).

Supporting: `docs/phase-1-detailed-plan.md` (what was built), `docs/m6-nt8-reproduction.md` (parity anchor), `docs/nt8-backtest-methodology.md` (NT8 reference protocol).

---

## First-session priorities (Phase 2)

1. Read **`docs/orb_opt3_phase2_closeout.md`** and **`docs/research-log.md`** (Waves **0e–0h**) for the **ORB+Opt3** boundary conditions and **session-loss tail** vs **TDD**.
2. Re-read charter Phase **2** for any remaining stale “must improve ORB” language; **`docs/phase-2-kickoff.md`** + **close-out** supersede for the **success** definition. (Charter still carries the **≥ X% vs ORB** framing — realignment is an open operator edit per lessons log **2026-05-17**.)
3. **Pre-register** the **first new-strategy hypothesis wave** (**5–10** ideas) in **`docs/research-log.md`** before runs; include **per-session tail** screens where relevant (**Wave 0h** JSON agenda).
4. Agree how **findings** are **documented and surfaced** (summary format, pass/fail, links to trade logs / reports).

---

## Closure

When this document and the Phase 2 **`docs/current-working-plan.md`** are committed to **main**, Phase 1 closure is **administratively complete** and Phase 2 work may proceed in dedicated chats with clean context.
