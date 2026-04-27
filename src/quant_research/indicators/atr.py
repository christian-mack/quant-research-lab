"""Average True Range (ATR) and True Range, validated against pandas-ta.

This module implements the canonical Wilder ATR plus its SMA and EMA
variants. The numerical convention exactly matches ``pandas_ta.atr``
(within machine epsilon, ~1e-15 relative error on a 1000-bar synthetic
series), so research output is directly comparable to the reference
implementation that the rest of the systematic-trading literature uses.

Formulas
--------
**True Range** (Wilder, 1978):

.. math::

    \\mathrm{TR}_t = \\max\\!\\big(
      H_t - L_t,\\;
      |H_t - C_{t-1}|,\\;
      |L_t - C_{t-1}|
    \\big)

with :math:`\\mathrm{TR}_0 = H_0 - L_0` (no prior close, so the gap
terms vanish).

**ATR** is then a moving average of TR, with three modes:

- ``rma`` — *Wilder's recursive smoothing* (the textbook ATR and the
  pandas-ta default). Equivalent to an EWM with :math:`\\alpha = 1/n`,
  ``adjust=False``.
- ``sma`` — *Simple moving average* of TR over an :math:`n`-bar window.
- ``ema`` — *Exponential moving average* of TR with span :math:`n`,
  ``adjust=False``.

Pandas-ta seeding convention (replicated here)
----------------------------------------------
Before the smoothing is applied, pandas-ta replaces the TR series with:

- :math:`\\mathrm{TR}_t = \\mathrm{NaN}` for :math:`t < n - 1`
- :math:`\\mathrm{TR}_{n-1} = \\frac{1}{n}\\sum_{k=0}^{n-1}\\mathrm{TR}_k`
  (the simple mean of the first :math:`n` TR values)
- :math:`\\mathrm{TR}_t = \\mathrm{TR}_t` (unchanged) for :math:`t \\geq n`

This "presma" seed gives the smoothed series a deterministic warm-up
that converges quickly. Without it, recursive-smoothing implementations
disagree about how to initialize the recursion and produce different
values for the first few bars. Following pandas-ta means our ATR
matches the most widely-used Python TA reference, which is the only
sane definition for cross-validation.

The first :math:`n - 1` bars of the output ATR are therefore null; the
:math:`n`-th bar (index :math:`n - 1`) and onwards are valid.

Indicator-API conventions established here
------------------------------------------
This is the first indicator module; the patterns below are the template
for the rest of M3.

1. **Two-tier API.** Every indicator exposes a low-level polars
   :class:`~polars.Expr` factory (:func:`true_range_expr`, :func:`atr_expr`)
   and a high-level DataFrame-in/DataFrame-out wrapper
   (:func:`add_true_range`, :func:`add_atr`). Expression factories
   compose into lazy pipelines; the wrappers are the convenient
   one-liner for notebooks and tests.

2. **Output-column naming.** Default name is ``{indicator}_{length}``
   for RMA-default indicators (``atr_14``, ``rsi_14``, ``ema_20``).
   When ``mamode`` is non-default, include it: ``atr_sma_14``. The
   ``output``/``name`` keyword argument always overrides the default.

3. **Required-column convention.** Indicators that consume OHLC take
   ``high``, ``low``, ``close`` keyword arguments defaulting to those
   strings. This lets callers operate on renamed/shifted columns
   without copying the DataFrame.

4. **Validation.** Each indicator has at least three test layers:

   - *Numerical primitive*: a hand-computed small example (5-10 bars)
     pinning the formula.
   - *Cross-check vs pandas-ta* on a 1000-bar synthetic series with
     ``relative_error < 1e-6`` outside the warm-up.
   - *Real-data smoke* on the continuous MNQ contract: schema/no
     unexpected nulls/positivity/bounded-range invariants.

5. **Polars-native and vectorized.** No Python loops, no ``map_elements``,
   no per-row callbacks. Every primitive is a polars expression that
   the optimizer can fuse with the surrounding pipeline.
"""

from __future__ import annotations

from typing import Final, Literal

import polars as pl

ATR_DEFAULT_LENGTH: Final[int] = 14
"""Default ATR period. Matches pandas-ta and Wilder's original 1978 paper."""

MaMode = Literal["rma", "sma", "ema"]
"""Smoothing mode for ATR. ``rma`` is Wilder smoothing (the default),
``sma`` is a simple moving average, ``ema`` is span-based EMA with
``adjust=False``. All three pre-seed TR with :math:`\\mathrm{SMA}` at
index :math:`n - 1`, matching pandas-ta.
"""

_VALID_MAMODES: Final[tuple[str, ...]] = ("rma", "sma", "ema")


def true_range_expr(
    *,
    high: str = "high",
    low: str = "low",
    close: str = "close",
) -> pl.Expr:
    """Return a polars expression computing per-bar True Range.

    True Range is the largest of:

    - Today's range (``high - low``)
    - Today's high vs yesterday's close (``|high - prev_close|``)
    - Today's low vs yesterday's close (``|low - prev_close|``)

    For the first bar, ``prev_close`` is null so both gap terms collapse
    to null and the maximum is just ``high - low``.

    Args:
        high: Name of the high column. Defaults to ``"high"``.
        low: Name of the low column. Defaults to ``"low"``.
        close: Name of the close column. Defaults to ``"close"``.

    Returns:
        A polars expression. Apply with
        ``df.with_columns(true_range_expr().alias("tr"))``.
    """
    prev_close = pl.col(close).shift(1)
    return pl.max_horizontal(
        pl.col(high) - pl.col(low),
        (pl.col(high) - prev_close).abs(),
        (pl.col(low) - prev_close).abs(),
    )


