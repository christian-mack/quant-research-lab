# Wave 0b — R(q) methodology investigation

**Git SHA:** `f95fb9fc20ff94d9e941fb210d4970e56375a2ee`  
**Dirty tree:** True  
**Generated:** 2026-05-16T05:15:31.282436+00:00  

## Scope

Methodology investigation (not a strategy hypothesis): reconcile **closed-trade cumulative DD** (Wave 0) with **session-close aggregation** and **Apex-style EOD trailing rules**, block-bootstrap tail of max DD, and optional live funded CSV.

### Account / rule assumptions

- **Starting balance:** **$50,000** ($50K EOD class; see `docs/ai-project-instructions.md`).
- **Trailing:** \$3,000 below high-water **equity** after each session’s net P&amp;L.
- **Funded-style lock (`funded_lock`):** when HWM first reaches start+\$100, `locked_floor = HWM_at_lock − \$3,000`; **allowed minimum equity** stays at `locked_floor` (does not rise with later equity highs). **Pure trailing** keeps `allowed_min = HWM − \$3,000` throughout.
- **DLL:** sessions with daily P&amp;L &lt; **\-$1,000** are counted; path is **not** censored for DD (underlying profile).

## Deliverable 1 — EOD trailing on 6y ORB+Opt3 daily P&amp;L

| Qty | Mode | Peak-to-trough DD on equity | Min margin to floor | Breach sessions | DLL hits | Binding session |
|-----|------|----------------------------|---------------------|-----------------|----------|----------------|
| 1 | pure_trailing | $2,675.00 | $325.00 | 0 | 0 | 2020-01-02 |
| 1 | funded_lock | $2,675.00 | $2,739.50 | 0 | 0 | 2020-01-02 |
| 2 | pure_trailing | $5,350.00 | $-2,350.00 | 125 | 4 | 2023-11-16 |
| 2 | funded_lock | $5,350.00 | $2,479.00 | 0 | 4 | 2020-01-02 |
| 3 | pure_trailing | $8,025.00 | $-5,025.00 | 249 | 5 | 2023-11-16 |
| 3 | funded_lock | $8,025.00 | $2,328.00 | 0 | 5 | 2020-01-02 |

**Interpretation:** **funded_lock** freezes the trailing floor after the first HWM ≥ start+\$100; on this backtest that removes **trailing breach** sessions at qty 2–3 that appear under **pure_trailing**, while **DLL** flags are unchanged. **Peak-to-trough** equity drawdown at q=3 still reaches **\$8,025**, matching closed-trade ×3 — the “stop” gap example (EOD \ll closed×3) **did not occur** here.

- **Wave 0 closed-trade DD(1):** \$2,675.00 (recomputed here; logged \$2,675).
- **Wave 0 closed-trade DD(3) scaled:** \$**8,025**.
- **EOD funded_lock DD(3):** \$**8,025.00**.

### Finding — closed-trade vs EOD (qty=3)

Ratio of EOD DD to linear scaled closed-trade DD is in JSON — review if margin is narrower than the example in the investigation brief.

## Deliverable 2 — Block bootstrap max DD (qty=1), 10k resamples, seed=42

Per block length: **closed-trade** max DD (positive magnitude) and **EOD** peak-to-trough on the **collapsed session series** under **funded_lock**.

| Block len | Closed p95 | Closed p99 | EOD p95 | EOD p99 |
|-----------|------------|------------|---------|---------|
| 1 | $5,112.52 | $6,623.60 | $5,112.52 | $6,623.60 |
| 5 | $4,815.15 | $6,162.07 | $4,815.15 | $6,162.07 |
| 10 | $5,344.60 | $6,866.10 | $5,342.12 | $6,866.10 |

Percentiles + **histograms** (40 bins) per block length are in JSON; re-run the script to regenerate 10k draws.

## Deliverable 3 — Live production audit

**Incomplete:** place operator CSV at `data/wave0b_live_funded_daily.csv` (under gitignored `data/`). No live conclusions without it.

## Operator review summary

- **Empirical DD(1) under EOD funded_lock (point, 6y):** \$2,675.00 peak-to-trough on equity.
- **Bootstrap (block=5) closed-trade DD qty=1:** **p95 \$4,815.15**, **p99 \$6,162.07**.
- **Bootstrap (block=5) EOD funded_lock DD qty=1:** **p95 \$4,815.15**, **p99 \$6,162.07**.
- **Live audit:** **Not completed** (no CSV).

### Proposed R(q) (for operator decision only)

Using **percentile** margin instead of **1.5×**, illustrative forms at qty=1 scale:

- **R₁(q)** = max( **4815.15** × q , q × **2675.00** + 500 ) → largest q ≤ \$3k ceiling: **0**.
- **R₂(q)** = max( **4815.15** × q , q × **2675.00** + 500 ) → **0**.

Legacy Wave 0 rule gave **q_max = 0** at DD(1)=\$2,675.

Artifacts: `2026-05-16_wave0b_rq_methodology.json`, runner `scripts/run_wave0b_rq_methodology.py`.
