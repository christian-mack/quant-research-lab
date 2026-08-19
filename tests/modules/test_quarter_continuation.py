"""Unit tests for H-W4-7 quarter close-location continuation."""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import polars as pl
import pytest

from quant_research.backtest import BacktestEngine, as_module
from quant_research.backtest.validation import validate_backtest_result
from quant_research.modules.quarter_continuation import (
    BLOCK_0200_0600,
    BLOCK_1400_1700,
    BLOCK_1800_2200,
    MODULE_ID,
    QuarterContinuationStrategy,
    close_location,
    completed_quarter_stats,
    holds_cross_maintenance_et,
    qcl_backtest_config,
    qcl_validation_thresholds,
    quarter_block_id_et,
    resample_to_15m_et,
    signal_from_close_location,
    tier_bucket,
)

_ET = ZoneInfo("America/New_York")
_CT = ZoneInfo("America/Chicago")


def _et(y: int, mo: int, d: int, h: int, mi: int) -> dt.datetime:
    return dt.datetime(y, mo, d, h, mi, tzinfo=_ET)


def test_close_location_and_signal() -> None:
    assert close_location(110.0, 120.0, 100.0) == pytest.approx(0.5)
    assert signal_from_close_location(0.5) is None
    assert signal_from_close_location(0.51) == "long"
    assert signal_from_close_location(0.49) == "short"
    assert close_location(100.0, 100.0, 100.0) is None
    assert signal_from_close_location(None) is None
    assert tier_bucket(0.75) == "ge_0.75"
    assert tier_bucket(0.74) == "0.50_to_0.75"
    assert tier_bucket(0.25) == "le_0.25"
    assert tier_bucket(0.26) == "0.25_to_0.50"


def test_quarter_blocks_cover_clock_and_deadzone() -> None:
    assert quarter_block_id_et(_et(2020, 1, 6, 18, 0)) == BLOCK_1800_2200
    assert quarter_block_id_et(_et(2020, 1, 6, 21, 45)) == BLOCK_1800_2200
    assert quarter_block_id_et(_et(2020, 1, 6, 22, 0)) == "22:00-02:00"
    assert quarter_block_id_et(_et(2020, 1, 7, 1, 45)) == "22:00-02:00"
    assert quarter_block_id_et(_et(2020, 1, 7, 2, 0)) == BLOCK_0200_0600
    assert quarter_block_id_et(_et(2020, 1, 7, 14, 0)) == BLOCK_1400_1700
    assert quarter_block_id_et(_et(2020, 1, 7, 16, 45)) == BLOCK_1400_1700
    assert quarter_block_id_et(_et(2020, 1, 6, 17, 0)) is None
    assert quarter_block_id_et(_et(2020, 1, 6, 17, 30)) is None


def test_dst_spring_forward_and_fall_back_block_ids() -> None:
    spring_0145 = _et(2020, 3, 8, 1, 45)
    spring_0300 = dt.datetime(2020, 3, 8, 3, 0, tzinfo=_ET)
    assert quarter_block_id_et(spring_0145) == "22:00-02:00"
    assert quarter_block_id_et(spring_0300) == BLOCK_0200_0600
    ct_0145 = spring_0145.astimezone(_CT)
    assert quarter_block_id_et(ct_0145) == "22:00-02:00"
    fall_first = dt.datetime(2020, 11, 1, 1, 15, tzinfo=_ET)
    assert quarter_block_id_et(fall_first) == "22:00-02:00"
    fall_0215 = _et(2020, 11, 1, 2, 15)
    assert quarter_block_id_et(fall_0215) == BLOCK_0200_0600


def test_resample_15m_left_labeled_et() -> None:
    rows = []
    start = dt.datetime(2020, 1, 6, 17, 0, tzinfo=_CT)
    for i in range(15):
        ts = start + dt.timedelta(minutes=i)
        rows.append((ts, 100.0 + i, 101.0 + i, 99.0, 100.5 + i, 10, dt.date(2020, 1, 7)))
    raw = pl.DataFrame(
        rows,
        schema=["timestamp", "open", "high", "low", "close", "volume", "cme_session_date"],
        orient="row",
    )
    out = resample_to_15m_et(raw)
    assert out.height == 1
    assert out["open"][0] == 100.0
    assert out["high"][0] == pytest.approx(101.0 + 14)
    assert out["close"][0] == pytest.approx(100.5 + 14)
    ts0 = out["timestamp"][0]
    assert ts0.astimezone(_ET).hour == 18
    assert ts0.astimezone(_ET).minute == 0


