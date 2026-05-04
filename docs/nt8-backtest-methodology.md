# NT8 Backtest Methodology (Flux V1 research baseline)

**Document type:** Reference (not a lessons-log entry).  
**Purpose:** Single source of truth for how Flux V1 strategies were (or are) backtested in NinjaTrader 8, so the Python engine (M4) and M6 validation can mirror or consciously diverge from NT8.  
**Status:** **Complete** — **2026-04-30.** Values below come from operator-provided Strategy Analyzer assumptions, **`docs/nt8-artifacts/`** CSV exports, and committed Flux **C#** sources (`docs/nt8-artifacts/flux/`). Supplementary screenshot staging (`docs/nt8-screenshots/`) is optional for future UI captures; this revision does not depend on it.

**Sequencing (approved):** PT3 (this document) → M4 design §9 sign-off → M4 implementation.

---

## 1. Scope and non-goals

**In scope**

- Historical backtest / Strategy Analyzer assumptions used for the **6-year ORB+Opt3 baseline** (2020-01-01 → 2026-04-19) and for M6 parity work.
- MNQ as traded in Flux V1.
- Execution realism: fills, commissions, slippage, sessions, and NT8-/strategy-level order rules that affect P&L.

**Out of scope (for this document)**

- Live SIM / production routing beyond what is needed to interpret sizing (document separately if it differs materially from backtest).
- Phase 1b execution platform migration.
- Python implementation details (see `docs/m4-backtest-engine-design.md`).

---

## 2. Data and instrument (research repo vs NT8)

| Topic | Value / convention |
|--------|-------------------|
| **Primary symbol (backtest)** | **MNQ** — chart/export semantics match **1-minute** data. Operator uses **continuous MNQ** in Strategy Analyzer for the 6-year protocol. **Research repo:** continuous MNQ built from NT8-exported `MNQ MM-YY.Last.txt`; loader converts source timestamps **UTC → America/Chicago** (`lessons-log.md` 2026-04-27). |
| **Bar type / timeframe** | **1 minute.** |
| **Session / hours** | **No custom session template applied** — NT8 default session handling for the chart/instrument. Strategy-side: **`RTHOnly`** is a **parameter** (see §8); production funded/export row uses **`True`**. |
| **Tick size** | **0.25** (CME MNQ standard). |
| **Point value** | **$2** per index point (MNQ; operator-confirmed). |
| **Instrument Manager** | **No customization** — standard CME MNQ instrument definitions in NT8. |

---

## 3. Backtest configuration (Strategy Analyzer–class settings)

| Setting | Value |
|---------|--------|
| **Date range (6-year ORB+Opt3 baseline protocol)** | **2020-01-01** through **2026-04-19** (inclusive interpretation per NT8 date picker; operator-defined). |
| **Starting capital / account size in Analyzer** | **Not configurable** in Strategy Analyzer in a way that changes the backtest mechanics here. **Reference notional:** **$50,000** — use for **max drawdown interpretation** and alignment with **$50K prop** account context in production. |
| **Include commissions** | **No — $0.** Excluded by **operator decision.** **Rationale:** prop commission rates vary by account; edge validation is prioritized over net-of-commission P&L for now. Commission modeling is **deferred** until Python infrastructure is stable; total edge must be large enough that commission impact is expected to be minor. |
| **Include slippage** | **0 ticks** (NT8 default; never changed). |
| **Fill type (Analyzer)** | Default: **“By strategy”** / strategy-driven fill resolution (operator). Aligns with managed stops/targets and **`OrderFillResolution.Standard`** in strategy defaults (§4). |
| **Data series** | **1-minute MNQ continuous** (operator). |

---

## 4. Fill model and intrabar behavior

**Why it matters:** M6 divergences often trace here.

| Topic | Ground truth / note |
|--------|---------------------|
| **Signal / bar timing** | Strategy defaults: **`Calculate = OnBarClose`** — logic runs on **bar close** unless overridden in code paths. |
| **Order fill resolution** | **`OrderFillResolution.Standard`** (`FluxV1Strategy.cs` `OnStateChange` → `SetDefaults`). |
| **Slippage (strategy)** | **`Slippage = 0`** in `SetDefaults` — consistent with §3. |
| **Limit-touch fills** | **`IsFillLimitOnTouch = false`** in `SetDefaults`. |
| **Entry mechanism** | **`EnterLong` / `EnterShort`** with **`SetStopLoss` / `SetProfitTarget`** set **before** entry (managed bracket pattern) in `ExecutionEngine.cs`. |
| **Stop / target handling** | **`StopTargetHandling.ByStrategyPosition`** — one stop + one target per **strategy position** (comment in source: avoids quantity-dependent partial-fill exit fragmentation). |
| **Intrabar OHLC ordering** | Governed by NT8 **Standard** fill resolution and Analyzer historical data — **exact same-bar sequencing** for stops vs targets should be treated as **NT8-defined**; M6 should match NinjaTrader’s documented behavior for this mode or flag measured deltas. |

