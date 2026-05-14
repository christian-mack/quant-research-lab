# Program Charter: Systematic Trading Development

**Owner:** Christian
**Created:** April 20, 2026
**Status:** Living document — umbrella only, rarely updated
**Related documents:** `phase-1-detailed-plan.md`, `current-working-plan.md`, `lessons-log.md`, `ai-project-instructions.md`, `README.md`

---

## Purpose of This Document

This charter defines the long-term structure of the systematic trading development program. It captures the umbrella goals, the phased roadmap, the decision gates between phases, the skills progression required to execute each phase, and the operational constraints that apply across all phases.

This document is intentionally stable. Tactical details live in the current working plan. Lessons and post-mortems live in the lessons log. This document changes only when the overall structure of the program changes — not when individual phases adjust their scope.

---

## Program Vision

Build a portfolio of systematic trading strategies that progresses from retail-level systematic trading to edge sources comparable to what small systematic funds access. The **income target is the constraint**; **system architecture** (single- vs multi-module, platform choice, regime overlays, how many “generations” you run) is the **empirical means** to close **per-account and portfolio income gaps** — not an end in itself. Strategy **generations** named below (Flux V1/V2/V3, Onyx-class, etc.) are the **current best-understood path** for sequencing investigations and skill-building — **not** a fixed ladder of mandatory next builds. What advances is decided by evidence, prop compliance, and **backtest-to-live correspondence**, not by table order.

### Long-Term Income Target

**$500,000–$1,000,000/year net from systematic trading, achieved through multiple funded accounts across multiple strategies.**

The path to this target is not a single strategy at institutional scale. It is a portfolio of strategies, each operating within prop firm funded account constraints, with aggregate capacity limited by the number of accounts a solo operator can monitor and maintain rather than by underlying strategy capacity.

### Per-Account Target

**$65,000–$100,000/year net per funded account** after prop firm payout splits. This is the engineering target for each strategy generation — individual account economics must support the aggregate income target without requiring unrealistic account counts.

**Current empirical anchor (2026-05, corrected):** Six-year NT8 **ORB+Opt3** reference P&amp;L was **~$10,885/yr at qty = 10**, i.e. **~$1,088.50/yr per contract** — **not** ~$10.9K/yr per contract (see lessons log **2026-05-13** correction). Static backtest anchor for **funded qty = 3** (same protocol class): roughly **~$1,088.50 × 3 ≈ ~$3,265/yr per account** before payout splits and live frictions; validated Python M6 is **~$1,014/yr × 3 ≈ ~$3,042/yr** on the research **RTH-only** rerun (~6.8% below NT8 per contract). Either way this **trails** the **$65K–$100K/yr per funded account** bar by an order of magnitude — the gap is **explicit** and **first-order** for research; the per-account target remains the north star.

---

## Program Structure

The program is organized into **strategy generations** and **phases** (research units with gates). **Phase justifications are “next empirical investigations toward the income goal”** — not “the next architectural installment” regardless of results. Generations are **not** strict linear successors; work can stack, fork, or pause. **Multi-module vs single-module, Flux vs Onyx-class work, regime overlay vs not** are **hypotheses under test**.

### Strategy Generations

| Generation | Character | Status |
|---|---|---|
| **Flux V1** | Educated-retail systematic; intraday NQ/MNQ on NT8. **Live: ORB+Opt3** (LatestEntryHourET=11; sizing in lessons log). Historical quad-module stack remains in repo for reproduction only. Migrating to more stable execution in Phase 1b. | Deployed, live on funded account |
| **Flux V2** | Data-informed **configuration research** in Python (6-year protocol): improve income vs **ORB+Opt3 baseline** via **any** evidence-backed path — new modules, sizing, filters/overlays, or other discoveries. | Not started — gated on Phase 1 infrastructure |
| **Flux V3** | **Leading candidate:** regime-overlay / meta-gating on Flux-style edge; ML-adjacent **if** pursued. | Planned **if** Phase 2 outcome warrants |
| **Onyx-class V1** | **Leading candidate — not “next” by default:** multi-instrument systematic, cross-sectional signals, portfolio construction; architecturally separable from Flux. Opens only if economics and evidence justify. | Candidate — conditional |
| **Future (placeholder)** | **Leading candidates** TBD from cumulative evidence. Examples: microstructure, options vol, macro, other. | Undecided — do not commit until an Onyx-class **or equivalent** major phase completes or is explicitly deprioritized |

