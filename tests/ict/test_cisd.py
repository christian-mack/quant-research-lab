"""Tests for :mod:`quant_research.ict.cisd` (Primitive 3 — CISD).

Setups are hand-constructed to match the TTrades CISD transcript (``CHIK5oBRKiw``)
worked examples cited in the Bias Module Spec (@47s, @49s, @61s, @80s, @163s).
The load-bearing assertion throughout is "close beyond the OPENING PRICE of the
FIRST opposing-close candle in the series".
"""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import polars as pl
import pytest

from quant_research.ict.cisd import (
    DIRECTION_BEARISH,
    DIRECTION_BULLISH,
    detect_cisd,
)

CT = ZoneInfo("America/Chicago")


def _bars(rows: list[tuple[float, float, float, float]]) -> pl.DataFrame:
    """OHLC bars at 1h spacing from (open, high, low, close) tuples (pairing TF)."""
    base = dt.datetime(2024, 6, 10, 0, 0, tzinfo=CT)
    return pl.DataFrame(
        {
            "timestamp": [base + dt.timedelta(hours=i) for i in range(len(rows))],
            "open": [r[0] for r in rows],
            "high": [r[1] for r in rows],
            "low": [r[2] for r in rows],
            "close": [r[3] for r in rows],
        }
    )


def test_bearish_cisd_single_up_close_candle() -> None:
    """@47–49s: one up-close candle made the high; a close below its open fires."""
    df = _bars(
        [
            (96.0, 96.0, 94.0, 94.0),  # 0 down-close
            (100.0, 106.0, 99.0, 105.0),  # 1 up-close, makes high
            (104.0, 104.0, 97.0, 98.0),  # 2 displacement: close 98 < open[1]=100
        ]
    )
    res = detect_cisd(df, direction=DIRECTION_BEARISH)
    assert res.fired is True
    assert res.cisd_level == pytest.approx(100.0)
    assert res.anchor_index == 1
    assert res.run_start_index == 1 and res.run_end_index == 1
    assert res.fired_index == 2
    assert res.fired_timestamp == df.sort("timestamp")["timestamp"][2]


def test_bearish_cisd_series_uses_first_candle_open() -> None:
    """@80s: with a series of up-close candles, the level is the FIRST candle's open."""
    df = _bars(
        [
            (91.0, 91.0, 88.0, 89.0),  # 0 down-close
            (100.0, 104.0, 99.0, 103.0),  # 1 up-close (first of run) open=100
            (103.0, 107.0, 102.0, 106.0),  # 2 up-close (makes high 107) open=103
            (105.0, 105.0, 96.0, 97.0),  # 3 close 97 < 100 -> fires on FIRST open
        ]
    )
    res = detect_cisd(df, direction=DIRECTION_BEARISH)
    assert res.fired is True
    assert res.cisd_level == pytest.approx(100.0)  # first candle, NOT 103
    assert res.run_start_index == 1 and res.run_end_index == 2
    assert res.fired_index == 3


def test_bearish_cisd_close_between_two_opens_does_not_fire() -> None:
    """Closing below the 2nd candle's open but above the 1st must NOT fire."""
    df = _bars(
        [
            (91.0, 91.0, 88.0, 89.0),  # 0 down-close
            (100.0, 104.0, 99.0, 103.0),  # 1 up-close, first open=100
            (103.0, 107.0, 102.0, 106.0),  # 2 up-close, open=103
            (105.0, 105.0, 100.5, 101.0),  # 3 close 101: < 103 but > 100 -> NO fire
        ]
    )
    res = detect_cisd(df, direction=DIRECTION_BEARISH)
    assert res.fired is False
    assert res.cisd_level == pytest.approx(100.0)
    assert res.run_start_index == 1 and res.run_end_index == 2


def test_bullish_cisd_symmetric() -> None:
    """@61s: down-close run made the low; a close above the first candle's open fires."""
    df = _bars(
        [
            (109.0, 110.0, 108.0, 109.5),  # 0 up-close
            (100.0, 101.0, 96.0, 97.0),  # 1 down-close (first of run) open=100
            (97.0, 98.0, 93.0, 94.0),  # 2 down-close (makes low 93) open=97
            (95.0, 104.0, 95.0, 103.0),  # 3 close 103 > 100 -> fires
        ]
    )
    res = detect_cisd(df, direction=DIRECTION_BULLISH)
    assert res.fired is True
    assert res.cisd_level == pytest.approx(100.0)
    assert res.anchor_index == 2
    assert res.run_start_index == 1 and res.run_end_index == 2
    assert res.fired_index == 3


