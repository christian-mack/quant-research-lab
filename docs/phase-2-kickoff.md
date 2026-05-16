# Phase 2 Kickoff — Flux V2 / Income-Gap Research

**Status:** Entry artifact for Phase 2 (fresh-chat startup)
**Date:** May 2026
**Owner:** Christian
**Related:** `docs/program-charter.md`, `docs/lessons-log.md`, `docs/current-working-plan.md`, `docs/research-log.md`, `flux-v2-module-search-starter.md` (repo root), `docs/ai-project-instructions.md`

---

## Program state summary

**Phase 1 is complete** per the amended milestone gate (M1–M7 core path; M8/M9 minimal scope documented in `docs/phase-1-detailed-plan.md` and lessons log **2026-05-14**).

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
| **Economics (static backtest, pre-payout)** | **ORB+Opt3** at **qty = 3** reflects an **operator/production** funded sizing choice, not a research **graded** size. At that snapshot, NT8-class reference economics are on the order of **~$3,265/yr per account** (~$1,088.50/yr per contract × 3 — see `docs/program-charter.md` and lessons log **2026-05-13**). **Do not** infer floor/target/stretch pass or fail from this row alone — see **funded q_max (Gate A)** grading below. |
| **Python vs NT8** | Research rerun is within **~6.8%** of the NT8 reference on a **per-contract** basis (RTH-only protocol; `docs/m6-nt8-reproduction.md`). Per-contract behavior is the input to **sizing-scaled** graded P&L once **funded q_max** is known. |
| **Live / operational** | Even when edge appears real in backtest, **trade frequency** for the current ORB+Opt3 configuration appears **structurally low** for prop **eval/funded window** dynamics: variance can dominate short horizons until sample size catches up — a concern **alongside** economically scaled grading. |

---

## Per-account income gap

- **Charter engineering target:** **$65,000–$100,000/yr net per funded account** (after payout splits).
- **Phase 2 compares apples to apples:** Strategies (including **ORB+Opt3** as baseline) are evaluated at each strategy’s **funded q_max (Gate A)**, not at an arbitrary fixed qty (see below). The **~$3,265/yr at qty = 3** figure is a **historical production snapshot** for continuity with prior analysis; it is **not** the graded economic anchor until **ORB+Opt3** is re-run under the **two-gate** methodology.
- **Gap:** Closing a **meaningful fraction** of the distance from **graded baseline → charter target range** is the program burden. Order-of-magnitude tension at legacy snapshot sizing (e.g. **~20×** vs $65K+ if that snapshot were representative) illustrates scale of ambition; **graded** baseline may differ once **funded q_max** sizing is applied.

Phase 2 must close **a meaningful fraction** of this gap — not merely ship marginal tweaks. Success is judged against **aggregate per-account economics at sustainable sizing**, not a single satisfying backtest curve at a hand-picked qty.

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

**Wave 0 (mandatory before hypothesis waves — re-baselined Wave 0c):**

**Re-run ORB+Opt3** under **Gate A** and **Gate B** with the corrected Apex rules and document **(funded q_max, eval pass rate at funded q_max)** plus economics at **funded q_max**. Earlier Wave 0 / 0b artifacts that assumed **$3K** trail and **+$100** lock are **obsolete** for firm-rule conclusions (see `docs/lessons-log.md`).

Tight stops and high win rates can support **higher** sustainable qty than wide-stop, lower-win-rate structures — **both** are legitimate; each is graded at **its** sustainable size.

| Tier | Criteria (all at **funded q_max** unless noted) |
|------|--------------------------------------------------------|
| **Floor** (acceptable minimum) | Eval pass rate **≥ 50%** within **30 days**; average funded P&L **≥ $36K/yr** (~**$3K/month**); profitable **≥ 4 of 6** years; edge survives **deflated Sharpe** (or agreed multiple-comparisons correction). |
| **Target** (genuinely good) | Eval pass rate **≥ 70%**; average funded P&L **≥ $60K/yr**; profitable **≥ 5 of 6** years; **low correlation** with existing **portfolio** strategies. |
| **Stretch** (transformative) | Eval pass rate **≥ 80%**; average funded P&L **≥ $100K/yr**; profitable **all 6** years; **stacks** with portfolio strategies (combined / displaced economics documented). |

**Eval pass rate column:** Use **live/eval** sample when sufficient; otherwise the **rolling 30-session backtest simulation** at **funded q_max** (and optionally other **q** for diagnostics). The “30 days” floor wording aligns with that window length (sessions, not calendar days).

