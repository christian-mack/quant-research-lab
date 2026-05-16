# **OPERATOR — STOP CONDITIONS TRIGGERED (see end of note)**

# Wave 0c — ORB+Opt3 two-gate baseline ($2K trail / $52K lock / $50K floor)

**Git SHA:** `3177dc0fe2a3450cbd29594d96177e906691fc89`  
**Dirty tree:** True  
**Generated:** 2026-05-16T06:12:14.620109+00:00  

## Apex rules (corrected)

- **Start:** $50,000 — **pre-lock floor** trails as HWM − **$2,000** (initial floor $48,000).
- **Lock:** when **high-water equity ≥ $52,000**, floor **locks at $50,000**.
- **Profit target (eval):** account reaches **$53,000** (+$3,000).
- **DLL:** NY calendar day realized sum **&lt; −$1,000** fails (same convention as Wave 0).

## Deliverable 1 — Two gates (6y daily funded path vs 30-session eval windows)

### Funded survival (chronological **session / daily** totals, scaled)

| q | Survived | Trail breach sessions | DLL fail | Locked HWM≥$52K | Min margin pre | Min margin post |
|---|----------|------------------------|----------|----------------|----------------|-----------------|
| 1 | True | 0 | False | True | 1249.00 | 827.50 |
| 2 | False | 0 | True | True | 1479.00 | 1102.00 |
| 3 | False | 0 | True | True | 1218.50 | 1609.50 |
| 4 | False | 0 | True | True | 958.00 | 2146.00 |
| 5 | False | 0 | True | True | 697.50 | 2400.00 |

**Funded q_max (passing subset):** **1**  

### Eval pass rate (trade-by-trade in each 30-session window)

| q | Pass | Total windows | Pass rate |
|---|------|---------------|-----------|
| 1 | 30 | 1532 | 1.96% |
| 2 | 30 | 1532 | 1.96% |
| 3 | 53 | 1532 | 3.46% |
| 4 | 164 | 1532 | 10.70% |
| 5 | 262 | 1532 | 17.10% |

## Deliverable 2 — Bootstrap funded survival (all q ∈ {1..5}, blocks 5 / 20 / 50)

See JSON `deliverable_2_bootstrap_funded_survival_all_q`. Summary for **funded q_max**:

| Block | Survival frac | pre p01 | pre p95 | pre p99 |
|-------|---------------|---------|---------|---------|
| 5 | 0.6100 | -3799.10 | 1651.02 | 1893.00 |
| 20 | 0.5849 | -4355.03 | 1727.00 | 2000.00 |
| 50 | 0.6032 | -3367.56 | 1840.00 | 1840.00 |

### Grading pair (funded_q_max, eval pass rate at that q)

- **(1, 1.96%)** — see Deliverable 3 for window counts.

## Deliverable 3 — Eval pass rate at funded q_max

- **Passing windows:** 30 / 1532 (**1.96%**)

## Deliverable 4 — Graded economics at funded q_max

- **q used:** 1 (0 if no funded-passing qty)
- **Avg annual P&amp;L:** $1,014.16
- **Tier:** below_floor
- **Profitable years (2020–2026):** 4 / 7

## STOP flags (from JSON `stop_conditions`)

- **Funded fails q=1:** False
- **Eval 0% all q:** False
- **Bootstrap survival &lt; 80% at funded q_max:** True

Full JSON: `2026-05-17_wave0c_orb_opt3_two_gate_baseline.json`