def test_no_fire_when_price_continues_in_trend() -> None:
    """An up-close run with no subsequent close below the level does not fire."""
    df = _bars(
        [
            (95.0, 95.0, 93.0, 94.0),  # 0 down-close
            (100.0, 106.0, 99.0, 105.0),  # 1 up-close
            (105.0, 111.0, 104.0, 110.0),  # 2 up-close (continues up, no close < 100)
        ]
    )
    res = detect_cisd(df, direction=DIRECTION_BEARISH)
    assert res.fired is False
    assert res.cisd_level == pytest.approx(100.0)  # run still identified
    assert res.run_start_index == 1 and res.run_end_index == 2


def test_close_exactly_at_level_does_not_fire() -> None:
    """Boundary: close == CISD level is not 'strictly below'."""
    df = _bars(
        [
            (95.0, 95.0, 93.0, 94.0),
            (100.0, 106.0, 99.0, 105.0),  # up-close, open=100
            (104.0, 104.0, 99.5, 100.0),  # close == 100 -> not < 100
        ]
    )
    res = detect_cisd(df, direction=DIRECTION_BEARISH)
    assert res.fired is False


def test_bearish_cisd_sweep_wick_high_fallback() -> None:
    """@155–178s: highest high is a sweep (down-close) wick; run excludes it.

    The up-close candle into the high anchors the level; the sweep candle (a
    higher wick that closes lower) is not part of the up-close run.
    """
    df = _bars(
        [
            (95.0, 95.0, 93.0, 94.0),  # 0 down-close
            (100.0, 105.0, 99.0, 104.0),  # 1 up-close into the high, open=100
            (104.0, 108.0, 100.0, 101.0),  # 2 sweep: down-close, highest high (108)
            (101.0, 101.0, 97.0, 98.0),  # 3 close 98 < 100 -> fires
        ]
    )
    res = detect_cisd(df, direction=DIRECTION_BEARISH)
    assert res.anchor_index == 2  # the sweep candle made the highest high
    assert res.run_start_index == 1 and res.run_end_index == 1  # run excludes sweep
    assert res.cisd_level == pytest.approx(100.0)
    assert res.fired is True
    assert res.fired_index == 3


def test_order_block_zone_exposed() -> None:
    """The opposing-close run is the order-block zone (top=max high, bottom=min low)."""
    df = _bars(
        [
            (91.0, 91.0, 88.0, 89.0),
            (100.0, 104.0, 99.0, 103.0),  # 1 high 104, low 99
            (103.0, 107.0, 102.0, 106.0),  # 2 high 107, low 102
            (105.0, 105.0, 96.0, 97.0),
        ]
    )
    res = detect_cisd(df, direction=DIRECTION_BEARISH)
    assert res.ob_top == pytest.approx(107.0)
    assert res.ob_bottom == pytest.approx(99.0)


def test_anchor_at_last_bar_cannot_fire() -> None:
    """Boundary: if the swing high is the final bar, no subsequent candle to fire."""
    df = _bars(
        [
            (95.0, 95.0, 93.0, 94.0),
            (96.0, 97.0, 95.0, 96.5),
            (100.0, 106.0, 99.0, 105.0),  # last bar makes the high -> no candle after
        ]
    )
    res = detect_cisd(df, direction=DIRECTION_BEARISH)
    assert res.anchor_index == 2
    assert res.fired is False
    assert res.fired_index is None


def test_caller_supplied_anchor_index() -> None:
    """An explicit anchor_index overrides the argmax/argmin auto-selection."""
    df = _bars(
        [
            (95.0, 95.0, 93.0, 94.0),
            (100.0, 104.0, 99.0, 103.0),  # up-close, open=100
            (103.0, 120.0, 102.0, 119.0),  # much higher high; would be argmax
            (105.0, 105.0, 96.0, 97.0),
        ]
    )
    # Force anchor on bar 1 instead of bar 2.
    res = detect_cisd(df, direction=DIRECTION_BEARISH, anchor_index=1)
    assert res.anchor_index == 1
    assert res.run_start_index == 1 and res.run_end_index == 1
    assert res.cisd_level == pytest.approx(100.0)


def test_unsorted_input_is_sorted_by_timestamp() -> None:
    """Out-of-order rows are sorted before indexing so indices are chronological."""
    df = _bars(
        [
            (95.0, 95.0, 93.0, 94.0),
            (100.0, 106.0, 99.0, 105.0),
            (104.0, 104.0, 97.0, 98.0),
        ]
    ).sample(fraction=1.0, shuffle=True, seed=7)
    res = detect_cisd(df, direction=DIRECTION_BEARISH)
    assert res.run_start_index == 1 and res.fired_index == 2


def test_invalid_direction_raises() -> None:
    with pytest.raises(ValueError, match="direction must be"):
        detect_cisd(_bars([(1.0, 1.0, 1.0, 1.0)]), direction="sideways")


def test_missing_columns_raises() -> None:
    df = pl.DataFrame({"timestamp": [], "open": []})
    with pytest.raises(ValueError, match="missing required columns"):
        detect_cisd(df, direction=DIRECTION_BEARISH)
