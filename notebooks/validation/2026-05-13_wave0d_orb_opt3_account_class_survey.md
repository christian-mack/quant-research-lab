# Wave 0d — DLL session-pause + Apex EOD account-class survey (ORB+Opt3)

**Status: OBSOLETE as of Wave 0e (2026-05-17).** Operator-verified May 2026 Apex EOD parameters differ (PA contract limits, TDD, **PA balance tiers** with tiered DLL and **max** contracts per band). Wave 0d assumed static DLL/qty caps and did not model tier progression. Use `notebooks/validation/2026-05-17_wave0e_orb_opt3_survey.{md,json}` and `research-log.md` Wave **0e** for current research conclusions.

**Git SHA:** `17dde52f3421bc7dcf4cde8e6cfbe7d062b69c7f`  
**Dirty tree:** True  
**Generated:** 2026-05-17T07:47:36.281937+00:00  

## Parameter verification

See JSON `verification` for operator row vs third-party deltas (confirm on [Apex Help Center](https://apextraderfunding.com/help-center/)).

## Summary table (by account class)

| Class | funded_q_max | eval@q_max | boot@q_max | $/yr@q_max | DLL pauses/yr@q_max | tier |
|-------|-------------|------------|------------|------------|---------------------|------|
| 25k | 4 | 32.77% | 0.1819 | $4056.64 | 24.7627 | below_floor |
| 50k | 7 | 24.22% | 0.1672 | $7099.12 | 20.1594 | below_floor |
| 100k | 9 | 14.82% | 0.1700 | $9127.44 | 0.9524 | below_floor |
| 150k | 11 | 8.22% | 0.1540 | $11155.76 | 0.9524 | below_floor |

## Joint criteria (funded + bootstrap ≥ 80% + eval ≥ 50%)

**None** — see JSON `joint_criteria_scan.closest_candidates_top15_by_pnl` for nearest misses and gate failures.

## STOP / flags (see JSON `stop_conditions`)

- **Wave 0c material DLL regression (survival or >20% eval rate change q=1):** False
- **No triple-gate pass:** True
- **No funded-passing qty reaches bootstrap ≥ 80% (any class):** True

## Wave 0c terminal-vs-pause ( $50K, q=1 )

- Funded survived — terminal: **True**, pause: **True**
- Eval passes (30-sess windows) — terminal: **30**, pause: **30** / 1532
- |Δ eval rate| / terminal rate: **0.0**

Full JSON: `2026-05-13_wave0d_orb_opt3_account_class_survey.json`
