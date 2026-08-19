"""One-off diagnostic for M6 full-window ORB run (not part of public API)."""

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
    root = Path(__file__).resolve().parents[1] / "data" / "raw"
    raw = data_loader.load_all_contracts(root)
    cont = continuous_contract.build_continuous_contract(raw)
    cls = session.classify_sessions(cont)
    dated = session.assign_cme_session_date(cls)
    rth = dated.filter(pl.col("session") == session.SESSION_RTH)
    ts0 = dt.datetime(2020, 1, 1, tzinfo=_CHI)
    ts1 = dt.datetime(2026, 4, 20, 0, 0, 0, tzinfo=_CHI)
    window = rth.filter((pl.col("timestamp") >= ts0) & (pl.col("timestamp") < ts1))
    yc = window.with_columns(pl.col("timestamp").dt.year().alias("y")).group_by("y").len().sort("y")
    lines = [
        str(window.height),
        str(yc),
        f"unique session_date {window['cme_session_date'].n_unique()}",
        f"null sd {window['cme_session_date'].null_count()}",
    ]
    out = BacktestEngine(
        BacktestConfig(
            orchestration=OrchestrationSpec(module_ids=("orb",), one_position_at_a_time=True),
        ),
    ).run(window, [as_module("orb", OrbStrategy(production_orb_opt3_funded_params()))])
    tl = out.trade_log
    by = tl.group_by(pl.col("exit_time").dt.year().alias("y")).len().sort("y")
    lines.append(f"trades {tl.height}")
    lines.append(str(by))
    er = tl.group_by("exit_reason").agg(pl.col("net_pnl").sum())
    lines.append(str(er))
    fl = tl.filter(pl.col("exit_reason") == "flatten")
    if fl.height:
        lines.append(
            str(
                fl.select("entry_time", "exit_time", "entry_price", "exit_price", "net_pnl").row(
                    0, named=True
                )
            )
        )
    Path("._m6_dbg.txt").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
