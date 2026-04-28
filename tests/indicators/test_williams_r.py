"""Tests for :mod:`quant_research.indicators.williams_r`."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pandas_ta as ta
import polars as pl
import pytest

from quant_research.data import continuous_contract, data_loader
from quant_research.indicators.williams_r import (
    WILLR_DEFAULT_LENGTH,
    add_williams_r,
    williams_r_expr,
)


def _synthetic_hlc(*, n: int = 1000, seed: int = 7) -> tuple[pl.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0, 0.3, size=n))
    high = close + rng.uniform(0.05, 0.5, size=n)
    low = close - rng.uniform(0.05, 0.5, size=n)
    pdf = pd.DataFrame({"high": high, "low": low, "close": close})
    return pl.DataFrame({"high": high, "low": low, "close": close}), pdf


def test_willr_hand_computation() -> None:
    """length=3: compare to pandas-ta on the same small frame (source of truth)."""
    df = pl.DataFrame(
        {
            "high": [10.0, 11.0, 12.0, 11.0],
            "low": [9.0, 10.0, 10.5, 10.0],
            "close": [9.5, 10.5, 11.5, 10.5],
        }
    )
    pdf = df.to_pandas()
    theirs = ta.willr(pdf["high"], pdf["low"], pdf["close"], length=3, talib=False)
    out = add_williams_r(df, length=3)
    for i in range(df.height):
        te = theirs.iloc[i]
        ow = out["willr_3"][i]
        if np.isnan(te):
            assert ow is None
        else:
            assert ow == pytest.approx(te, rel=1e-10)


@pytest.mark.parametrize("length", [5, 14, 30])
def test_willr_matches_pandas_ta_talib_false(length: int) -> None:
    """Cross-check vs pandas-ta ``talib=False`` rolling formula."""
    pldf, pdf = _synthetic_hlc()
    ours = add_williams_r(pldf, length=length)[f"willr_{length}"].to_numpy()
    theirs = ta.willr(pdf["high"], pdf["low"], pdf["close"], length=length, talib=False).to_numpy()
    mask = ~(np.isnan(theirs) | np.isnan(ours))
    rel = np.abs(ours[mask] - theirs[mask]) / np.maximum(np.abs(theirs[mask]), 1e-12)
    assert rel.max() < 1e-6


def test_willr_length_one() -> None:
    df = pl.DataFrame({"high": [5.0], "low": [4.0], "close": [4.5]})
    out = add_williams_r(df, length=1)
    assert out["willr_1"][0] == pytest.approx(100 * ((4.5 - 4.0) / (5.0 - 4.0) - 1))


def test_willr_invalid_length_raises() -> None:
    df = pl.DataFrame({"high": [1.0], "low": [0.0], "close": [0.5]})
    with pytest.raises(ValueError, match="length"):
        add_williams_r(df, length=0)


def test_willr_missing_column_raises() -> None:
    df = pl.DataFrame({"high": [1.0], "close": [0.5]})
    with pytest.raises(ValueError, match="missing"):
        add_williams_r(df)


def test_willr_expr_lazy() -> None:
    pldf, _ = _synthetic_hlc(n=100)
    out = (
        pldf.lazy()
        .with_columns(williams_r_expr(length=10).alias("w"))
        .filter(pl.col("w").is_not_null())
        .collect()
    )
    assert out.height == pldf.height - 9


_REAL = data_loader.default_data_root() / "MNQ 03-26.Last.txt"
_REAL_OK = _REAL.is_file()


@pytest.mark.skipif(not _REAL_OK, reason="raw MNQ data not present")
def test_real_willr_population() -> None:
    raw = data_loader.load_all_contracts()
    cont = continuous_contract.build_continuous_contract(raw)
    out = add_williams_r(cont)
    w = out[f"willr_{WILLR_DEFAULT_LENGTH}"].drop_nulls().to_numpy()
    assert not np.isinf(w).any()
    finite = w[np.isfinite(w)]
    assert finite.size > cont.height * 0.99
    assert finite.min() >= -101.0
    assert finite.max() <= 101.0