def atr_expr(
    *,
    length: int = ATR_DEFAULT_LENGTH,
    mamode: MaMode = "rma",
    high: str = "high",
    low: str = "low",
    close: str = "close",
) -> pl.Expr:
    """Return a polars expression computing Average True Range.

    Implements pandas-ta's ATR exactly: TR is computed, then the first
    :math:`n - 1` values are set to null and the value at index
    :math:`n - 1` is replaced with the SMA of the first :math:`n` raw
    TR values, and finally the requested smoothing is applied to the
    seeded series.

    The resulting expression produces null for the first
    ``length - 1`` bars and the smoothed ATR from bar ``length - 1``
    onwards.

    Args:
        length: Period of the smoothing. Defaults to
            :data:`ATR_DEFAULT_LENGTH` (14).
        mamode: Smoothing mode. Defaults to ``"rma"`` (Wilder).
        high: Name of the high column. Defaults to ``"high"``.
        low: Name of the low column. Defaults to ``"low"``.
        close: Name of the close column. Defaults to ``"close"``.

    Returns:
        A polars expression. Apply with
        ``df.with_columns(atr_expr(length=14).alias("atr_14"))``.

    Raises:
        ValueError: If ``length < 1`` or ``mamode`` is not one of
            ``"rma"``, ``"sma"``, ``"ema"``.
    """
    if length < 1:
        raise ValueError(f"`length` must be >= 1; got {length}")
    if mamode not in _VALID_MAMODES:
        raise ValueError(f"`mamode` must be one of {_VALID_MAMODES}; got {mamode!r}")

    tr = true_range_expr(high=high, low=low, close=close)
    seeded = _seed_with_sma(tr, length=length)

    if mamode == "rma":
        return seeded.ewm_mean(alpha=1.0 / length, adjust=False, ignore_nulls=False, min_samples=1)
    if mamode == "sma":
        return seeded.rolling_mean(window_size=length)
    return seeded.ewm_mean(span=length, adjust=False, ignore_nulls=False, min_samples=1)


def add_true_range(
    df: pl.DataFrame,
    *,
    high: str = "high",
    low: str = "low",
    close: str = "close",
    output: str = "true_range",
) -> pl.DataFrame:
    """Return ``df`` with a True Range column appended.

    Convenience wrapper around :func:`true_range_expr`.

    Args:
        df: Input bars with ``high``, ``low``, ``close`` columns.
        high: Name of the high column. Defaults to ``"high"``.
        low: Name of the low column. Defaults to ``"low"``.
        close: Name of the close column. Defaults to ``"close"``.
        output: Name for the appended TR column. Defaults to
            ``"true_range"``.

    Returns:
        ``df`` with ``output`` column added (``Float64``).

    Raises:
        ValueError: If any of ``high``, ``low``, ``close`` is missing
            from ``df``.
    """
    _require_ohlc(df, high=high, low=low, close=close)
    return df.with_columns(true_range_expr(high=high, low=low, close=close).alias(output))


def add_atr(
    df: pl.DataFrame,
    *,
    length: int = ATR_DEFAULT_LENGTH,
    mamode: MaMode = "rma",
    high: str = "high",
    low: str = "low",
    close: str = "close",
    output: str | None = None,
) -> pl.DataFrame:
    """Return ``df`` with an ATR column appended.

    Convenience wrapper around :func:`atr_expr`.

    Args:
        df: Input bars with ``high``, ``low``, ``close`` columns.
        length: Period of the smoothing. Defaults to
            :data:`ATR_DEFAULT_LENGTH` (14).
        mamode: Smoothing mode. Defaults to ``"rma"`` (Wilder).
        high: Name of the high column. Defaults to ``"high"``.
        low: Name of the low column. Defaults to ``"low"``.
        close: Name of the close column. Defaults to ``"close"``.
        output: Name for the appended ATR column. Defaults to
            ``"atr_{length}"`` for ``mamode="rma"`` (the canonical
            convention) and ``"atr_{mamode}_{length}"`` otherwise.

    Returns:
        ``df`` with ATR column added (``Float64``).

    Raises:
        ValueError: If any of ``high``, ``low``, ``close`` is missing
            from ``df``, ``length < 1``, or ``mamode`` is invalid.
    """
    _require_ohlc(df, high=high, low=low, close=close)
    if output is None:
        output = f"atr_{length}" if mamode == "rma" else f"atr_{mamode}_{length}"
    return df.with_columns(
        atr_expr(length=length, mamode=mamode, high=high, low=low, close=close).alias(output)
    )


def _seed_with_sma(expr: pl.Expr, *, length: int) -> pl.Expr:
    """Pandas-ta-compatible ``presma`` seed.

    Returns an expression equivalent to:

    - null for index ``< length - 1``
    - SMA over the first ``length`` values at index ``length - 1``
    - the original expression value for index ``>= length``

    This matches the seeding pandas-ta applies inside ``atr()`` before
    handing the TR series off to the chosen smoothing function.
    """
    idx = pl.int_range(pl.len())
    return (
        pl.when(idx < length - 1)
        .then(None)
        .when(idx == length - 1)
        .then(expr.rolling_mean(window_size=length))
        .otherwise(expr)
    )


def _require_ohlc(df: pl.DataFrame, *, high: str, low: str, close: str) -> None:
    """Raise ``ValueError`` if any of the OHLC columns is missing."""
    missing = [c for c in (high, low, close) if c not in df.columns]
    if missing:
        raise ValueError(f"missing required columns: {missing}")