*Open point (not guessed):* If Strategy Analyzer global **Backtest…** options introduce an additional layer beyond `OrderFillResolution.Standard`, capture a screenshot or NT8 version Help reference in a future revision. **Proposed M6 approach:** treat **committed C# + Standard resolution + OnBarClose** as the **primary** behavioral spec; compare trade list timing against Python.

---

## 5. Commissions

| Topic | Value |
|--------|--------|
| **Mode** | **$0** — excluded (§3). |
| **Per-side / round-turn** | N/A for current baseline. |
| **Future work** | When commission templates are added for net P&L, document template name and per-contract economics here and in M4 `CommissionSpec`. |

---

## 6. Slippage

| Topic | Value |
|--------|--------|
| **Enabled** | **No** — **0 ticks** (operator; matches strategy `Slippage = 0`). |
| **Model** | None / zero. |

---

## 7. Orders: Time in force, partial fills, multi-fill behavior

| Topic | Ground truth |
|--------|--------------|
| **Default TIF** | **`TimeInForce.Gtc`** in `FluxV1Strategy` `SetDefaults`. |
| **Entry / exit** | Market-style entries via `EnterLong`/`EnterShort`; exits via `ExitLong`/`ExitShort` and managed stop/target. **Confirm in NT8** whether any module path submits working limit entries — M5 port should trace `ExecutionEngine` for each `ModuleId`. |
| **Partial fills** | Not separately modeled in Flux C# excerpt reviewed; NT8 backtest engine simulates Part 1: Managed stop/target with **ByStrategyPosition** reduces duplicate exit-order fragmentation (see source comment). |
| **Brackets** | **SetStopLoss** + **SetProfitTarget** + entry — treat as **OCO-style managed bundle** per NT8 managed order rules. |

---

## 8. Strategy parameters and configs (CSV + modules)

### 8.1 Artifact locations

| Artifact | Path | Role |
|----------|------|------|
| Production + sizing references | `docs/nt8-artifacts/flux-v1-orb-opt3-funded.csv` | Operator-labeled **current production** export. |
| Historical / lessons reference | `docs/nt8-artifacts/flux-v1-quad-module.csv` | Operator-labeled **historical** config tied to **April 2026 lessons log** backtest citations. |
| Flux C# sources | `docs/nt8-artifacts/flux/**/*.cs` | **Ground-truth** execution and parameter **definitions** for M5 validation. |

### 8.2 Important finding: CSV identity

A **byte-for-byte compare** of `flux-v1-orb-opt3-funded.csv` and `flux-v1-quad-module.csv` in this repo shows **identical content** (all rows).

**Implication:** This repository **does not** currently store a distinct on-disk parameter set for the **quad-module / tri-module** era described in **`lessons-log.md` (2026-04-28)** (multi-module + pre–Opt3 baselines).  

**Proposed interpretation (operator confirm):**

1. Treat the CSV as the **canonical export format** for **current** ORB+Opt3 live lanes (eval + funded) + one **Sim** template row.  
2. For M6 reproduction of **historical multi-module** results, either (a) obtain a **separate export** from the NT8 workspace / backup that produced those runs, or (b) reconstruct enables + `ORBLatestEntryHourET` (0 vs 11) + per-module quantities from archived notes and **diff against the table below**.

Do **not** assume quad-module numbers can be replayed from `flux-v1-quad-module.csv` **until** a non-identical export exists.

### 8.3 Parsed rows (from either CSV — content identical)

Exports include **three** enabled rows per file (Strategy `FluxV1`, instrument `MNQ JUN26`, data series `1 Minute`). **Parameters** column is NT8’s **`value / value / … (Name/Name/…)`** encoding.

| Account display name (export) | **ORBQuantity** | **ORBLatestEntryHourET** | **EnableORBModule** | **EnableMomentumModule** | **EnableRangeModule** | **EnableAfternoonMRModule** | **RTHOnly** |
|-------------------------------|-----------------|--------------------------|---------------------|--------------------------|----------------------|----------------------------|-------------|
| `APEX3027390000023` (eval-style row in export) | **10** | **11** | True | False | False | False | True |
| `PAAPEX3027390000003` (funded PA row in export) | **3** | **11** | True | False | False | False | True |
| `SimFlux v1` | **16** | **0** | True | False | True | True | False |

