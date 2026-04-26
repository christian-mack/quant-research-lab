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

Build a portfolio of systematic trading strategies that progresses from retail-level systematic trading to edge sources comparable to what small systematic funds access. The program is structured as a ladder: each strategy generation teaches the skills and infrastructure required for the next, and each generation must be deployable and income-generating on its own — not a stepping stone that only pays off at the end.

### Long-Term Income Target

**$500,000–$1,000,000/year net from systematic trading, achieved through multiple funded accounts across multiple strategies.**

The path to this target is not a single strategy at institutional scale. It is a portfolio of strategies, each operating within prop firm funded account constraints, with aggregate capacity limited by the number of accounts a solo operator can monitor and maintain rather than by underlying strategy capacity.

### Per-Account Target

**$65,000–$100,000/year net per funded account** after prop firm payout splits. This is the engineering target for each strategy generation — individual account economics must support the aggregate income target without requiring unrealistic account counts.

---

## Program Structure

The program is organized into strategy generations (Flux V1, V2, V3, Onyx V1, etc.) and development phases within each generation. Generations are not strict successors — Flux V2 does not replace V1, it augments the system while V1 continues to generate income. The ladder is cumulative.

### Strategy Generations

| Generation | Character | Status |
|---|---|---|
| **Flux V1** | Educated-retail systematic. Module-driven intraday NQ/MNQ. Currently on NT8; migrating to more stable execution platform in Phase 1b. | Deployed, live on funded account |
| **Flux V2** | Data-informed systematic. Python research environment, 6-year backtest validation, replacement of broken modules (AMR, Range). | Not started — gated on Phase 1 infrastructure |
| **Flux V3** | Quant-adjacent enhancement. Regime-overlay meta-strategy that dynamically manages Flux module activation based on market regime features. First exposure to ML-in-trading. | Planned |
| **Onyx V1** | First bonafide quant-level system. Multi-instrument systematic. Cross-sectional and portfolio construction. Separate architecture from Flux. | Planned |
| **Future (placeholder)** | Direction TBD based on what Onyx V1 teaches. Candidates: microstructure/order flow on a single instrument, options volatility surface strategies, macro systematic, other. | Undecided — do not commit until Onyx V1 is running |

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
4. Python vs. NT8 full backtests compared for all four V1 modules; every divergence >5% investigated and documented (not necessarily resolved — explained)
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
- **Phase 1b: Execution platform migration** (see below)

---

### Phase 1b: Execution Platform Migration

**Objective:** Replace NT8 as the execution platform to resolve chronic data feed stability issues that are compromising live system integrity.

**Problem statement:** NT8 data feed stalls 2-3 times daily for variable durations on live accounts. This creates periods where modules operate on stale state, corrupting the relationship between live results and backtest expectations. Running funded accounts in this state is both an integrity risk and a pollution of the live pass-rate data being collected.

**Scope:** Evaluate and migrate to a more stable execution platform. Current leading candidate: Sierra Chart (ACSIL-based strategy development, Apex-approved, stronger stability reputation than NT8). Alternatives considered: MotiveWave, Quantower, direct Tradovate API (ruled out if prop firm API access is prohibited). Final choice contingent on verification of prop firm compatibility and successful proof-of-concept port.

**Entry Criteria:**
- Prop firm API access policy confirmed (determines whether direct API is viable)
- Sierra Chart (or selected alternative) trial environment accessible

**Exit Criteria:**
- All Flux V1 modules ported to new platform with unit-test-verified correctness
- Side-by-side SIM validation against NT8 for 30+ trading days showing fill quality, trade timing, and P&L within acceptable divergence
- Platform operational on dev machine or VPS with documented reliability over the validation window
- Migration plan for funded accounts drafted (one account at a time, starting with smallest)

**Stop Conditions:**
- Selected platform reveals stability problems comparable to NT8 during validation → return to evaluation, consider alternative candidate
- Port effort exceeds 6 weeks without completion → reassess whether platform choice is correct

