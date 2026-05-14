"""Assemble a standardized research report from a ``TradeLedger`` / trade log DF."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import polars as pl

from quant_research.statistics.bootstrap import BootstrapConfig, bootstrap_trade_metrics
from quant_research.statistics.deflated_sharpe import (
    DeflatedSharpeResult,
    deflated_sharpe_ratio,
    sample_moments_from_returns,
)
from quant_research.statistics.is_oos import IsoSplitConfig, split_trade_log_is_oos


@dataclass(frozen=True, slots=True)
class DeflatedSharpeRunParams:
    """Optional DSR block; set ``n_trials`` to enable."""

    n_trials: int
    variance_across_trials: float
    mean_sr_across_trials: float = 0.0


@dataclass(frozen=True, slots=True)
class ResearchReport:
    """Nested dict-like report suitable for JSON serialization (convert manually)."""

    meta: dict[str, Any]
    performance: dict[str, Any]
    bootstrap: dict[str, Any]
    deflated_sharpe: dict[str, Any] | None
    is_oos: dict[str, Any] | None
    notes: list[str]


def _trade_sharpe(net: np.ndarray) -> float:
    if net.size < 2:
        return float("nan")
    m, s = float(np.mean(net)), float(np.std(net, ddof=1))
    if s <= 0:
        return float("nan")
    return float(np.sqrt(net.size) * m / s)


def trade_log_research_report(
    trade_log: pl.DataFrame,
    *,
    strategy_label: str = "",
    bootstrap_config: BootstrapConfig | None = None,
    deflated_sharpe_params: DeflatedSharpeRunParams | None = None,
    iso_config: IsoSplitConfig | None = None,
) -> ResearchReport:
    """
    Build a report: totals, win rate, Sharpe (trade series), bootstrap CIs,
    optional DSR, optional IS/OOS on ``net_pnl``.

    **Sample size note:** ``adequacy`` is a qualitative string — not a formal power calc.
    """
    notes: list[str] = []
    if trade_log.height == 0:
        return ResearchReport(
            meta={"strategy": strategy_label, "n_trades": 0},
            performance={},
            bootstrap={},
            deflated_sharpe=None,
            is_oos=None,
            notes=["empty trade log"],
        )
    if "net_pnl" not in trade_log.columns:
        msg = "trade_log requires 'net_pnl' column"
        raise ValueError(msg)

    net = trade_log["net_pnl"].to_numpy()
    n = int(net.size)
    wins = int(np.count_nonzero(net > 0))
    win_rate = wins / n
    total_pnl = float(np.sum(net))
    sharpe = _trade_sharpe(net)

    bcfg = bootstrap_config or BootstrapConfig()
    bc = bootstrap_trade_metrics(net, bcfg)

    dsr_block: dict[str, Any] | None = None
    if deflated_sharpe_params is not None and deflated_sharpe_params.n_trials >= 1:
        sk, ku = sample_moments_from_returns(net)
        dsr: DeflatedSharpeResult = deflated_sharpe_ratio(
            sharpe,
            n,
            sk,
            ku,
            deflated_sharpe_params.n_trials,
            deflated_sharpe_params.variance_across_trials,
            deflated_sharpe_params.mean_sr_across_trials,
        )
        dsr_block = {
            "observed_trade_sharpe": dsr.observed_sharpe,
            "probabilistic_sharpe_vs_e_max": dsr.probabilistic_sharpe,
            "expected_max_sharpe_null_trials": dsr.expected_max_sr_benchmark,
            "n_trials_disclosed": dsr.n_trials,
            "skewness_returns": sk,
            "kurtosis_pearson_returns": ku,
            "note": "DSR uses trade P&Ls as 'returns'; interpret vs continuous-time SR carefully.",
        }
    else:
        notes.append("Deflated Sharpe omitted (set DeflatedSharpeRunParams to include).")

    iso_block: dict[str, Any] | None = None
    icfg = iso_config or IsoSplitConfig(is_fraction=0.6, mode="trade_count")
    try:
        is_df, oos_df = split_trade_log_is_oos(trade_log, icfg)
        iso_block = {
            "mode": icfg.mode,
            "is_fraction": icfg.is_fraction,
            "is_trades": is_df.height,
            "oos_trades": oos_df.height,
            "is_total_net_pnl": float(is_df["net_pnl"].sum()),
            "oos_total_net_pnl": float(oos_df["net_pnl"].sum()),
            "is_win_rate": float(np.mean(is_df["net_pnl"].to_numpy() > 0)),
            "oos_win_rate": float(np.mean(oos_df["net_pnl"].to_numpy() > 0)),
        }
    except ValueError as e:
        notes.append(f"IS/OOS split skipped: {e}")

    if n < 30:
        adequacy = "low (<30 trades): wide sampling uncertainty; treat CIs as indicative only"
    elif n < 100:
        adequacy = "moderate: bootstrap CIs increasingly stable"
    else:
        adequacy = "adequate for trade-level bootstrap (not a power analysis)"

    performance = {
        "n_trades": n,
        "win_rate": win_rate,
        "total_net_pnl": total_pnl,
        "trade_series_sharpe": sharpe,
        "sample_size_adequacy": adequacy,
    }

    bootstrap_out = {
        "confidence_level": bc.confidence_level,
        "n_bootstrap": bc.n_iterations,
        "pnl_total_ci": list(bc.pnl_total),
        "sharpe_ci": list(bc.sharpe_ratio),
        "win_rate_ci": list(bc.win_rate),
        "max_drawdown_ci": list(bc.max_drawdown),
        "note": "Sharpe is sqrt(n)*mean/std on trade P&Ls (not annualized).",
    }

    meta = {"strategy": strategy_label, "n_trades": n}

    return ResearchReport(
        meta=meta,
        performance=performance,
        bootstrap=bootstrap_out,
        deflated_sharpe=dsr_block,
        is_oos=iso_block,
        notes=notes,
    )


def research_report_to_dict(rep: ResearchReport) -> dict[str, Any]:
    """Flatten ``ResearchReport`` into a JSON-friendly ``dict``."""
    out: dict[str, Any] = {
        "meta": rep.meta,
        "performance": rep.performance,
        "bootstrap": rep.bootstrap,
        "notes": rep.notes,
    }
    if rep.deflated_sharpe is not None:
        out["deflated_sharpe"] = rep.deflated_sharpe
    if rep.is_oos is not None:
        out["is_oos"] = rep.is_oos
    return out