**Production ORB+Opt3 (lessons log):** **`ORBLatestEntryHourET = 11`** — confirmed on **live** eval/funded rows. The **Sim** row shows **`ORBLatestEntryHourET = 0`** and enables **Range + AfternoonMR** — treat as **not** matching production ORB+Opt3; do not use this row for the 6-year ORB+Opt3 baseline without operator sign-off.

### 8.4 Full parameter set (funded PA row — canonical for production ORB+Opt3)

Parsed from **row `PAAPEX3027390000003`** (`ORBQuantity = 3`, `ORBLatestEntryHourET = 11`). **All** name/value pairs:

| Parameter | Value |
|-----------|-------|
| AfternoonMRBETriggerR | 1 |
| AfternoonMREnableBE | True |
| AfternoonMREndHour | 15 |
| AfternoonMRMaxATR | 35 |
| AfternoonMRMaxDailyTrades | 3 |
| AfternoonMRMaxVWAPDev | 60 |
| AfternoonMRMinVWAPDev | 15 |
| AfternoonMRQuantity | 20 |
| AfternoonMRStartHour | 13 |
| AfternoonMRStopDistance | 20 |
| AfternoonMRTargetFraction | 0.5 |
| CloseContMaxATR | 35 |
| CloseContMinSetupMag | 5 |
| CloseContQuantity | 1 |
| CloseContStopDistance | 25 |
| CloseContTargetDistance | 25 |
| DynamicSizerBufferThreshold | 1000 |
| DynamicSizerFullMultiplier | 1.25 |
| DynamicSizerInitialMultiplier | 0.5 |
| EnableAfternoonMRModule | False |
| EnableCloseContModule | False |
| EnableDynamicSizer | False |
| EnableFileAuditLogging | False |
| EnableLogging | False |
| EnableMomentumModule | False |
| EnableORBModule | True |
| EnableRangeModule | False |
| EnableVolatilityGate | True |
| LogLevelValue | 3 |
| MaxDailyLoss | 2000 |
| MaxTradesPerDay | 10 |
| MaxTrailingDrawdown | 4500 |
| MomentumBETriggerR | 1.5 |
| MomentumBlockedHoursET | 91314 |
| MomentumDailyProfitCap | 0 |
| MomentumEnableAutoBreakEven | True |
| MomentumEnableVWAPFilter | False |
| MomentumFixedStopDistance | 80 |
| MomentumHardExitHourCT | 0 |
| MomentumMaxATR | 30 |
| MomentumMaxATR15m | 40 |
| MomentumMaxDailyTrades | 3 |
| MomentumParityMode | True |
| MomentumQuantity | 0 |
| MomentumVWAPDeviation | 0 |
| ORBBETriggerR | 1 |
| ORBEarliestEntryHourET | 10 |
| ORBEnableBreakEven | True |
| ORBEnableVWAPFilter | True |
| **ORBLatestEntryHourET** | **11** |
| ORBMaxATR15m | 0 |
| ORBMaxHoldMinutes | 0 |
| ORBMaxRangeATR | 2.5 |
| ORBMaxStopATR | 1.5 |
| ORBMaxStopPoints | 80 |
| ORBMinRangeATR | 0.25 |
| **ORBQuantity** | **3** |
| ORBTargetMultiplier | 0.8 |
| ORBUseATRRangeFilter | False |
| ORBUseATRStop | False |
| RangeBlockedHoursCT | 72022 |
| RangeQuantity | 16 |
| RangeTrailMultiplierInitial | 0.5 |
| RangeTrailMultiplierMid | 0.4 |
| RangeTrailMultiplierTight | 0.3 |
| RangeTrailRatchetEnabled | True |
| RangeTrailRatchetThreshold1R | 1 |
| RangeTrailRatchetThreshold2R | 2 |
| RTHOnly | True |
| VolHighPercentile | 0.7 |

**Eval row** (`APEX…0023`): identical parameters except **`ORBQuantity = 10`** (operator: **$50K EOD eval** sizing vs **qty 3** funded).

### 8.5 Module table (M6 scope)

| Module | Strategy / namespace | Notes |
|--------|----------------------|--------|
| ORB | `Modules.ORB` / `ORBModule.cs` | **Production focus;** Opt3 = **`ORBLatestEntryHourET = 11`**. |
| Momentum | `Modules.Momentum` | Disabled in production CSV exports above; still in scope for **historical** M6 replay if/when parameters are recovered. |
| Range | `Modules.Range` | Same. |
| Afternoon MR | `Modules.AfternoonMR` | Same. |

