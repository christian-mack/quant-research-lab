# NT8 Backtest Methodology (Flux V1 research baseline)

**Document type:** Reference (not a lessons-log entry).  
**Purpose:** Single source of truth for how Flux V1 strategies were (or are) backtested in NinjaTrader 8, so the Python engine (M4) and M6 validation can mirror or consciously diverge from NT8.  
**Status:** *Scaffold* — structure and Python/research-repo context are filled in. **Sections marked “OPERATOR REQUIRED” must be completed from your live NT8 workspace** (Strategy Analyzer settings, order handling, commissions UI, instrument properties, screenshots or exported summaries acceptable). **Screenshot drop zone:** `docs/nt8-screenshots/` (see that folder’s `README.md`). After images are committed, an agent pass merges extracted values into §§2–9 and updates §11.

**Sequencing (approved):** PT3 (this document) → M4 design → operator review → M4 implementation.

---

## 1. Scope and non-goals

**In scope**

- Historical backtest / Strategy Analyzer (or equivalent) assumptions used to produce the baseline results that M6 will compare against Python.
- MNQ (and NQ if used) as traded in Flux V1.
- Execution realism: fills, commissions, slippage, session templates, and any NT8-specific order rules that affect P&L.

**Out of scope (for this document)**

- Live SIM / production routing (document separately if it differs materially from backtest).
- Phase 1b execution platform migration.
- Python implementation details (see `docs/m4-backtest-engine-design.md`).

---

## 2. Data and instrument (research repo vs NT8)

| Topic | Known in this repo | OPERATOR REQUIRED |
|--------|-------------------|-------------------|
| **Primary symbol** | MNQ continuous research series built in Python from NT8-exported contract files `MNQ MM-YY.Last.txt`; loader converts UTC → `America/Chicago`. | Confirm NT8 backtest uses **same root symbol** (e.g. continuous vs front month, roll / data feed vendor). |
| **Bar type / timeframe** | Minute bars aligned to research pipeline. | NT8 bar period (1m / etc.), **Merge policy** (if any), **Break at EOD** settings. |
| **Session / hours** | Python: RTH / ETH / BREAK / HOLIDAY via `CME_Equity` + `session.py`. | NT8 **session template** name attached to the chart/instrument for backtest; any **eth all / rth only** flags. |
| **Tick / point value** | *Exchange reference:* CME Micro E-mini Nasdaq-100 futures (**MNQ**) — minimum price fluctuation **0.25 index points**; micro contract multiplier vs NQ is documented by CME. **Verify in NT8** Instrument Manager (tick size, point value, currency). | Screenshot or copy-paste from NT8 **Instruments** → MNQ (or data series used in backtest). |

---

## 3. Backtest configuration (Strategy Analyzer–class settings)

| Setting | OPERATOR REQUIRED |
|---------|-------------------|
| **Date range** | Exact from / to used for “official” Flux V1 baseline comparisons (per module if different). |
| **Starting capital** | … |
| **Include commissions** | Y/N; if Y, see §5. |
| **Include slippage** | Y/N; if Y, see §6. |
| **SetOrderQuantity / default quantity** | … |
| **Maximum bars lookback** | If relevant to memory or indicator warm-up. |

---

## 4. Fill model and intrabar behavior

**Why it matters:** M6 divergences often trace here.

| Topic | OPERATOR REQUIRED |
|--------|-------------------|
| **Default fill resolution** | How NT8 resolves fills when using historicalminute data (e.g. fill on **close of signal bar** vs **open of next bar** vs other Analyzer options). |
| **Market order fills** | Assumed price (bar open / close / bid-ask model if any). |
| **Stop / limit fills** | Intrabar assumption: touched = filled, or OHLC ordering, or pessimistic/optimistic mode. |
| **Gaps through stops** | Fill at gap open or stop price. |
| **Max lookahead** | Any NT8 setting that allows/prohibits seeing same-bar high/low for fill. |

*Research-repo placeholder:* Phase 1 plan text mentions **next-bar open for market orders for baseline** — **do not treat as NT8 ground truth until confirmed in your Analyzer/strategy.*

---

## 5. Commissions

