"""Tests for :mod:`quant_research.statistics.trade_report`."""

from __future__ import annotations

import datetime as dt

import polars as pl

from quant_research.statistics.bootstrap import BootstrapConfig
from quant_research.statistics.trade_report import (
    DeflatedSharpeRunParams,
    research_report_to_dict,
    trade_log_research_report,
)


def test_report_contains_bootstrap_and_split() -> None:
    base = dt.datetime(2021, 6, 1, tzinfo=dt.UTC)
    df = pl.DataFrame(
        {
            "exit_time": [base + dt.timedelta(days=i) for i in range(40)],
            "net_pnl": [10.0 if i % 2 == 0 else -4.0 for i in range(40)],
        },
    )
    rep = trade_log_research_report(
        df,
        strategy_label="unit",
        bootstrap_config=BootstrapConfig(n_iterations=200, confidence_level=0.9, random_seed=0),
        deflated_sharpe_params=DeflatedSharpeRunParams(
            n_trials=20,
            variance_across_trials=0.02**2,
        ),
    )
    d = research_report_to_dict(rep)
    assert d["performance"]["n_trades"] == 40
    assert "pnl_total_ci" in d["bootstrap"]
    assert d["deflated_sharpe"] is not None
    assert d["is_oos"]["is_trades"] + d["is_oos"]["oos_trades"] == 40
