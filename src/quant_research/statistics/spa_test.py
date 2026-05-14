"""White's (2000) Reality Check – bootstrap *p*-value for the best strategy.

Tests whether the **largest** observed mean excess return across *M* rules could
have arisen by chance when all rules have equal true performance.

**Model:** ``returns`` is ``(T, M)`` matrix of **period returns** (e.g. daily or
per-trade); column **0** is the **benchmark**. Excess for rule *j*:
``r[:, j] - r[:, 0]``. Bootstrap uses **IID row resampling** of **centered**
excess returns (simplest Reality-Check bootstrap; block bootstrap deferred).

**Reference:** White, H. (2000) "A Reality Check for Data Snooping."
*Econometrica* **68**(5), 1097–1126. See also Hansen (2005) SPA for studentized
variants — this module implements the **basic** max-mean statistic.

**Limitation (flagged):** Studentized / consistent test (Hansen SPA) is not
implemented here; *p*-values can be conservative vs SPA.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from quant_research.statistics.bootstrap import BootstrapConfig


@dataclass(frozen=True, slots=True)
class RealityCheckResult:
    statistic: float
    pvalue: float
    n_periods: int
    n_strategies: int
    mean_excess: np.ndarray
    n_bootstrap: int


def whites_reality_check(
    returns: np.ndarray,
    *,
    benchmark_col: int = 0,
    n_bootstrap: int = 2000,
    random_seed: int | None = None,
) -> RealityCheckResult:
    """
    ``returns`` shape ``(T, M)`` — each column a return series aligned in time.

    Benchmark column ``benchmark_col`` (default **0**); excess
    ``returns[:, j] - returns[:, benchmark_col]``.
    Statistic: ``sqrt(T) * max_j mean(excess_j)``.
    """
    r = np.asarray(returns, dtype=np.float64)
    if r.ndim != 2 or r.shape[0] < 3 or r.shape[1] < 2:
        msg = "returns must be 2-D with shape (T>=3, M>=2)"
        raise ValueError(msg)
    t, m = r.shape
    if not 0 <= benchmark_col < m:
        msg = "benchmark_col out of range"
        raise ValueError(msg)
    bench = r[:, benchmark_col : benchmark_col + 1]
    excess = r - bench
    sample_mean = excess.mean(axis=0)
    stat_obs = float(np.sqrt(t) * np.max(sample_mean))

    centered = excess - sample_mean
    rng = np.random.default_rng(random_seed)
    count_ge = 0
    for _ in range(n_bootstrap):
        idx = rng.integers(0, t, size=t)
        boot_mean = centered[idx].mean(axis=0)
        boot_stat = float(np.sqrt(t) * np.max(boot_mean))
        if boot_stat >= stat_obs:
            count_ge += 1
    pval = (1 + count_ge) / (1 + n_bootstrap)
    return RealityCheckResult(
        statistic=stat_obs,
        pvalue=pval,
        n_periods=t,
        n_strategies=m,
        mean_excess=sample_mean,
        n_bootstrap=n_bootstrap,
    )


def reality_check_from_config(
    returns: np.ndarray,
    bootstrap: BootstrapConfig | None = None,
    *,
    benchmark_col: int = 0,
) -> RealityCheckResult:
    """Convenience: map ``BootstrapConfig`` fields to ``whites_reality_check``."""
    cfg = bootstrap or BootstrapConfig()
    return whites_reality_check(
        returns,
        benchmark_col=benchmark_col,
        n_bootstrap=cfg.n_iterations,
        random_seed=cfg.random_seed,
    )
