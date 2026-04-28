"""Williams %R, validated against pandas-ta (non-TA-Lib path).

Formula (pandas-ta ``momentum.willr``, ``talib=False``):

.. math::

    \\%R_t = 100 \\cdot \\Big(
      \\frac{C_t - L^{\\min}_n}{H^{\\max}_n - L^{\\min}_n} - 1
    \\Big)

where :math:`H^{\\max}_n` and :math:`L^{\\min}_n` are the rolling maximum
high and minimum low over ``length`` bars with ``min_periods=length``
(pandas convention). This is algebraically equivalent to the more
common :math:`-100 \\cdot (H^{\\max}-C)/(H^{\\max}-L^{\\min})`.

Values lie in (approximately) :math:`[-100, 0]` when
:math:`C \\in [L^{\\min}, H^{\\max}]`; when the range is zero, pandas
produces ``NaN`` from division by zero — polars matches with ``Inf`` or
``NaN`` depending on backend; cross-checked against pandas-ta on
synthetic data where range stays positive.

Follows the two-tier API template in :mod:`quant_research.indicators.atr`.
"""

from __future__ import annotations

from typing import Final

import polars as pl

WILLR_DEFAULT_LENGTH: Final[int] = 14
"""Default lookback. Matches pandas-ta and TradingView defaults."""


def williams_r_expr(
    *,
    length: int = WILLR_DEFAULT_LENGTH,
    high: str = "high",
    low: str = "low",
    close: str = "close",
) -> pl.Expr:
    """Return Williams %R as a polars expression.

    Args:
        length: Rolling window size. Must be >= 1.
        high: High column name.
        low: Low column name.
        close: Close column name.

    Raises:
        ValueError: If ``length < 1``.
    """
    if length < 1:
        raise ValueError(f"`length` must be >= 1; got {length}")
    lowest = pl.col(low).rolling_min(window_size=length)
    highest = pl.col(high).rolling_max(window_size=length)
    den = highest - lowest
    return 100 * ((pl.col(close) - lowest) / den - 1)


def add_williams_r(
    df: pl.DataFrame,
    *,
    length: int = WILLR_DEFAULT_LENGTH,
    high: str = "high",
    low: str = "low",
    close: str = "close",
    output: str | None = None,
) -> pl.DataFrame:
    """Append a Williams %R column to ``df``."""
    _require_hlc(df, high=high, low=low, close=close)
    if output is None:
        output = f"willr_{length}"
    return df.with_columns(
        williams_r_expr(length=length, high=high, low=low, close=close).alias(output)
    )


def _require_hlc(df: pl.DataFrame, *, high: str, low: str, close: str) -> None:
    missing = [c for c in (high, low, close) if c not in df.columns]
    if missing:
        raise ValueError(f"missing required columns: {missing}")
