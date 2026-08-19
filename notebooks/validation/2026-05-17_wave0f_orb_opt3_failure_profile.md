# Wave 0f — Failure profile + low-qty survivability (ORB+Opt3)

**Git:** `75c84e5ae8ce1edc1d19e4c0788144dc5f6dff7d` dirty=True  
**UTC:** 2026-05-17T09:19:57.730027+00:00  

## Headline

- **$50 funded survival @ 1 MNQ:** True
- **Any low-qty funded survival:** True
- **Any triple-gate pass (low-qty sweep):** False
- **50K incompatible (qty=1 fails funded):** False

## Wave 0e failure-mode aggregates

- Primary modes: `{'trailing_breach_pre_lock': 19}`
- Catastrophic vs cumulative hints: `{'lean_single_catastrophic_session': 19}`

## Lowest qty with funded survival (by class)

- **25k:** qty **1.0** MNQ → ~**$1,014**/yr est.
- **50k:** qty **1.0** MNQ → ~**$1,014**/yr est.
- **100k:** qty **5.0** MNQ → ~**$5,071**/yr est.
- **150k:** qty **10.0** MNQ → ~**$10,142**/yr est.

## Triple gate (low-qty sweep)

**None** — see `gate_fail_counts_low_qty_sweep` in JSON.

Full JSON: `2026-05-17_wave0f_orb_opt3_failure_profile.json`
