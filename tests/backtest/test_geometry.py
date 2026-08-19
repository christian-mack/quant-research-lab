"""Tests for trade geometry invariants."""

from __future__ import annotations

import pytest

from quant_research.backtest.geometry import (
    REJECT_STOP_WRONG_SIDE,
    REJECT_TARGET_WRONG_SIDE,
    GeometryError,
    check_trade_geometry,
    validate_trade_geometry,
)


def test_long_stop_wrong_side_rejected() -> None:
    reject = check_trade_geometry("long", 100.0, 100.5, 105.0)
    assert reject is not None
    assert reject.reason == REJECT_STOP_WRONG_SIDE


def test_short_target_wrong_side_rejected() -> None:
    reject = check_trade_geometry("short", 100.0, 101.0, 100.5)
    assert reject is not None
    assert reject.reason == REJECT_TARGET_WRONG_SIDE


def test_coherent_long_accepted() -> None:
    assert check_trade_geometry("long", 100.0, 99.0, 105.0) is None


def test_coherent_short_accepted() -> None:
    assert check_trade_geometry("short", 100.0, 101.0, 95.0) is None


def test_audit_t5_geometry_raises() -> None:
    with pytest.raises(GeometryError) as exc:
        validate_trade_geometry("long", 100.0, 100.5, 103.0)
    assert exc.value.reject.reason == REJECT_STOP_WRONG_SIDE


def test_long_target_wrong_side() -> None:
    reject = check_trade_geometry("long", 100.0, 99.0, 99.5)
    assert reject is not None
    assert reject.reason == REJECT_TARGET_WRONG_SIDE