**Aggregator:** `FluxV1Strategy.cs` + `ExecutionEngine.cs` + `ModuleRouter.cs` — **one module active at a time (OMAT)**, central risk (`RiskManager`, limits in CSV / strategy).

---

## 9. Outputs and reproducibility

| Topic | Detail |
|--------|--------|
| **Baseline artifacts** | Strategy Analyzer **Summary / trade list** exports live outside this methodology; **parameter exports** committed as **`docs/nt8-artifacts/*.csv`**. |
| **NT8 version** | **Not recorded** in repo as of 2026-04-30 — **recommended:** append NT8 exact version string here when known. |
| **Source revision** | Flux C# tree under **`docs/nt8-artifacts/flux/`** — treat as parity reference for M5/M6. |

---

## 10. Traceability to Python (M4 / M6)

- Each setting in §§2–7 should map to a **`BacktestRunSpec`** / related field in `docs/m4-backtest-engine-design.md`, or an explicit **“Python uses X; NT8 uses Y”** delta.
- **`ORB+Opt3` / `ORBLatestEntryHourET`** must match **§8** for the **6-year baseline** run configuration.
- **`$0` commission** is a **conscious baseline simplification** — net P&L in Python for “apples-to-apples” M6 should match this assumption unless intentionally testing commission sensitivity.

---

## 11. Operator input checklist (PT3 closure)

Evidence for this **Complete** revision is **committed artifacts** + operator explicit answers (not necessarily screenshots).

1. [x] Strategy Analyzer **settings** — captured in **§3** and operator narrative (date range, slippage, fill type, commission $0, continuous MNQ 1m, $50K DD reference).
2. [x] **Commission** — §5 ($0, rationale documented).
3. [x] **Instrument** — §2 (tick **0.25**, point **$2**, no Instrument Manager customization).
4. [x] **Strategy parameters** — §8 (CSV parse + tables); **C#** in `docs/nt8-artifacts/flux/`.
5. [x] **Date range** — §3 (**2020-01-01** → **2026-04-19**).
6. [ ] **NT8 version string** — still **TBD** (recommended follow-up).
7. [ ] **Historical quad-module export** distinct from ORB+Opt3 — **missing** today (§8.2); required for confident replay of April lessons multi-module baselines.

---

## 12. M4 implementation gate — operator review

PT3 (**this document**) is **Complete** as of **2026-04-30**. Per program sequencing, **M4 coding** remains blocked until **`docs/m4-backtest-engine-design.md` §9** is explicitly signed off.

**Please complete in `m4-backtest-engine-design.md` §9:**

- [ ] Operator: review the M4 backtest engine design.
- [ ] Operator: confirm **`docs/nt8-backtest-methodology.md`** is acceptable as the NT8 reference (including **$0** commission baseline and **§8.2** CSV caveat for historical configs).
- [ ] Record **approval date / initials** in **§9** before the first M4 implementation PR.

---

## 13. Open ambiguities (clarify rather than guess)

| Item | Issue | Proposed next step |
|------|--------|-------------------|
| **`flux-v1-quad-module.csv` vs `flux-v1-orb-opt3-funded.csv`** | Files are **identical** in git; cannot distinguish historical multi-module export from current. | Operator supplies **non-identical** historical export or confirms **lessons log** numbers were produced with a documented NT8 workspace not captured here. |
| **Sim row (`SimFlux v1`)** | **`ORBLatestEntryHourET = 0`**, modules enabled differ from production. | Do **not** treat as ORB+Opt3 baseline row; confirm intended use (if any) for M6. |
| **NT8 Analyzer vs strategy `SetDefaults`** | Rare mismatches if UI overrides strategy defaults on compile. | When in doubt, **C# `SetDefaults` + saved workspace** wins; screenshot optional. |
| **NT8 exact version** | Not in repo. | Operator adds one line to §9 table when convenient. |

---

## Revision history

| Date | Change |
|------|--------|
| 2026-04-28 | Initial scaffold; operator checklist; data/session context from research repo. |
| 2026-04-29 | §11: screenshot staging under `docs/nt8-screenshots/`; merge workflow after operator commit. |
| 2026-04-30 | **Complete:** Strategy Analyzer + instrument + session + commission/slippage; §8 CSV parse + **ORBLatestEntryHourET=11**; **`docs/nt8-artifacts/flux/`** as C# ground truth; §8.2 CSV identity caveat; §12–13 ambiguities; M4 §9 called out for sign-off. |