**Relationship to Phase 1a:** Phase 1b runs in parallel with Phase 1a (Python research infrastructure). Both tracks are active concurrently. They are independent — Phase 1b progress does not block Phase 1a milestones and vice versa. However, the Python research environment built in Phase 1a will eventually inform how strategies are developed and ported in future phases, so coordination matters.

**Parallel Tracks (during Phase 1b):**
- Continued NT8 operation until migration is validated (accept ongoing integrity cost as the price of deliberate migration)
- Live comparison logging during side-by-side validation

---

### Phase 2: Flux V2 Module Research & Deployment

**Objective:** Use the Phase 1 research environment to replace AfternoonMR and Range modules with new modules that clear the minimum viable edge criteria on 6-year OOS data. Ship improved Flux to live.

**Scope:** Ground-up pattern search across NQ microstructure. Candidate module development. IS/OOS validation with deflated Sharpe and bootstrap CIs. Integration testing for displacement effects against ORB and Momentum. NT8 implementation of validated modules. Live deployment alongside V1 components.

**Entry Criteria:**
- Phase 1 milestone gate passed
- Data gaps addressed (or explicitly accepted)
- Preparatory reading complete on backtest overfitting and multiple-comparisons correction

**Exit Criteria (Milestone Gate):**
- At least one new module clears minimum viable edge (OOS WR ≥57%, edge over BE ≥+3pp, P&L ≥$5K/yr at 1 NQ, trades ≥80/yr, profitable in ≥4 of 6 years)
- Deflated Sharpe ratio positive after multiple-comparisons correction across all hypotheses tested
- Full-system (ORB + Momentum + new module[s]) projected annual P&L ≥ $30,000 at Config E sizing or equivalent
- Live deployment successful on SIM account for ≥30 trading days matching backtest expectations

**Stop Conditions:**
- After ground-up search of 10+ pattern hypotheses, no candidate clears minimum viable edge → accept reduced module count, proceed to Phase 3 with smaller base P&L
- Full-system P&L projection falls below $25K/yr → pause and reassess architecture before proceeding to Phase 3

**Parallel Tracks:**
- Continued Flux V1 operation
- Ongoing eval sampling for pass-rate confidence
- Research environment maintenance and enhancement

---

### Phase 3: Flux V3 Regime Overlay

**Objective:** Develop a regime-detection meta-strategy that dynamically manages Flux module activation based on market regime features. First ML-adjacent component in the system.

**Scope:** Regime feature engineering (VIX level/change, realized volatility regime, trend strength metrics, macro calendar proximity, session-type classification). Regime classification model (starting simple: rule-based or logistic regression; advancing to tree-based or similar only if justified). Module activation logic conditioned on regime state. Backtesting the overlay against V2 baseline to measure multiplier effect. Live deployment.

**Entry Criteria:**
- Phase 2 milestone gate passed
- System base P&L ≥ $30,000/yr

**Exit Criteria (Milestone Gate):**
- Regime overlay improves backtested risk-adjusted returns by ≥15% over V2 baseline (Sharpe ratio improvement, not just P&L)
- Overlay does not materially increase max drawdown beyond V2 baseline
- OOS validation positive across the 6-year dataset
- Live SIM deployment for ≥30 trading days matching backtest expectations

**Stop Conditions:**
- No combination of regime features produces statistically significant improvement over V2 baseline after thorough research → ship Flux V2 as final V-series, skip V3, proceed to Onyx V1
- Regime overlay adds drawdown risk that breaks prop firm DD compliance → abandon approach, proceed to Onyx V1

**Parallel Tracks:**
- Continued live operation of Flux V1/V2 hybrid
- Scaling live account count if per-account economics support it

---

### Phase 4: Onyx V1 — Multi-Instrument Systematic

**Objective:** Build the first bonafide quant-level system. Architecturally separate from Flux. Multi-instrument universe with proper portfolio construction, cross-sectional signals, and risk budgeting.

