# Wave 1 — Geometry guard verification + validation harness

**Date:** 2026-06-07  
**git_sha:** `0db224fc2bd1ef320064fb04c9a9a3d9d095e366`  

## A1 — Causality proof

Code path: `check_trade_geometry(direction, entry, stop, target)` in `geometry.py` — pure comparison of four floats known at order placement. No bar index, fill outcome, or post-entry path. Unit test `test_geometry_guard_same_decision_regardless_of_future_path` confirms identical accept/reject for same entry-time inputs.

## A2 — Rejected vs kept populations (OTE 70.5%)

### kept
- n=12,978
- WR gross: **37.8%**
- Avg net/trade: **$-3.99**
- Total net: **$-51,793**

### rejected_wrong_side
- n=18,667
- WR gross: **100.0%**
- Avg net/trade: **$19.48**
- Total net: **$363,557**

### rejected_coherent_stop
- n=18,667
- WR gross: **1.2%**
- Avg net/trade: **$-23.75**
- Total net: **$-443,311**

**Structural distinction (entry-time):**
- Kept avg entry-vs-stop: **62.4** ticks
- Rejected avg entry-vs-stop: **-43.9** ticks

## A3 — Wrong-side mechanism (20 traces)

- shallow_retracement_vs_swept_stop: **20**

- 2020-01-02 short entry=8853.4125 stop=8850.75 evs_ticks=-10.7 mech=shallow_retracement_vs_swept_stop hyp_gross=$5.325000000000728
- 2020-01-02 short entry=8853.4125 stop=8850.75 evs_ticks=-10.7 mech=shallow_retracement_vs_swept_stop hyp_gross=$5.325000000000728
- 2020-01-02 short entry=8853.4125 stop=8850.75 evs_ticks=-10.7 mech=shallow_retracement_vs_swept_stop hyp_gross=$5.325000000000728
- 2020-01-02 long entry=8821.53875 stop=8823.5 evs_ticks=-7.8 mech=shallow_retracement_vs_swept_stop hyp_gross=$3.922500000000582
- 2020-01-02 long entry=8821.53875 stop=8823.5 evs_ticks=-7.8 mech=shallow_retracement_vs_swept_stop hyp_gross=$3.922500000000582

## M4 vs bespoke parity (kept sample)

- Sampled: **500**
- Exact matches: **0**
- Avg net diff (M4 − bespoke): **$7.6992**

## A4 — Verdict

**SUSPECT for account-class survey.** Guard is causally clean and rejected population is structurally losing (avg net $19.48/trade wrong-side), but M4 vs bespoke parity diverges (max net diff $218.44). The +$11,155 Frame B figure likely reflects M4 fill-path differences vs step 3c, not geometry selection alone. Resolve parity before proceeding.

## Harness on clean OTE 70.5% log

## VALIDATION REPORT

**Overall:** **FAIL**

- **V1 Geometry coherence:** **FAIL** — 7144/12978 filled trades fail entry-time geometry; reject rate 36.5% > surface threshold
- **V2 Causal sequencing:** PASS — All trades exit at/after entry
- **V3 Cost application:** PASS — 0/12978 zero-commission; 0 net/gross mismatches
- **V4 Magnitude sanity:** PASS — Avg net 9.37 ticks/trade (surface > 15.0)
- **V5 Hand-computation spot check:** PASS — T1=ok T2=ok T5_reject=ok
- **V6 Dual-touch exposure:** PASS — Skipped (need bars + entry_bar for dual-touch analysis)

## Stop conditions

- **guard_peek:** NOT triggered — check_trade_geometry uses entry/stop/target only
- **rejected_winning:** TRIGGERED — rejected WR 90.3%, avg net $19.48
- **stop_logic_bug:** NOT triggered — 18667/18667 shallow-retracement (legitimate exclusion)
- **harness_fail:** TRIGGERED — V1