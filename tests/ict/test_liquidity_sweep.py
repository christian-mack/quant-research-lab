"""Tests for :mod:`quant_research.ict.liquidity_sweep` (Primitive 5 — sweep)."""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import polars as pl
import pytest

from quant_research.ict.liquidity_sweep import (
    DIRECTION_BEARISH,
    DIRECTION_BULLISH,
    SIDE_HIGH,
    SIDE_LOW,
    SweepConfig,
    detect_sweep,
    recent_swing_level,
)

CT = ZoneInfo("America/Chicago")
TICK = 0.25  # MNQ tick size


def _bars(rows: list[tuple[float, float, float, float]]) -> pl.DataFrame:
    base = dt.datetime(2024, 6, 10, 8, 30, tzinfo=CT)
    return pl.DataFrame(
        {
            "timestamp": [base + dt.timedelta(minutes=i) for i in range(len(rows))],
            "open": [r[0] for r in rows],
            "high": [r[1] for r in rows],
            "low": [r[2] for r in rows],
            "close": [r[3] for r in rows],
        }
    )


def _cfg(pen_ticks: int = 1, n: int = 3) -> SweepConfig:
    return SweepConfig(tick_size=TICK, penetration_ticks=pen_ticks, close_back_within_bars=n)


def test_single_bar_high_sweep_then_reversal() -> None:
    """Wick above level, closes back below in the same bar -> bearish sweep."""
    # level = 100. Bar 1 wicks to 100.5 (>= 100 + 1 tick) and closes 99.5 (< 100).
    df = _bars(
        [
            (98.0, 99.0, 97.0, 98.5),
            (98.5, 100.5, 98.0, 99.5),  # penetration + close-back same bar
            (99.5, 100.0, 98.0, 99.0),
        ]
    )
    res = detect_sweep(df, level=100.0, side=SIDE_HIGH, config=_cfg())
    assert res.swept is True
    assert res.reversal_direction == DIRECTION_BEARISH
    assert res.penetration_index == 1
    assert res.close_back_index == 1
    assert res.penetration_extreme == pytest.approx(100.5)


def test_single_bar_low_sweep_then_reversal() -> None:
    """Wick below level, closes back above -> bullish sweep."""
    df = _bars(
        [
            (101.0, 102.0, 100.5, 101.5),
            (101.5, 102.0, 99.0, 100.5),  # low 99 <= 100 - 1 tick; close 100.5 > 100
            (100.5, 101.0, 100.0, 100.8),
        ]
    )
    res = detect_sweep(df, level=100.0, side=SIDE_LOW, config=_cfg())
    assert res.swept is True
    assert res.reversal_direction == DIRECTION_BULLISH
    assert res.penetration_index == 1
    assert res.penetration_extreme == pytest.approx(99.0)


def test_multi_bar_close_back_within_n() -> None:
    """Penetrate, hold above 1 bar, then close back inside on the 2nd bar (N=3)."""
    df = _bars(
        [
            (98.0, 99.0, 97.0, 98.5),
            (98.5, 101.0, 98.0, 100.6),  # 1 penetration, closes above level (100.6)
            (100.6, 101.2, 100.1, 100.7),  # 2 still above
            (100.7, 100.9, 98.0, 99.0),  # 3 closes back below 100 -> within window
        ]
    )
    res = detect_sweep(df, level=100.0, side=SIDE_HIGH, config=_cfg(n=3))
    assert res.swept is True
    assert res.penetration_index == 1
    assert res.close_back_index == 3


def test_continuation_does_not_flag() -> None:
    """Penetrate and keep going (never close back inside) -> no sweep."""
    df = _bars(
        [
            (98.0, 99.0, 97.0, 98.5),
            (98.5, 101.0, 98.0, 100.8),  # penetration, closes above
            (100.8, 102.0, 100.5, 101.8),  # continues up
            (101.8, 103.0, 101.5, 102.8),  # continues up
        ]
    )
    res = detect_sweep(df, level=100.0, side=SIDE_HIGH, config=_cfg(n=3))
    assert res.swept is False
    assert res.penetration_index is None


def test_close_back_outside_window_does_not_flag() -> None:
    """Close-back happens but only after N bars -> not flagged (boundary on N)."""
    df = _bars(
        [
            (98.0, 99.0, 97.0, 98.5),
            (98.5, 101.0, 98.0, 100.8),  # 1 penetration
            (100.8, 101.2, 100.5, 100.9),  # 2 above
            (100.9, 101.1, 100.4, 100.7),  # 3 above (window N=2 ends here for p=1: bars 1,2)
            (100.7, 100.8, 98.0, 99.0),  # 4 closes back below, but outside N=2 window
        ]
    )
    # With N=2, window for penetration at index 1 is bars {1,2}; close-back at 4 is too late.
    res = detect_sweep(df, level=100.0, side=SIDE_HIGH, config=_cfg(n=2))
    assert res.swept is False