### Phases

Phases are the unit of work. Each phase has entry criteria, defined scope, a milestone gate with quantitative exit criteria, and stop conditions that would pause or abandon it.

---

## Phase Structure

### Phase 1: Research Infrastructure (Python Environment)

**Objective:** Build a comprehensive Python-based research environment that replaces NT8 as the primary research platform. NT8 remains the execution platform.

**Scope:** Comprehensive — includes core backtest engine, statistical testing framework with deflated Sharpe and bootstrap confidence intervals, parameter optimization with proper IS/OOS handling, multi-instrument capability designed in from the start, regime detection framework, and results visualization.

**Entry Criteria:**
- Flux V1 live operation stable and producing eval samples
- Decision made on tier 0 local-development approach (confirmed)
- Data gaps in MNQ dataset identified for potential backfill

**Exit Criteria (Milestone Gate):**
1. Data integrity verified against raw MNQ files (bar counts, session alignment, gap handling)
2. Indicator correctness verified against reference libraries (pandas-ta, talib) within floating-point tolerance
3. Unit tests pass for each Flux V1 module's execution logic on hand-constructed scenarios
4. Python vs. NT8 full backtests compared for all four historical V1 modules (Momentum, ORB, Range, AfternoonMR); every divergence >5% investigated and documented (not necessarily resolved — explained). **Live production** is ORB+Opt3 (see lessons log); full-module comparison supports methodology and counterfactual analysis, not current routing.
5. Statistical testing framework operational: deflated Sharpe, bootstrap CIs, walk-forward validation
6. Multi-instrument data infrastructure in place (even if only MNQ is actively loaded)
7. Regime detection framework scaffolded (even if only basic features implemented)

**Stop Conditions:**
- Layer 4 validation reveals Flux V1 backtest results are materially wrong (>20% P&L divergence unexplained) → pause phase, investigate NT8 backtest methodology before proceeding
- Operational demand from live Flux V1 accounts exceeds 50% of available time for >4 weeks → pause phase until operational load normalizes
- Python infrastructure scope exceeds 12 weeks of effort → pause and reassess scope reduction

**Parallel Tracks (during Phase 1):**
- Continued Flux V1 live operation (mandatory)
- Additional eval attempts to build live pass-rate sample toward statistical significance (target: 8-10 completed attempts)
- Documentation of current NT8 backtest methodology for validation reference
- Preparatory reading: Lopez de Prado *Advances in Financial Machine Learning*, specifically chapters on backtest overfitting, deflated Sharpe ratio, purged cross-validation
- Instrumentation of live system to log per-module trade frequency for regime analysis

**Phase 1b (execution platform migration)** is **not** a parallel track during Phase 1 — it **begins after** the Phase 1 milestone gate passes (see Phase 1b below).

---

### Phase 1b: Execution Platform Migration

**Objective:** Replace NT8 as the execution platform to resolve chronic data feed stability issues that are compromising live system integrity.

**Problem statement:** NT8 data feed stalls 2-3 times daily for variable durations on live accounts. This creates periods where modules operate on stale state, corrupting the relationship between live results and backtest expectations. Running funded accounts in this state is both an integrity risk and a pollution of the live pass-rate data being collected.

**Sequencing — after Phase 1, not parallel:** Phase 1b **starts after** the **Phase 1 milestone gate passes**. It does **not** run in parallel with building the Python research infrastructure. **Sierra Chart** (ACSIL) remains the **leading target** platform (Apex-compatible, stronger stability reputation than NT8); alternatives (MotiveWave, Quantower, etc.) remain available if trial evidence warrants.

