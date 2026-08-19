# Wave 1 Stage 1 Track 1 — quant coarse screen vs Apex-style gates

**Artifact JSON:** `C:\Users\chris\Documents\Trading\quant-research-lab\notebooks\validation\2026-05-26_wave1_stage1_track1_quant_screen.json`
**Protocol:** MNQ qty=1 economics; exits **America/New_York** calendar attribution; evaluation years **[2021, 2022, 2023, 2024, 2025]** (Frame B excludes 2020).

## Loader / ES–RTY status
- ES glob `ES *.Last.txt`: **0** files.
- RTY glob `RTY *.Last.txt`: **0** files.
- Cross-instrument hypotheses **H8/H9/H10:** blocked where ES or RTY export missing — see JSON.

## Operator summary — survivors vs killed
- **SURVIVE (all five gates):** **NONE**

### Findings before Stage 2
- **H11 (15m opening range breakout)** cleared **Gates 2–5** on the best path but **failed Gate 1**: at the $30K/yr sizing heuristic, **worst single-session loss (~$1.3K) exceeds the $1,000** (per-session DLL-style screen). Only MNQ hypothesis with four-of-five coarse gate passes.
- **H12** passes year profile (G5) but fails **frequency**, **win rate**, **R:R**, and **session tail** vs Gate 1 sizing.
- **H1/H2** fail **Gate 1** (negative mean annual at qty=1) and **win rate**.
- **Deflated Sharpe (N=7):** wide SR spread (H1/H2 negative vs H11/H12 positive); PSR vs track null is strong for H11/H12, but **Gate 1** blocks H11 anyway here.

### H1
- **Selected sweep:** `X12`
- Gates: G1=FAIL, G2=FAIL, G3=FAIL, G4=FAIL, G5=FAIL → **KILLED**
- Bootstrap mean-annual P&L CI95: `{'ci95_low': -633.16625, 'ci95_high': -70.10875000000027, 'point_mean_annual_usd': -385.45, 'block_len_sessions': 20, 'n_iterations': 1000, 'years_span': 5.0, 'includes_zero': False}`

### H2
- **Selected sweep:** `stop12`
- Gates: G1=FAIL, G2=PASS, G3=FAIL, G4=FAIL, G5=FAIL → **KILLED**
- Bootstrap mean-annual P&L CI95: `{'ci95_low': -1633.4176661593244, 'ci95_high': -641.5161757843841, 'point_mean_annual_usd': -1141.3028797439408, 'block_len_sessions': 20, 'n_iterations': 1000, 'years_span': 5.0, 'includes_zero': False}`

### H8
- Gates: G1=FAIL, G2=FAIL, G3=FAIL, G4=FAIL, G5=FAIL → **KILLED**
- Blocked: `H8 ES–NQ divergence: no ES raw exports under `ES *.Last.txt`. Stage 1 runs without macro calendar filter (pre-registered: first-hour post FOMC/NFP/CPI window).`
- Bootstrap mean-annual P&L CI95: `{'ci95_low': nan, 'ci95_high': nan, 'point_mean_annual_usd': nan, 'note': 'insufficient sessions for block bootstrap'}`

### H9
- Gates: G1=FAIL, G2=FAIL, G3=FAIL, G4=FAIL, G5=FAIL → **KILLED**
- Blocked: `H9 RTY lead: no RTY raw exports under `RTY *.Last.txt` (count=0).`
- Bootstrap mean-annual P&L CI95: `{'ci95_low': nan, 'ci95_high': nan, 'point_mean_annual_usd': nan, 'note': 'insufficient sessions for block bootstrap'}`

### H10
- Gates: G1=FAIL, G2=FAIL, G3=FAIL, G4=FAIL, G5=FAIL → **KILLED**
- Blocked: `H10 ES levels reaction: no stitched ES tape (same glob as H8 prerequisite).`
- Bootstrap mean-annual P&L CI95: `{'ci95_low': nan, 'ci95_high': nan, 'point_mean_annual_usd': nan, 'note': 'insufficient sessions for block bootstrap'}`

### H11
- Gates: G1=FAIL, G2=PASS, G3=PASS, G4=PASS, G5=PASS → **KILLED**
- Bootstrap mean-annual P&L CI95: `{'ci95_low': 7099.09, 'ci95_high': 11133.4725, 'point_mean_annual_usd': 9127.2, 'block_len_sessions': 20, 'n_iterations': 1000, 'years_span': 5.0, 'includes_zero': False}`

### H12
- Gates: G1=FAIL, G2=FAIL, G3=FAIL, G4=FAIL, G5=PASS → **KILLED**
- Bootstrap mean-annual P&L CI95: `{'ci95_low': 3400.81375, 'ci95_high': 6174.44, 'point_mean_annual_usd': 4709.3, 'block_len_sessions': 20, 'n_iterations': 1000, 'years_span': 5.0, 'includes_zero': False}`

## Deflated Sharpe (within-track N=7)
```json
{
  "n_trials_registered": 7,
  "variance_across_trial_sharpes_substituted_zeros": 7.99844113198152,
  "adjusted_sharpes_track_vector": [
    -2.5437950009926165,
    -1.7654920679819721,
    0.0,
    0.0,
    0.0,
    4.507399293567078,
    4.627377417417
  ],
  "note": "NaN Sharpes become 0 in the track vector for Var(SRhat) only; PSR rows stay NaN for blocked runs.",
  "per_hypothesis_deflated_block": [
    {
      "hypothesis_order_index": 0,
      "observed_daily_sharpe_annualized": -2.5437950009926165,
      "expected_max_sr_under_null_trials": 3.9220083282116276,
      "probabilistic_sharpe_vs_track_null": 4.5871259059983303e-119,
      "n_observations_daily": 330,
      "skewness_daily_fisher": 2.5742931847595143,
      "kurtosis_pearson_daily": 12.1715353552351
    },
    {
      "hypothesis_order_index": 1,
      "observed_daily_sharpe_annualized": -1.7654920679819721,
      "expected_max_sr_under_null_trials": 3.9220083282116276,
      "probabilistic_sharpe_vs_track_null": 0.0,
      "n_observations_daily": 1256,
      "skewness_daily_fisher": 2.636258577398891,
      "kurtosis_pearson_daily": 11.463066969560236
    },
    {
      "hypothesis_order_index": 2,
      "probabilistic_sharpe_vs_track_null": null,
      "note": "blocked or insufficient daily samples"
    },
    {
      "hypothesis_order_index": 3,
      "probabilistic_sharpe_vs_track_null": null,
      "note": "blocked or insufficient daily samples"
    },
    {
      "hypothesis_order_index": 4,
      "probabilistic_sharpe_vs_track_null": null,
      "note": "blocked or insufficient daily samples"
    },
    {
      "hypothesis_order_index": 5,
      "observed_daily_sharpe_annualized": 4.507399293567078,
      "expected_max_sr_under_null_trials": 3.9220083282116276,
      "probabilistic_sharpe_vs_track_null": 0.9999999397399743,
      "n_observations_daily": 1145,
      "skewness_daily_fisher": 0.00481333933044354,
      "kurtosis_pearson_daily": 3.562699189663778
    },
    {
      "hypothesis_order_index": 6,
      "observed_daily_sharpe_annualized": 4.627377417417,
      "expected_max_sr_under_null_trials": 3.9220083282116276,
      "probabilistic_sharpe_vs_track_null": 0.9988809877982996,
      "n_observations_daily": 449,
      "skewness_daily_fisher": 1.3173463599193067,
      "kurtosis_pearson_daily": 6.408506424024298
    }
  ]
}
```