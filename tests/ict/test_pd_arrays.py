"""Tests for :mod:`quant_research.ict.pd_arrays` (Primitive 1 — PDH/PDL/EQ)."""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import polars as pl
import pytest

from quant_research.ict.pd_arrays import (
    PDH_COL,
    PDL_COL,
    PRIOR_EQ_COL,
    add_pd_arrays,
    daily_pd_arrays,
)

CT = ZoneInfo("America/Chicago")


def _daily_bars() -> pl.DataFrame:
    """Three hand-constructed sessions, one bar each, with known H/L.

    Uses an explicit ``cme_session_date`` so the test does not depend on the
    PMC calendar (session-date assignment is tested separately in the data
    package). Day 1 H/L = 110/90, Day 2 = 120/100, Day 3 = 105/95.
    """
    return pl.DataFrame(
        {
            "cme_session_date": [
                dt.date(2024, 6, 10),
                dt.date(2024, 6, 11),
                dt.date(2024, 6, 12),
            ],
            "timestamp": [
                dt.datetime(2024, 6, 10, 9, 0, tzinfo=CT),
                dt.datetime(2024, 6, 11, 9, 0, tzinfo=CT),
                dt.datetime(2024, 6, 12, 9, 0, tzinfo=CT),
            ],
            "open": [100.0, 105.0, 102.0],
            "high": [110.0, 120.0, 105.0],
            "low": [90.0, 100.0, 95.0],
            "close": [108.0, 118.0, 100.0],
        }
    )


def test_daily_pd_arrays_known_values() -> None:
    """PDH/PDL/EQ equal the previous session's high/low and their midpoint."""
    out = daily_pd_arrays(_daily_bars()).sort("cme_session_date")
    # Day 1: no prior day -> nulls.
    assert out[PDH_COL][0] is None
    assert out[PDL_COL][0] is None
    assert out[PRIOR_EQ_COL][0] is None
    # Day 2: prior = Day 1 (110/90) -> eq 100.
    assert out[PDH_COL][1] == pytest.approx(110.0)
    assert out[PDL_COL][1] == pytest.approx(90.0)
    assert out[PRIOR_EQ_COL][1] == pytest.approx(100.0)
    # Day 3: prior = Day 2 (120/100) -> eq 110.
    assert out[PDH_COL][2] == pytest.approx(120.0)
    assert out[PDL_COL][2] == pytest.approx(100.0)
    assert out[PRIOR_EQ_COL][2] == pytest.approx(110.0)


def test_daily_pd_arrays_aggregates_intraday_to_day_ohlc() -> None:
    """Multiple bars per session aggregate to first-open/max-high/min-low/last-close."""
    rows = []
    # Session A: opens 100, high 115, low 95, closes 110.
    for t, o, h, low_, c in [
        (dt.time(8, 30), 100.0, 105.0, 99.0, 104.0),
        (dt.time(9, 0), 104.0, 115.0, 95.0, 112.0),
        (dt.time(9, 30), 112.0, 113.0, 108.0, 110.0),
    ]:
        rows.append(
            {
                "cme_session_date": dt.date(2024, 6, 10),
                "timestamp": dt.datetime.combine(dt.date(2024, 6, 10), t, CT),
                "open": o,
                "high": h,
                "low": low_,
                "close": c,
            }
        )
    # Session B: just one bar to receive A's prior levels.
    rows.append(
        {
            "cme_session_date": dt.date(2024, 6, 11),
            "timestamp": dt.datetime.combine(dt.date(2024, 6, 11), dt.time(8, 30), CT),
            "open": 110.0,
            "high": 120.0,
            "low": 109.0,
            "close": 118.0,
        }
    )
    out = daily_pd_arrays(pl.DataFrame(rows)).sort("cme_session_date")
    assert out["day_open"][0] == pytest.approx(100.0)
    assert out["day_high"][0] == pytest.approx(115.0)
    assert out["day_low"][0] == pytest.approx(95.0)
    assert out["day_close"][0] == pytest.approx(110.0)
    # Session B prior-day levels come from session A aggregate.
    assert out[PDH_COL][1] == pytest.approx(115.0)
    assert out[PDL_COL][1] == pytest.approx(95.0)
    assert out[PRIOR_EQ_COL][1] == pytest.approx((115.0 + 95.0) / 2.0)


def test_add_pd_arrays_joins_levels_to_every_bar() -> None:
    """Every intraday bar carries its session's prior-day levels; row count preserved."""
    bars = _daily_bars()
    # Duplicate each session into two intraday bars.
    bars2 = pl.concat(
        [
            bars,
            bars.with_columns(
                pl.col("timestamp") + pl.duration(minutes=1),
                pl.col("high") - 1.0,
                pl.col("low") + 1.0,
            ),
        ]
    ).sort("timestamp")
    out = add_pd_arrays(bars2)
    assert out.height == bars2.height
    # Both Day 2 bars get PDH=110, PDL=90.
    day2 = out.filter(pl.col("cme_session_date") == dt.date(2024, 6, 11))
    assert day2[PDH_COL].to_list() == [pytest.approx(110.0)] * day2.height
    assert day2[PDL_COL].to_list() == [pytest.approx(90.0)] * day2.height


def test_first_day_has_null_prior_levels() -> None:
    """First-day-of-data edge case: no prior session -> null reference levels."""
    out = daily_pd_arrays(_daily_bars()).sort("cme_session_date")
    first = out.row(0, named=True)
    assert first[PDH_COL] is None and first[PDL_COL] is None and first[PRIOR_EQ_COL] is None


def test_null_session_date_bars_dropped_from_aggregation() -> None:
    """Bars with a null session date (break/weekend/holiday) are not aggregated."""
    rows = _daily_bars().to_dicts()
    rows.append(
        {
            "cme_session_date": None,
            "timestamp": dt.datetime(2024, 6, 11, 16, 30, tzinfo=CT),
            "open": 999.0,
            "high": 999.0,
            "low": 999.0,
            "close": 999.0,
        }
    )
    out = daily_pd_arrays(pl.DataFrame(rows, schema_overrides={"cme_session_date": pl.Date}))
    # The 999 break bar must not appear and must not corrupt any day's high.
    assert out["day_high"].max() == pytest.approx(120.0)
    assert out.height == 3


def test_missing_price_columns_raises() -> None:
    df = pl.DataFrame({"cme_session_date": [dt.date(2024, 6, 10)], "timestamp": [None]})
    with pytest.raises(ValueError, match="missing required price columns"):
        daily_pd_arrays(df)