**Rationale for sequencing:** Phase 1 produces **validated strategy logic in Python** — unit-tested module implementations (M5) and NT8-parity validation (M6) — before any port begins. That **Python is the primary specification** for the execution platform port; **NT8 C# is secondary reference** (cross-check and fills/infra detail only). Porting **directly from NT8 to Sierra** would inherit NT8’s specification ambiguity and skip the validated research artifact chain; **Python-first** is cleaner and matches the program’s **backtest-to-live** discipline.

**Research vs execution (independence):** The Python **research environment** and the **M1–M9 milestone path** are **independent of which platform runs live** — the same research work proceeds regardless. Only the **start** of Phase 1b port work is gated on Phase 1 completion; the **content** of Phase 1 does not change based on execution stack.

**Production continuity:** **NT8 remains** the live execution platform for the full Phase 1 period and until Phase 1b achieves **side-by-side SIM validation** against NT8 on the new stack (then phased migration per plan).

**Scope:** Evaluate and migrate to the selected platform. **Direct prop-firm / Tradovate API execution** is **not** treated as a viable path for funded accounts (access effectively restricted); plan assumes a **chart/platform** execution route (e.g. Sierra ACSIL), not API-first. Final platform choice still contingent on compatibility and proof-of-concept port.

**Port specification:** Implement on the new platform from **Phase 1 Python module logic** as the source of truth; use NT8/C# where needed for reconciliation. Port **scope** follows the **live deployment plan** (e.g. production ORB+Opt3 first; additional modules as required for parity or research).

**Entry Criteria:**
- **Phase 1 milestone gate passed** (Python research infrastructure complete per charter Phase 1 exit criteria)
- Sierra Chart (or selected alternative) trial environment accessible

**Exit Criteria:**
- **Strategy logic from Phase 1 Python implementations** ported to the new platform with correctness verified (unit tests / deterministic checks as appropriate; NT8 as secondary cross-check)
- Side-by-side SIM validation against NT8 for 30+ trading days showing fill quality, trade timing, and P&L within acceptable divergence
- Platform operational on dev machine or VPS with documented reliability over the validation window
- Migration plan for funded accounts drafted (one account at a time, starting with smallest)

**Stop Conditions:**
- Selected platform reveals stability problems comparable to NT8 during validation → return to evaluation, consider alternative candidate
- Port effort exceeds 6 weeks without completion → reassess whether platform choice is correct

**Relationship to Phase 1:** Phase 1b is **sequenced after** Phase 1. Phase 1 owes **no** porting or Sierra trial work to clear its gate; Phase 1b owes its **spec** to Phase 1’s Python artifacts.

**Parallel Tracks (during Phase 1b):**
- Continued **NT8** live operation until migration is validated (accept ongoing integrity cost until side-by-side validation passes)
- Live comparison logging during side-by-side validation

---

### Phase 2: Flux V2 — Configuration & Module Research

**Objective:** Use the Phase 1 research environment to **investigate configurations that improve income trajectory vs. the ORB+Opt3 baseline**, including but **not limited to** additional modules. Acceptable outcomes include higher-sized single-module variants, new complementary modules (only if **integrated** P&L after displacement is positive), regime or time gating improvements, and other approaches discovered during research.

**Scope:** Ground-up pattern search where useful; candidate module development; sizing/configuration studies. IS/OOS validation with deflated Sharpe and bootstrap CIs. **Integration / displacement testing** whenever multiple signals or size changes interact. Implementation on NT8 or successor execution stack. Phased SIM and live deployment with **backtest-to-live correspondence** assessed — not backtest-only claims.

**Entry Criteria:**
- Phase 1 milestone gate passed
- **ORB+Opt3 baseline** definition frozen for comparisons (reconciled Python ↔ NT8 reference on the 6-year protocol; methodology current)
- Data gaps addressed (or explicitly accepted)
- Preparatory reading complete on backtest overfitting and multiple-comparisons correction
- **Improvement threshold X%** vs. baseline agreed for gate (**numeric X is set only after** the ORB+Opt3 reference is frozen in Python research artifacts following **M6/M7-class** NT8 parity work; agree X at Phase 2 kickoff together with that frozen baseline)