def test_completed_quarter_stats_signal() -> None:
    sess = dt.date(2020, 1, 7)
    bars = pl.DataFrame(
        {
            "timestamp": [_et(2020, 1, 6, 18, 0), _et(2020, 1, 6, 18, 15)],
            "open": [100.0, 110.0],
            "high": [120.0, 130.0],
            "low": [90.0, 100.0],
            "close": [115.0, 125.0],
            "volume": [1, 1],
            "cme_session_date": [sess, sess],
        }
    )
    stats = completed_quarter_stats(bars)
    assert stats.height == 1
    assert stats["quarter_block"][0] == BLOCK_1800_2200
    assert stats["q_high"][0] == 130.0
    assert stats["q_low"][0] == 90.0
    assert stats["signal"][0] == "long"
    assert stats["tier"][0] == "ge_0.75"


def _bars_for_long_round_trip() -> pl.DataFrame:
    sess = dt.date(2020, 1, 7)
    rows: list[tuple[dt.datetime, float, float, float, float, float, dt.date]] = []
    rows.append((_et(2020, 1, 7, 13, 30), 10050.0, 10100.0, 10000.0, 10040.0, 100.0, sess))
    rows.append((_et(2020, 1, 7, 13, 45), 10040.0, 10100.0, 10020.0, 10080.0, 100.0, sess))
    rows.append((_et(2020, 1, 7, 14, 0), 10080.0, 10090.0, 10070.0, 10082.0, 100.0, sess))
    rows.append((_et(2020, 1, 7, 14, 15), 10082.0, 10090.0, 10075.0, 10085.0, 100.0, sess))
    rows.append((_et(2020, 1, 7, 14, 30), 10085.0, 10140.0, 10080.0, 10135.0, 100.0, sess))
    return pl.DataFrame(
        rows,
        schema=["timestamp", "open", "high", "low", "close", "volume", "cme_session_date"],
        orient="row",
    )


def test_m4_engine_long_hits_target() -> None:
    cfg = qcl_backtest_config()
    strat = QuarterContinuationStrategy()
    engine = BacktestEngine(cfg)
    result = engine.run(
        _bars_for_long_round_trip(),
        [as_module(MODULE_ID, strat)],
        run_validation=False,
    )
    assert result.trade_log.height == 1
    row = result.trade_log.row(0, named=True)
    assert row["direction"] == "long"
    assert row["exit_reason"] == "target"
    assert float(row["entry_price"]) == pytest.approx(10082.0)
    report = validate_backtest_result(
        result.trade_log,
        config=cfg,
        fills=result.fills,
        bars=result.bars,
        thresholds=qcl_validation_thresholds(),
        run_spot_checks=False,
    )
    v_ids = {c.check_id: c.passed for c in report.checks}
    assert v_ids["V1"] is True
    assert v_ids["V3"] is True
    assert v_ids["V7"] is True


def test_skip_when_position_still_open() -> None:
    sess = dt.date(2020, 1, 7)
    rows: list[tuple[dt.datetime, float, float, float, float, float, dt.date]] = []
    rows.append((_et(2020, 1, 7, 9, 30), 10050.0, 10100.0, 10000.0, 10080.0, 1.0, sess))
    rows.append((_et(2020, 1, 7, 9, 45), 10080.0, 10100.0, 10050.0, 10090.0, 1.0, sess))
    rows.append((_et(2020, 1, 7, 10, 0), 10090.0, 10100.0, 10080.0, 10092.0, 1.0, sess))
    rows.append((_et(2020, 1, 7, 10, 15), 10092.0, 10100.0, 10080.0, 10095.0, 1.0, sess))
    rows.append((_et(2020, 1, 7, 10, 30), 10095.0, 10110.0, 10070.0, 10080.0, 1.0, sess))
    rows.append((_et(2020, 1, 7, 13, 45), 10080.0, 10120.0, 10060.0, 10110.0, 1.0, sess))
    rows.append((_et(2020, 1, 7, 14, 0), 10110.0, 10120.0, 10100.0, 10112.0, 1.0, sess))
    df = pl.DataFrame(
        rows,
        schema=["timestamp", "open", "high", "low", "close", "volume", "cme_session_date"],
        orient="row",
    )
    strat = QuarterContinuationStrategy()
    BacktestEngine(qcl_backtest_config()).run(
        df, [as_module(MODULE_ID, strat)], run_validation=False
    )
    assert strat.signal_count >= 1
    assert strat.skip_count >= 1


def test_maintenance_cross_helper() -> None:
    entry = _et(2020, 1, 7, 15, 0)
    exit_before = _et(2020, 1, 7, 16, 30)
    exit_after = _et(2020, 1, 7, 18, 15)
    assert holds_cross_maintenance_et(entry, exit_before) is False
    assert holds_cross_maintenance_et(entry, exit_after) is True