| Topic | OPERATOR REQUIRED |
|--------|-------------------|
| **Template** | Named commission template or per-order values. |
| **Per-side vs round-turn** | Dollar(s) per contract per fill and whether entry and exit both charged. |
| **Exchange / regulatory fees** | Included in template or disabled for baseline. |

---

## 6. Slippage

| Topic | OPERATOR REQUIRED |
|--------|-------------------|
| **Enabled** | Y/N. |
| **Model** | Fixed ticks, % of price, volatility-linked (if any NT8 option), none. |
| **Direction** | Symmetric vs worse-case for entries/exits. |

---

## 7. Orders: Time in force, partial fills, multi-fill behavior

| Topic | OPERATOR REQUIRED |
|--------|-------------------|
| **Default TIF** | GTC, DAY, etc., for market / limit / stop variants used by Flux. |
| **Partial fills** | Supported Y/N; how backtest simulates partials on historical data. |
| **OCO / bracket** | If modules use brackets, how NT8 fills legs in backtest. |

---

## 8. Module-specific NT8 settings (Flux V1)

For **each** module in scope for M6 (ORB, Momentum, Range, AfternoonMR — adjust names to match your codebase):

| Module | Strategy / class name in NT8 | Parameters file / screenshot | **OPERATOR REQUIRED** notes |
|--------|-------------------------------|-------------------------------|----------------------------|
| ORB | … | … | Unique fill/session overrides if any. |
| Momentum | … | … | … |
| Range | … | … | … |
| Afternoon MR | … | … | … |

**Aggregator / controller:** If one strategy hosts sub-modules, document **priority order**, **OneModuleAtATime** (or equivalent), and any **disable / throttle** logic that affects which orders fire.

---

## 9. Outputs and reproducibility

| Topic | OPERATOR REQUIRED |
|--------|-------------------|
| **Baseline artifacts** | Where Summary / trade list / CSV exports live (path convention, naming). |
| **Version** | NT8 version (e.g. 8.1.x) and workspace name. |
| **Strategy assembly hash / export** | If you version exported strategy ZIP or git SHA for `NinjaTrader` folder (outside this repo). |

---

## 10. Traceability to Python (M4 / M6)

- Every **numbered operator-required row** above should eventually map to a **configuration field** in `docs/m4-backtest-engine-design.md` (or explicit “Python uses X; NT8 uses Y” for known deltas).
- Unknown items stay **TBD** here until filled; M4 **must not** hard-code “matching NT8” for those items without operator sign-off.

---

## 11. Operator input checklist (gather before locking M4 defaults)

**Staging:** Commit evidence under **`docs/nt8-screenshots/`** (see `docs/nt8-screenshots/README.md` for suggested filenames). Plain-text sidecars (e.g. session template name) are welcome.

**After artifacts are on `main`:** Request a doc pass to transcribe **concrete values** into §§2–9 (replacing OPERATOR REQUIRED placeholders), tick the boxes below, set **Status** at document top to **Complete** with date, add **Revision history**, then proceed to **`docs/m4-backtest-engine-design.md` §9** approval.

Paste or attach to this task (sensitive items may stay out of git; then summarize numbers here only):

1. [ ] Strategy Analyzer **screenshots** in `docs/nt8-screenshots/` (general + **Order handling** / **slippage** / **historical fill** pages if separate).
2. [ ] **Commission** template definition (screenshot, text export, or values typed into §5).
3. [ ] **Instrument** MNQ (and any alternate series) properties in `docs/nt8-screenshots/` or §2: tick size, point value, margin (optional).
4. [ ] Per-module **strategy parameters** (screenshot in `docs/nt8-screenshots/` or table in §8).
5. [ ] **Date range(s)** used for “official” baseline backtests per module (typed into §3 / §8).
6. [ ] One **sample trade list** or Summary snippet for sanity-checking fill timestamps vs bar index (screenshot, CSV path note, or §9).

When the checklist is complete, update §§2–9 by replacing tables with finalized values and bump **Status** at the top from *Scaffold* to *Complete* with date.

---

## Revision history

| Date | Change |
|------|--------|
| 2026-04-28 | Initial scaffold; operator checklist; data/session context from research repo. |
| 2026-04-29 | §11: screenshot staging under `docs/nt8-screenshots/`; merge workflow after operator commit. |