**Exit Criteria (Milestone Gate):**
- **≥X% improvement** vs. **ORB+Opt3 baseline** on KPIs agreed at Phase 2 entry (e.g., net P&L, drawdown-adjusted metric, or composite) on the standard 6-year OOS protocol — achieved by **at least one** configuration accepted for continued deployment
- Deflated Sharpe ratio positive (or strategy-class-appropriate multiple-comparisons correction) across hypotheses tested
- **If** the winning path includes a **new module:** that module clears minimum viable edge (OOS WR ≥57%, edge over BE ≥+3pp, P&L ≥$5K/yr at 1 NQ, trades ≥80/yr, profitable in ≥4 of 6 years) **and** does not **net-destroy** baseline edge after displacement (see lessons log: multi-module harm is a verified failure mode)
- SIM (then live as appropriate) for **≥30 trading days** with **backtest-to-live alignment** documented per program standards

**Stop Conditions:**
- After **≥10 distinct hypotheses / configuration families** without meeting the improvement gate → pause; document negative evidence; narrow scope, accept baseline-only, or reassess Phase 3/4 **candidates**
- Any candidate fails prop DD or eval pass-rate constraints despite backtest strength → reject or redesign; **do not** size multi-module stacks past survival thresholds based on paper P&L alone

**Parallel Tracks:**
- Continued Flux V1 operation on current production config
- Ongoing eval sampling for pass-rate confidence
- Research environment maintenance and enhancement

---

### Phase 3: Flux V3 Regime Overlay

**Objective:** Develop a regime-detection meta-strategy that dynamically manages Flux module activation based on market regime features. First ML-adjacent component in the system.

**Scope:** Regime feature engineering (VIX level/change, realized volatility regime, trend strength metrics, macro calendar proximity, session-type classification). Regime classification model (starting simple: rule-based or logistic regression; advancing to tree-based or similar only if justified). Module activation logic conditioned on regime state. Backtesting the overlay against **post–Phase 2 Flux baseline** (ORB+Opt3-derived) to measure multiplier effect. Live deployment.

**Entry Criteria:**
- Phase 2 milestone gate passed (**Phase 2 relative-improvement vs. frozen ORB+Opt3-derived baseline satisfied**, unless Phase 2 exited early with documented rationale)

**Exit Criteria (Milestone Gate):**
- Regime overlay improves backtested risk-adjusted returns by ≥15% over **post–Phase 2 Flux baseline** (Sharpe ratio improvement, not just P&L)
- Overlay does not materially increase max drawdown beyond that baseline
- OOS validation positive across the 6-year dataset
- Live SIM deployment for ≥30 trading days matching backtest expectations

**Stop Conditions:**
- No combination of regime features produces statistically significant improvement over Flux baseline after thorough research → ship Phase 2 outcome as final Flux iteration for the window, skip V3, consider **Onyx-class Phase 4 candidate**
- Regime overlay adds drawdown risk that breaks prop firm DD compliance → abandon approach; consider **Onyx-class Phase 4 candidate**

**Parallel Tracks:**
- Continued live operation of Flux per **Phase 2 shipped configuration**
- Scaling live account count if per-account economics support it

---

### Phase 4: Leading Candidate — Onyx-Class Multi-Instrument Systematic

**Objective:** **If** single-instrument Flux work cannot close the per-account income gap, **a leading candidate** (not a predetermined “next generation”) is a **bona fide multi-instrument systematic**: architecturally separate from Flux, with cross-sectional signals, portfolio construction, and risk budgeting. Commitment to this track is **conditional** on evidence, capacity, and economics after Phases 2–3.

**Scope:** Universe selection (likely liquid futures: ES, NQ, YM, RTY, CL, GC, ZN, 6E, or similar). Cross-sectional signal research (momentum, value if applicable, carry, mean reversion, or other structural signals). Portfolio construction with volatility targeting and risk parity. Correlation-aware position sizing. Execution approach appropriate for multi-instrument rebalancing cadence. NT8 or alternative execution platform decision. Live deployment.

