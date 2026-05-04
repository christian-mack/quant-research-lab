"""End-to-end ORB+Opt3 on one calendar month of MNQ continuous (M5 smoke, not M6 parity).

**Window:** March 2024 RTH — mix of directional days and chop on MNQ without hand‑picking
individual regimes (operator‑reviewable).

Skips when ``data/raw`` has no contract files (CI / fresh clone).
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo

import polars as pl
import pytest

from quant_research.backtest import (
    BacktestConfig,
    BacktestEngine,
    OrchestrationSpec,
    as_module,
)
from quant_research.modules import OrbStrategy, production_orb_opt3_funded_params

_CHI = ZoneInfo("America/Chicago")


def _month_rth_slice(year: int, month: int) -> pl.DataFrame | None:
    root = Path(__file__).resolve().parents[2] / "data" / "raw"
    if not any(root.glob("MNQ *.Last.txt")):
        return None

    from quant_research.data import continuous_contract, data_loader, session

    raw = data_loader.load_all_contracts(root)
    cont = continuous_contract.build_continuous_contract(raw)
    cls = session.classify_sessions(cont)
    dated = session.assign_cme_session_date(cls)
    rth = dated.filter(pl.col("session") == session.SESSION_RTH)

    start = dt.datetime(year, month, 1, tzinfo=_CHI)
    if month == 12:
        end = dt.datetime(year + 1, 1, 1, tzinfo=_CHI)
    else:
        end = dt.datetime(year, month + 1, 1, tzinfo=_CHI)

    return rth.filter(
        pl.col("timestamp").is_between(start, end, closed="left")
    ).sort("timestamp")


@pytest.fixture(scope="module")
def march_2024_rth() -> pl.DataFrame:
    df = _month_rth_slice(2024, 3)
    if df is None:
        pytest.skip("No MNQ raw files under data/raw")
    if df.height < 1000:
        pytest.skip("Insufficient March 2024 RTH rows in dataset")
    return df


def test_orb_march_2024_mnq_smoke(march_2024_rth: pl.DataFrame) -> None:
    strat = OrbStrategy(production_orb_opt3_funded_params())
    orch = OrchestrationSpec(module_ids=("orb",), one_position_at_a_time=True)
    cfg = BacktestConfig(orchestration=orch)

    out = BacktestEngine(cfg).run(march_2024_rth, [as_module("orb", strat)])

    tl = out.trade_log
    assert tl.height >= 1, "expected at least one closed trade in March 2024 ORB run"

    assert (tl["module_id"] == "orb").all()
    assert (tl["quantity"] == 3).all()
    assert (tl["entry_time"] <= tl["exit_time"]).all()
    assert tl["bars_held"].dtype in (pl.Int32, pl.Int64)
    assert (tl["bars_held"] >= 0).all()

    allowed_exit = {"orb_exit_target", "orb_exit_stop", "flatten"}
    bad = tl.filter(~pl.col("exit_reason").is_in(list(allowed_exit)))
    assert bad.height == 0, bad

    # Non-trivial PnL; cap catch order-of-magnitude bugs (3× MNQ)
    assert tl["gross_pnl"].abs().max() > 0
    assert tl["gross_pnl"].abs().max() < 60_000.0
    assert tl["net_pnl"].abs().sum() > 0

    # Round-trips: even fills per contract scale (entry + exit per trade minimum)
    assert len(out.fills) >= tl.height * 2

    # Spot: first trade direction / prices finite
    r0 = tl.row(0, named=True)
    assert r0["direction"] in ("long", "short")
    assert 1_000.0 < float(r0["entry_price"]) < 50_000.0
    assert 1_000.0 < float(r0["exit_price"]) < 50_000.0
