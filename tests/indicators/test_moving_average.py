"""Tests for :mod:`quant_research.indicators.moving_average`."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pandas_ta as ta
import polars as pl
import pytest

from quant_research.data import continuous_contract, data_loader
from quant_research.indicators.moving_average import (
    EMA_DEFAULT_LENGTH,
    SMA_DEFAULT_LENGTH,
    add_ema,
    add_sma,
    ema_expr,
    sma_expr,
)


def _synthetic_close(*, n: int = 1000, seed: int = 11) -> tuple[pl.DataFrame, pd.Series]:
    rng = np.random.default_rng(seed)
    close = 50 + np.cumsum(rng.normal(0, 0.2, size=n))
    return pl.DataFrame({"close": close}), pd.Series(close)


def test_sma_hand_computation() -> None:
    df = pl.DataFrame({"close": [1.0, 2.0, 3.0, 4.0, 5.0]})
    out = add_sma(df, length=3)
    assert out["sma_3"].to_list()[:2] == [None, None]
    assert out["sma_3"][2] == pytest.approx(2.0)
    assert out["sma_3"][3] == pytest.approx(3.0)
    assert out["sma_3"][4] == pytest.approx(4.0)


def test_sma_matches_pandas_ta_no_talib() -> None:
    pldf, s = _synthetic_close()
    ours = add_sma(pldf, length=SMA_DEFAULT_LENGTH)["sma_10"].to_numpy()
    theirs = ta.sma(s, length=SMA_DEFAULT_LENGTH, talib=False).to_numpy()
    mask = ~(np.isnan(theirs) | np.isnan(ours))
    rel = np.abs(ours[mask] - theirs[mask]) / np.maximum(np.abs(theirs[mask]), 1e-12)
    assert rel.max() < 1e-6


def test_ema_matches_pandas_ta_no_talib() -> None:
    pldf, s = _synthetic_close()
    length = EMA_DEFAULT_LENGTH
    ours = add_ema(pldf, length=length)[f"ema_{length}"].to_numpy()
    theirs = ta.ema(s, length=length, talib=False).to_numpy()
    mask = ~(np.isnan(theirs) | np.isnan(ours))
    rel = np.abs(ours[mask] - theirs[mask]) / np.maximum(np.abs(theirs[mask]), 1e-12)
    assert rel.max() < 1e-6
    assert np.array_equal(np.isnan(ours), np.isnan(theirs))


def test_ema_seed_index_matches_sma_of_first_n() -> None:
    pldf, _ = _synthetic_close(n=100)
    length = 10
    out = add_ema(pldf, length=length)
    first_n = pldf["close"].to_numpy()[:length]
    assert out[f"ema_{length}"][: length - 1].is_null().all()
    assert out[f"ema_{length}"][length - 1] == pytest.approx(float(np.mean(first_n)))


def test_sma_expr_length_invalid() -> None:
    with pytest.raises(ValueError, match="length"):
        sma_expr(length=0)


def test_ema_expr_length_invalid() -> None:
    with pytest.raises(ValueError, match="length"):
        ema_expr(length=-1)


def test_add_sma_lazy() -> None:
    pldf, _ = _synthetic_close()
    out = pldf.lazy().with_columns(sma_expr(length=5).alias("x")).collect()
    assert out["x"].null_count() == 4


_REAL = data_loader.default_data_root() / "MNQ 03-26.Last.txt"
_REAL_OK = _REAL.is_file()


@pytest.mark.skipif(not _REAL_OK, reason="raw MNQ data not present")
def test_real_ema_sma_positive() -> None:
    raw = data_loader.load_all_contracts()
    cont = continuous_contract.build_continuous_contract(raw)
    out = add_ema(add_sma(cont, close="close"), close="close")
    assert (out[f"ema_{EMA_DEFAULT_LENGTH}"].drop_nulls() > 0).all()
