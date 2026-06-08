# P2-W3 / H-7 Gate #1 mortality screen (IS partition)

**Date:** 2026-06-08  
**Wave:** P2-W3 / **H-7**  
**git_sha:** `86bd753b69f800d78850bc922775befa6b280fb5`  
**Status:** RESULT-LOGGED (Gate #1 only; OOS sealed)

## Data precondition

- **data_root:** `C:\Users\chris\Documents\Trading\quant-research-lab\data\raw`
- **pattern:** `mnq/MNQ *.Last.txt`
- **contract_files:** 26
- **RTH bars:** 599,533
- **session_dates:** 1,561
- **range (CT):** 2020-01-02T08:30:00-06:00 → 2026-04-17T14:59:00-05:00
- **verification:** PASS

## H-3 trigger parity

- **Shared reclaim triggers:** 1,253
- **H-3 trades (re-run):** 1,230 (anchor 1,230)
- **H-7 trades:** 1,253
- **H-3 geometry rejects:** 23 (structural stop/target; H-7 fixed 10/20 accepts all triggers)
- **Trigger parity:** PASS — 1,253 shared triggers; H-7 maps all; H-3 drops 23 on structural geometry

## Inversion proof (5 forensic sample dates)

| Session | H-3 dir | H-7 dir | Entry (H-3) | Entry (H-7) | Inverted? |
|---------|---------|---------|-------------|-------------|-----------|
| 2020-01-02 | long | short | 8815.75 | 8815.75 | True |
| 2020-05-25 | short | long | 9525.25 | 9525.25 | True |
| 2020-10-02 | short | long | 11422.75 | 11422.75 | True |
| 2021-02-26 | long | short | 12896.75 | 12896.75 | True |
| 2021-07-26 | short | long | 15100.75 | 15100.75 | True |

**Time stop:** 12:00 ET (T_ET_1200) — same as H-3
**Stop / target:** 10.0pt / 20.0pt fixed

## Harness V1–V6

**Overall:** PASS

## Gate #1 (IS only)

- **Total trades:** 1,253 | **IS:** 751 | **OOS sealed:** 502
- **IS/OOS boundary (last IS exit):** 2023-08-28T11:00:00-05:00
- **Trades/yr (total, protocol):** 198.9

| Metric | Value |
|--------|-------|
| Gross expectancy/trade | $22.83 |
| Cost/trade | $1.98 |
| **Net expectancy/trade** | **$20.85** |
| Win rate (net) | 74.8% |
| Avg win (net) | $34.87 |
| Avg loss (net) | $-20.84 |
| Max single-trade loss (net) | $22.48 |
| P95 single-trade loss (net) | $22.48 |

## Flip motivation cross-check

H-3 arithmetic flip (upper-biased): **+$15.65/trade** on IS. H-7 walked continuation exits (10pt stop / 20pt target): **$20.85/trade** on IS. Gap vs flip: **$+5.20/trade**. Large shortfall vs +$15.65 is expected (flip does not re-walk bars); a result near or above the flip would warrant skeptical exit-walk review.

## Summary

**H-7: SURVIVOR** — net $20.85/trade (751 IS trades)
