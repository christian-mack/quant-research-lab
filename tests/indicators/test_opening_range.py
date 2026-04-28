"""Tests for :mod:`quant_research.indicators.opening_range`."""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import polars as pl
import pytest

from quant_research.data import session
from quant_research.indicators.opening_range import add_opening_range


def test_opening_range_first_30_min_rth() -> None:
    """Synthetic RTH-only bars: OR high/low equals max/min over 08:30-09:00."""
    z = ZoneInfo("America/Chicago")
    day = dt.date(2024, 6, 10)
    times = [dt.datetime.combine(day, dt.time(8, 30), z)]
    for m in range(1, 45):
        times.append(dt.datetime.combine(day, dt.time(8, 30), z) + dt.timedelta(minutes=m))
    highs = [float(i) for i in range(len(times))]
    lows = [h - 0.5 for h in highs]
    df = pl.DataFrame(
        {
            "timestamp": times,
            "high": highs,
            "low": lows,
        }
    )
    df = session.classify_sessions(df)
    out = add_opening_range(df, duration_minutes=30)
    assert out["or_high"][0] == pytest.approx(max(highs[:30]))
    assert out["or_low"][0] == pytest.approx(min(lows[:30]))


def test_opening_range_duration_invalid() -> None:
    df = pl.DataFrame(
        {
            "timestamp": [dt.datetime(2024, 6, 10, 8, 31, tzinfo=ZoneInfo("America/Chicago"))],
            "high": [1.0],
            "low": [0.5],
        }
    )
    with pytest.raises(ValueError, match="duration"):
        add_opening_range(df, duration_minutes=0)


def test_opening_range_missing_columns() -> None:
    df = pl.DataFrame({"timestamp": []}).cast(pl.Datetime("us", "America/Chicago"))
    with pytest.raises(ValueError, match="missing"):
        add_opening_range(df.with_columns(pl.Series("high", [], dtype=pl.Float64)))
