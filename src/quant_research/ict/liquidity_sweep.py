"""Primitive 5 — Liquidity sweep detection.

A *sweep* (a.k.a. liquidity raid / stop run) is price trading **through** a
reference level (a prior swing high/low, PDH/PDL) and then **closing back inside**
within ``N`` bars. The classic single-bar case is a wick above an old high that
rejects and closes back below it.

Sweep depth has **no numeric rule** in the ICT source material — it is taught
"just above/below" by example. This module therefore parameterises the sweep as:

    trades through the level by >= ``penetration_ticks`` ticks, then closes back
    inside within ``close_back_within_bars`` bars.

Both ``penetration_ticks`` and ``close_back_within_bars`` are **[MANUAL OBS]**
parameters with no source-derived value; they are carried in :class:`SweepConfig`
(not hardcoded into detection) so the bias-module / strategy layer can sweep them
and the choice is auditable. Defaults are intentionally minimal
(:data:`DEFAULT_PENETRATION_TICKS` = 1 tick) and small
(:data:`DEFAULT_CLOSE_BACK_WITHIN_BARS`).

Sides
-----
- ``"high"`` — buy-side liquidity resting **above** a high level. Penetration is
  ``high >= level + penetration``; close-back-inside is ``close < level``. A
  confirmed high sweep is a **bearish** signal (swept the highs, reverses down).
- ``"low"`` — sell-side liquidity resting **below** a low level. Penetration is
  ``low <= level - penetration``; close-back-inside is ``close > level``. A
  confirmed low sweep is a **bullish** signal.

The reference ``level`` is supplied by the caller (e.g. PDH/PDL from
:mod:`quant_research.ict.pd_arrays`, or a recent swing via
:func:`recent_swing_level`). Timeframe-agnostic.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Final

import polars as pl

SIDE_HIGH: Final[str] = "high"
SIDE_LOW: Final[str] = "low"

DIRECTION_BEARISH: Final[str] = "bearish"
DIRECTION_BULLISH: Final[str] = "bullish"

DEFAULT_PENETRATION_TICKS: Final[int] = 1
"""[MANUAL OBS] Minimum ticks price must trade beyond the level to count as a poke.

No ICT source value exists; 1 tick is the minimal non-zero choice. Carried in
:class:`SweepConfig`, sweepable by the strategy layer.
"""

DEFAULT_CLOSE_BACK_WITHIN_BARS: Final[int] = 3
"""[MANUAL OBS] Window size (bars, incl. the penetration bar) for the close-back.

