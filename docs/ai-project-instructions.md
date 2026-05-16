# AI Project Instructions

**Purpose:** Rules and conventions for any AI coding agent (Cursor, GitHub Copilot, Claude Code, or similar) working within this project. Human collaborators should also follow these conventions.

**Scope:** All code, documentation, and research artifacts produced in the systematic trading development program.

**Related documents:** `program-charter.md`, `phase-1-detailed-plan.md`, `current-working-plan.md`, `lessons-log.md`, `README.md`

---

## Section 1: Agent Behavior — What to Do Without Asking

When working on a task in this project, agents should:

- Read the current working plan and charter before proposing new work
- Check the lessons log for relevant prior findings before proposing approaches
- Write unit tests for any new functional code before claiming completion
- Run existing tests before committing changes to verify no regressions
- Document non-obvious design decisions in code comments or dedicated markdown files
- Use type hints on all Python function signatures
- Follow PEP 8 style conventions, enforced by ruff or similar
- Commit with descriptive messages referencing the milestone or task

---

## Section 2: Agent Behavior — What Requires Asking First

Agents MUST confirm with the human operator before:

- Modifying any file in the production NT8 strategy directory (Flux V1 live code)
- Changing backtest methodology or fill assumptions in a way that affects prior results
- Adding new dependencies to the Python environment (confirm each addition)
- Committing code that doesn't pass existing tests
- Modifying the charter, Phase 1 plan, or other stable documents
- Purchasing paid data, services, or tooling
- Running code against live trading accounts (never without explicit approval)
- Removing or archiving significant artifacts (backtest results, research notebooks, etc.)

---

## Section 3: Code Conventions

### IDE and Runtime

- **IDE:** Cursor (a VS Code fork with built-in agentic AI). All editor operations and agent sessions run inside Cursor. Do not suggest or assume VS Code; the VS Code extension ecosystem (Python, Jupyter) is reachable from Cursor unchanged.
- **Runtime host:** Windows-native Python 3.13 with `uv`. WSL2 is not used for Phase 1 (see lessons-log 2026-04-26 for rationale). If a future phase needs Linux-only tooling, revisit then.

### Language and Style

- Python 3.11+ only
- PEP 8 style, enforced by ruff (configuration in pyproject.toml)
- Type hints required on all public function signatures
- Docstrings required on all public functions and classes (Google style preferred)
- Maximum line length: 100 characters
- Prefer explicit over implicit (no wildcard imports, no unused imports)

### File Organization

The research repo follows this structure:

```
repo_root/
├── README.md                           # Project entry point
├── pyproject.toml                      # Python project configuration
├── uv.lock                             # Locked dependencies
├── .gitignore
├── docs/                               # Project documentation
│   ├── program-charter.md
│   ├── phase-1-detailed-plan.md
│   ├── current-working-plan.md
│   ├── lessons-log.md
│   └── ai-project-instructions.md
├── src/                                # Production Python modules
│   └── quant_research/
│       ├── data/                       # Data loading and pipeline
│       ├── indicators/                 # Indicator library
│       ├── backtest/                   # Backtest engine
│       ├── modules/                    # Strategy module implementations
│       ├── statistics/                 # Statistical testing framework
│       ├── regime/                     # Regime detection framework
│       └── utils/                      # Shared utilities
├── tests/                              # Unit tests (pytest)
│   └── [mirrors src/ structure]
├── notebooks/                          # Jupyter notebooks for research
│   ├── exploration/                    # Ad-hoc exploration (can rot)
│   ├── experiments/                    # Named experiments with results
│   └── validation/                     # Reproduction and validation work
├── data/                               # Data files (gitignored for size)
│   ├── raw/                            # Raw contract files
│   └── processed/                      # Cleaned/combined datasets
└── results/                            # Backtest outputs, reports (gitignored)
```

### Naming Conventions

- Modules: lowercase with underscores (`data_loader.py`)
- Classes: CamelCase (`BacktestEngine`)
- Functions and variables: lowercase with underscores (`load_contract_data`)
- Constants: UPPERCASE with underscores (`DEFAULT_SLIPPAGE`)
- Notebooks: `YYYY-MM-DD_short_description.ipynb` for experiments; descriptive names for validation notebooks
- Test files: `test_<module_name>.py`

### Imports

- Standard library first, third-party second, local last
- Each group alphabetized
- No wildcard imports
- Prefer `import polars as pl` over `from polars import *`

---

## Section 4: Correctness Requirements

These are non-negotiable. Code that violates these does not ship.

### Unit Testing

