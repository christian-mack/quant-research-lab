"""Tests for :mod:`quant_research.indicators.vwap`."""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import numpy as np
import polars as pl
import pytest

from quant_research.data import continuous_contract, data_loader, session
from quant_research.indicators.vwap import add_session_vwap, typical_price_expr

_Z = ZoneInfo("America/Chicago")


def test_typical_price_expr() -> None:
    df = pl.DataFrame({"high": [3.0], "low": [1.0], "close": [2.0]})
    v = df.with_columns(typical_price_expr().alias("tp"))["tp"][0]
    assert v == pytest.approx(2.0)


def test_session_vwap_hand_computed_two_sessions() -> None:
    """Hand arithmetic for TP×V cumulative; two distinct ``cme_session_date`` groups."""
    ts = [
        dt.datetime(2024, 3, 4, 9, 0, tzinfo=_Z),
        dt.datetime(2024, 3, 4, 9, 1, tzinfo=_Z),
        dt.datetime(2024, 3, 4, 9, 2, tzinfo=_Z),
        dt.datetime(2024, 3, 5, 9, 0, tzinfo=_Z),
    ]
    df = pl.DataFrame(
        {
            "timestamp": ts,
            "high": [10.0, 11.0, 12.0, 100.0],
            "low": [9.0, 10.0, 11.0, 99.0],
            "close": [9.5, 10.5, 11.5, 99.5],
            "volume": [100, 200, 100, 50],
        }
    )
    df = session.assign_cme_session_date(df)
    out = add_session_vwap(df, session_date_col="cme_session_date")
    tp0 = (10 + 9 + 9.5) / 3
    tp1 = (11 + 10 + 10.5) / 3
    tp2 = (12 + 11 + 11.5) / 3
    assert out["session_vwap"][0] == pytest.approx(tp0)
    assert out["session_vwap"][1] == pytest.approx((tp0 * 100 + tp1 * 200) / 300)
    assert out["session_vwap"][2] == pytest.approx((tp0 * 100 + tp1 * 200 + tp2 * 100) / 400)
    tp_s2 = (100 + 99 + 99.5) / 3
    assert out["session_vwap"][3] == pytest.approx(tp_s2)


def test_session_vwap_missing_volume_raises() -> None:
    df = pl.DataFrame(
        {
            "timestamp": [dt.datetime(2024, 3, 4, 9, 0, tzinfo=_Z)],
            "high": [1.0],
            "low": [1.0],
            "close": [1.0],
        }
    )
    with pytest.raises(ValueError, match="missing"):
        add_session_vwap(df)


_REAL = data_loader.default_data_root() / "MNQ 03-26.Last.txt"
_REAL_OK = _REAL.is_file()


@pytest.mark.skipif(not _REAL_OK, reason="raw MNQ data not present")
def test_real_session_vwap_matches_numpy_cumsum_per_session() -> None:
    raw = data_loader.load_all_contracts()
    cont = continuous_contract.build_continuous_contract(raw).head(20_000)
    out = add_session_vwap(cont)
    for d in out["cme_session_date"].drop_nulls().unique().to_list()[:5]:
        sl = out.filter(pl.col("cme_session_date") == d).sort("timestamp")
        tp = (
            sl["high"].to_numpy().astype(float)
            + sl["low"].to_numpy().astype(float)
            + sl["close"].to_numpy().astype(float)
        ) / 3.0
        vol = sl["volume"].to_numpy().astype(float)
        exp = (tp * vol).cumsum() / np.maximum(vol.cumsum(), 1e-12)
        got = sl["session_vwap"].to_numpy()
        m = ~np.isnan(got)
        assert np.allclose(got[m], exp[m], rtol=1e-9)
