"""Primitive 2 — Fair Value Gap (FVG) detection + midpoint.

A fair value gap is a 3-candle imbalance. Indexing the three consecutive candles
as ``c1`` (oldest), ``c2`` (middle / displacement), ``c3`` (newest):

- **Bullish FVG** — ``c3.low > c1.high``. The middle candle displaces up so far
  that ``c3`` opens above ``c1``'s high, leaving an unfilled gap. The FVG zone is
  ``[bottom=c1.high, top=c3.low]``.
- **Bearish FVG** — ``c3.high < c1.low``. The middle candle displaces down,
  leaving ``[bottom=c3.high, top=c1.low]`` unfilled.

The "candle-2 does not fill the gap" condition is exactly the strict inequality
between ``c1`` and ``c3`` extremes (the middle candle's body/wicks are the
displacement, not a fill). The gap is **confirmed at c3's close**, so for
no-look-ahead use the FVG is known at ``c3.timestamp``.

For each FVG this module reports ``top``, ``bottom``, ``midpoint`` (the 50%
"consequent encroachment" level ``(top + bottom) / 2``), and ``gap_size``
(``top - bottom``).

This is a reusable, timeframe-agnostic component: pass bars at whatever timeframe
you want gaps on (daily, hourly, 15m, 5m). :func:`resample_ohlc` is provided to
build a coarser timeframe from minute bars when needed. Used by Spec A entry, the
FVG-midpoint validation variant, and (later) the H7/H17 ideas.
"""

from __future__ import annotations

from typing import Final

import polars as pl

DIRECTION_BULLISH: Final[str] = "bullish"
DIRECTION_BEARISH: Final[str] = "bearish"

FVG_SCHEMA: Final[dict[str, pl.DataType]] = {
    "direction": pl.String,
    "c1_index": pl.Int64,
    "c2_index": pl.Int64,
    "c3_index": pl.Int64,
    "c1_timestamp": pl.Datetime,
    "c2_timestamp": pl.Datetime,
    "c3_timestamp": pl.Datetime,
    "top": pl.Float64,
    "bottom": pl.Float64,
    "midpoint": pl.Float64,
    "gap_size": pl.Float64,
}


def fvg_midpoint(top: float, bottom: float) -> float:
    """Return the 50% level of an FVG zone (``(top + bottom) / 2``).

    Args:
        top: Upper bound of the gap.
        bottom: Lower bound of the gap.

    Returns:
        The midpoint (consequent encroachment) price.
    """
    return (top + bottom) / 2.0


