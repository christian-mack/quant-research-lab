# Wave 0e — Tiered PA rules + bootstrap diagnosis + survey

> **Wave 0d is obsolete** for PA contract limits, TDD values, and tier-DLL behavior.

**Git:** `75c84e5ae8ce1edc1d19e4c0788144dc5f6dff7d` dirty=True  
**UTC:** 2026-05-17T08:56:45.705867+00:00  

## Bootstrap diagnosis ($50K flat q=1 MNQ, block-20 vs block-1)

- Unconditional survival (block 20): **0.5791**
- Unconditional survival (block 1): **0.5878**
- Gap (20 − 1): **-0.0087**
- Conditional survival (|2023 count − expected| ≤10%): **0.5817711700064642**
- **Bias flag:** False (no_strong_artifact_flag)
- **Diagnosis class:** Low unconditional survival may reflect path fragility; year-bias not dominant by coarse flags.

See JSON `deliverable_2_bootstrap_diagnosis` for full counts and `proposed_bootstrap_revision`.

## Joint gates (funded + bootstrap≥80% + eval≥50%)

**None** — inspect `deliverable_3_survey` and `closest_by_pnl_sample`.

## STOP flags

- **Any funded survival:** False
- **Joint triple gate:** False
- **Bootstrap bias flag:** False

JSON: `2026-05-17_wave0e_orb_opt3_survey.json`
