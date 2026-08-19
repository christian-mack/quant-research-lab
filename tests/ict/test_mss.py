"""Tests for :mod:`quant_research.ict.mss` (Primitive 6 — Market Structure Shift).

Synthetic bars mirror the 2022 mentorship geometries cited in Phase 3a / step 0:
- Ep 6 @1416s — bullish MSS after sell-side sweep.
- Ep 6 @1110s — bearish MSS after buy-side run.
- Ep 12 @2247s — short-term low broken (bearish MSS anchor).
MSS vs CISD independence documents the Phase 3a finding in code.
"""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import polars as pl
import pytest

from quant_research.ict.cisd import DIRECTION_BEARISH as CISD_BEAR, detect_cisd
from quant_research.ict.liquidity_sweep import (
    SIDE_HIGH,
    SIDE_LOW,
    SweepConfig,
    detect_sweep,
)
from quant_research.ict.mss import (
    DIRECTION_BEARISH,
    DIRECTION_BULLISH,
    MssConfig,
    confirmed_fractal_swings,
    detect_mss,
    detect_mss_after_sweep,
)

CT = ZoneInfo("America/Chicago")
TICK = 0.25


def _bars(rows: list[tuple[float, float, float, float]]) -> pl.DataFrame:
    base = dt.datetime(2024, 6, 10, 8, 30, tzinfo=CT)
    return pl.DataFrame(
        {
            "timestamp": [base + dt.timedelta(minutes=5 * i) for i in range(len(rows))],
            "open": [r[0] for r in rows],
            "high": [r[1] for r in rows],
            "low": [r[2] for r in rows],
            "close": [r[3] for r in rows],
        }
    )


def _sweep_cfg() -> SweepConfig:
    return SweepConfig(tick_size=TICK, penetration_ticks=1, close_back_within_bars=3)


# ---------------------------------------------------------------------------
# Worked examples — Ep 6 / Ep 12 geometries
# ---------------------------------------------------------------------------


def test_bullish_mss_ep6_1416_geometry() -> None:
    """Ep 6 @1416s: sweep lows → close above short-term high with displacement."""
    # Fractal swing high at bar 2 (106). Sweep below 100 at bar 4, close-back bar 5.
    # MSS fires bar 7 when close clears 106.
    df = _bars(
        [
            (100.0, 101.0, 100.5, 100.5),  # 0 stay above sweep level
            (100.5, 103.0, 100.0, 102.5),  # 1
            (102.5, 106.0, 102.0, 105.5),  # 2 fractal high 106
            (105.5, 104.5, 104.0, 104.5),  # 3
            (104.5, 104.5, 96.0, 97.0),  # 4 sweep penetration
            (97.0, 98.0, 96.5, 101.0),  # 5 close back inside
            (101.0, 104.0, 100.5, 103.0),  # 6 displacement rally
            (103.0, 108.0, 102.0, 107.0),  # 7 MSS: close 107 > 106
        ]
    )
    sweep = detect_sweep(
        df, level=100.0, side=SIDE_LOW, config=_sweep_cfg(), search_start_index=2
    )
    assert sweep.swept is True
    assert sweep.close_back_index == 5
    assert sweep.penetration_index == 4

    res = detect_mss_after_sweep(df, sweep)
    assert res.fired is True
    assert res.direction == DIRECTION_BULLISH
    assert res.swing_level_broken == pytest.approx(106.0)
    assert res.swing_center_index == 2
    assert res.fired_index == 7
    assert res.displacement is not None
    assert res.displacement.start_index == 4
    assert res.displacement.end_index == 7
    assert res.displacement.low == pytest.approx(96.0)
    assert res.displacement.high == pytest.approx(108.0)


def test_bearish_mss_ep6_1110_geometry() -> None:
    """Ep 6 @1110s: run above old high → break below short-term low."""
    # Fractal swing low at bar 3 (112). High sweep at bar 4. MSS at bar 6.
    df = _bars(
        [
            (115.0, 118.0, 114.0, 117.0),  # 0
            (117.0, 119.0, 116.0, 118.0),  # 1
            (118.0, 121.0, 117.0, 120.0),  # 2
            (120.0, 121.0, 112.0, 119.0),  # 3 fractal low 112
            (119.0, 125.0, 118.5, 119.5),  # 4 sweep high (close back inside 120)
            (119.5, 124.0, 119.0, 121.0),  # 5
            (121.0, 122.0, 110.0, 111.0),  # 6 MSS: close 111 < 112
        ]
    )
    sweep = detect_sweep(df, level=120.0, side=SIDE_HIGH, config=_sweep_cfg())
    assert sweep.swept is True

    res = detect_mss_after_sweep(df, sweep)
    assert res.fired is True
    assert res.direction == DIRECTION_BEARISH
    assert res.swing_level_broken == pytest.approx(112.0)
    assert res.swing_center_index == 3
    assert res.fired_index == 6
    assert res.displacement is not None
    assert res.displacement.low == pytest.approx(110.0)


