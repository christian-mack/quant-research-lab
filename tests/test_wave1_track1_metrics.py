"""Smoke tests for Wave 1 Stage 1 Track 1 coarse screening metrics."""

from __future__ import annotations

import datetime as dt

from quant_research.research_wave1.track1_metrics import TradeRow, evaluate_gates


def test_evaluate_gates_empty_trade_list_fails() -> None:
    gr = evaluate_gates([])
    assert gr.gate1_pass is False
    assert gr.overall_survives is False


def test_gate_boolean_types_are_native_python() -> None:
    """Regression: JSON serialization must not see numpy.bool_."""
    gr = evaluate_gates([])
    assert type(gr.gate4_pass) is bool


def test_trade_row_exit_reason_default() -> None:
    t = TradeRow(
        exit_et_date=dt.date(2025, 1, 2),
        cme_session_date=dt.date(2025, 1, 2),
        pnl_usd_qty1=1.0,
        gross_points=0.5,
    )
    assert t.exit_reason == ""
