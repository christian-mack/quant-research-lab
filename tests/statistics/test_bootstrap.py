"""Tests for :mod:`quant_research.statistics.bootstrap`."""

from __future__ import annotations

import numpy as np
from scipy import stats

from quant_research.statistics.bootstrap import (
    BootstrapConfig,
    bootstrap_trade_metrics,
)


def test_bootstrap_pnl_mean_normal_matches_classical_ci() -> None:
    """IID normal trades: bootstrap CI for *mean* (scaled) aligns with t-interval."""
    rng = np.random.default_rng(42)
    n = 80
    true_mu = 12.5
    pnl = rng.normal(true_mu, 40.0, size=n)
    # Classical 95% CI for mean (total / n is same as mean scale)
    mean = float(np.mean(pnl))
    se = float(np.std(pnl, ddof=1) / np.sqrt(n))
    half = stats.t.ppf(0.975, df=n - 1) * se
    classical_lo, classical_hi = mean - half, mean + half

    out = bootstrap_trade_metrics(
        pnl,
        BootstrapConfig(n_iterations=8000, confidence_level=0.95, random_seed=123),
    )
    boot_mean_lo = out.pnl_total[0] / n
    boot_mean_hi = out.pnl_total[1] / n
    tol = 4.0 * se
    assert classical_lo - tol < boot_mean_lo < classical_lo + tol
    assert classical_hi - tol < boot_mean_hi < classical_hi + tol


def test_win_rate_binomial_coverage_roughly_nominal() -> None:
    """Bernoulli trades: bootstrap median win-rate CI contains true p (smoke)."""
    rng = np.random.default_rng(7)
    n = 200
    p_true = 0.55
    signs = rng.binomial(1, p_true, size=n).astype(np.float64)
    pnl = np.where(signs > 0, 100.0, -80.0)

    out = bootstrap_trade_metrics(
        pnl,
        BootstrapConfig(n_iterations=6000, confidence_level=0.95, random_seed=99),
    )
    assert out.point_win_rate == float(np.mean(pnl > 0))
    assert out.win_rate[0] < p_true < out.win_rate[1]


def test_max_drawdown_deterministic_all_losses() -> None:
    """Path MDD: constant losers produce known cumulative drawdown."""
    pnl = np.array([-1.0] * 10)
    out = bootstrap_trade_metrics(
        pnl, BootstrapConfig(n_iterations=500, confidence_level=0.95, random_seed=0)
    )
    assert out.point_max_drawdown == -10.0
    assert out.max_drawdown[0] == -10.0
    assert out.max_drawdown[1] == -10.0