def test_bearish_mss_ep12_2247_short_term_low_broken() -> None:
    """Ep 12 @2247s: MSS = short-term low broken (bearish confirmation)."""
    df = _bars(
        [
            (105.0, 106.0, 104.0, 105.5),  # 0
            (105.5, 107.0, 105.0, 106.5),  # 1
            (106.5, 108.0, 104.0, 107.5),  # 2 fractal low 104
            (107.5, 109.0, 106.5, 108.5),  # 3
            (108.5, 112.0, 108.0, 109.0),  # 4 push up (no sweep required here)
            (109.0, 111.0, 107.0, 110.0),  # 5
            (110.0, 110.5, 102.0, 103.0),  # 6 close 103 < 104 — MSS
        ]
    )
    res = detect_mss(
        df,
        direction=DIRECTION_BEARISH,
        leg_start_index=4,
        penetration_index=4,
    )
    assert res.fired is True
    assert res.swing_level_broken == pytest.approx(104.0)
    assert res.fired_index == 6


# ---------------------------------------------------------------------------
# No-fire and boundary cases
# ---------------------------------------------------------------------------


def test_no_mss_when_sweep_has_no_swing_break() -> None:
    """Sweep confirmed but price never closes through opposing swing."""
    df = _bars(
        [
            (100.0, 103.0, 99.5, 102.5),  # 0
            (102.5, 106.0, 102.0, 105.5),  # 1 fractal high 106
            (105.5, 104.5, 104.0, 104.5),  # 2
            (104.5, 104.5, 96.0, 97.0),  # 3 sweep
            (97.0, 98.0, 96.5, 101.0),  # 4 close back
            (101.0, 104.0, 100.5, 103.0),  # 5 rally stalls below 106
            (103.0, 105.5, 102.0, 105.0),  # 6 close 105 < 106
        ]
    )
    sweep = detect_sweep(df, level=100.0, side=SIDE_LOW, config=_sweep_cfg())
    res = detect_mss_after_sweep(df, sweep)
    assert res.fired is False


def test_no_mss_when_swing_wicked_but_not_closed_through() -> None:
    """Wick through swing level without close beyond does not fire (Spec A default)."""
    df = _bars(
        [
            (100.0, 103.0, 99.5, 102.5),  # 0
            (102.5, 106.0, 102.0, 105.5),  # 1 fractal high 106
            (105.5, 104.5, 104.0, 104.5),  # 2
            (104.5, 104.5, 96.0, 97.0),  # 3 sweep
            (97.0, 98.0, 96.5, 101.0),  # 4 close back
            (101.0, 107.5, 100.5, 105.0),  # 5 wick above 106, close 105 < 106
        ]
    )
    sweep = detect_sweep(df, level=100.0, side=SIDE_LOW, config=_sweep_cfg())
    res = detect_mss_after_sweep(df, sweep)
    assert res.fired is False


def test_swing_at_lookback_edge_still_detected() -> None:
    """Fractal at lookback edge (penetration − fallback) is eligible."""
    cfg = MssConfig(max_lookback_fallback_bars=2)
    df = _bars(
        [
            (100.0, 101.0, 100.0, 100.5),  # 0
            (100.5, 106.0, 100.0, 105.0),  # 1 fractal high 106 (edge: pen=3, start=1)
            (105.0, 105.0, 104.5, 104.5),  # 2
            (104.5, 105.0, 104.0, 104.0),  # 3 penetration
            (104.0, 104.5, 96.0, 97.0),  # 4 sweep continuation
            (97.0, 98.0, 96.5, 101.0),  # 5 close back
            (101.0, 108.0, 100.0, 107.0),  # 6 MSS
        ]
    )
    res = detect_mss(
        df,
        direction=DIRECTION_BULLISH,
        leg_start_index=5,
        penetration_index=3,
        config=cfg,
    )
    assert res.fired is True
    assert res.swing_center_index == 1


