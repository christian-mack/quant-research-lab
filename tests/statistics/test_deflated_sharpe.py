"""Tests for :mod:`quant_research.statistics.deflated_sharpe`."""

from __future__ import annotations

import numpy as np
import pytest
from scipy import stats

from quant_research.statistics.deflated_sharpe import (
    deflated_sharpe_ratio,
    expected_max_sharpe,
    probabilistic_sharpe_ratio,
    sample_moments_from_returns,
)


def test_expected_max_sharpe_matches_monte_carlo() -> None:
    """Bailey–LdP ``getExpMaxSR`` vs empirical mean of max of N Normal draws."""
    rng = np.random.default_rng(101)
    n_trials = 400
    mu, sigma = 0.02, 0.15
    analytical = expected_max_sharpe(n_trials, mu, sigma)
    reps = 12_000
    draws = rng.normal(mu, sigma, size=(reps, n_trials))
    mc = float(np.mean(np.max(draws, axis=1)))
    assert abs(analytical - mc) < 0.012 * max(1.0, abs(analytical))


def test_psr_at_zero_benchmark_normal_returns_near_median_under_null() -> None:
    """Centered Gaussian returns → PSR vs SR₀=0 should cluster near 0.5 (smoke)."""
    rng = np.random.default_rng(202)
    t = 5000
    r = rng.normal(0.0, 1.0, size=t)
    r = r - np.mean(r)
    m = float(np.mean(r))
    s = float(np.std(r, ddof=1))
    sr = float(np.sqrt(t) * m / s)
    sk, ku = sample_moments_from_returns(r)
    psr = probabilistic_sharpe_ratio(sr, 0.0, t, sk, ku)
    assert abs(sr) < 0.05
    assert 0.40 < psr < 0.60


def test_deflated_sharpe_decreases_with_more_trials_fixed_sr() -> None:
    """More independent trials ⇒ higher E[max SR] under null ⇒ lower DSR, ceteris paribus."""
    skew, kurt_p = 0.0, 3.0
    obs_sr = 0.12
    n_obs = 800
    var_tr = 0.01**2
    dsr_small = deflated_sharpe_ratio(
        obs_sr, n_obs, skew, kurt_p, n_trials=5, variance_across_trials=var_tr
    )
    dsr_large = deflated_sharpe_ratio(
        obs_sr, n_obs, skew, kurt_p, n_trials=120, variance_across_trials=var_tr
    )
    assert dsr_large.expected_max_sr_benchmark > dsr_small.expected_max_sr_benchmark
    assert dsr_large.probabilistic_sharpe < dsr_small.probabilistic_sharpe


def test_hand_psr_normal_known_moments_matches_norm_cdf() -> None:
    """Manual PSR with γ3=0, κ=3: z reduces to sqrt(T-1)*SR / sqrt(1 + SR²/2)."""
    sr = 0.25
    t_obs = 120
    skew = 0.0
    kurt_p = 3.0
    psr = probabilistic_sharpe_ratio(sr, 0.0, t_obs, skew, kurt_p)
    den = np.sqrt(1.0 + sr**2 / 2.0)
    z = sr * np.sqrt(t_obs - 1) / den
    assert psr == pytest.approx(float(stats.norm.cdf(z)), rel=0.0, abs=1e-12)
