"""Tests for OTE execution via M4 BacktestEngine."""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import polars as pl
import pytest

from quant_research.backtest.geometry import GeometryReject
from quant_research.ict.liquidity_sweep import SIDE_LOW, detect_sweep
from quant_research.backtest.specs import (
    BacktestConfig,
    FillModelSpec,
    IntradaySessionHygieneSpec,
    LimitFillMode,
    SessionSpec,
    StopLimitIntrabarPolicy,
)
from quant_research.ict.ote_execution import execute_setup, ote_research_backtest_config
from quant_research.ict.ote_strategy import (
    DIRECTION_LONG,
    OteSetup,
    OteStrategyConfig,
    build_setup_from_sweep,
)

CT = ZoneInfo("America/Chicago")
SESSION = dt.date(2024, 6, 10)
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
            "cme_session_date": [SESSION] * len(rows),
            "volume": [100.0] * len(rows),
        }
    )


def _long_sequence() -> pl.DataFrame:
    return _bars(
        [
            (108.0, 111.0, 107.5, 110.0),
            (110.0, 113.0, 109.0, 112.0),
            (112.0, 105.0, 111.5, 104.0),
            (104.0, 106.0, 103.5, 105.5),
            (105.5, 104.5, 104.0, 104.5),
            (104.5, 104.5, 96.0, 97.0),
            (97.0, 99.0, 96.5, 101.0),
            (101.0, 110.0, 100.5, 108.0),
            (108.0, 109.0, 101.5, 107.0),
            (107.0, 108.0, 104.0, 105.0),
            (105.0, 106.0, 103.0, 104.0),
        ]
    )


def _make_setup(
    *,
    entry: float = 100.0,
    stop: float = 99.0,
    target: float = 102.0,
    fill_idx: int = 0,
) -> OteSetup:
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


def _hand_trace_config() -> BacktestConfig:
    return BacktestConfig(
        fill_model=FillModelSpec(
            stop_limit_intrabar=StopLimitIntrabarPolicy.STOP_BEFORE_TARGET,
            limit_fill_mode=LimitFillMode.TOUCH,
            same_bar_exit_after_entry=True,
        ),
        session=SessionSpec(
            intraday_hygiene=IntradaySessionHygieneSpec(enabled=False),
        ),
        enforce_trade_geometry=True,
    )


def test_incoherent_setup_rejected_not_booked() -> None:
    setup = _make_setup(entry=100.0, stop=100.5, target=103.0)
    sess = _bars([(100.0, 101.0, 99.5, 100.5), (100.5, 102.0, 100.0, 101.5)])
    outcome = execute_setup(setup, sess)
    assert isinstance(outcome, GeometryReject)
    assert outcome.reason == "stop_wrong_side"


def test_long_target_hand_trace() -> None:
    setup = _make_setup(entry=100.0, stop=99.0, target=102.0, fill_idx=1)
    sess = _bars([(100.0, 101.0, 99.8, 100.2), (100.2, 102.0, 100.0, 101.5)])
    trade = execute_setup(setup, sess, config=_hand_trace_config())
    assert trade is not None
    assert trade.exit_price == pytest.approx(102.0)
    assert trade.gross_pnl == pytest.approx(4.0)


def test_long_stop_hand_trace() -> None:
    sess = _bars([(100.0, 100.5, 99.8, 100.2), (100.2, 100.4, 98.5, 99.0)])
    setup = _make_setup(entry=100.0, stop=99.0, target=105.0, fill_idx=1)
    trade = execute_setup(setup, sess, config=_hand_trace_config())
    assert trade is not None
    assert trade.exit_price == pytest.approx(99.0)
    assert trade.gross_pnl == pytest.approx(-2.0)


def test_commission_applied_once_per_round_trip() -> None:
    setup = _make_setup(entry=100.0, stop=99.0, target=102.0, fill_idx=1)
    sess = _bars([(100.0, 101.0, 99.8, 100.2), (100.2, 102.0, 100.0, 101.5)])
    trade = execute_setup(setup, sess, config=ote_research_backtest_config())
    assert trade is not None
    assert trade.commission == pytest.approx(1.98, rel=0.01)


def test_end_to_end_long_setup_via_scan() -> None:
    df = _long_sequence()
    cfg = OteStrategyConfig(tick_size=TICK, rth_only=False)
    sweep = detect_sweep(
        df, level=100.0, side=SIDE_LOW, config=cfg.sweep_config, search_start_index=2
    )
    setup = build_setup_from_sweep(
        df, sweep, config=cfg, session_date=SESSION, pdh=115.0, pdl=90.0
    )
    assert setup is not None
    trade = execute_setup(setup, df, config=_hand_trace_config())
    assert trade is not None
    assert trade.direction == "long"
