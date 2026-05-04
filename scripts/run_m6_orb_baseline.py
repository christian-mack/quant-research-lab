#!/usr/bin/env python3
"""Run ORB+Opt3 (funded params, qty=3) over the PT3 6-year protocol window; print M6 metrics.

Usage (from repo root)::

    uv run python scripts/run_m6_orb_baseline.py

Requires ``data/raw/MNQ *.Last.txt`` (gitignored).
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import polars as pl

_REPO = Path(__file__).resolve().parents[1]

from quant_research.backtest import (
    BacktestConfig,
    BacktestEngine,
    OrchestrationSpec,
    as_module,
)
from quant_research.backtest.schema import empty_trade_log
from quant_research.backtest.m6_metrics import compute_m6_aggregates, protocol_year_fraction
from quant_research.data import continuous_contract, data_loader, session
from quant_research.data.quality import split_dataframe_at_operator_export_gaps
from quant_research.modules import OrbStrategy, production_orb_opt3_funded_params

_CHI = ZoneInfo("America/Chicago")
_CHI_KEY = "America/Chicago"
_START = dt.date(2020, 1, 1)
_END = dt.date(2026, 4, 19)


def main() -> None:
    root = _REPO / "data" / "raw"
    if not any(root.glob("MNQ *.Last.txt")):
        print("No MNQ contract files under data/raw; abort.", file=sys.stderr)
        sys.exit(2)

    raw = data_loader.load_all_contracts(root)
    cont = continuous_contract.build_continuous_contract(raw)
    cls = session.classify_sessions(cont)
    dated = session.assign_cme_session_date(cls)
    rth = dated.filter(pl.col("session") == session.SESSION_RTH)

    ts0 = dt.datetime.combine(_START, dt.time.min).replace(tzinfo=_CHI)
    ts_end_excl = dt.datetime(2026, 4, 20, 0, 0, 0, tzinfo=_CHI)

    window = rth.filter(
        (pl.col("timestamp") >= ts0) & (pl.col("timestamp") < ts_end_excl)
    ).sort("timestamp")

    segments = split_dataframe_at_operator_export_gaps(window)
    orch = OrchestrationSpec(module_ids=("orb",), one_position_at_a_time=True)
    cfg = BacktestConfig(orchestration=orch)

    logs: list[pl.DataFrame] = []
    realized = 0.0
    comm = 0.0
    for seg in segments:
        strat = OrbStrategy(production_orb_opt3_funded_params())
        out = BacktestEngine(cfg).run(seg, [as_module("orb", strat)])
        if out.trade_log.height > 0:
            logs.append(out.trade_log)
        realized += out.account.realized_pnl
        comm += out.account.total_commission

    combined = pl.concat(logs) if logs else empty_trade_log()
    m = compute_m6_aggregates(combined)

    trades_per_exit_year = {
        str(y): int(
            combined.filter(
                pl.col("exit_time").dt.convert_time_zone(_CHI_KEY).dt.year() == y
            ).height,
        )
        for y in range(2020, 2027)
    }
    annual_net_by_year = {
        str(y): float(m.years_calendar.get(y, 0.0)) for y in range(2020, 2027)
    }

    yfrac = protocol_year_fraction(_START, _END)
    contracts = production_orb_opt3_funded_params().quantity
    pnl_per_contract_per_year = (m.net_pnl_total / contracts) / yfrac if yfrac > 0 else 0.0
    max_dd_per_contract = m.max_drawdown / contracts if contracts else m.max_drawdown

    payload = {
        "protocol_start": _START.isoformat(),
        "protocol_end_inclusive": _END.isoformat(),
        "segment_count": len(segments),
        "rth_bars": window.height,
        "contracts": contracts,
        "trade_count": m.trade_count,
        "net_pnl_total": m.net_pnl_total,
        "pnl_per_contract_per_year": pnl_per_contract_per_year,
        "win_rate": m.win_rate,
        "win_rate_pct": round(100.0 * m.win_rate, 2),
        "profit_factor": m.profit_factor,
        "avg_win": m.avg_win,
        "avg_loss": m.avg_loss,
        "max_drawdown_total": m.max_drawdown,
        "max_drawdown_per_contract": max_dd_per_contract,
        "years_calendar_pnl": {str(k): v for k, v in sorted(m.years_calendar.items())},
        "trades_per_exit_year": trades_per_exit_year,
        "annual_net_by_year_chicago": annual_net_by_year,
        "years_positive": m.years_positive_count,
        "years_with_trades": m.years_total_count,
        "realized_pnl_account_sum_segments": realized,
        "commission_total_sum_segments": comm,
    }
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
