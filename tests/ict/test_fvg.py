"""Tests for :mod:`quant_research.ict.fvg` (Primitive 2 — FVG detection)."""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import polars as pl
import pytest

from quant_research.ict.fvg import (
    DIRECTION_BEARISH,
    DIRECTION_BULLISH,
    detect_fvgs,
    fvg_midpoint,
    resample_ohlc,
)

CT = ZoneInfo("America/Chicago")


def _bars(rows: list[tuple[float, float, float, float]]) -> pl.DataFrame:
    """Build OHLC bars at 1-minute spacing from (open, high, low, close) tuples."""
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


def test_fvg_midpoint_helper() -> None:
    assert fvg_midpoint(110.0, 100.0) == pytest.approx(105.0)


def test_bullish_fvg_detected_with_correct_zone() -> None:
    """c1.high=101, c3.low=105 -> bullish gap [101, 105], midpoint 103."""
    df = _bars(
        [
            (100.0, 101.0, 99.0, 100.5),  # c1
            (100.5, 106.0, 100.0, 105.5),  # c2 displacement up
            (105.5, 107.0, 105.0, 106.0),  # c3 low=105 > c1 high=101
        ]
    )
    out = detect_fvgs(df)
    assert out.height == 1
    row = out.row(0, named=True)
    assert row["direction"] == DIRECTION_BULLISH
    assert row["bottom"] == pytest.approx(101.0)
    assert row["top"] == pytest.approx(105.0)
    assert row["midpoint"] == pytest.approx(103.0)
    assert row["gap_size"] == pytest.approx(4.0)
    assert (row["c1_index"], row["c2_index"], row["c3_index"]) == (0, 1, 2)


def test_bearish_fvg_detected_with_correct_zone() -> None:
    """c1.low=99, c3.high=95 -> bearish gap [95, 99], midpoint 97."""
    df = _bars(
        [
            (100.0, 101.0, 99.0, 99.5),  # c1
            (99.5, 100.0, 94.0, 94.5),  # c2 displacement down
            (94.5, 95.0, 93.0, 94.0),  # c3 high=95 < c1 low=99
        ]
    )
    out = detect_fvgs(df)
    assert out.height == 1
    row = out.row(0, named=True)
    assert row["direction"] == DIRECTION_BEARISH
    assert row["bottom"] == pytest.approx(95.0)
    assert row["top"] == pytest.approx(99.0)
    assert row["midpoint"] == pytest.approx(97.0)
    assert row["gap_size"] == pytest.approx(4.0)


def test_no_gap_sequence_detects_nothing() -> None:
    """Overlapping candles (c3.low <= c1.high) produce no FVG."""
    df = _bars(
        [
            (100.0, 102.0, 99.0, 101.0),
            (101.0, 103.0, 100.0, 102.0),
            (102.0, 104.0, 101.0, 103.0),  # c3 low=101 == c1 high=102? 101 < 102 -> no gap
        ]
    )
    out = detect_fvgs(df)
    assert out.height == 0


def test_touching_levels_are_not_a_gap() -> None:
    """Exact equality (c3.low == c1.high) is not a strict gap."""
    df = _bars(
        [
            (100.0, 101.0, 99.0, 100.5),
            (100.5, 106.0, 100.0, 105.5),
            (105.5, 107.0, 101.0, 106.0),  # c3 low == c1 high == 101 -> not strict
        ]
    )
    assert detect_fvgs(df).height == 0


def test_min_gap_size_filters_small_gaps() -> None:
    """A 4-point gap is dropped when min_gap_size=5."""
    df = _bars(
        [
            (100.0, 101.0, 99.0, 100.5),
            (100.5, 106.0, 100.0, 105.5),
            (105.5, 107.0, 105.0, 106.0),  # gap = 4
        ]
    )
    assert detect_fvgs(df, min_gap_size=5.0).height == 0
    assert detect_fvgs(df, min_gap_size=3.0).height == 1


def test_multiple_fvgs_both_directions() -> None:
    """A bullish then a bearish FVG in one series are both detected, ordered."""
    df = _bars(
        [
            (100.0, 101.0, 99.0, 100.5),  # 0 c1 of bull
            (100.5, 106.0, 100.0, 105.5),  # 1 c2
            (105.5, 107.0, 105.0, 106.0),  # 2 c3 bull (gap 101->105)
            (106.0, 108.0, 105.5, 107.0),  # 3 c1 of bear (low 105.5)
            (107.0, 107.5, 100.0, 100.5),  # 4 c2 down
            (100.5, 101.0, 99.0, 100.0),  # 5 c3 bear (high 101 < 105.5)
        ]
    )
    out = detect_fvgs(df)
    assert out["direction"].to_list() == [DIRECTION_BULLISH, DIRECTION_BEARISH]
    assert out["c2_index"].to_list() == [1, 4]


def test_fewer_than_three_bars_returns_empty() -> None:
    df = _bars([(100.0, 101.0, 99.0, 100.5), (100.5, 106.0, 100.0, 105.5)])
    out = detect_fvgs(df)
    assert out.height == 0
    assert set(
        ["direction", "top", "bottom", "midpoint", "gap_size"]
    ).issubset(out.columns)


def test_first_and_last_bar_cannot_be_middle_candle() -> None:
    """Boundary: a gap requires a candle on both sides; ends never anchor an FVG."""
    # Only possible FVG uses bar 1 as middle; bars 0 and 2 cannot be c2.
    df = _bars(
        [
            (100.0, 101.0, 99.0, 100.5),
            (100.5, 106.0, 100.0, 105.5),
            (105.5, 107.0, 105.0, 106.0),
        ]
    )
    out = detect_fvgs(df)
    assert out["c2_index"].to_list() == [1]


def test_missing_columns_raises() -> None:
    df = pl.DataFrame({"timestamp": [], "high": []})
    with pytest.raises(ValueError, match="missing required columns"):
        detect_fvgs(df)


def test_resample_then_detect() -> None:
    """resample_ohlc builds coarser bars; FVG detection runs on them."""
    # 9 one-minute bars -> three 3-minute bars forming a bullish gap.
    rows = [
        (100.0, 101.0, 99.0, 100.0),
        (100.0, 101.0, 99.5, 100.5),
        (100.5, 101.0, 99.0, 100.0),  # 3m bar 1: high 101, low 99
        (100.0, 106.0, 100.0, 105.0),
        (105.0, 106.0, 104.0, 105.5),
        (105.5, 106.0, 104.0, 105.0),  # 3m bar 2: high 106, low 100
        (105.0, 107.0, 105.0, 106.0),
        (106.0, 107.5, 105.5, 107.0),
        (107.0, 108.0, 105.0, 107.5),  # 3m bar 3: high 108, low 105 > bar1 high 101
    ]
    df = _bars(rows)
    bars3 = resample_ohlc(df, every="3m")
    assert bars3.height == 3
    out = detect_fvgs(bars3)
    assert out.height == 1
    assert out["direction"][0] == DIRECTION_BULLISH
    assert out["bottom"][0] == pytest.approx(101.0)
    assert out["top"][0] == pytest.approx(105.0)