**Entry Criteria:**
- Phase 3 complete (success, skipped, or exhausted — documented)
- **Economics:** Per-account net from Flux **at or approaching** $65,000 **or** a **documented charter gate decision** that Flux has plateaued below target but an Onyx-class probe is the best remaining path to the aggregate income goal (target unchanged; evidence must justify incremental complexity)
- Research environment proven on Flux work — infrastructure ready for multi-instrument extension

**Exit Criteria (Milestone Gate):**
To be defined in detail when Phase 3 completes and Phase 4 begins. Placeholder criteria:
- Backtest Sharpe ratio ≥ 1.0 on OOS data after deflated Sharpe correction
- Maximum drawdown compatible with prop firm funded account constraints
- Positive across multiple regime types in historical data
- Live SIM deployment for ≥60 trading days matching backtest expectations

**Stop Conditions:**
- Research reveals no durable edge across the instrument universe at the strategy cadence being researched → pivot to alternative Onyx direction (microstructure, options vol, macro) rather than force-shipping a weak system
- Infrastructure requirements exceed Phase 1 research environment capabilities → extend Phase 1 rather than proceed with inadequate tooling

**Parallel Tracks:**
- Continued Flux operation and maintenance
- Onyx-class system operates alongside Flux, not as a replacement

---

### Phase 5+: Future Generations (Leading Candidates)

**Not planned in detail.** Placeholder for **leading candidate** directions **after** an Onyx-class phase (or equivalent major track) completes or is deprioritized — not a fixed sequence. Direction will reflect:
- What multi-instrument (or alternative major) work teaches about strengths and preferences
- Which edge sources remain underexploited after Flux and the largest concurrent track
- Whether infrastructure for higher-frequency or alternative-asset strategies has become practical

Candidate directions include microstructure/order flow (requires tick data infrastructure), options volatility surface strategies (requires options data and risk framework), crypto basis or funding rate strategies, macro systematic across asset classes. Do not commit to any until **prior major-phase evidence** supports it.

---

## Persistent Assets

Some assets are not tied to a specific phase — they are built once and maintained across all phases.

### Python Research Environment

Built in Phase 1. Maintained across all subsequent phases. Any strategy research across all generations runs through this environment. Maintenance includes:
- Dependency updates
- Bug fixes discovered during research
- Extension to new instruments as needed
- New analytical capabilities as new strategy types require them

### NT8 Execution Platform

Execution platform for Flux generations. May be replaced or supplemented for **Onyx-class** systems depending on strategy cadence and instrument requirements. Maintenance includes:
- C# code for executing modules
- Watchdog and monitoring infrastructure
- AutoHotkey automation for operational tasks

### Data Pipeline

Historical and live market data infrastructure. Starts with MNQ 1-minute for Flux. Extends to multi-instrument for Onyx. Always owned and maintained locally; vendor data sources may change but the pipeline survives.

### Documentation System

The charter, working plans, lessons log, and AI project instructions. Maintained across all phases. This system is itself a strategic asset — it is what allows a solo operator to run a multi-year, multi-strategy program without losing context.

---

## Skills Ladder

Each phase requires skills that must be functional before the phase can execute. A skill appearing on the ladder is not the same as having the skill — skills are only "acquired" when applied successfully in a project artifact. Phase advancement gates on application, not exposure.

### Phase 1 Required Skills
- Python proficiency (have — comfortable level)
- Data manipulation with polars (new — to be acquired in Phase 1)
- Event-driven backtest design (partial — NT8 experience transfers conceptually)
- Unit testing with pytest (new — to be acquired in Phase 1)
- Statistical testing: bootstrap methods, deflated Sharpe ratio (new — to be acquired via reading + application)
- Walk-forward validation methodology (partial — conceptually familiar, not yet applied rigorously)

