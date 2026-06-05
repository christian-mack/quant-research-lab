"""Primitive 3 — CISD detection (Change in State of Delivery).

Implements the TTrades mechanical definition of CISD (video ``CHIK5oBRKiw``,
ingested as the ``cisd_smt`` corpus). The load-bearing rule, quoted from the
source transcript:

- *"this up close candle here gets closed below here and that is when the change
  in state of delivery occurs when the opening price of this up closed candle or
  series of up closed candles gets closed below"* (@41–53s)
- *"when there is more than one up closed candle or a series ... I use the opening
  price of the first candle ... as my change in state of delivery"* (@75–101s)
- *"the series or single up close candle that made the new high before displacing
  and closing below ... one two candles that made the new high before the
  displacement down and I'd want to see a close below"* (@133–151s)
- bullish symmetric: *"price puts in a swing low ... and then closes over the
  series or single down clos candle changing the state of delivery"* (@60–71s)
- *"closed below the opening price of that ... validating it as an order block"*
  (@819–824s) — the opposing-close run is the order block exposed for entry.

Computable definition
----------------------
**Bearish CISD** (bullish→bearish, at a high):

1. Anchor on the swing-high candle (the candle that made the new high; auto =
   ``argmax(high)`` over the frame, or caller-supplied).
2. Identify the maximal run of consecutive **up-close** candles
   (``close > open``) that made that high. The run is the order block.
3. The CISD level is the **opening price of the first** candle in that run.
4. CISD **fires** when a subsequent candle **closes strictly below** the CISD
   level.

**Bullish CISD** (bearish→bullish, at a low) is the mirror image: a run of
consecutive **down-close** candles (``close < open``) making the swing low, CISD
level = opening price of the first candle in the run, fires when a subsequent
candle **closes strictly above** the level.

Anchor fallback
    If the swing-extreme candle is itself not an opposing-close candle (e.g. the
    high is a rejection/sweep wick on a down-close candle), the run is taken as
    the consecutive opposing-close run ending at the nearest opposing-close
    candle at/ before the anchor — i.e. "the up-close candles that made the move
    into the high", excluding the sweep candle. This keeps the level anchored to
    the displacement leg, matching the transcript's sweep examples (@155–178s).

Timeframe
    Timeframe-agnostic: pass bars at the pairing timeframe (hourly/30m early,
    15m/5m into NY per the Bias Module Spec). Resample upstream with
    :func:`quant_research.ict.fvg.resample_ohlc` if needed.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Final

import polars as pl

DIRECTION_BEARISH: Final[str] = "bearish"
DIRECTION_BULLISH: Final[str] = "bullish"


@dataclass(frozen=True)
class CisdResult:
    """Outcome of a CISD scan over one candle series.

    Attributes:
        direction: ``"bearish"`` or ``"bullish"``.
        fired: Whether a CISD confirmation occurred.
        cisd_level: Opening price of the first opposing-close candle in the run
            (the level that must be closed beyond). ``None`` if no valid
            opposing-close run was found.
        anchor_index: 0-based index of the swing-extreme candle used as anchor.
        run_start_index: 0-based index of the first opposing-close candle of the
            run (the order block start). ``None`` if no run found.
        run_end_index: 0-based index of the last opposing-close candle of the run
            (order block end). ``None`` if no run found.
        ob_top: Top of the order-block zone (max high over the run). ``None`` if
            no run found.
        ob_bottom: Bottom of the order-block zone (min low over the run).
            ``None`` if no run found.
        fired_index: 0-based index of the candle whose close confirmed the CISD.
            ``None`` if not fired.
        fired_timestamp: Timestamp of the confirming candle. ``None`` if not
            fired or no timestamp column.
    """

    direction: str
    fired: bool
    cisd_level: float | None
    anchor_index: int | None
    run_start_index: int | None
    run_end_index: int | None
    ob_top: float | None
    ob_bottom: float | None
    fired_index: int | None
    fired_timestamp: dt.datetime | None


def detect_cisd(
    df: pl.DataFrame,
    *,
    direction: str,
    anchor_index: int | None = None,
    timestamp: str = "timestamp",
    open_: str = "open",
    high: str = "high",
    low: str = "low",
    close: str = "close",
) -> CisdResult:
    """Detect a Change in State of Delivery in ``direction`` over a candle series.

    See the module docstring for the full mechanical definition.

    Args:
        df: OHLC bars at the pairing timeframe, processed in ``timestamp`` order.
        direction: ``"bearish"`` (close below first up-close candle's open) or
            ``"bullish"`` (close above first down-close candle's open).
        anchor_index: 0-based index (into the timestamp-sorted frame) of the swing
            extreme. ``None`` auto-selects ``argmax(high)`` for bearish or
            ``argmin(low)`` for bullish.
        timestamp: Tz-aware timestamp column name.
        open_: Open price column name.
        high: High price column name.
        low: Low price column name.
        close: Close price column name.

    Returns:
        A :class:`CisdResult`.

    Raises:
        ValueError: If ``direction`` is not recognised or required columns are
            missing.
    """
    if direction not in (DIRECTION_BEARISH, DIRECTION_BULLISH):
        raise ValueError(f"direction must be 'bearish' or 'bullish'; got {direction!r}")
    missing = [c for c in (open_, high, low, close) if c not in df.columns]
    if missing:
        raise ValueError(f"missing required columns: {missing}")

    not_found = CisdResult(
        direction=direction,
        fired=False,
        cisd_level=None,
        anchor_index=None,
        run_start_index=None,
        run_end_index=None,
        ob_top=None,
        ob_bottom=None,
        fired_index=None,
        fired_timestamp=None,
    )

    if df.height == 0:
        return not_found

    has_ts = timestamp in df.columns
    work = df.sort(timestamp) if has_ts else df
    opens = work[open_].to_list()
    highs = work[high].to_list()
    lows = work[low].to_list()
    closes = work[close].to_list()
    times = work[timestamp].to_list() if has_ts else [None] * work.height
    n = work.height

    is_bear = direction == DIRECTION_BEARISH

    def is_opposing(i: int) -> bool:
        """An up-close candle for bearish, a down-close candle for bullish."""
        return closes[i] > opens[i] if is_bear else closes[i] < opens[i]

    # 1. Anchor on the swing extreme.
    if anchor_index is None:
        anchor = _argmax(highs) if is_bear else _argmin(lows)
    else:
        if not 0 <= anchor_index < n:
            raise ValueError(f"anchor_index {anchor_index} out of range [0, {n})")
        anchor = anchor_index

    # 2. Find the opposing-close run that made the extreme.
    run_end = anchor
    if not is_opposing(run_end):
        run_end = _nearest_opposing_at_or_before(anchor, is_opposing)
        if run_end is None:
            return CisdResult(
                direction=direction,
                fired=False,
                cisd_level=None,
                anchor_index=anchor,
                run_start_index=None,
                run_end_index=None,
                ob_top=None,
                ob_bottom=None,
                fired_index=None,
                fired_timestamp=None,
            )
    run_start = run_end
    while run_start - 1 >= 0 and is_opposing(run_start - 1):
        run_start -= 1

    # 3. CISD level = opening price of the first candle in the run.
    level = opens[run_start]
    ob_top = max(highs[run_start : run_end + 1])
    ob_bottom = min(lows[run_start : run_end + 1])

    # 4. Scan forward from after the anchor for the confirming close.
    fired_index: int | None = None
    for i in range(anchor + 1, n):
        if (is_bear and closes[i] < level) or (not is_bear and closes[i] > level):
            fired_index = i
            break

    return CisdResult(
        direction=direction,
        fired=fired_index is not None,
        cisd_level=level,
        anchor_index=anchor,
        run_start_index=run_start,
        run_end_index=run_end,
        ob_top=ob_top,
        ob_bottom=ob_bottom,
        fired_index=fired_index,
        fired_timestamp=times[fired_index] if fired_index is not None else None,
    )


def _argmax(values: list[float]) -> int:
    """Index of the first maximal element."""
    best = 0
    for i in range(1, len(values)):
        if values[i] > values[best]:
            best = i
    return best


def _argmin(values: list[float]) -> int:
    """Index of the first minimal element."""
    best = 0
    for i in range(1, len(values)):
        if values[i] < values[best]:
            best = i
    return best


def _nearest_opposing_at_or_before(anchor: int, is_opposing) -> int | None:
    """Walk backward from ``anchor`` to the nearest opposing-close candle."""
    for i in range(anchor, -1, -1):
        if is_opposing(i):
            return i
    return None
