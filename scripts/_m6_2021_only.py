"""Run ORB on 2021 RTH only — diagnostic."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo

import polars as pl

from quant_research.backtest import (
    BacktestConfig,
    BacktestEngine,
    OrchestrationSpec,
    as_module,
)
from quant_research.data import continuous_contract, data_loader, session
from quant_research.modules import OrbStrategy, production_orb_opt3_funded_params

_CHI = ZoneInfo("America/Chicago")


def main() -> None:
    root = Path(__file__).resolve().parent.parent / "data" / "raw"
    raw = data_loader.load_all_contracts(root)
    cont = continuous_contract.build_continuous_contract(raw)
    cls = session.classify_sessions(cont)
    dated = session.assign_cme_session_date(cls)
    rth = dated.filter(pl.col("session") == session.SESSION_RTH)
    ts0 = dt.datetime(2021, 1, 1, tzinfo=_CHI)
    ts1 = dt.datetime(2022, 1, 1, tzinfo=_CHI)
    window = rth.filter((pl.col("timestamp") >= ts0) & (pl.col("timestamp") < ts1))
    out = BacktestEngine(
        BacktestConfig(
            orchestration=OrchestrationSpec(module_ids=("orb",), one_position_at_a_time=True),
        ),
    ).run(window, [as_module("orb", OrbStrategy(production_orb_opt3_funded_params()))])
    tl = out.trade_log
    msg = f"bars={window.height} trades={tl.height} net={tl['net_pnl'].sum() if tl.height else 0}\n"
    out_path = Path(__file__).resolve().parent.parent / "._m6_2021.txt"
    out_path.write_text(msg, encoding="utf-8")


if __name__ == "__main__":
    main()