### Phase 2 Required Skills
- All Phase 1 skills at functional level
- Pattern discovery methodology (ground-up rather than hypothesis-driven)
- Multiple-comparisons correction in practice
- Deflated Sharpe ratio computation and interpretation
- NT8 C# implementation of Python-validated strategies

### Phase 3 Required Skills
- All Phase 2 skills
- Feature engineering for regime detection
- Basic ML fundamentals: logistic regression, tree-based methods, proper cross-validation
- Causal vs. correlational signal evaluation

### Phase 4 Required Skills
- All Phase 3 skills
- Multi-instrument data management
- Portfolio construction theory (risk parity, volatility targeting, mean-variance, Black-Litterman)
- Cross-sectional signal design
- Factor-based risk decomposition

### Skills Acquisition Principle

Skills should be applied in anger (in actual project work producing actual artifacts) during the phase where they are first required, not pre-learned abstractly. Reading precedes application, but reading alone does not constitute skill acquisition. Each phase's lessons log entries should document specific artifacts that demonstrate each required skill was actually used.

---

## Operational Capacity Framework

Time is finite. This framework defines how available time is allocated across activities that compete for it.

### Time Allocation Principle

Allocation shifts across phases but respects these floors:
- **Live operation and monitoring:** always sufficient to detect and respond to account issues within one trading day
- **Documentation maintenance:** sufficient to keep working plan and lessons log current (weekly review minimum)
- **Learning:** sufficient to stay ahead of the next phase's skill requirements

### Expected Allocations by Phase

| Phase | Live Ops | Research/Development | Documentation | Learning |
|---|---|---|---|---|
| Phase 1 | 20% | 60% | 10% | 10% |
| Phase 2 | 20% | 65% | 10% | 5% |
| Phase 3 | 25% | 55% | 10% | 10% |
| Phase 4 | 30% | 45% | 10% | 15% |

These are guidelines, not hard rules. Actual allocations fluctuate based on operational load. When live operation demands spike (eval windows, funded account issues, regime transitions), development pauses.

### Scaling Account Count

Number of funded accounts operated in parallel is itself a capacity decision. More accounts mean more income but more operational load. Target account count per strategy generation:
- Flux V1: 1-3 accounts during Phase 1 and early Phase 2
- Flux V2: 3-5 accounts after deployment
- Flux V3: 5-8 accounts after deployment
- Onyx-class: add 1-3 accounts alongside Flux accounts when that track is active

Scaling is additive across generations. By Phase 4, operational load may justify investment in better monitoring infrastructure (the "operations dashboard" web app mentioned during program design).

---

## Data Strategy

### Current Dataset

6-year MNQ 1-minute dataset (Jan 2020 – Apr 2026, ~2.1M bars, 1,580 trading days). Two known gaps: Jun 18 – Jul 31 2024 (32 days), Feb 3 – Mar 11 2026 (27 days).

### Decisions Made

**Dataset length: 6 years is sufficient.** Not extending to 15-20 years. Rationale: older data reflects market regimes (pre-2015 microstructure, different algorithmic trading landscape) that are less representative of current conditions than the regime diversity already captured in 2020-2026. Extending backward adds regime examples at the cost of relevance. Marginal information gain does not justify cost.

**Tick data: not needed for Flux generations or the leading Onyx-class track.** Required only if a future strategy generation pursues microstructure/order flow. Historical tick data can be purchased when needed; there is no first-mover advantage to early acquisition.

**Gap filling: worthwhile investment.** Budget $200-500 to fill the two known gaps from alternative sources (CME DataMine direct, Kibot, FirstRate Data, or similar). This is the highest-ROI data investment available. Prioritize the 2024 gap first as it falls within expected OOS validation windows.

**Data quality: current NT8 dataset is sufficient for research purposes.** CME DataMine direct would be marginally cleaner but not worth the subscription cost at current scale.

### Future Data Needs

- Multi-instrument data for Onyx-class work: acquire when Phase 4 (or equivalent) entry clears
- Options data if options-based strategies are pursued: acquire when that direction is committed to
- Tick data if microstructure strategies are pursued: acquire when that direction is committed to

