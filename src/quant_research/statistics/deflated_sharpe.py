"""Probabilistic and Deflated Sharpe ratio (Bailey & López de Prado).

Implements the **Probabilistic Sharpe Ratio (PSR)** and **Deflated Sharpe Ratio (DSR)**
from *The Deflated Sharpe Ratio: Correcting for Selection Bias, Backtest Overfitting
and Non-Normality* (Bailey & López de Prado, 2014, working paper / JPM).

Equations match the authors' published appendix code for **expected maximum Sharpe**
under independent Gaussian trial estimates (``getExpMaxSR`` analog) and the standard
PSR display equation using **Pearson** kurtosis :math:`\\kappa` (normal :math:`\\kappa=3`).

**Uncertainty / implementation notes (flagged for operator LdP text cross-check):**

- PSR denominator follows the common form
  :math:`\\sqrt{1 - \\hat\\gamma_3 \\widehat{SR} + \\frac{\\hat\\kappa - 1}{4} \\widehat{SR}^2}`
  with :math:`\\hat\\gamma_3` = sample skewness and :math:`\\hat\\kappa` = **Pearson**
  kurtosis (not excess). Verify against your AFML edition / Snippet if results disagree.
- ``mean_`` and ``std_`` for ``expected_max_sharpe`` are the **assumed** center and
  scale of *estimated* Sharpe ratios across **N** independent trials (under the paper's
  Gaussian model). Under the **null that all trials are noise**, often
  ``mean_=0`` and ``std_= sqrt(variance_across_trial_sharpes)``.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import stats

_EULER_MASCHERONI = 0.5772156649015329


def expected_max_sharpe(
    n_trials: int,
    mean_: float,
    std_: float,
) -> float:
    """
    Expected maximum of **N** independent Normal(mean_, std_²) Sharpe estimates.

    Bailey–López de Prado (2014) appendix / Eq. (6) construction; ``numpy`` equivalent
    of their ``getExpMaxSR`` snippet.
    """
    if n_trials < 1:
        msg = "n_trials must be >= 1"
        raise ValueError(msg)
    if n_trials == 1:
        return float(mean_)
    if std_ < 0.0 or not np.isfinite(std_):
        msg = "std_ must be finite and non-negative"
        raise ValueError(msg)
    emc = _EULER_MASCHERONI
    max_z = (1 - emc) * stats.norm.ppf(1 - 1.0 / n_trials) + emc * stats.norm.ppf(
        1 - 1.0 / (n_trials * np.e)
    )
    return float(mean_ + std_ * max_z)


def probabilistic_sharpe_ratio(
    observed_sr: float,
    sr_benchmark: float,
    n_observations: int,
    skewness: float,
    kurtosis_pearson: float,
) -> float:
    """
    Probability :math:`P(SR > SR_{\\text{benchmark}})` under the PSR normal approximation.

    ``skewness``: sample skew (Fisher, scipy default).
    ``kurtosis_pearson``: Pearson kurtosis (normal = **3**); use
    ``scipy.stats.kurtosis(..., fisher=False)``.
    """
    if n_observations < 2:
        msg = "n_observations must be >= 2"
        raise ValueError(msg)
    if not np.isfinite(observed_sr):
        return float("nan")
    den = 1.0 - skewness * observed_sr + (kurtosis_pearson - 1.0) / 4.0 * observed_sr**2
    if den <= 0.0 or not np.isfinite(den):
        return float("nan")
    z = (observed_sr - sr_benchmark) * np.sqrt(n_observations - 1) / np.sqrt(den)
    return float(stats.norm.cdf(z))


@dataclass(frozen=True, slots=True)
class DeflatedSharpeResult:
    expected_max_sr_benchmark: float
    probabilistic_sharpe: float
    observed_sharpe: float
    n_trials: int
    n_observations: int


def deflated_sharpe_ratio(
    observed_sr: float,
    n_observations: int,
    skewness: float,
    kurtosis_pearson: float,
    n_trials: int,
    variance_across_trials: float,
    mean_sr_across_trials: float = 0.0,
) -> DeflatedSharpeResult:
    """
    **Deflated Sharpe Ratio:** PSR evaluated at benchmark = ``expected_max_sharpe(...)``.

    ``variance_across_trials``: :math:`\\mathrm{Var}[\\{\\widehat{SR}_i\\}]` across the **N**
    experiments; pass ``std = sqrt(variance)`` into ``expected_max_sharpe``.

    ``mean_sr_across_trials``: center for the trial-SR Gaussian (often **0** under
    the null that strategies have no edge).
    """
    if variance_across_trials < 0.0 or not np.isfinite(variance_across_trials):
        msg = "variance_across_trials must be finite and non-negative"
        raise ValueError(msg)
    std_trials = float(np.sqrt(variance_across_trials))
    e_max = expected_max_sharpe(n_trials, mean_sr_across_trials, std_trials)
    psr = probabilistic_sharpe_ratio(
        observed_sr,
        e_max,
        n_observations,
        skewness,
        kurtosis_pearson,
    )
    return DeflatedSharpeResult(
        expected_max_sr_benchmark=e_max,
        probabilistic_sharpe=psr,
        observed_sharpe=observed_sr,
        n_trials=n_trials,
        n_observations=n_observations,
    )


def sample_moments_from_returns(returns: np.ndarray) -> tuple[float, float]:
    """(Fisher skew, Pearson kurtosis) for 1-D ``returns``."""
    x = np.asarray(returns, dtype=np.float64).ravel()
    if x.size < 3:
        msg = "returns must have length >= 3"
        raise ValueError(msg)
    skew = float(stats.skew(x, bias=False))
    k_pearson = float(stats.kurtosis(x, fisher=False, bias=False))
    return skew, k_pearson