- Any new functional code ships with unit tests
- Tests cover both happy path and edge cases
- Tests cover boundary conditions: first bar, last bar, session transitions, missing data
- Tests run via pytest; all tests must pass before committing
- Coverage target: 80%+ on core modules (data pipeline, backtest engine, indicators, strategy modules)

### Statistical Rigor

No claims of strategy performance are made without:

- Explicit IS/OOS split documented
- Walk-forward validation where appropriate
- Confidence intervals on key metrics (bootstrap where parametric assumptions don't hold)
- Deflated Sharpe ratio after multiple comparisons correction, once the statistical framework (M7) is operational
- Sample size sufficient for the claim (typically 100+ trades for module-level claims)

### Backtest Hygiene

- No look-ahead bias — indicators and decisions use only data available at the time of the bar
- Fill assumptions documented in the trade log output
- Slippage and commissions configurable; default values match NT8 for reproduction, realistic values for strategy evaluation
- Trade logs include full context: entry time, exit time, module, direction, quantity, entry price, exit price, P&L, exit reason
- Every backtest result commits with the code version that produced it (git SHA in output metadata)

### Pre-Registration for New Hypotheses

When researching a new strategy or filter:

1. Write down the hypothesis in a notebook before running the backtest
2. Specify the test conditions before seeing results
3. Count the hypothesis toward multiple-comparisons correction
4. Document the result whether positive or negative

This discipline exists because of the lesson from Phase 16-17: filters that look significant in-sample often don't survive OOS when multiple hypotheses were tested without correction.

---

## Section 5: Research Methodology

### Notebooks vs. Modules

- **Notebooks** are for exploration, experimentation, and one-off analysis. They can be messy. They should not contain logic that will be reused.
- **Modules** (in `src/`) are for reusable logic. They have tests. They have documentation. They have stable APIs.

The rule: if a piece of logic is used more than once, or if its correctness matters beyond the current notebook, it belongs in a module.

### Experiment Workflow

1. Pre-register hypothesis in a markdown cell at the top of the notebook
2. Load data using the standard data pipeline (never ad-hoc loading)
3. Run the experiment using the standard backtest engine (never ad-hoc backtesting)
4. Report results with statistical qualifications (CIs, sample sizes, OOS validation)
5. If the result changes plans or assumptions, add an entry to the lessons log
6. Commit the notebook with results for future reference

### Research Artifact Retention

- Keep all experiment notebooks even if the hypothesis failed — failure data informs future research
- Keep all backtest result outputs even for abandoned strategies — they're evidence against repeating mistakes
- Do not delete research artifacts without explicit approval

---

## Section 6: Lessons Log Rules

### What Goes In

Add an entry to the lessons log when any of the following occur:

- An assumption turned out to be wrong (backtest result contradicted expectation, architectural choice needed revising)
- A decision was made that wasn't in the plan (new approach, new tool choice, scope change)
- Something was significantly harder or easier than estimated (affects future estimation)
- A finding affects a future phase (insight about Flux V2 discovered during Phase 1 infrastructure work)
- A bug or methodology issue was discovered in existing work (NT8 backtests, prior research, etc.)
- A learning about market behavior emerged that has strategic implications
- An external event changed the context (market regime shift, prop firm rule change, etc.)

### What Does NOT Go In

- Routine task completions ("Finished M1 environment setup" — not a lesson, just a status update)
- Non-surprising progress ("Week 2 went as planned")
- Minor bug fixes or typo corrections
- Personal notes unrelated to program decisions

### Entry Format

```
## YYYY-MM-DD — [One-line summary]

**Phase:** [1/2/3/4 or parallel track ID]
**Context:** [What was being done when this was discovered]
**Finding:** [What was learned]
**Implication:** [What changes because of this — plans, assumptions, architecture, approach]
**Artifact:** [Link to code commit, backtest result, research notebook, or other supporting evidence]
```

Newest entries at the top.

### When an Agent Should Add an Entry

If an agent is working on a task and one of the "what goes in" conditions occurs, the agent should:

1. Flag the finding in its response to the operator
2. Propose a lessons log entry (full text, not a summary)
3. Add the entry upon operator approval

Agents should not add lessons log entries silently. The operator should see and approve each entry to maintain curation quality.

---

## Section 7: Project-Specific Constraints

### Data Format

- MNQ data format: semicolon-delimited `YYYYMMDD HHMMSS;Open;High;Low;Close;Volume`
- Source timezone: assumed to be CME native timing (America/Chicago)
- Known gaps: Jun 18 – Jul 31 2024, Feb 3 – Mar 11 2026
- Contract files: `MNQ MM-YY.Last.txt` (NT8 default export format: space between symbol and contract code, dot before "Last") where MM-YY is contract expiration code (03/06/09/12 quarterly + 2-digit year). Files live under `data/raw/`. Loader code should accept arbitrary filenames matching this glob rather than hardcoding the list.

### Flux Architecture Constraints

- OneModuleAtATime: only one strategy module can hold a position at any time
- Module priority order (for Flux V1): ORB → Momentum → AfternoonMR → Range
- Session windows:
  - ORB: 9:45+ ET, max 1 trade per day
  - Momentum: 9:30-14:30 ET
  - AfternoonMR: 14:00-16:00 ET (currently, subject to V2 replacement)
  - Range: ETH + RTH (currently, subject to V2 replacement)

### Prop Firm Compliance (Apex EOD $50K class — research defaults)

All strategy logic must respect **research-track** Apex Trader Funding **$50K EOD** constraints used in Phase 2 grading:

- **Starting balance:** **$50,000**
- **Pre-lock trailing drawdown:** **$2,000** below the **equity high-water mark** (floor starts at **$48,000** when HWM is $50K; floor rises **$1-for-$1** with new highs)
- **Lock:** when HWM reaches **$52,000**, the drawdown floor **locks permanently at $50,000** (post-lock breach if equity **&lt; $50,000**)
- **Eval profit target:** **+$3,000** vs start (account reaches **$53,000**)
- **Daily loss limit (DLL):** **$1,000** per **America/New_York** calendar day on **realized** P&amp;L (research convention: day total **&lt; −$1,000** fails, consistent with Wave 0 eval sim)
- Max contracts: 60 MNQ on $50K account, 80 MNQ on $100K account (full-size NQ equivalents)
- Consistency rule: no single trading day may be >30% of total profit

These are production constraints. Research code may explore strategies that violate them, but any proposed live deployment must verify compliance. **Older docs** that cite **$3,000** trail and **starting balance + $100** lock describe a **superseded** research mistake — see `docs/lessons-log.md` (**Wave 0c correction**).

### NT8 Integration

- NT8 remains the execution platform throughout the program
- C# module implementations live in `NinjaTrader/Strategies/Flux/` (outside this research repo)
- Python-validated strategies must be ported to C# for live deployment
- Port-fidelity checking is a step between Phase 2 completion and live deployment

---

## Section 8: Security and Privacy

- No API keys, passwords, or account credentials in the repo (use environment variables or a gitignored `.env` file)
- No prop firm account numbers in commit messages or code
- No trade logs from live accounts committed to the repo (live logs stay local)
- Research repo is private on GitHub; do not make public without explicit decision

---

## Section 9: Document Maintenance

Which documents get updated when:

| Event | Charter | Phase Plan | Working Plan | Lessons Log | AI Instructions |
|---|---|---|---|---|---|
| Routine weekly progress | — | — | Update tasks | — | — |
| Significant finding | — | — | — | Add entry | — |
| Phase 1 milestone complete | — | Mark complete | Update current tasks | Maybe entry | — |
| Phase completed | Update phase status | Archive | New plan drafted | Summary entry | — |
| Major assumption invalidated | Consider update | Possible update | Update tasks | Add entry | — |
| New AI agent rule needed | — | — | — | — | Update |
| New tool adopted | — | Mention | Mention | Add entry | Update conventions |

### Change Discipline

- Charter changes are rare and should be preceded by discussion
- Phase plans change when milestones complete or stop conditions trigger
- Working plans update weekly at minimum
- Lessons log is append-only (no editing or deletion of entries)
- AI instructions evolve as agent usage patterns reveal gaps

---

## Section 10: Operator Interaction Style

When an agent is assisting with work in this project:

- Be direct about uncertainty. If the agent isn't sure whether an approach is correct, say so.
- Push back on decisions that seem wrong. The operator prefers disagreement over sycophancy.
- Don't oversell intermediate progress. "Done" means tested and validated, not "wrote some code."
- Flag when a task might trigger a stop condition or violate a constraint.
- Reference the relevant documents when suggesting approaches. "Per the charter, this should..." grounds decisions in prior commitments.
- When in doubt about scope, ask. Scope creep is the main risk in a multi-year solo project.

---

## Section 11: Revision Log

| Date | Revision | Rationale |
|---|---|---|
| 2026-04-20 | Initial instructions | Program formalization; guidance needed before AI-assisted development begins |
| 2026-04-26 | Added IDE/runtime conventions (Section 3) | Codified Cursor as the IDE and Windows-native Python as Phase 1 runtime; see lessons-log 2026-04-26 |
