"""Bootstrap confidence intervals for trade-level performance metrics.

Resamples trades **with replacement** (IID trade bootstrap). Order within each
replicate is the resampling order; cumulative metrics (e.g. max drawdown) are
computed on that path.

**Sharpe (trade series):** ``sqrt(n) * mean(pnl) / std(pnl)`` with ``n`` the
number of resampled trades — a common *per-sample-root* statistic for i.i.d.
trade P&Ls (not annualized; document horizon when interpreting).

References: **Efron & Tibshirani** (*An Introduction to the Bootstrap*, 1993).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

SENTINEL_SHARPE = -999.0


@dataclass(frozen=True, slots=True)
class BootstrapConfig:
    """Bootstrap settings."""

    n_iterations: int = 10_000
    confidence_level: float = 0.95
    #: RNG seed for reproducibility; ``None`` → non-deterministic.
    random_seed: int | None = None


@dataclass(frozen=True, slots=True)
class BootstrapCIs:
    """Percentile bootstrap confidence intervals (lower, upper) and point estimates."""

    pnl_total: tuple[float, float]
    sharpe_ratio: tuple[float, float]
    win_rate: tuple[float, float]
    max_drawdown: tuple[float, float]
    point_pnl_total: float
    point_sharpe_ratio: float
    point_win_rate: float
    point_max_drawdown: float
    n_trades: int
    n_iterations: int
    confidence_level: float


def _max_drawdown_from_pnl_path(pnl: np.ndarray) -> float:
    """Max drawdown on cumulative P&amp;L path (negative = drawdown depth).

    Path starts at **zero** cumulative P&amp;L before the first trade.
    """
    if pnl.size == 0:
        return 0.0
    equity = np.concatenate([[0.0], np.cumsum(pnl.astype(np.float64))])
    peaks = np.maximum.accumulate(equity)
    dd = equity - peaks
    return float(np.min(dd))


def _trade_sharpe(pnl: np.ndarray) -> float:
    """``sqrt(n) * mean/std`` for non-empty ``pnl``; else sentinel."""
    if pnl.size < 2:
        return float(SENTINEL_SHARPE)
    m = float(np.mean(pnl))
    s = float(np.std(pnl, ddof=1))
    if s <= 0.0 or not np.isfinite(s):
        return float(SENTINEL_SHARPE)
    return float(np.sqrt(pnl.size) * m / s)


def bootstrap_trade_metrics(
    net_pnls: np.ndarray,
    config: BootstrapConfig | None = None,
) -> BootstrapCIs:
    """
    Compute bootstrap percentile CIs for total P&amp;L, trade-series Sharpe,
    win rate, and max drawdown.

    Parameters
    ----------
    net_pnls
        1-D array of **net** P&amp;L per trade (same sign convention as ``TradeLedger``).
    """
    cfg = config or BootstrapConfig()
    if cfg.n_iterations < 2:
        msg = "n_iterations must be at least 2"
        raise ValueError(msg)
    if not 0.0 < cfg.confidence_level < 1.0:
        msg = "confidence_level must be in (0, 1)"
        raise ValueError(msg)

    pnl = np.asarray(net_pnls, dtype=np.float64).ravel()
    n = int(pnl.size)
    if n == 0:
        msg = "net_pnls must be non-empty"
        raise ValueError(msg)

    rng = np.random.default_rng(cfg.random_seed)
    alpha = (1.0 - cfg.confidence_level) / 2.0
    lo_q, hi_q = alpha, 1.0 - alpha

    p_total = float(np.sum(pnl))
    p_sharpe = _trade_sharpe(pnl)
    p_wr = float(np.mean(pnl > 0.0))
    p_dd = _max_drawdown_from_pnl_path(pnl)

    sums = np.empty(cfg.n_iterations, dtype=np.float64)
    sharpes = np.empty(cfg.n_iterations, dtype=np.float64)
    wrs = np.empty(cfg.n_iterations, dtype=np.float64)
    dds = np.empty(cfg.n_iterations, dtype=np.float64)

    for i in range(cfg.n_iterations):
        idx = rng.integers(0, n, size=n)
        sample = pnl[idx]
        sums[i] = float(np.sum(sample))
        sharpes[i] = _trade_sharpe(sample)
        wrs[i] = float(np.mean(sample > 0.0))
        dds[i] = _max_drawdown_from_pnl_path(sample)

    def _ci(arr: np.ndarray) -> tuple[float, float]:
        return (
            float(np.quantile(arr, lo_q)),
            float(np.quantile(arr, hi_q)),
        )

    # Sharpe replicates with undefined variance: filter sentinel for quantiles
    sh_ok = sharpes[sharpes > SENTINEL_SHARPE / 2]
    sharpe_ci = _ci(sh_ok) if sh_ok.size > 0 else (float("nan"), float("nan"))

    return BootstrapCIs(
        pnl_total=_ci(sums),
        sharpe_ratio=sharpe_ci,
        win_rate=_ci(wrs),
        max_drawdown=_ci(dds),
        point_pnl_total=p_total,
        point_sharpe_ratio=p_sharpe,
        point_win_rate=p_wr,
        point_max_drawdown=p_dd,
        n_trades=n,
        n_iterations=cfg.n_iterations,
        confidence_level=cfg.confidence_level,
    )