def test_first_bars_insufficient_for_fractal() -> None:
    """Fewer than 2*half_width+1 bars → no fractal → no MSS."""
    df = _bars(
        [
            (100.0, 101.0, 99.0, 100.5),
            (100.5, 102.0, 100.0, 101.5),
        ]
    )
    res = detect_mss(
        df,
        direction=DIRECTION_BULLISH,
        leg_start_index=0,
        penetration_index=0,
    )
    assert res.fired is False


def test_session_gap_does_not_break_detection() -> None:
    """Timestamp gap (session transition) does not affect index-based MSS logic."""
    df = _bars(
        [
            (100.0, 103.0, 99.5, 102.5),
            (102.5, 106.0, 102.0, 105.5),
            (105.5, 104.5, 104.0, 104.5),
            (104.5, 104.5, 96.0, 97.0),
            (97.0, 98.0, 96.5, 101.0),
            (101.0, 108.0, 100.0, 107.0),
        ]
    )
    # Simulate overnight gap in timestamps only.
    ts = df["timestamp"].to_list()
    ts[3] = ts[2] + dt.timedelta(hours=16)
    ts[4] = ts[3] + dt.timedelta(minutes=5)
    ts[5] = ts[4] + dt.timedelta(minutes=5)
    df = df.with_columns(pl.Series("timestamp", ts))

    sweep = detect_sweep(df, level=100.0, side=SIDE_LOW, config=_sweep_cfg())
    res = detect_mss_after_sweep(df, sweep)
    assert res.fired is True


# ---------------------------------------------------------------------------
# Phase 3a — MSS vs CISD independence
# ---------------------------------------------------------------------------


def test_mss_and_cisd_fire_independently_cisd_only() -> None:
    """CISD fires on close beyond first opposing open; MSS needs fractal swing break."""
    # Bearish: up-close run; close below CISD level (100) but stays above fractal low (98).
    df = _bars(
        [
            (95.0, 95.0, 93.0, 94.0),  # 0 down-close
            (100.0, 106.0, 99.0, 105.0),  # 1 up-close (CISD level 100)
            (105.0, 107.0, 104.0, 106.0),  # 2 up-close makes high
            (104.0, 105.0, 98.5, 99.0),  # 3 close 99 < 100 → CISD; 99 > 98 → no MSS
        ]
    )
    cisd = detect_cisd(df, direction=CISD_BEAR)
    assert cisd.fired is True

    mss = detect_mss(
        df,
        direction=DIRECTION_BEARISH,
        leg_start_index=1,
        penetration_index=1,
    )
    assert mss.fired is False


def test_mss_and_cisd_fire_independently_mss_only() -> None:
    """Fractal swing break (MSS) without close beyond first opposing candle open (CISD)."""
    # CISD level = 100; fractal swing low = 105. Close 102: no CISD, yes MSS.
    df = _bars(
        [
            (95.0, 95.0, 93.0, 94.0),  # 0 down-close
            (100.0, 112.0, 99.0, 111.0),  # 1 up-close (CISD level 100)
            (111.0, 113.0, 110.0, 112.0),  # 2
            (112.0, 113.0, 105.0, 112.5),  # 3 fractal low 105
            (112.5, 113.0, 108.0, 112.0),  # 4
            (112.0, 112.5, 101.0, 102.0),  # 5 close 102: MSS, not CISD
        ]
    )
    cisd = detect_cisd(df, direction=CISD_BEAR)
    assert cisd.fired is False

    mss = detect_mss(
        df,
        direction=DIRECTION_BEARISH,
        leg_start_index=3,
        penetration_index=3,
    )
    assert mss.fired is True
    assert mss.swing_level_broken == pytest.approx(105.0)


def test_confirmed_fractal_swings_causal() -> None:
    """Fractal at center 1 is only confirmed once bar 2 exists (3-bar, half_width=1)."""
    df = _bars(
        [
            (100.0, 101.0, 99.0, 100.5),
            (100.5, 106.0, 100.0, 105.0),  # center 1 high 106
            (105.0, 104.0, 103.0, 103.5),
        ]
    )
    assert confirmed_fractal_swings(df, side="high", up_to_index=2) == []
    swings = confirmed_fractal_swings(df, side="high", up_to_index=3)
    assert len(swings) == 1
    assert swings[0].center_index == 1
    assert swings[0].level == pytest.approx(106.0)