---

## Stop Conditions (Program-Level)

The program itself has stop conditions, not just individual phases. If any of these trigger, reassessment is warranted before continuing:

- **Flux V1 live pass rate over 10+ completed evals falls below 35%** → the system may have decayed or may have been overfit initially. Pause phase work, investigate root cause before continuing.
- **Per-account net yield target (≥$65,000) looks unreachable after Flux V3** → the entire ladder's economics may need reassessment (lessons log: corrected **ORB+Opt3** static anchor **~$3.3K/yr** per funded account at qty=3 on the six-year backtest protocol — **~$3K/yr** on Python M6 — vs. charter bar; see **2026-05-13**). May justify pivoting to non-Flux strategies or an Onyx-class probe earlier.
- **Multiple consecutive phase stop conditions trigger** → pattern indicates structural issues with the program approach, not with individual phases. Consider external perspective or significant restructuring.

---

## Decision-Making Principles (All Phases)

1. **Edge creation over edge multiplication.** New modules and strategy types create edge. Position sizing, account scaling, and overlays multiply it. Always prioritize creation first.

2. **Structural reasoning over curve-fitting.** Every strategic decision must be justifiable on market microstructure grounds, not just backtested P&L. If a strategy works but there's no structural reason why, it probably doesn't really work.

3. **Prop firm compliance is non-negotiable.** Max DD, consistency rules, and evaluation pass rates cannot be sacrificed for higher P&L projections. All research must respect these constraints.

4. **Ship incrementally.** Each phase produces a deployable or deployed system. Never have the entire system in a broken state waiting on a future phase to fix it.

5. **Walk-forward OOS validation is mandatory.** No strategy ships without IS/OOS split. No claim of edge survives without OOS confirmation.

6. **Multiple-comparisons correction is mandatory.** Hypotheses tested get counted. Deflated Sharpe or equivalent correction applies.

7. **Interaction effects are real.** A module that improves in isolation may harm the full system. Always validate in the integrated context before shipping.

8. **Document as a habit, not a project.** Documentation decay is silent and costly. Weekly review of working plan and ad hoc lessons log updates are the norm.

9. **Infrastructure investments compound.** Building the Python research environment properly in Phase 1 makes every subsequent phase cheaper. Shortcuts here are false economies.

10. **Loose coupling between generations.** Flux and Onyx-class systems should be architecturally independent. A problem in one should not propagate to the other.

11. **Backtest-to-live alignment is first-class.** Configurations are validated by **both** backtest performance (under the agreed protocol) **and** demonstrated **backtest-to-live correspondence** (or explainable, bounded gaps) — not backtest performance alone.

---

## Revision Log

| Date | Revision | Rationale |
|---|---|---|
| 2026-04-20 | Initial charter | Program formalization after Flux V1 deployment and V2 scoping |
| 2026-04-21 | Added Phase 1b: Execution Platform Migration | NT8 data feed stability compromising live integrity; migration treated as parallel infrastructure track rather than deferred work |
| 2026-04-28 | Income constraint & empirical architecture; ORB+Opt3 baseline; Phase 2 relative gates; conditional Onyx / future framing | Production cut + lessons log: architecture serves income target; tri-module dollar gates obsolete; leading-candidate wording for late phases |
| 2026-04-30 | Phase 1b sequenced **after** Phase 1; Python-first port spec; Sierra Chart remains target | Validated Python (M5/M6) is primary port specification; NT8 C# secondary; M1–M9 independent of live stack; NT8 production until side-by-side SIM passes |
| 2026-05-13 | NT8 ORB+Opt3 anchor corrected ($10.9K/yr was qty=10; **~$1,088.50/yr per contract**); M6 closed; per-account income anchor **~$3.3K/yr** at qty=3 (vs obsolete ~$8K) | `docs/lessons-log.md` correction entry; `m6-nt8-reproduction.md` closure; empirical anchor and stop-conditions wording updated |
