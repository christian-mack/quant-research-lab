# P2-W3 / H-7 exit-integrity forensic (IS partition)

**Date:** 2026-06-08  
**Scope:** Diagnosis only — IS **751** trades; OOS sealed  
**Gate #1 anchor:** net **$20.85/tr**, WR **74.8%**  
**git_sha:** `0383f84adac8908a92a187de043711703a517443`  
**H-7 implementation ref:** `86bd753` (`simulate_p2_trade` walker)

## Summary verdict

**H-7 result CONTAMINATED — next-bar bracket recompute net $-2.41/tr (WR 35.0% vs gate 74.8%); H-7 does not route through backtest/engine.py M4 ledger — uses bespoke simulate_p2_trade walker (stop-first on minute bar, not pivot path); 429 same-bar bracket exits (57.1% of IS; bracket live on entry bar); entry_px is 5m close but bracket walks from first minute of bucket**

## Check 1 — Intrabar dual-touch resolution

- **Fill path:** `research_p2w2/costs.py::simulate_p2_trade (inline bar walker)`
- **M4 engine (`backtest/engine.py`)?** **No**
- **Dual-touch rule applied:** stop-before-target on same minute bar (lines 144-146 long, 156-158 short)
- **Config policy (unused by walker):** StopLimitIntrabarPolicy.STOP_BEFORE_TARGET (not invoked by walker)
- **IS target exits:** 497
- **Dual-touch on exit bar (booked target):** 0 (0.00% of IS)
- **Dual-touch any bar (among targets):** 0
- **Dual-touch inflation vector:** none on booked target exits (stop-first holds on exit bar); primary mechanical issue is Check 2 same-bar entry bracket.

### Hand-verify samples (booked vs first-touch)

| Session | Booked | Dual-touch bar? | Pessimistic first | Optimistic first | 1-min chrono |
|---------|--------|-----------------|-------------------|------------------|--------------|
| 2020-01-03 | target | False | target | None | target |
| 2020-02-03 | target | False | target | target | target |
| 2020-02-05 | target | False | target | target | target |
| 2020-02-07 | target | False | target | target | target |
| 2020-02-11 | target | False | target | target | target |
| 2020-02-19 | target | False | target | target | target |
| 2020-02-24 | target | False | target | target | target |
| 2020-02-27 | target | False | None | None | None |
| 2020-02-28 | target | False | target | target | target |
| 2020-03-02 | target | False | target | target | target |

### Worst-case stop-first recomputation

- **Recomputed net/tr:** $20.85 (delta **$+0.00**)
- **Recomputed WR:** 74.8% (delta **+0.0 pp**)
- **Trades flipped target→stop:** 0

## Check 2 — Entry-bar fill realism

- **Bracket arms next bar?** **No**
- **Mechanism:** Entry at reclaim 5m bar CLOSE price; walker starts at entry_idx=0 (first minute of 5m bucket = anchor_ts). Bracket is LIVE on entry bar.
- **Same-bar stop/target exits:** **429** (57.1% of IS; expect 0)
- **Entry bar spans full 10/20 bracket:** 3

### Next-bar bracket diagnostic recompute

- **IS trades re-walked:** 749
- **Net/tr:** $-2.41 (delta **$-23.26** vs gate #1)
- **WR:** 35.0%
- **Same-bar exits after fix:** 152
- **Note:** Entry on last minute of reclaim 5m bucket; if walker still exits same bar, force bracket walk from entry_idx+1.

## Check 3 — Trigger look-ahead

- **Completed 5m reclaim close required:** True
- **Within-bucket look-ahead:** YES — bracket walk begins at anchor_ts (minute 1 of bucket) while entry_px is the bucket close (minute 5). Minutes 1–4 of reclaim bar are evaluated against a bracket priced at the not-yet-realized close.
- **H-3 shared-trigger context:** H-3 IS net −$19.61 on same trigger — look-ahead that inflates WR would tend to help both directions; H-3 failure is partial evidence trigger is not grossly lookahead-biased, but H-7/H-3 entry timing issue is shared.

## Check 4 — Exit disposition (IS)

| Bucket | Count | % | Net total | Net/tr |
|--------|-------|---|-----------|--------|
| TARGET | 497 | 66.2% | $18,771 | $37.77 |
| STOP | 169 | 22.5% | $-3,799 | $-22.48 |
| TIME | 85 | 11.3% | $684 | $8.04 |

- **Time-stop mark bugs (win at target price):** 0
- **Target-capture wins / total wins:** 497 / 562 (88.4% of wins)
- **Time-stop wins / total wins:** 65 / 562 (11.6% of wins)
- **Genuine target captures as % of IS trades:** 66.2%
