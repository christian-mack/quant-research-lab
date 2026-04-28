"""Simple and exponential moving averages, validated against pandas-ta.

**SMA** — arithmetic mean over a rolling window. Matches
``pandas_ta.sma`` when ``talib=False`` (numba convolution path); polars
``rolling_mean`` is bitwise-equivalent to pandas ``rolling(n,
min_periods=n).mean()`` for our tests.

**EMA** — ``ewm(span=length, adjust=False).mean()`` with pandas-ta's
``presma=True`` seed: the first ``length - 1`` closes are set to null,
the seed at index ``length - 1`` is the SMA of the first ``length``
closes, then the exponential recursion runs. This matches
``pandas_ta.ema`` when ``talib=False`` within machine epsilon — same
invisible initialization detail as ATR (see :mod:`quant_research.indicators.atr`).

Follows the two-tier API template in :mod:`quant_research.indicators.atr`.
"""

from __future__ import annotations

from typing import Final

import polars as pl

SMA_DEFAULT_LENGTH: Final[int] = 10
EMA_DEFAULT_LENGTH: Final[int] = 10


def sma_expr(*, length: int = SMA_DEFAULT_LENGTH, close: str = "close") -> pl.Expr:
    """Rolling simple moving average of ``close``.

    Raises:
        ValueError: If ``length < 1``.
    """
    if length < 1:
        raise ValueError(f"`length` must be >= 1; got {length}")
    return pl.col(close).rolling_mean(window_size=length)


def ema_expr(*, length: int = EMA_DEFAULT_LENGTH, close: str = "close") -> pl.Expr:
    """EMA with pandas-ta ``presma`` initialization.

    Raises:
        ValueError: If ``length < 1``.
    """
    if length < 1:
        raise ValueError(f"`length` must be >= 1; got {length}")
    c = pl.col(close)
    seeded = _seed_close_sma(c, length=length)
    return seeded.ewm_mean(span=length, adjust=False, ignore_nulls=False, min_samples=1)


def add_sma(
    df: pl.DataFrame,
    *,
    length: int = SMA_DEFAULT_LENGTH,
    close: str = "close",
    output: str | None = None,
) -> pl.DataFrame:
    """Append ``sma_{length}`` (or ``output``)."""
    _require_close(df, close=close)
    if output is None:
        output = f"sma_{length}"
    return df.with_columns(sma_expr(length=length, close=close).alias(output))


def add_ema(
    df: pl.DataFrame,
    *,
    length: int = EMA_DEFAULT_LENGTH,
    close: str = "close",
    output: str | None = None,
) -> pl.DataFrame:
    """Append ``ema_{length}`` (or ``output``)."""
    _require_close(df, close=close)
    if output is None:
        output = f"ema_{length}"
    return df.with_columns(ema_expr(length=length, close=close).alias(output))


def _seed_close_sma(expr: pl.Expr, *, length: int) -> pl.Expr:
    """Pandas-ta ``presma`` seed on a close series (same pattern as ATR TR seed)."""
    idx = pl.int_range(pl.len())
    return (
        pl.when(idx < length - 1)
        .then(None)
        .when(idx == length - 1)
        .then(expr.rolling_mean(window_size=length))
        .otherwise(expr)
    )


def _require_close(df: pl.DataFrame, *, close: str) -> None:
    if close not in df.columns:
        raise ValueError(f"missing required column: {close!r}")
