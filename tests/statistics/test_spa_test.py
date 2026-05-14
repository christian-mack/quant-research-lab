"""Tests for :mod:`quant_research.statistics.spa_test`."""

from __future__ import annotations

import numpy as np

from quant_research.statistics.spa_test import whites_reality_check


def test_reality_check_identical_columns_high_pvalue() -> None:
    """All strategies equal to benchmark → max excess ~0 → non-significant."""
    rng = np.random.default_rng(42)
    t, m = 400, 5
    bench = rng.normal(0.0, 0.01, size=(t, 1))
    r = np.repeat(bench, m, axis=1)
    out = whites_reality_check(r, benchmark_col=0, n_bootstrap=800, random_seed=1)
    assert out.pvalue > 0.1


def test_reality_check_one_clear_winner_low_pvalue() -> None:
    """One column dominates in mean → low p-value."""
    rng = np.random.default_rng(0)
    t, m = 500, 4
    r = rng.normal(0.0, 0.02, size=(t, m))
    r[:, 2] += 0.012
    out = whites_reality_check(r, benchmark_col=0, n_bootstrap=1500, random_seed=2)
    assert out.pvalue < 0.05
