# ORB+Opt3 account-class survey — floor-income fit

**Date:** 2026-06-08  
**Git:** `0db224fc2bd1ef320064fb04c9a9a3d9d095e366` dirty=True  
**Input mode:** fresh_backtest  

> Edge is **not** re-tested. Input: Wave 0 validated ORB+Opt3 qty=1 log (**$1,014/yr/MNQ**).

**Harness / log:** FAIL — see JSON

## Cross-class comparison

| class | max sust qty (MNQ) | binding constraint | funded $/yr net | eval pass rate | eval cost / funded acct | clears floor? | tier |
|-------|-------------------|--------------------|---------------|---------------|-------------------------|---------------|------|
| 50k | 0 (econ@1) | consistency_30pct (strict; ex-consistency q=1) | $1,014 | 2.0% | $8,528 | NO | below_floor |
| 100k | 0 (econ@2) | consistency_30pct (strict; ex-consistency q=2) | $2,028 | 2.0% | $10,571 | NO | below_floor |
| 150k | 0 (econ@3) | consistency_30pct (strict; ex-consistency q=3) | $3,042 | 2.0% | $15,167 | NO | below_floor |

## Verdict

**NO class clears floor + eval gate — loss-tail / sizing wall structural**

### Constraint detail (qty limits, MNQ)

- **50k:** R_q_closed_trade_dd=0, EOD_path_R_q_screen=0, worst_session_vs_tier1_dll=1, consistency_30pct=0, tier1_contract_cap_mnq=20, gate_a_funded_survival=7
- **100k:** R_q_closed_trade_dd=0, EOD_path_R_q_screen=0, worst_session_vs_tier1_dll=2, consistency_30pct=0, tier1_contract_cap_mnq=30, gate_a_funded_survival=11
- **150k:** R_q_closed_trade_dd=0, EOD_path_R_q_screen=0, worst_session_vs_tier1_dll=3, consistency_30pct=0, tier1_contract_cap_mnq=40, gate_a_funded_survival=15

### Gate A funded q_max (income context — not DLL-bound operational qty)

| class | Gate A q_max (MNQ) | gross $/yr at Gate A | gap to $36K floor |
|-------|-------------------|----------------------|-------------------|
| 50k | 7 | $7,099 | $28,901 short |
| 100k | 11 | $11,156 | $24,844 short |
| 150k | 15 | $15,212 | $20,788 short |

### Operator recommendation

ORB+Opt3 **does not fit any** Apex EOD class at **$36K/yr floor** with **eval pass rate ≥ 50%**. The wall is **structural**: per-MNQ edge (~$1K/yr) requires ~**36 MNQ** for floor gross, but **loss-tail / TDD / DLL / Gate A** caps sustainable qty at **≤5–15 MNQ** depending on class — far below income size. This confirms the **$50K production cut** logic extends across larger classes; the constraint is **account rules × loss tail**, not missing edge.

Full JSON: `2026-06-08_orb_account_class_survey.json`