def detect_fvgs(
    df: pl.DataFrame,
    *,
    timestamp: str = "timestamp",
    high: str = "high",
    low: str = "low",
    min_gap_size: float = 0.0,
) -> pl.DataFrame:
    """Detect bullish and bearish 3-candle fair value gaps.

    Bars are processed in ``timestamp`` order. A bullish FVG is recorded when
    ``c3.low - c1.high > min_gap_size``; a bearish FVG when
    ``c1.low - c3.high > min_gap_size`` (where ``c1``/``c3`` are the candles
    immediately before/after the middle candle ``c2``). ``min_gap_size`` defaults
    to ``0.0`` so any strictly positive imbalance qualifies; raise it (in price
    units) to ignore negligible gaps.

    Args:
        df: OHLC bars at the desired timeframe with ``timestamp``/``high``/``low``
            columns. Resample first (see :func:`resample_ohlc`) if you want gaps
            on a coarser timeframe than the input bars.
        timestamp: Tz-aware timestamp column name (used for ordering and output).
        high: High price column name.
        low: Low price column name.
        min_gap_size: Minimum strict gap size (``top - bottom``) to record.

    Returns:
        One row per detected FVG following :data:`FVG_SCHEMA`: ``direction``
        (``bullish``/``bearish``), the integer indices and timestamps of the
        three candles, and ``top``/``bottom``/``midpoint``/``gap_size``. Indices
        are 0-based positions into the timestamp-sorted input. Empty (schema-only)
        when fewer than 3 bars or no gaps are found.

    Raises:
        ValueError: If ``timestamp``/``high``/``low`` columns are missing.
    """
    missing = [c for c in (timestamp, high, low) if c not in df.columns]
    if missing:
        raise ValueError(f"missing required columns: {missing}")

    ts_dtype = df.schema[timestamp]
    empty = _empty_fvg_frame(ts_dtype)
    if df.height < 3:
        return empty

    work = df.sort(timestamp).with_row_index("_idx")

    # c2 is the middle candle (current row); c1 is previous, c3 is next.
    c1_high = pl.col(high).shift(1)
    c1_low = pl.col(low).shift(1)
    c3_high = pl.col(high).shift(-1)
    c3_low = pl.col(low).shift(-1)

    bull_gap = c3_low - c1_high
    bear_gap = c1_low - c3_high

    annotated = work.with_columns(
        c1_high.alias("_c1_high"),
        c1_low.alias("_c1_low"),
        c3_high.alias("_c3_high"),
        c3_low.alias("_c3_low"),
        pl.col("_idx").shift(1).alias("_c1_index"),
        pl.col("_idx").shift(-1).alias("_c3_index"),
        pl.col(timestamp).shift(1).alias("_c1_ts"),
        pl.col(timestamp).shift(-1).alias("_c3_ts"),
        bull_gap.alias("_bull_gap"),
        bear_gap.alias("_bear_gap"),
    )

    bull = (
        annotated.filter(pl.col("_bull_gap") > min_gap_size)
        .with_columns(
            pl.lit(DIRECTION_BULLISH).alias("direction"),
            pl.col("_c1_high").alias("bottom"),
            pl.col("_c3_low").alias("top"),
        )
    )
    bear = (
        annotated.filter(pl.col("_bear_gap") > min_gap_size)
        .with_columns(
            pl.lit(DIRECTION_BEARISH).alias("direction"),
            pl.col("_c3_high").alias("bottom"),
            pl.col("_c1_low").alias("top"),
        )
    )

    combined = pl.concat([bull, bear], how="vertical")
    if combined.height == 0:
        return empty

    return (
        combined.with_columns(
            pl.col("_c1_index").cast(pl.Int64).alias("c1_index"),
            pl.col("_idx").cast(pl.Int64).alias("c2_index"),
            pl.col("_c3_index").cast(pl.Int64).alias("c3_index"),
            pl.col("_c1_ts").alias("c1_timestamp"),
            pl.col(timestamp).alias("c2_timestamp"),
            pl.col("_c3_ts").alias("c3_timestamp"),
            ((pl.col("top") + pl.col("bottom")) / 2.0).alias("midpoint"),
            (pl.col("top") - pl.col("bottom")).alias("gap_size"),
        )
        .select(
            "direction",
            "c1_index",
            "c2_index",
            "c3_index",
            "c1_timestamp",
            "c2_timestamp",
            "c3_timestamp",
            "top",
            "bottom",
            "midpoint",
            "gap_size",
        )
        .sort("c2_index")
    )


def resample_ohlc(
    df: pl.DataFrame,
    *,
    every: str,
    timestamp: str = "timestamp",
    open_: str = "open",
    high: str = "high",
    low: str = "low",
    close: str = "close",
    volume: str | None = "volume",
) -> pl.DataFrame:
    """Aggregate bars up to a coarser timeframe (e.g. ``"5m"``, ``"1h"``, ``"1d"``).

    Thin convenience wrapper around polars ``group_by_dynamic`` producing standard
    OHLC(V) bars labeled at each window's left edge. Useful to run
    :func:`detect_fvgs` on a higher timeframe than the source minute bars.

    Args:
        df: Source bars with a tz-aware ``timestamp`` column.
        every: Polars duration string for the target bar size (``"5m"``, ``"15m"``,
            ``"1h"``, ``"1d"`` ...).
        timestamp: Timestamp column name.
        open_: Open column name.
        high: High column name.
        low: Low column name.
        close: Close column name.
        volume: Volume column name, or ``None`` to skip volume aggregation.

    Returns:
        Resampled OHLC(V) bars sorted by ``timestamp``.
    """
    aggs = [
        pl.col(open_).first().alias(open_),
        pl.col(high).max().alias(high),
        pl.col(low).min().alias(low),
        pl.col(close).last().alias(close),
    ]
    if volume is not None and volume in df.columns:
        aggs.append(pl.col(volume).sum().alias(volume))
    return (
        df.sort(timestamp)
        .group_by_dynamic(timestamp, every=every)
        .agg(aggs)
        .sort(timestamp)
    )


def _empty_fvg_frame(ts_dtype: pl.DataType) -> pl.DataFrame:
    """Return a zero-row FVG frame with timestamp columns matching ``ts_dtype``."""
    schema: dict[str, pl.DataType] = {}
    for name, dtype in FVG_SCHEMA.items():
        if name.endswith("timestamp"):
            schema[name] = ts_dtype
        else:
            schema[name] = dtype
    return pl.DataFrame(schema=schema)