**Live vs backtest:** Backtest establishes **funded q_max** and long-horizon economics; **eval pass rate** and **funded P&L** come from **live/eval** when the sample is large enough — otherwise use the **rolling 30-session backtest simulation** rule above (pre-registered window spec).

---

## Phase 2 framing

Phase 2 is **ground-up pattern and configuration discovery** on **~6 years of MNQ** data using the Phase 1 environment. It is **not** “extend Flux with one more module by default” and **not** framed around **replacing AfternoonMR and Range** (that language is obsolete given production is **ORB+Opt3**-only).

The **V2 starter packet** mental model remains useful:

- **Phase 0 (done):** Data infrastructure and research platform.
- **Phase 1 (this program’s Phase 2 entry):** Pattern discovery and hypothesis testing.
- **Phase 2:** Strategy development from validated patterns.
- **Phase 3:** Integration and deployment planning.

**Updated mantra:** discover **any configurations** (filters, session/regime gates, structural rule changes, new modules only if justified, or other discoveries) that **close the income gap** while surviving statistical gates and prop constraints — with **sizing** set by **funded survival (Gate A)** and **eval pass dynamics (Gate B)** under the documented Apex **$2K / $52K / $50K** rules, not by fixing qty a priori.

Canonical supplemental research-process detail: **`flux-v2-module-search-starter.md`** (repo root; see deprecation header — **`docs/phase-2-kickoff.md`** is authoritative on framing).

---

## Charter minimum viable edge (new modules, normalized)

When the winning path includes a **new module**, `docs/program-charter.md` still specifies **minimum viable edge** for **go/no-go on that module** (OOS WR **≥ 57%**, edge over BE **≥ +3pp**, P&L **≥ $5K/yr** at **1 NQ**, trades **≥ 80/yr**, profitable **≥ 4 of 6** years). Treat that block as a **normalized isolation screen** at **one contract** (or per-contract analog) before integration and **displacement** tests — **not** a substitute for the **Phase 2 grading table** above, which always applies at **funded q_max**.

**Program success** remains **closing the income gap** under the **floor / target / stretch** framework; that may require **multiple strategies** and **portfolio** construction, not a single module clearing MV edge in isolation.

---

## Research methodology principles

All of the following are **defaults** unless the operator explicitly approves an exception (documented in the lessons log):

1. **Pre-registration:** Hypotheses and primary metrics are stated **before** the backtest run that tests them.
2. **IS / OOS:** **60/40 split by trade count** (or charter-aligned variant if superseded — document if changed).
3. **Multiple testing:** **Deflated Sharpe** (or equivalent Bailey–López de Prado–style correction) across the **set of hypotheses tested** in a research **wave**, with **N = wave size** (see `docs/research-log.md`).
4. **Uncertainty:** **Bootstrap confidence intervals** on key metrics where applicable.
5. **Temporal robustness:** **Walk-forward** validation for candidates that survive initial screens.
6. **Structural rationale:** Patterns must have a **structural / behavioral reason**, not only favorable equity curves.
7. **Sustainable sizing:** Every graded run reports **funded q_max (Gate A)** and **eval pass rate at that qty (Gate B)** under Apex **$50K EOD** rules in `docs/ai-project-instructions.md`; headline P&L targets assume that pair unless pre-registered otherwise.

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
5. **`flux-v2-module-search-starter.md`** — legacy process detail; see **deprecation header** — authoritative framing is this kickoff + charter.
6. `docs/ai-project-instructions.md` — agent and documentation conventions (incl. Apex **$50K EOD**: **$2K** trailing pre-lock, **$52K** lock, **$50K** static floor, **$3K** profit target, **$1K** DLL).

Supporting: `docs/phase-1-detailed-plan.md` (what was built), `docs/m6-nt8-reproduction.md` (parity anchor), `docs/nt8-backtest-methodology.md` (NT8 reference protocol).

---

## First-session priorities (Phase 2)

1. Re-read **`flux-v2-module-search-starter.md`** and the charter Phase 2 section for **any remaining stale framing**; align language with **income-gap discovery** (not “replace named legacy modules”).
2. **Confirm** research methodology; **pre-register** hypotheses in **`docs/research-log.md`** (append-only) before runs.
3. After **Wave 0** completes: identify the **first hypothesis wave** (**5–10** ideas) and **pre-register** them before running tests.
4. Agree how **findings** are **documented and surfaced** (summary format, pass/fail, links to artifacts, operator sign-off checkpoints).

---

## Closure

When this document and the Phase 2 **`docs/current-working-plan.md`** are committed to **main**, Phase 1 closure is **administratively complete** and Phase 2 work may proceed in dedicated chats with clean context.
