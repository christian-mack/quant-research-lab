"""Tests for M4 hand-trace parity."""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import pytest

from quant_research.backtest.parity import hand_trace_setup
from quant_research.ict.liquidity_sweep import SIDE_LOW
from quant_research.ict.ote_execution import execute_setup, ote_research_backtest_config
from quant_research.ict.ote_strategy import (
    DIRECTION_LONG,
    OteSetup,
)

CT = ZoneInfo("America/Chicago")
SESSION = dt.date(2024, 6, 10)


def _bars(rows: list[tuple[float, float, float, float]]) -> __import__("polars").DataFrame:
    import polars as pl

    base = dt.datetime(2024, 6, 10, 8, 30, tzinfo=CT)
    return pl.DataFrame(
        {
            "timestamp": [base + dt.timedelta(minutes=i) for i in range(len(rows))],
            "open": [r[0] for r in rows],
            "high": [r[1] for r in rows],
            "low": [r[2] for r in rows],
            "close": [r[3] for r in rows],
            "cme_session_date": [SESSION] * len(rows),
            "volume": [100.0] * len(rows),
        }
    )


def _make_setup(*, entry: float, stop: float, target: float, fill_idx: int) -> OteSetup:
    ts = dt.datetime(2024, 6, 10, 9, 30, tzinfo=CT)
    return OteSetup(
        direction=DIRECTION_LONG,
        session_date=SESSION,
        sweep_level=99.0,
        sweep_side=SIDE_LOW,
        sweep_penetration_index=0,
        sweep_close_back_index=1,
        swept_extreme=98.0,
        mss_index=0,
        mss_swing_broken=101.0,
        displacement_low=96.0,
        displacement_high=110.0,
        equilibrium=103.0,
        fvg_top=101.0,
        fvg_bottom=100.0,
        fvg_c2_index=0,
        fvg_ote_conflict=False,
        fvg_ote_distance_ticks=None,
        entry_price=entry,
        ote_level_pct=0.705,
        entry_fill_index=fill_idx,
        entry_fill_timestamp=ts,
        stop_arm_a=stop,
        stop_arm_b=stop - 1.0,
        stop_price=stop,
        target_nearest=target,
        target_nearest_kind="fractal_high",
        target_far=target + 5.0,
        target_far_kind="pdh",
        target_price=target,
        signal_index=0,
        signal_timestamp=ts,
    )


def test_hand_trace_matches_m4_target_exit() -> None:
    cfg = ote_research_backtest_config()
    sess = _bars([(100.0, 101.0, 99.8, 100.2), (100.2, 102.0, 100.0, 101.5)])
    setup = _make_setup(entry=100.0, stop=99.0, target=102.0, fill_idx=1)
    hand = hand_trace_setup(setup, sess, config=cfg)
    m4 = execute_setup(setup, sess, config=cfg)
    assert hand is not None
    assert m4 is not None
    assert hand.net_pnl == pytest.approx(m4.net_pnl, abs=0.02)
    assert hand.gross_pnl == pytest.approx(m4.gross_pnl, abs=0.02)