def test_close_back_exactly_at_window_edge_flags() -> None:
    """Close-back on the last bar of the N-window is still inside the window."""
    df = _bars(
        [
            (98.0, 99.0, 97.0, 98.5),
            (98.5, 101.0, 98.0, 100.8),  # 1 penetration (offset 0)
            (100.8, 101.2, 100.5, 100.9),  # 2 offset 1
            (100.9, 100.95, 98.0, 99.0),  # 3 offset 2 -> close-back, N=3 includes it
        ]
    )
    res = detect_sweep(df, level=100.0, side=SIDE_HIGH, config=_cfg(n=3))
    assert res.swept is True
    assert res.close_back_index == 3


def test_penetration_must_exceed_tick_threshold() -> None:
    """A poke smaller than penetration_ticks does not count as trading through."""
    # High reaches exactly 100.0 == level, with 1-tick threshold need >= 100.25.
    df = _bars(
        [
            (99.0, 99.5, 98.5, 99.2),
            (99.2, 100.0, 99.0, 99.5),  # high == level, not >= level + 1 tick
            (99.5, 99.8, 98.0, 98.5),
        ]
    )
    res = detect_sweep(df, level=100.0, side=SIDE_HIGH, config=_cfg(pen_ticks=1))
    assert res.swept is False


def test_larger_penetration_threshold_filters_shallow_poke() -> None:
    """A 1-tick poke is filtered when penetration_ticks=4 (needs 1.0 beyond)."""
    df = _bars(
        [
            (98.0, 99.0, 97.0, 98.5),
            (98.5, 100.5, 98.0, 99.5),  # only 0.5 beyond level (2 ticks)
            (99.5, 100.0, 98.0, 99.0),
        ]
    )
    assert detect_sweep(df, level=100.0, side=SIDE_HIGH, config=_cfg(pen_ticks=4)).swept is False
    assert detect_sweep(df, level=100.0, side=SIDE_HIGH, config=_cfg(pen_ticks=1)).swept is True


def test_search_start_index_skips_earlier_sweep() -> None:
    df = _bars(
        [
            (98.5, 100.5, 98.0, 99.5),  # 0 early sweep
            (99.5, 100.0, 98.0, 99.0),
            (99.0, 100.6, 98.5, 99.4),  # 2 later sweep
        ]
    )
    res = detect_sweep(df, level=100.0, side=SIDE_HIGH, config=_cfg(), search_start_index=1)
    assert res.swept is True
    assert res.penetration_index == 2


def test_recent_swing_level_high_and_low() -> None:
    df = _bars(
        [
            (98.0, 105.0, 97.0, 100.0),
            (100.0, 103.0, 95.0, 99.0),
            (99.0, 101.0, 98.0, 100.0),  # current bar, excluded by end_index=2
        ]
    )
    assert recent_swing_level(df, side=SIDE_HIGH, lookback=2, end_index=2) == pytest.approx(105.0)
    assert recent_swing_level(df, side=SIDE_LOW, lookback=2, end_index=2) == pytest.approx(95.0)


def test_recent_swing_level_empty_window_returns_none() -> None:
    df = _bars([(98.0, 99.0, 97.0, 98.5)])
    assert recent_swing_level(df, side=SIDE_HIGH, lookback=2, end_index=0) is None


def test_invalid_side_raises() -> None:
    with pytest.raises(ValueError, match="side must be"):
        detect_sweep(_bars([(1.0, 1.0, 1.0, 1.0)]), level=1.0, side="up", config=_cfg())


def test_invalid_config_raises() -> None:
    with pytest.raises(ValueError, match="tick_size must be"):
        SweepConfig(tick_size=0.0)
    with pytest.raises(ValueError, match="close_back_within_bars must be"):
        SweepConfig(tick_size=0.25, close_back_within_bars=0)


def test_missing_columns_raises() -> None:
    df = pl.DataFrame({"timestamp": [], "high": []})
    with pytest.raises(ValueError, match="missing required columns"):
        detect_sweep(df, level=1.0, side=SIDE_HIGH, config=_cfg())


def test_empty_frame_not_swept() -> None:
    df = _bars([]) if False else _bars([(1.0, 1.0, 1.0, 1.0)]).head(0)
    res = detect_sweep(df, level=100.0, side=SIDE_HIGH, config=_cfg())
    assert res.swept is False
