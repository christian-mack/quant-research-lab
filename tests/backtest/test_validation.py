"""Tests for standing backtest validation harness (V1–V7)."""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import polars as pl

from quant_research.backtest.geometry import check_trade_geometry
from quant_research.backtest.provenance import M4_ENGINE_PROVENANCE_MARKER
from quant_research.backtest.schema import trade_log_schema
from quant_research.backtest.specs import (
    BacktestConfig,
    CommissionSpec,
    SlippageMode,
    SlippageSpec,
)
from quant_research.backtest.validation import (
    ValidationThresholds,
    validate_backtest_result,
)

CT = ZoneInfo("America/Chicago")
TICK_VAL = 0.5


def _row(**kwargs: object) -> dict[str, object]:
    base: dict[str, object] = {
        "trade_id": 1,
        "module_id": "test",
        "entry_time": dt.datetime(2024, 1, 1, 14, 0, tzinfo=CT),
        "exit_time": dt.datetime(2024, 1, 1, 15, 0, tzinfo=CT),
        "direction": "long",
        "quantity": 1,
        "entry_price": 100.0,
        "stop_price": 99.0,
        "target_price": 102.0,
        "exit_price": 102.0,
        "gross_pnl": 4.0,
        "commission": 1.98,
        "net_pnl": 2.02,
        "exit_reason": "target",
        "entry_bar": 0,
        "bars_held": 1,
        "mfa_git_sha": "",
        "mfa_engine_provenance": M4_ENGINE_PROVENANCE_MARKER,
    }
    base.update(kwargs)
    return base


def _log(*rows: dict[str, object]) -> pl.DataFrame:
    return pl.DataFrame(list(rows), schema=trade_log_schema())


def _cfg(*, commission: float = 0.99) -> BacktestConfig:
    return BacktestConfig(
        commission=CommissionSpec(per_contract_per_fill=commission),
        slippage=SlippageSpec(mode=SlippageMode.NONE),
        enforce_trade_geometry=True,
    )


def test_v1_fails_on_incoherent_filled_trades() -> None:
    log = _log(
        _row(
            entry_price=100.0,
            exit_price=100.5,
            gross_pnl=1.0,
            exit_reason="stop",
            stop_price=100.5,
            target_price=103.0,
        )
    )
    report = validate_backtest_result(log, config=_cfg(), run_spot_checks=False)
    v1 = next(c for c in report.checks if c.check_id == "V1")
    assert not v1.passed


def test_v1_passes_clean_log() -> None:
    log = _log(
        _row(
            stop_price=99.0,
            target_price=102.0,
        )
    )
    report = validate_backtest_result(log, config=_cfg(), run_spot_checks=False)
    v1 = next(c for c in report.checks if c.check_id == "V1")
    assert v1.passed


def test_v1_passes_clean_booked_log_despite_high_upstream_reject_rate() -> None:
    """Scan reject rate is informational when bracket columns prove booked log clean."""
    log = _log(_row(stop_price=99.0, target_price=102.0))
    report = validate_backtest_result(
        log,
        config=_cfg(),
        geometry_reject_rate=0.65,
        run_spot_checks=False,
    )
    v1 = next(c for c in report.checks if c.check_id == "V1")
    assert v1.passed
    assert "booked population clean" in v1.message


def test_v2_fails_exit_before_entry() -> None:
    log = _log(
        _row(
            entry_time=dt.datetime(2024, 1, 1, 15, 0, tzinfo=CT),
            exit_time=dt.datetime(2024, 1, 1, 14, 0, tzinfo=CT),
        )
    )
    report = validate_backtest_result(log, config=_cfg(), run_spot_checks=False)
    v2 = next(c for c in report.checks if c.check_id == "V2")
    assert not v2.passed


def test_v3_fails_zero_commission_when_configured() -> None:
    log = _log(_row(commission=0.0, net_pnl=4.0))
    report = validate_backtest_result(log, config=_cfg(), run_spot_checks=False)
    v3 = next(c for c in report.checks if c.check_id == "V3")
    assert not v3.passed


def test_v4_fires_on_fvg_artifact_magnitude() -> None:
    """FVG-only step-3 class: ~45 net ticks/trade should trip V4."""
    log = _log(
        _row(
            gross_pnl=50.0,
            commission=1.98,
            net_pnl=45.0,
            stop_price=99.0,
            target_price=150.0,
        )
    )
    th = ValidationThresholds(implausible_net_ticks_per_trade=15.0)
    report = validate_backtest_result(log, config=_cfg(), run_spot_checks=False, thresholds=th)
    v4 = next(c for c in report.checks if c.check_id == "V4")
    assert not v4.passed
    assert v4.details["avg_net_ticks"] > 15


