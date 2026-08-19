# Wave 1 Stage 1 Track 1b — H8b MES–MNQ divergence coarse screen

**Artifact JSON:** `C:\Users\chris\Documents\Trading\quant-research-lab\notebooks\validation\2026-05-29_wave1_stage1_track1b_h8b_screen.json`
**Protocol:** MNQ execution; MES cross-feature; H8b trades **with** divergence leader.
**Evaluation years:** [2021, 2022, 2023, 2024, 2025] (Frame B excludes 2020).

## Data coverage
- **MES** files: **26** (`mes/MES *.Last.txt`)
- **MES RTH bars:** 629,048; **2020-01-02 08:30:00-06:00** → **2026-05-26 14:59:00-05:00**
- **MNQ RTH bars:** 599,533; overlapping sessions: **1551**
- **MES-only unexpected missing (2021–2025 eval):** ['2023-04-06', '2023-04-10', '2023-04-11', '2023-04-12', '2023-04-13', '2023-04-14', '2023-11-13', '2025-02-10', '2025-07-14', '2025-08-18']
- **Known MNQ export gaps:** MES **has bars** for Jun–Jul 2024 and Feb–Mar 2026 holes where MNQ export is empty; H8b still cannot trade those MNQ days.

## Operator summary
- **Outcome:** **KILLED** (selected `stop10`)
- **Gates:** G1=FAIL, G2=PASS, G3=FAIL, G4=FAIL, G5=FAIL
- **Failed gate gaps:**
  - **G1:** avg annual qty=1 -1743.7 <= 0
  - **G3:** win rate 0.091 < 0.60
  - **G4:** R:R 6.831433823529411 outside [0.8, 1.5]
  - **G5:** profitable years 1 < 4 (need >=4 of [2021, 2022, 2023, 2024, 2025])
- **Daily Sharpe (ann.):** -2.3818598401264732
- **Bootstrap mean annual CI95:** `{'ci95_low': -2530.2774999999997, 'ci95_high': -843.4975000000011, 'point_mean_annual_usd': -1743.7, 'block_len_sessions': 20, 'n_iterations': 1000, 'years_span': 5.0, 'includes_zero': False}`

## Joint deflated Sharpe (N=5: H1, H2, H8b, H11, H12)
```json
{
  "n_trials_registered": 5,
  "variance_across_trial_sharpes_substituted_zeros": 13.94902909508231,
  "adjusted_sharpes_track_vector": [
    -2.5437950009926165,
    -1.7654920679819721,
    -2.3818598401264732,
    4.507399293567078,
    4.627377417417
  ],
  "hypothesis_ids_ordered": [
    "H1",
    "H2",
    "H8b",
    "H11",
    "H12"
  ],
  "note": "NaN Sharpes become 0 in the track vector for Var(SRhat) only; PSR rows stay NaN for blocked/insufficient trials.",
  "per_hypothesis_deflated_block": [
    {
      "hypothesis_id": "H1",
      "observed_daily_sharpe_annualized": -2.5437950009926165,
      "expected_max_sr_under_null_trials": 4.454147662117097,
      "probabilistic_sharpe_vs_track_null": 4.462277100876418e-139,
      "n_observations_daily": 330,
      "skewness_daily_fisher": 2.5742931847595143,
      "kurtosis_pearson_daily": 12.1715353552351
    },
    {
      "hypothesis_id": "H2",
      "observed_daily_sharpe_annualized": -1.7654920679819721,
      "expected_max_sr_under_null_trials": 4.454147662117097,
      "probabilistic_sharpe_vs_track_null": 0.0,
      "n_observations_daily": 1256,
      "skewness_daily_fisher": 2.636258577398891,
      "kurtosis_pearson_daily": 11.463066969560236
    },
    {
      "hypothesis_id": "H8b",
      "observed_daily_sharpe_annualized": -2.3818598401264732,
      "expected_max_sr_under_null_trials": 4.454147662117097,
      "probabilistic_sharpe_vs_track_null": 2.0678881958936437e-245,
      "n_observations_daily": 801,
      "skewness_daily_fisher": 3.3835260177537165,
      "kurtosis_pearson_daily": 18.19031574477147
    },
    {
      "hypothesis_id": "H11",
      "observed_daily_sharpe_annualized": 4.507399293567078,
      "expected_max_sr_under_null_trials": 4.454147662117097,
      "probabilistic_sharpe_vs_track_null": 0.6849069333938113,
      "n_observations_daily": 1145,
      "skewness_daily_fisher": 0.00481333933044354,
      "kurtosis_pearson_daily": 3.562699189663778
    },
    {
      "hypothesis_id": "H12",
      "observed_daily_sharpe_annualized": 4.627377417417,
      "expected_max_sr_under_null_trials": 4.454147662117097,
      "probabilistic_sharpe_vs_track_null": 0.7735780535440513,
      "n_observations_daily": 449,
      "skewness_daily_fisher": 1.3173463599193067,
      "kurtosis_pearson_daily": 6.408506424024298
    }
  ]
}
```

## H11 PSR: N=5 vs Track 1 N=7
- **H11 PSR @ N=7 (Track 1):** 0.9999999397399743
- **H11 PSR @ N=5 (joint rerun):** 0.6849069333938113