"""Synthetic + optional real-data smoke tests for :class:`OrbStrategy`."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo

import polars as pl
import pytest

from quant_research.backtest import (
    BacktestConfig,
    BacktestEngine,
    OrchestrationSpec,
    as_module,
)
from quant_research.modules.orb import (
    OrbParams,
    OrbStrategy,
    production_orb_opt3_funded_params,
)

_CHISAGO = ZoneInfo("America/Chicago")


def _bar_time(d: dt.date, hour: int, minute: int) -> dt.datetime:
    return dt.datetime(d.year, d.month, d.day, hour, minute, tzinfo=_CHISAGO)


def _synthetic_orb_session(*, breakout_close: float) -> pl.DataFrame:
    """One RTH day: 9:30–9:44 ET range (15 bars) builds [90,100] range; breakout at 10:00 ET."""
    d = dt.date(2020, 1, 6)
    rows: list[tuple[dt.datetime, float, float, float, float, float, dt.date]] = []

    # Forming 9:30–9:44 ET == 8:30–8:44 CT: range [90,100]
    for m in range(30, 45):
        ts = _bar_time(d, 8, m)
        rows.append((ts, 95.0, 100.0, 90.0, 95.0, 2000.0, d))

    # 9:45 ET == 8:45 CT — range complete bar
    ts_845 = _bar_time(d, 8, 45)
    rows.append((ts_845, 95.0, 100.0, 90.0, 95.0, 2000.0, d))

    # 10:00 ET == 9:00 CT — breakout long
    ts_1000 = _bar_time(d, 9, 0)
    rows.append(
        (
            ts_1000,
            95.0,
            breakout_close + 0.5,
            94.0,
            breakout_close,
            3000.0,
            d,
        ),
    )

    # Next bars: rise through target 108 (limit uncrossable if open gaps above 108)
    ts2 = _bar_time(d, 9, 1)
    rows.append((ts2, 101.0, 104.0, 100.5, 103.0, 2000.0, d))

    ts3 = _bar_time(d, 9, 2)
    rows.append((ts3, 103.0, 109.0, 102.0, 108.5, 1500.0, d))

    return pl.DataFrame(
        rows,
        schema=[
            "timestamp",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "cme_session_date",
        ],
        orient="row",
    )


def _two_session_carry_break_even() -> pl.DataFrame:
    """Day1 long near close; day2 first bar triggers BE; second bar hits BE stop."""
    d1 = dt.date(2020, 1, 6)
    d2 = dt.date(2020, 1, 7)
    rows: list[tuple] = []

    for m in range(30, 45):
        ts = _bar_time(d1, 8, m)
        rows.append((ts, 95.0, 100.0, 90.0, 95.0, 2000.0, d1))
    rows.append((_bar_time(d1, 8, 45), 95.0, 100.0, 90.0, 95.0, 2000.0, d1))
    rows.append((_bar_time(d1, 9, 0), 95.0, 101.5, 94.0, 101.0, 3000.0, d1))
    for minute, cl in [(1, 103.0), (2, 104.0), (3, 106.0)]:
        rows.append((_bar_time(d1, 9, minute), cl - 1.0, cl + 1.0, cl - 2.0, cl, 1200.0, d1))

    rows.append((_bar_time(d2, 8, 30), 106.0, 118.0, 106.0, 117.0, 4000.0, d2))
    rows.append((_bar_time(d2, 8, 31), 105.0, 105.0, 97.0, 99.0, 5000.0, d2))

    return pl.DataFrame(
        rows,
        schema=[
            "timestamp",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "cme_session_date",
        ],
        orient="row",
    )


def test_orb_cross_session_position_break_even_regression() -> None:
    """M6: break-even must run after cme_session_date change while position is open."""
    p = OrbParams(
        quantity=1,
        latest_entry_hour_et=11,
        earliest_entry_hour_et=10,
        enable_break_even=True,
        be_trigger_r=1.0,
        enable_vwap_filter=False,
        target_multiplier=3.0,
    )
    strat = OrbStrategy(p)
    bars = _two_session_carry_break_even()
    orch = OrchestrationSpec(module_ids=("orb",), one_position_at_a_time=True)
    cfg = BacktestConfig(orchestration=orch)
    out = BacktestEngine(cfg).run(bars, [as_module("orb", strat)])

    assert out.trade_log.height == 1
    row = out.trade_log.row(0, named=True)
    assert row["direction"] == "long"
    d2 = dt.date(2020, 1, 7)
    exit_day = row["exit_time"].astimezone(_CHISAGO).date()
    assert exit_day == d2
    assert row["exit_price"] >= 100.0
    assert row["exit_reason"] in ("orb_exit_stop", "orb_break_even")


def test_orb_synthetic_long_round_trip() -> None:
    p = OrbParams(
        quantity=1,
        latest_entry_hour_et=11,
        earliest_entry_hour_et=10,
        enable_break_even=False,
        enable_vwap_filter=False,
    )
    strat = OrbStrategy(p)
    bars = _synthetic_orb_session(breakout_close=101.0)
    orch = OrchestrationSpec(module_ids=("orb",), one_position_at_a_time=True)
    cfg = BacktestConfig(orchestration=orch)
    out = BacktestEngine(cfg).run(bars, [as_module("orb", strat)])

    assert out.trade_log.height >= 1
    row = out.trade_log.row(0, named=True)
    assert row["module_id"] == "orb"
    assert row["direction"] == "long"
    assert row["quantity"] == 1
    assert row["exit_reason"] == "orb_exit_target"
    assert row["net_pnl"] != pytest.approx(0.0)
    # Target ~108 from range math; positive PnL on winner
    assert row["gross_pnl"] > 0


def test_production_params_factory() -> None:
    p = production_orb_opt3_funded_params()
    assert p.quantity == 3
    assert p.latest_entry_hour_et == 11


@pytest.mark.parametrize(
    "data_root",
    [Path(__file__).resolve().parents[2] / "data" / "raw"],
)
def test_orb_real_mnq_smoke_small_slice(data_root: Path) -> None:
    contracts = sorted(data_root.glob("MNQ *.Last.txt"))
    if not contracts:
        pytest.skip("No MNQ raw files under data/raw (gitignored)")

    from quant_research.data import continuous_contract, data_loader, session

    raw = data_loader.load_all_contracts(data_root)
    cont = continuous_contract.build_continuous_contract(raw)
    cls = session.classify_sessions(cont)
    dated = session.assign_cme_session_date(cls)
    rth = dated.filter(pl.col("session") == session.SESSION_RTH).head(15_000)
    if rth.height < 500:
        pytest.skip("Insufficient RTH rows after filter")

    strat = OrbStrategy(production_orb_opt3_funded_params())
    orch = OrchestrationSpec(module_ids=("orb",), one_position_at_a_time=True)
    out = BacktestEngine(BacktestConfig(orchestration=orch)).run(
        rth,
        [as_module("orb", strat)],
    )

    assert isinstance(out.fills, list)
    for f in out.fills:
        assert f.module_id == "orb"
    if out.trade_log.height > 0:
        tr = out.trade_log
        assert (tr["quantity"] > 0).all()
        assert (tr["exit_reason"].str.len_chars() > 0).all()
        assert (tr["bars_held"] >= 0).all()
