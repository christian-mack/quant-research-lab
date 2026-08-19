"""Primitive 6 — Market Structure Shift (MSS) detection.

Implements the 2022 mentorship MSS mechanic (distinct from TTrades CISD in
:mod:`quant_research.ict.cisd`). MSS is a **swing-break** confirmation after a
liquidity sweep, not a close-beyond-opening-price rule.

Source anchors (2022 corpus):
- Ep 6 @1110s — bearish MSS: run above old high, then break below short-term low.
- Ep 6 @1416s — bullish MSS: sweep lows, close above short-term high with displacement.
- Ep 12 @2247s — MSS = short-term swing broken, then retrace into imbalance.

Operational definition (Spec A + Phase 3 step 0):
- **Short-term swing** = 3-bar fractal (center bar strictly exceeds both neighbors).
- **Opposing swing lookback** = manipulation-leg bounded from sweep close-back through the
  MSS candidate bar (D0.4 default; extend to session start / 100-bar cap if empty).
- **Trigger** = close strictly beyond the most recent opposing fractal level in lookback.
- **Displacement leg** = running price extreme from sweep penetration bar through MSS bar
  (D0.3); exposed for downstream FVG / OTE consumption.

MSS does **not** require FVG presence — displacement magnitude is validated separately via
:mod:`quant_research.ict.fvg` per Spec A.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Final

import polars as pl

from quant_research.ict.liquidity_sweep import SweepResult

DIRECTION_BULLISH: Final[str] = "bullish"
DIRECTION_BEARISH: Final[str] = "bearish"

DEFAULT_FRACTAL_HALF_WIDTH: Final[int] = 1
"""3-bar fractal: one bar on each side of the center."""

DEFAULT_MAX_LOOKBACK_FALLBACK_BARS: Final[int] = 100
"""[MANUAL OBS] Cap when no fractal exists in the manipulation-leg window (D0.4)."""


@dataclass(frozen=True)
class MssConfig:
    """Tunable MSS parameters.

    Attributes:
        fractal_half_width: Bars on each side of a fractal center (1 → 3-bar fractal).
        max_lookback_fallback_bars: [MANUAL OBS] Maximum backward extension when the
            manipulation-leg window contains no opposing fractal (D0.4).
        require_close_through: If True, MSS fires on **close** beyond the swing level
            (Spec A / Ep 6 @1433). If False, wick penetration counts (not recommended).
    """

    fractal_half_width: int = DEFAULT_FRACTAL_HALF_WIDTH
    max_lookback_fallback_bars: int = DEFAULT_MAX_LOOKBACK_FALLBACK_BARS
    require_close_through: bool = True

    def __post_init__(self) -> None:
        if self.fractal_half_width < 1:
            raise ValueError(f"fractal_half_width must be >= 1; got {self.fractal_half_width}")
        if self.max_lookback_fallback_bars < 1:
            raise ValueError(
                f"max_lookback_fallback_bars must be >= 1; got {self.max_lookback_fallback_bars}"
            )


@dataclass(frozen=True)
class DisplacementLeg:
    """Price swing from sweep penetration through MSS confirmation (D0.3).

    Attributes:
        start_index: Sweep penetration bar (inclusive).
        end_index: MSS confirmation bar (inclusive).
        high: ``max(high[start_index:end_index+1])``.
        low: ``min(low[start_index:end_index+1])``.
    """

    start_index: int
    end_index: int
    high: float
    low: float


@dataclass(frozen=True)
class FractalSwing:
    """A confirmed 3-bar (or wider) fractal swing."""

    side: str
    center_index: int
    level: float
    confirmation_index: int


@dataclass(frozen=True)
class MssResult:
    """Outcome of an MSS scan.

    Attributes:
        fired: Whether MSS confirmed on this scan.
        direction: ``bullish`` or ``bearish``.
        swing_level_broken: Opposing fractal level that was broken. ``None`` if not fired.
        swing_center_index: Center bar index of the broken fractal. ``None`` if not fired.
        fired_index: Bar whose close (or wick) confirmed the break. ``None`` if not fired.
        fired_timestamp: Timestamp of the confirming bar.
        displacement: Displacement leg from sweep penetration through MSS bar.
            ``None`` if not fired.
    """

    direction: str
    fired: bool
    swing_level_broken: float | None
    swing_center_index: int | None
    fired_index: int | None
    fired_timestamp: dt.datetime | None
    displacement: DisplacementLeg | None


def detect_mss(
    df: pl.DataFrame,
    *,
    direction: str,
    leg_start_index: int,
    penetration_index: int | None = None,
    search_end_index: int | None = None,
    config: MssConfig | None = None,
    timestamp: str = "timestamp",
    open_: str = "open",
    high: str = "high",
    low: str = "low",
    close: str = "close",
) -> MssResult:
    """Detect Market Structure Shift after a liquidity sweep.

    Scans forward from ``leg_start_index + 1`` (typically the sweep close-back bar per
    D0.4) for the **first** bar that closes through the most recent opposing fractal swing
    in the manipulation-leg lookback window.

    Args:
        df: OHLC bars in ``timestamp`` order.
        direction: ``bullish`` (close above opposing swing high) or ``bearish`` (close
            below opposing swing low).
        leg_start_index: D0.4 lower bound — sweep close-back bar index (swing search
            starts here; MSS scan starts at ``leg_start_index + 1``).
        penetration_index: Sweep penetration bar for displacement leg anchoring (D0.3).
            Defaults to ``leg_start_index`` when ``None``.
        search_end_index: Exclusive end of forward scan. ``None`` scans to frame end.
        config: MSS parameters. Uses defaults when ``None``.
        timestamp: Tz-aware timestamp column name.
        open_: Open column (unused; kept for API symmetry with other primitives).
        high: High column name.
        low: Low column name.
        close: Close column name.

    Returns:
        :class:`MssResult` for the first MSS found, or a not-fired result.

    Raises:
        ValueError: If ``direction`` is invalid, indices are out of range, or required
            columns are missing.
    """
    del open_  # API symmetry; MSS uses close-through only.
    if direction not in (DIRECTION_BULLISH, DIRECTION_BEARISH):
        raise ValueError(f"direction must be 'bullish' or 'bearish'; got {direction!r}")

    missing = [c for c in (high, low, close) if c not in df.columns]
    if missing:
        raise ValueError(f"missing required columns: {missing}")

    cfg = config or MssConfig()
    not_fired = MssResult(
        direction=direction,
        fired=False,
        swing_level_broken=None,
        swing_center_index=None,
        fired_index=None,
        fired_timestamp=None,
        displacement=None,
    )

    if df.height == 0:
        return not_fired

    has_ts = timestamp in df.columns
    work = df.sort(timestamp) if has_ts else df
    highs = work[high].to_list()
    lows = work[low].to_list()
    closes = work[close].to_list()
    times = work[timestamp].to_list() if has_ts else [None] * work.height
    n = work.height

    if not 0 <= leg_start_index < n:
        raise ValueError(f"leg_start_index {leg_start_index} out of range [0, {n})")

    pen_idx = leg_start_index if penetration_index is None else penetration_index
    if not 0 <= pen_idx < n:
        raise ValueError(f"penetration_index {pen_idx} out of range [0, {n})")

    end = n if search_end_index is None else max(0, min(search_end_index, n))
    is_bull = direction == DIRECTION_BULLISH
    swing_side = "high" if is_bull else "low"

    scan_start = leg_start_index + 1
    if scan_start >= end:
        return not_fired

    for t in range(scan_start, end):
        lookback_start = _lookback_start(
            pen_idx,
            cfg.max_lookback_fallback_bars,
        )
        swing = _most_recent_fractal(
            highs,
            lows,
            side=swing_side,
            lookback_start=lookback_start,
            before_index=t,
            half_width=cfg.fractal_half_width,
        )
        if swing is None:
            continue

        if is_bull:
            broken = (
                closes[t] > swing.level if cfg.require_close_through else highs[t] > swing.level
            )
        else:
            broken = closes[t] < swing.level if cfg.require_close_through else lows[t] < swing.level

        if not broken:
            continue

        disp = _displacement_leg(highs, lows, pen_idx, t)
        return MssResult(
            direction=direction,
            fired=True,
            swing_level_broken=swing.level,
            swing_center_index=swing.center_index,
            fired_index=t,
            fired_timestamp=times[t],
            displacement=disp,
        )

    return not_fired


def detect_mss_after_sweep(
    df: pl.DataFrame,
    sweep: SweepResult,
    *,
    config: MssConfig | None = None,
    timestamp: str = "timestamp",
    open_: str = "open",
    high: str = "high",
    low: str = "low",
    close: str = "close",
) -> MssResult:
    """Detect MSS in the direction implied by a confirmed :class:`SweepResult`.

    Maps sweep reversal direction to MSS direction and uses sweep indices for D0.3/D0.4
    anchoring.

    Args:
        df: OHLC bars.
        sweep: Confirmed sweep from :func:`quant_research.ict.liquidity_sweep.detect_sweep`.
        config: MSS parameters.
        timestamp: Timestamp column.
        open_: Open column.
        high: High column.
        low: Low column.
        close: Close column.

    Returns:
        :class:`MssResult`.

    Raises:
        ValueError: If ``sweep.swept`` is False or indices are missing.
    """
    if not sweep.swept:
        raise ValueError("sweep.swept must be True")
    if sweep.close_back_index is None or sweep.penetration_index is None:
        raise ValueError("sweep result missing penetration_index or close_back_index")

    direction = sweep.reversal_direction
    if direction is None:
        raise ValueError("sweep.reversal_direction is None")

    return detect_mss(
        df,
        direction=direction,
        leg_start_index=sweep.close_back_index,
        penetration_index=sweep.penetration_index,
        config=config,
        timestamp=timestamp,
        open_=open_,
        high=high,
        low=low,
        close=close,
    )


def confirmed_fractal_swings(
    df: pl.DataFrame,
    *,
    side: str,
    up_to_index: int | None = None,
    half_width: int = DEFAULT_FRACTAL_HALF_WIDTH,
    high: str = "high",
    low: str = "low",
) -> list[FractalSwing]:
    """Return all confirmed fractal swings of ``side`` known before ``up_to_index``.

    A fractal centered at ``i`` is confirmed once bar ``i + half_width`` has printed
    (causal, no look-ahead). Exposed for tests and downstream strategy tooling.

    Args:
        df: OHLC bars.
        side: ``high`` or ``low``.
        up_to_index: Exclusive index bound for confirmation (fractals with
            ``confirmation_index < up_to_index``). ``None`` uses full frame.
        half_width: Fractal half-width (1 → 3-bar).
        high: High column.
        low: Low column.

    Returns:
        Fractal swings sorted by ``center_index``.
    """
    if side not in ("high", "low"):
        raise ValueError(f"side must be 'high' or 'low'; got {side!r}")

    if df.height == 0:
        return []

    highs = df[high].to_list()
    lows = df[low].to_list()
    n = df.height
    bound = n if up_to_index is None else max(0, min(up_to_index, n))

    out: list[FractalSwing] = []
    for center in range(half_width, n - half_width):
        confirm = center + half_width
        if confirm >= bound:
            break
        if side == "high":
            level = highs[center]
            if not _is_fractal_high(highs, center, half_width):
                continue
        else:
            level = lows[center]
            if not _is_fractal_low(lows, center, half_width):
                continue
        out.append(
            FractalSwing(
                side=side,
                center_index=center,
                level=level,
                confirmation_index=confirm,
            )
        )
    return out


def _lookback_start(penetration_index: int, max_fallback: int) -> int:
    """Lookback lower bound anchored at sweep penetration (D0.4).

    Extends ``max_fallback`` bars before penetration so swings *prior to* the
    manipulation run are eligible (Ep 6 @1261 — broken swing is prior to the run above).
    """
    return max(0, penetration_index - max_fallback)


def _most_recent_fractal(
    highs: list[float],
    lows: list[float],
    *,
    side: str,
    lookback_start: int,
    before_index: int,
    half_width: int,
) -> FractalSwing | None:
    """Most recent confirmed opposing fractal with center in [lookback_start, before_index)."""
    best: FractalSwing | None = None
    # Fractal at center is known when before_index > center + half_width.
    last_center = min(before_index - half_width - 1, len(highs) - half_width - 1)
    for center in range(last_center, half_width - 1, -1):
        if center < lookback_start:
            break
        confirm = center + half_width
        if confirm >= before_index:
            continue
        if side == "high":
            if not _is_fractal_high(highs, center, half_width):
                continue
            level = highs[center]
        else:
            if not _is_fractal_low(lows, center, half_width):
                continue
            level = lows[center]
        return FractalSwing(
            side=side,
            center_index=center,
            level=level,
            confirmation_index=confirm,
        )
    return best


def _is_fractal_high(highs: list[float], center: int, half_width: int) -> bool:
    """Strict fractal high: center strictly greater than both sides."""
    h = highs[center]
    for off in range(1, half_width + 1):
        if h <= highs[center - off] or h <= highs[center + off]:
            return False
    return True


def _is_fractal_low(lows: list[float], center: int, half_width: int) -> bool:
    """Strict fractal low: center strictly less than both sides."""
    low = lows[center]
    for off in range(1, half_width + 1):
        if low >= lows[center - off] or low >= lows[center + off]:
            return False
    return True


def _displacement_leg(
    highs: list[float],
    lows: list[float],
    start: int,
    end: int,
) -> DisplacementLeg:
    """Running extreme over [start, end] inclusive (D0.3)."""
    seg_h = highs[start : end + 1]
    seg_l = lows[start : end + 1]
    return DisplacementLeg(
        start_index=start,
        end_index=end,
        high=max(seg_h),
        low=min(seg_l),
    )
