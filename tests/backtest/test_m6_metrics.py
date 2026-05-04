"""Tests for :mod:`quant_research.backtest.m6_metrics`."""

from __future__ import annotations

import datetime as dt

import polars as pl
import pytest

from quant_research.backtest.m6_metrics import compute_m6_aggregates, protocol_year_fraction


def test_compute_m6_aggregates_empty() -> None:
    empty = pl.DataFrame(
        schema={
            "exit_time": pl.Datetime("us", "UTC"),
            "net_pnl": pl.Float64,
        },
    )
    r = compute_m6_aggregates(empty)
    assert r.trade_count == 0
    assert r.net_pnl_total == 0.0
    assert r.win_rate == 0.0
    assert r.max_drawdown == 0.0


def test_compute_m6_aggregates_sorted_drawdown_and_years() -> None:
    """Exit order affects max DD; Chicago exit-year buckets for calendar P&L."""
    base = dt.datetime(2024, 6, 15, 16, 0, tzinfo=dt.UTC)
    # Deliberately unsorted input; function must sort by exit_time
    log = pl.DataFrame(
        {
            "exit_time": [
                base + dt.timedelta(days=2),
                base,
                base + dt.timedelta(days=1),
            ],
            "net_pnl": [50.0, -40.0, -30.0],
        },
    )
    r = compute_m6_aggregates(log, exit_year_tz="America/Chicago")
    assert r.trade_count == 3
    assert r.net_pnl_total == pytest.approx(-20.0)
    assert r.win_rate == pytest.approx(1.0 / 3.0)
    # Cumulative after sort: -40, -70, -20 => largest drop from a running peak is -30
    assert r.max_drawdown == pytest.approx(-30.0)
    assert 2024 in r.years_calendar
    assert r.years_total_count == 1
    assert r.years_positive_count == 0


def test_protocol_year_fraction_inclusive() -> None:
    start = dt.date(2020, 1, 1)
    end = dt.date(2020, 1, 2)
    assert protocol_year_fraction(start, end) == pytest.approx(2 / 365.25)
