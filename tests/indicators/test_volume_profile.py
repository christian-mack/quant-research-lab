"""Tests for :mod:`quant_research.indicators.volume_profile`."""

from __future__ import annotations

import polars as pl
import pytest

from quant_research.indicators.volume_profile import volume_profile


def test_volume_profile_two_bins_sums_to_total_volume() -> None:
    df = pl.DataFrame(
        {
            "cme_session_date": ["A", "A", "A", "A"],
            "close": [10.0, 11.0, 12.0, 11.0],
            "volume": [100, 50, 50, 25],
        }
    )
    vp = volume_profile(df, group="cme_session_date", n_bins=2)
    assert set(vp.columns) >= {"cme_session_date", "bin_id", "volume"}
    tot = vp.filter(pl.col("cme_session_date") == "A")["volume"].sum()
    assert tot == 225


def test_volume_profile_requires_columns() -> None:
    df = pl.DataFrame({"x": [1]})
    with pytest.raises(ValueError, match="missing"):
        volume_profile(df, group="cme_session_date")


def test_volume_profile_n_bins_invalid() -> None:
    df = pl.DataFrame({"cme_session_date": [1], "close": [1.0], "volume": [1]})
    with pytest.raises(ValueError, match="n_bins"):
        volume_profile(df, n_bins=0)