def test_fvg_artifact_log_trips_v1_and_v4() -> None:
    log = _log(
        _row(
            entry_price=100.0,
            exit_price=100.5,
            gross_pnl=50.0,
            net_pnl=48.0,
            commission=1.98,
            exit_reason="stop",
            stop_price=100.5,
            target_price=110.0,
        )
    )
    report = validate_backtest_result(log, config=_cfg(), run_spot_checks=False)
    failed = {c.check_id for c in report.failed_checks}
    assert "V1" in failed
    assert "V4" in failed


def test_clean_log_all_pass_except_optional_v6() -> None:
    log = _log(
        _row(
            stop_price=99.0,
            target_price=102.0,
            gross_pnl=4.0,
            net_pnl=2.02,
            commission=1.98,
        )
    )
    report = validate_backtest_result(log, config=_cfg(), run_spot_checks=True)
    for c in report.checks:
        if c.check_id == "V6":
            continue
        assert c.passed, c.message


def test_v7_fails_fabricated_log_without_marker() -> None:
    row = _row(mfa_engine_provenance="")
    log = _log(row)
    report = validate_backtest_result(log, config=_cfg(), run_spot_checks=False)
    v7 = next(c for c in report.checks if c.check_id == "V7")
    assert not v7.passed
    assert v7.details["offending_trade_ids"] == [1]


def test_v7_fails_missing_provenance_column() -> None:
    row = _row()
    del row["mfa_engine_provenance"]
    log = pl.DataFrame([row])
    report = validate_backtest_result(log, config=_cfg(), run_spot_checks=False)
    v7 = next(c for c in report.checks if c.check_id == "V7")
    assert not v7.passed
    assert "Missing mfa_engine_provenance" in v7.message


def test_v7_fails_mixed_provenance_log() -> None:
    log = _log(
        _row(trade_id=1, mfa_engine_provenance=M4_ENGINE_PROVENANCE_MARKER),
        _row(
            trade_id=2,
            entry_time=dt.datetime(2024, 1, 2, 14, 0, tzinfo=CT),
            exit_time=dt.datetime(2024, 1, 2, 15, 0, tzinfo=CT),
            mfa_engine_provenance="bespoke_walker",
        ),
    )
    report = validate_backtest_result(log, config=_cfg(), run_spot_checks=False)
    v7 = next(c for c in report.checks if c.check_id == "V7")
    assert not v7.passed
    assert v7.details["offending_trade_ids"] == [2]


def test_v7_passes_marked_log() -> None:
    log = _log(_row())
    report = validate_backtest_result(log, config=_cfg(), run_spot_checks=False)
    v7 = next(c for c in report.checks if c.check_id == "V7")
    assert v7.passed


def test_m4_engine_trade_log_passes_v7() -> None:
    from datetime import UTC, datetime

    from quant_research.backtest import BacktestConfig, BacktestEngine, as_module
    from quant_research.backtest.types import BarContext, OrderRequest, OrderSide, OrderType

    class _RoundTrip:
        def on_bar(self, ctx: BarContext) -> list[OrderRequest]:
            if ctx.bar_index == 0:
                return [OrderRequest(OrderSide.BUY, 1, OrderType.MARKET, module_id="m")]
            if ctx.bar_index == 1:
                return [OrderRequest(OrderSide.SELL, 1, OrderType.MARKET, module_id="m")]
            return []

    bars = pl.DataFrame(
        {
            "timestamp": [datetime(2020, 1, 2, tzinfo=UTC)] * 3,
            "open": [100.0, 100.5, 101.0],
            "high": [100.25, 100.75, 101.25],
            "low": [99.75, 100.25, 100.75],
            "close": [100.0, 100.5, 101.0],
            "volume": [1.0, 1.0, 1.0],
        }
    )
    out = BacktestEngine(BacktestConfig()).run(bars, [as_module("m", _RoundTrip())])
    assert out.validation_report is not None
    v7 = next(c for c in out.validation_report.checks if c.check_id == "V7")
    assert v7.passed
    assert out.trade_log.row(0, named=True)["mfa_engine_provenance"] == M4_ENGINE_PROVENANCE_MARKER


def test_geometry_guard_same_decision_regardless_of_future_path() -> None:
    """A1: identical entry-time inputs -> identical reject decision."""
    params = ("long", 100.0, 100.5, 103.0)
    r1 = check_trade_geometry(*params)
    r2 = check_trade_geometry(*params)
    assert r1 == r2
    assert r1 is not None
    assert r1.reason == "stop_wrong_side"
    coherent = ("long", 100.0, 99.0, 102.0)
    assert check_trade_geometry(*coherent) is None