No ICT source value exists; a small default keeps a sweep "prompt". Carried in
:class:`SweepConfig`, sweepable by the strategy layer.
"""


@dataclass(frozen=True)
class SweepConfig:
    """Tunable sweep parameters (the two depth/timing knobs are [MANUAL OBS]).

    Attributes:
        tick_size: Instrument tick size in price units (e.g. MNQ = 0.25). Used to
            convert ``penetration_ticks`` into a price threshold.
        penetration_ticks: [MANUAL OBS] minimum ticks beyond the level to register
            a penetration. Defaults to :data:`DEFAULT_PENETRATION_TICKS`.
        close_back_within_bars: [MANUAL OBS] number of bars (including the
            penetration bar) within which a close-back-inside must occur. Defaults
            to :data:`DEFAULT_CLOSE_BACK_WITHIN_BARS`. Must be >= 1.
    """

    tick_size: float
    penetration_ticks: int = DEFAULT_PENETRATION_TICKS
    close_back_within_bars: int = DEFAULT_CLOSE_BACK_WITHIN_BARS

    def __post_init__(self) -> None:
        if self.tick_size <= 0:
            raise ValueError(f"tick_size must be > 0; got {self.tick_size}")
        if self.penetration_ticks < 0:
            raise ValueError(f"penetration_ticks must be >= 0; got {self.penetration_ticks}")
        if self.close_back_within_bars < 1:
            raise ValueError(
                f"close_back_within_bars must be >= 1; got {self.close_back_within_bars}"
            )

    @property
    def penetration(self) -> float:
        """Penetration threshold in price units (``penetration_ticks * tick_size``)."""
        return self.penetration_ticks * self.tick_size


@dataclass(frozen=True)
class SweepResult:
    """Outcome of a sweep scan against one reference level.

    Attributes:
        swept: Whether a confirmed sweep (penetration + close-back) was found.
        side: ``"high"`` or ``"low"``.
        level: The reference level scanned.
        reversal_direction: ``"bearish"`` for a high sweep, ``"bullish"`` for a
            low sweep. ``None`` if not swept.
        penetration_index: 0-based index of the bar that traded through the level.
            ``None`` if not swept.
        penetration_extreme: The high (high side) or low (low side) that pierced.
            ``None`` if not swept.
        close_back_index: 0-based index of the bar that closed back inside.
            ``None`` if not swept.
        close_back_timestamp: Timestamp of the close-back bar. ``None`` if not
            swept or no timestamp column.
    """

    swept: bool
    side: str
    level: float
    reversal_direction: str | None
    penetration_index: int | None
    penetration_extreme: float | None
    close_back_index: int | None
    close_back_timestamp: dt.datetime | None


def detect_sweep(
    df: pl.DataFrame,
    *,
    level: float,
    side: str,
    config: SweepConfig,
    search_start_index: int = 0,
    timestamp: str = "timestamp",
    high: str = "high",
    low: str = "low",
    close: str = "close",
) -> SweepResult:
    """Detect a liquidity sweep of ``level`` on ``side`` within a candle series.

    Scans bars (in ``timestamp`` order) from ``search_start_index`` for the
    **first** bar that penetrates the level by at least ``config.penetration``,
    then checks whether a bar within ``config.close_back_within_bars`` (inclusive
    of the penetration bar) closes back inside the level. If the first
    penetration closes back inside its window, the sweep is confirmed; otherwise
    it is a breakout/continuation and **not** flagged (anchoring to the first
    poke avoids spuriously flagging a re-poke after price has already broken and
    held beyond the level). To look for a later, distinct sweep, call again with
    ``search_start_index`` past the breakout.

    Args:
        df: OHLC bars with ``timestamp``/``high``/``low``/``close`` columns.
        level: Reference price level (PDH/PDL or a swing high/low).
        side: ``"high"`` (sweep of buy-side liquidity above ``level``) or
            ``"low"`` (sweep of sell-side liquidity below ``level``).
        config: Sweep parameters; the depth/timing knobs are [MANUAL OBS].
        search_start_index: 0-based index to begin scanning from.
        timestamp: Tz-aware timestamp column name.
        high: High price column name.
        low: Low price column name.
        close: Close price column name.

    Returns:
        A :class:`SweepResult`.

    Raises:
        ValueError: If ``side`` is invalid or required columns are missing.
    """
    if side not in (SIDE_HIGH, SIDE_LOW):
        raise ValueError(f"side must be 'high' or 'low'; got {side!r}")
    missing = [c for c in (high, low, close) if c not in df.columns]
    if missing:
        raise ValueError(f"missing required columns: {missing}")

    not_swept = SweepResult(
        swept=False,
        side=side,
        level=level,
        reversal_direction=None,
        penetration_index=None,
        penetration_extreme=None,
        close_back_index=None,
        close_back_timestamp=None,
    )

    if df.height == 0:
        return not_swept

    has_ts = timestamp in df.columns
    work = df.sort(timestamp) if has_ts else df
    highs = work[high].to_list()
    lows = work[low].to_list()
    closes = work[close].to_list()
    times = work[timestamp].to_list() if has_ts else [None] * work.height
    n = work.height

    pen = config.penetration
    window = config.close_back_within_bars
    is_high = side == SIDE_HIGH

    start = max(0, search_start_index)
    for p in range(start, n):
        penetrated = (highs[p] >= level + pen) if is_high else (lows[p] <= level - pen)
        if not penetrated:
            continue
        # Anchor to this first penetration; only its window decides the outcome.
        last = min(p + window, n)  # offsets p .. p+window-1
        for c in range(p, last):
            closed_back = (closes[c] < level) if is_high else (closes[c] > level)
            if closed_back:
                return SweepResult(
                    swept=True,
                    side=side,
                    level=level,
                    reversal_direction=DIRECTION_BEARISH if is_high else DIRECTION_BULLISH,
                    penetration_index=p,
                    penetration_extreme=highs[p] if is_high else lows[p],
                    close_back_index=c,
                    close_back_timestamp=times[c],
                )
        return not_swept
    return not_swept


def recent_swing_level(
    df: pl.DataFrame,
    *,
    side: str,
    lookback: int,
    end_index: int | None = None,
    timestamp: str = "timestamp",
    high: str = "high",
    low: str = "low",
) -> float | None:
    """Return a recent swing level (max high / min low) over a lookback window.

    Convenience for feeding :func:`detect_sweep` when the level is "the recent
    swing" rather than a fixed PDH/PDL. Takes the extreme over the ``lookback``
    bars ending just before ``end_index`` (exclusive), so the returned level is
    fully known before the bars that may sweep it.

    Args:
        df: OHLC bars with ``timestamp``/``high``/``low``.
        side: ``"high"`` (returns max high) or ``"low"`` (returns min low).
        lookback: Number of bars in the window. Must be >= 1.
        end_index: Exclusive end of the window (the scan typically starts here).
            ``None`` uses the full frame.
        timestamp: Timestamp column for ordering.
        high: High column name.
        low: Low column name.

    Returns:
        The swing level, or ``None`` if the window is empty.

    Raises:
        ValueError: If ``side`` is invalid or ``lookback`` < 1.
    """
    if side not in (SIDE_HIGH, SIDE_LOW):
        raise ValueError(f"side must be 'high' or 'low'; got {side!r}")
    if lookback < 1:
        raise ValueError(f"lookback must be >= 1; got {lookback}")

    work = df.sort(timestamp) if timestamp in df.columns else df
    n = work.height
    end = n if end_index is None else max(0, min(end_index, n))
    start = max(0, end - lookback)
    if start >= end:
        return None
    if side == SIDE_HIGH:
        return float(work[high][start:end].max())
    return float(work[low][start:end].min())