**Scope:** Universe selection (likely liquid futures: ES, NQ, YM, RTY, CL, GC, ZN, 6E, or similar). Cross-sectional signal research (momentum, value if applicable, carry, mean reversion, or other structural signals). Portfolio construction with volatility targeting and risk parity. Correlation-aware position sizing. Execution approach appropriate for multi-instrument rebalancing cadence. NT8 or alternative execution platform decision. Live deployment.

**Entry Criteria:**
- Phase 3 complete (success or exhausted)
- Per-account net yield from Flux at least $65,000 (ensures Flux is not a project that needs rebuilding)
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
- Onyx V1 operates alongside Flux, not as a replacement

---

### Phase 5+: Future Strategy Generations

**Not planned in detail.** Placeholder for strategies beyond Onyx V1. Direction will be determined based on:
- What Onyx V1 teaches about personal research strengths and preferences
- Which edge sources remain underexploited after Flux and Onyx are deployed
- Whether infrastructure requirements for higher-frequency or alternative-asset strategies have become practical

Candidate directions include microstructure/order flow (requires tick data infrastructure), options volatility surface strategies (requires options data and risk framework), crypto basis or funding rate strategies, macro systematic across asset classes. Do not commit to any of these until Onyx V1 is running.

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

Execution platform for Flux generations. May be replaced or supplemented for Onyx V1 depending on strategy cadence and instrument requirements. Maintenance includes:
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
- Onyx V1: add 1-3 Onyx accounts alongside Flux accounts

Scaling is additive across generations. By Phase 4, operational load may justify investment in better monitoring infrastructure (the "operations dashboard" web app mentioned during program design).

---

## Data Strategy

### Current Dataset

6-year MNQ 1-minute dataset (Jan 2020 – Apr 2026, ~2.1M bars, 1,580 trading days). Two known gaps: Jun 18 – Jul 31 2024 (32 days), Feb 3 – Mar 11 2026 (27 days).

### Decisions Made

**Dataset length: 6 years is sufficient.** Not extending to 15-20 years. Rationale: older data reflects market regimes (pre-2015 microstructure, different algorithmic trading landscape) that are less representative of current conditions than the regime diversity already captured in 2020-2026. Extending backward adds regime examples at the cost of relevance. Marginal information gain does not justify cost.

**Tick data: not needed for Flux generations or Onyx V1.** Required only if a future strategy generation pursues microstructure/order flow. Historical tick data can be purchased when needed; there is no first-mover advantage to early acquisition.

**Gap filling: worthwhile investment.** Budget $200-500 to fill the two known gaps from alternative sources (CME DataMine direct, Kibot, FirstRate Data, or similar). This is the highest-ROI data investment available. Prioritize the 2024 gap first as it falls within expected OOS validation windows.

**Data quality: current NT8 dataset is sufficient for research purposes.** CME DataMine direct would be marginally cleaner but not worth the subscription cost at current scale.

### Future Data Needs

- Multi-instrument data for Onyx V1: acquire in Phase 4 entry
- Options data if options-based strategies are pursued: acquire when that direction is committed to
- Tick data if microstructure strategies are pursued: acquire when that direction is committed to

---

## Stop Conditions (Program-Level)

The program itself has stop conditions, not just individual phases. If any of these trigger, reassessment is warranted before continuing:

- **Flux V1 live pass rate over 10+ completed evals falls below 35%** → the system may have decayed or may have been overfit initially. Pause phase work, investigate root cause before continuing.
- **Per-account net yield target (≥$65,000) looks unreachable after Flux V3** → the entire ladder's economics may need reassessment. May justify pivoting to non-Flux strategies earlier.
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

10. **Loose coupling between generations.** Flux and Onyx should be architecturally independent. A problem in one should not propagate to the other.

---

## Revision Log

| Date | Revision | Rationale |
|---|---|---|
| 2026-04-20 | Initial charter | Program formalization after Flux V1 deployment and V2 scoping |
| 2026-04-21 | Added Phase 1b: Execution Platform Migration | NT8 data feed stability compromising live integrity; migration treated as parallel infrastructure track rather than deferred work |
