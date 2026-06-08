# P2-W2 Gate #1 mortality screen (IS partition)

**Date:** 2026-06-08  
**Wave:** P2-W2  
**git_sha:** `0585f9e9413e416357c041b086fbabe6bcd513c3`  
**Status:** RESULT-LOGGED (Gate #1 only; OOS sealed)

## Data precondition

- **data_root:** `C:\Users\chris\Documents\Trading\quant-research-lab\data\raw`
- **pattern:** `mnq/MNQ *.Last.txt`
- **contract_files:** 26
- **RTH bars:** 599,533
- **session_dates:** 1,561
- **range (CT):** 2020-01-02T08:30:00-06:00 → 2026-04-17T14:59:00-05:00
- **sessions:** 2020-01-02 → 2026-04-17
- **verification:** PASS

## Protocol

- Window: **2020-01-01** – **2026-04-19**
- Partition: **60/40** by trade count (chronological); **this run = IS only**
- Costs: **$1.98** RT + slip **1 tick** stop/time, **0.5 tick** target
- Gate #1: net-of-cost per-trade expectancy **> 0** on IS

## Per-hypothesis results

### H-1 — **DEAD** (net $-17.69/trade)

- **Total trades:** 12 | **IS:** 7 | **OOS sealed:** 5
- **IS/OOS boundary (last IS exit):** 2024-03-01T09:46:00-06:00
- **Harness V1–V6:** PASS

| Metric | Value |
|--------|-------|
| Gross expectancy/trade | $-15.71 |
| Cost/trade | $1.98 |
| **Net expectancy/trade** | **$-17.69** |
| Win rate (net) | 0.0% |
| Avg win (net) | $0.00 |
| Avg loss (net) | $-17.69 |
| Max single-trade loss (net) | $20.48 |
| P95 single-trade loss (net) | $20.48 |

### H-2 — **DEAD** (net $-5.34/trade)

- **Total trades:** 1,210 | **IS:** 726 | **OOS sealed:** 484
- **IS/OOS boundary (last IS exit):** 2023-06-15T10:36:00-05:00
- **Harness V1–V6:** PASS

| Metric | Value |
|--------|-------|
| Gross expectancy/trade | $-3.36 |
| Cost/trade | $1.98 |
| **Net expectancy/trade** | **$-5.34** |
| Win rate (net) | 23.1% |
| Avg win (net) | $38.23 |
| Avg loss (net) | $-18.46 |
| Max single-trade loss (net) | $18.48 |
| P95 single-trade loss (net) | $18.48 |

### H-3 — **DEAD** (net $-19.61/trade)

- **Total trades:** 1,230 | **IS:** 738 | **OOS sealed:** 492
- **IS/OOS boundary (last IS exit):** 2023-08-17T09:20:00-05:00
- **Harness V1–V6:** PASS

| Metric | Value |
|--------|-------|
| Gross expectancy/trade | $-17.63 |
| Cost/trade | $1.98 |
| **Net expectancy/trade** | **$-19.61** |
| Win rate (net) | 4.6% |
| Avg win (net) | $24.90 |
| Avg loss (net) | $-21.76 |
| Max single-trade loss (net) | $22.48 |
| P95 single-trade loss (net) | $22.48 |

### H-4 — **DEAD** (net $-3.34/trade)

- **Total trades:** 77 | **IS:** 46 | **OOS sealed:** 31
- **IS/OOS boundary (last IS exit):** 2023-06-26T08:47:00-05:00
- **Harness V1–V6:** PASS

| Metric | Value |
|--------|-------|
| Gross expectancy/trade | $-1.36 |
| Cost/trade | $1.98 |
| **Net expectancy/trade** | **$-3.34** |
| Win rate (net) | 21.7% |
| Avg win (net) | $65.57 |
| Avg loss (net) | $-22.48 |
| Max single-trade loss (net) | $22.48 |
| P95 single-trade loss (net) | $22.48 |

### H-6 — **DEAD** (net $-12.79/trade)

- **Total trades:** 470 | **IS:** 282 | **OOS sealed:** 188
- **IS/OOS boundary (last IS exit):** 2023-05-31T09:14:00-05:00
- **Harness V1–V6:** PASS

| Metric | Value |
|--------|-------|
| Gross expectancy/trade | $-10.81 |
| Cost/trade | $1.98 |
| **Net expectancy/trade** | **$-12.79** |
| Win rate (net) | 4.3% |
| Avg win (net) | $112.52 |
| Avg loss (net) | $-18.36 |
| Max single-trade loss (net) | $18.48 |
| P95 single-trade loss (net) | $18.48 |

## Summary

- **H-1:** DEAD — net $-17.69/trade (7 IS trades)
- **H-2:** DEAD — net $-5.34/trade (726 IS trades)
- **H-3:** DEAD — net $-19.61/trade (738 IS trades)
- **H-4:** DEAD — net $-3.34/trade (46 IS trades)
- **H-6:** DEAD — net $-12.79/trade (282 IS trades)
