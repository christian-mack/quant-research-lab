"""Screening gates, Sharpe, bootstrap, and Deflated Sharpe for Wave 1 Stage 1 Track 1."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import numpy as np
from scipy import stats

from quant_research.statistics.deflated_sharpe import (
    deflated_sharpe_ratio,
    sample_moments_from_returns,
)

MNQ_USD_PER_POINT_QTY1 = 2.0
GATE_EVAL_YEARS = (2021, 2022, 2023, 2024, 2025)


@dataclass(frozen=True, slots=True)
class TradeRow:
    """One closed-trade outcome on MNQ (qty=1) in points and USD."""

    exit_et_date: dt.date
    cme_session_date: dt.date | None
    pnl_usd_qty1: float
    gross_points: float
    exit_reason: str = ""


@dataclass(frozen=True, slots=True)
class GateResult:
    """Binary gate outcomes with diagnostic fields."""

    gate1_pass: bool
    gate1_detail: dict[str, object]

    gate2_pass: bool
    gate2_detail: dict[str, object]

    gate3_pass: bool
    gate3_detail: dict[str, object]

    gate4_pass: bool
    gate4_detail: dict[str, object]

    gate5_pass: bool
    gate5_detail: dict[str, object]

    overall_survives: bool


def session_pnl_arrays(
    trades: list[TradeRow],
    *,
    years_filter: tuple[int, ...] = GATE_EVAL_YEARS,
) -> tuple[np.ndarray, np.ndarray]:
    """Return parallel arrays (session_ord_key, session_pnl_usd_qty1).

    ``session_ord_key`` is ``YYYYMMDD`` int for stable sorting; uses
    ``cme_session_date`` when present else ``exit_et_date``.
    """
    acc: dict[int, float] = {}
    for t in trades:
        if t.exit_et_date.year not in years_filter:
            continue
        d = t.cme_session_date or t.exit_et_date
        if d.year not in years_filter:
            continue
        k = d.year * 10000 + d.month * 100 + d.day
        acc[k] = acc.get(k, 0.0) + t.pnl_usd_qty1
    if not acc:
        return np.array([], dtype=np.int64), np.array([], dtype=np.float64)
    keys = sorted(acc.keys())
    return np.array(keys, dtype=np.int64), np.array([acc[k] for k in keys], dtype=np.float64)


def annual_totals_qty1(trades: list[TradeRow], years: tuple[int, ...]) -> dict[int, float]:
    out = {int(y): 0.0 for y in years}
    for t in trades:
        y = int(t.exit_et_date.year)
        if y in out:
            out[y] += float(t.pnl_usd_qty1)
    return out


def avg_annual_profit_qty1(trades: list[TradeRow], years: tuple[int, ...]) -> float:
    sums = annual_totals_qty1(trades, years)
    vals = list(sums.values())
    return float(np.mean(vals)) if vals else 0.0


def daily_pnls_qty1_et(trades: list[TradeRow], years_filter: tuple[int, ...]) -> np.ndarray:
    """Non-zero-dollar days only returns empty if no trades; include zeros implicitly via SR?

    Caller supplies full-day regularization externally; here we return one value per
    sorted unique exit NY calendar day contributing to Sharpe aggregator.
    """
    acc: dict[dt.date, float] = {}
    for t in trades:
        if t.exit_et_date.year not in years_filter:
            continue
        acc[t.exit_et_date] = acc.get(t.exit_et_date, 0.0) + t.pnl_usd_qty1
    if not acc:
        return np.array([], dtype=np.float64)
    return np.array([acc[k] for k in sorted(acc.keys())], dtype=np.float64)


def trades_per_calendar_week_avg(
    trades: list[TradeRow],
    *,
    filter_years: tuple[int, ...] = GATE_EVAL_YEARS,
) -> float:
    ys = sorted({t.exit_et_date for t in trades if t.exit_et_date.year in filter_years})
    if len(ys) < 8:
        return 0.0
    elapsed_weeks = (ys[-1] - ys[0]).days / 7.0
    n = sum(1 for t in trades if t.exit_et_date.year in filter_years)
    return float(n / elapsed_weeks) if elapsed_weeks > 0 else 0.0


def eval_closed_trade_stats(
    trades: list[TradeRow],
    *,
    years_filter: tuple[int, ...] = GATE_EVAL_YEARS,
) -> dict[str, float]:
    wins: list[float] = []
    losses: list[float] = []
    for t in trades:
        if t.exit_et_date.year not in years_filter:
            continue
        if t.pnl_usd_qty1 > 0:
            wins.append(t.pnl_usd_qty1)
        elif t.pnl_usd_qty1 < 0:
            losses.append(-t.pnl_usd_qty1)
    n = len(wins) + len(losses)
    wr = (len(wins) / n) if n else 0.0
    aw = float(np.mean(wins)) if wins else 0.0
    al = float(np.mean(losses)) if losses else 0.0
    rr = (aw / al) if al > 0 else float("inf")
    return {
        "closed_trade_count": float(n),
        "win_rate": wr,
        "avg_win_usd_qty1": aw,
        "avg_loss_mag_usd_qty1": al,
        "risk_reward_avg_win_avg_loss": rr,
        "take_profit_truncated_rr_cap": rr,
    }


def evaluate_gates(
    trades: list[TradeRow],
    *,
    years: tuple[int, ...] = GATE_EVAL_YEARS,
    dll_session_cap_usd: float = 1_000.0,
    target_annual_design_usd: float = 30_000.0,
    mnq_pt_usd: float = MNQ_USD_PER_POINT_QTY1,
    min_trades_per_week: float = 3.0,
    min_win_rate: float = 0.60,
    rr_low: float = 0.8,
    rr_high: float = 1.5,
    min_profitable_years: int = 4,
) -> GateResult:
    """Apply Stage 1 Track 1 coarse gates to a fixed trade list (qty=1 economics)."""
    ann = annual_totals_qty1(trades, years)
    avg_ann = float(np.mean([ann[y] for y in years])) if years else 0.0

    # Gate 1
    g1: dict[str, object] = {
        "avg_annual_pnl_usd_qty1": avg_ann,
        "target_annual_design_usd": target_annual_design_usd,
    }
    if avg_ann <= 0:
        g1["qty_design"] = None
        g1["worst_session_loss_usd_at_qty_design"] = None
        g1["note"] = "non-positive average annual P&L at qty=1 -> fail Gate 1 by spec"
        gate1_pass = False
    else:
        qty_design = max(1, int(round(target_annual_design_usd / avg_ann)))
        g1["qty_design"] = qty_design
        _, sess_pnl = session_pnl_arrays(trades, years_filter=years)
        worst_scaled = float(np.min(sess_pnl) * qty_design) if sess_pnl.size else float("nan")
        g1["worst_session_loss_usd_at_qty_design"] = worst_scaled
        g1["note"] = "worst-session = min over CME-session (or ET exit date fallback) P&L sum"
        # Pass if worst per-session loss magnitude is strictly below cap (loss > -cap).
        gate1_pass = bool(np.isfinite(worst_scaled) and worst_scaled > -dll_session_cap_usd)

    # Gate 2
    tpw = trades_per_calendar_week_avg(trades, filter_years=years)
    g2 = {"avg_trades_per_week": tpw, "years_filter": list(years)}
    gate2_pass = bool(tpw >= min_trades_per_week)

    # Gate 3–4 closed-trade stats on filtered years (exclude scratches at 0)
    cts = eval_closed_trade_stats(trades, years_filter=years)
    g3 = {"win_rate": cts["win_rate"], "closed_trade_count": cts["closed_trade_count"]}
    gate3_pass = bool(cts["closed_trade_count"] > 0) and float(cts["win_rate"]) >= min_win_rate

    rr = float(cts["risk_reward_avg_win_avg_loss"])
    finite_rr = rr if np.isfinite(rr) else float("nan")
    g4 = {
        "avg_win_usd": cts["avg_win_usd_qty1"],
        "avg_loss_mag_usd": cts["avg_loss_mag_usd_qty1"],
        "rr": finite_rr,
    }
    gate4_pass = bool(np.isfinite(finite_rr) and (float(rr_low) <= finite_rr <= float(rr_high)))

    # Gate 5: profitable strictly > 0 in >=4 years
    prof_years = sum(1 for y in years if ann.get(int(y), 0.0) > 0.0)
    g5 = {"annual_pnls_qty1_et_exit_year": {str(y): float(ann.get(y, 0.0)) for y in years}}
    g5["profitable_year_count_strict_gt_0"] = prof_years
    gate5_pass = bool(prof_years >= min_profitable_years)

    survives = bool(gate1_pass and gate2_pass and gate3_pass and gate4_pass and gate5_pass)

    return GateResult(
        gate1_pass=gate1_pass,
        gate1_detail=g1,
        gate2_pass=gate2_pass,
        gate2_detail=g2,
        gate3_pass=gate3_pass,
        gate3_detail=g3,
        gate4_pass=gate4_pass,
        gate4_detail=g4,
        gate5_pass=gate5_pass,
        gate5_detail=g5,
        overall_survives=survives,
    )


def daily_sharpe_annualized(
    daily_pnls_usd: np.ndarray,
    *,
    trading_days_year: float = 252.0,
) -> float:
    """Sharpe on an irregular daily realized P&amp;L stream (usd), sqrt(252) scale."""
    x = np.asarray(daily_pnls_usd, dtype=np.float64).ravel()
    if x.size < 2:
        return float("nan")
    mu = float(np.mean(x))
    sd = float(np.std(x, ddof=1))
    if sd <= 0 or not np.isfinite(sd):
        return float("nan")
    return float(np.sqrt(trading_days_year) * mu / sd)


def block_bootstrap_session_mean_annual_ci(
    session_keys_sorted: np.ndarray,
    session_pnls: np.ndarray,
    *,
    block_len: int = 20,
    n_iterations: int = 1000,
    years_span: float = 5.0,
    seed: int = 42,
) -> dict[str, object]:
    """Circular block bootstrap on session totals; statistic = mean annual P&amp;L.

    Approximates dividing total resampled session P&amp;L by fixed ``years_span``
    (**5 years** for 2021--2025).
    """
    n = int(session_pnls.size)
    if n < block_len or n < 2:
        return {
            "ci95_low": float("nan"),
            "ci95_high": float("nan"),
            "point_mean_annual_usd": float("nan"),
            "note": "insufficient sessions for block bootstrap",
        }

    rng = np.random.default_rng(seed)

    def one_replicate() -> float:
        out: list[float] = []
        while len(out) < n:
            start = int(rng.integers(0, n))
            for j in range(block_len):
                out.append(float(session_pnls[(start + j) % n]))
        total = float(np.sum(np.array(out[:n], dtype=np.float64)))
        return total / years_span

    reps = np.array([one_replicate() for _ in range(n_iterations)], dtype=np.float64)
    point = float(np.sum(session_pnls) / years_span)
    lo, hi = float(np.quantile(reps, 0.025)), float(np.quantile(reps, 0.975))
    return {
        "ci95_low": lo,
        "ci95_high": hi,
        "point_mean_annual_usd": point,
        "block_len_sessions": block_len,
        "n_iterations": n_iterations,
        "years_span": years_span,
        "includes_zero": bool(lo <= 0.0 <= hi),
    }


def deflated_sharpe_joint_from_trial_stats(
    trials: list[dict[str, object]],
    *,
    n_trials: int,
    mean_sr_across_trials: float = 0.0,
) -> dict[str, object]:
    """Joint deflated Sharpe when daily vectors are unavailable (reuse stored moments).

    Each trial dict may include:
    ``hypothesis_id``, ``observed_daily_sharpe_annualized`` (finite or omitted),
    ``n_observations_daily``, ``skewness_daily_fisher``, ``kurtosis_pearson_daily``.
    """
    sharpes: list[float] = []
    for t in trials:
        sr = t.get("observed_daily_sharpe_annualized")
        sharpes.append(float(sr) if sr is not None and np.isfinite(float(sr)) else float("nan"))

    adj_sr = np.array([float(s) if np.isfinite(s) else 0.0 for s in sharpes], dtype=np.float64)
    var_across = float(np.var(adj_sr, ddof=1)) if adj_sr.size > 1 else 0.0
    if not np.isfinite(var_across):
        var_across = 0.0

    summary: dict[str, object] = {
        "n_trials_registered": n_trials,
        "variance_across_trial_sharpes_substituted_zeros": var_across,
        "adjusted_sharpes_track_vector": adj_sr.tolist(),
        "hypothesis_ids_ordered": [str(t.get("hypothesis_id", "")) for t in trials],
        "note": (
            "NaN Sharpes become 0 in the track vector for Var(SRhat) only; "
            "PSR rows stay NaN for blocked/insufficient trials."
        ),
    }

    dsr_cells: list[dict[str, object]] = []
    for i, t in enumerate(trials):
        hid = str(t.get("hypothesis_id", i))
        sr = sharpes[i]
        n_obs = t.get("n_observations_daily")
        sk = t.get("skewness_daily_fisher")
        ku = t.get("kurtosis_pearson_daily")
        if not np.isfinite(sr) or n_obs is None or int(n_obs) < 3:
            dsr_cells.append(
                {
                    "hypothesis_id": hid,
                    "probabilistic_sharpe_vs_track_null": float("nan"),
                    "note": "blocked or insufficient daily samples",
                }
            )
            continue
        dsr = deflated_sharpe_ratio(
            float(sr),
            int(n_obs),
            skewness=float(sk) if sk is not None else 0.0,
            kurtosis_pearson=float(ku) if ku is not None else 3.0,
            n_trials=int(n_trials),
            variance_across_trials=var_across,
            mean_sr_across_trials=float(mean_sr_across_trials),
        )
        dsr_cells.append(
            {
                "hypothesis_id": hid,
                "observed_daily_sharpe_annualized": float(sr),
                "expected_max_sr_under_null_trials": float(dsr.expected_max_sr_benchmark),
                "probabilistic_sharpe_vs_track_null": float(dsr.probabilistic_sharpe),
                "n_observations_daily": int(n_obs),
                "skewness_daily_fisher": float(sk) if sk is not None else float("nan"),
                "kurtosis_pearson_daily": float(ku) if ku is not None else float("nan"),
            }
        )

    summary["per_hypothesis_deflated_block"] = dsr_cells
    return summary


def deflated_sharpe_track(
    sharpes: list[float],
    daily_samples: list[np.ndarray],
    *,
    n_trials: int = 7,
    mean_sr_across_trials: float = 0.0,
) -> dict[str, object]:
    """Within-track Deflated Sharpe (N fixed).

    Non-finite trial Sharpes are replaced with 0.0 only when computing the
    across-trial variance for the common benchmark; per-hypothesis PSR is
    omitted when the hypothesis has no valid daily series.
    """
    adj_sr = np.array([float(s) if np.isfinite(s) else 0.0 for s in sharpes], dtype=np.float64)
    var_across = float(np.var(adj_sr, ddof=1)) if adj_sr.size > 1 else 0.0
    if not np.isfinite(var_across):
        var_across = 0.0

    summary: dict[str, object] = {
        "n_trials_registered": n_trials,
        "variance_across_trial_sharpes_substituted_zeros": var_across,
        "adjusted_sharpes_track_vector": adj_sr.tolist(),
        "note": (
            "NaN Sharpes become 0 in the track vector for Var(SRhat) only; "
            "PSR rows stay NaN for blocked runs."
        ),
    }

    dsr_cells: list[dict[str, object]] = []
    for i, sr in enumerate(sharpes):
        dail = daily_samples[i] if i < len(daily_samples) else np.array([])
        if not np.isfinite(sr) or dail.size < 3:
            dsr_cells.append(
                {
                    "hypothesis_order_index": i,
                    "probabilistic_sharpe_vs_track_null": float("nan"),
                    "note": "blocked or insufficient daily samples",
                }
            )
            continue
        sk, ku = sample_moments_from_returns(dail)
        dsr = deflated_sharpe_ratio(
            float(sr),
            int(dail.size),
            skewness=sk,
            kurtosis_pearson=ku,
            n_trials=int(n_trials),
            variance_across_trials=var_across,
            mean_sr_across_trials=float(mean_sr_across_trials),
        )
        dsr_cells.append(
            {
                "hypothesis_order_index": i,
                "observed_daily_sharpe_annualized": float(sr),
                "expected_max_sr_under_null_trials": float(dsr.expected_max_sr_benchmark),
                "probabilistic_sharpe_vs_track_null": float(dsr.probabilistic_sharpe),
                "n_observations_daily": int(dail.size),
                "skewness_daily_fisher": float(sk),
                "kurtosis_pearson_daily": float(ku),
            }
        )

    summary["per_hypothesis_deflated_block"] = dsr_cells
    return summary


def summarize_trade_sharpe_moments(daily_pnls_usd: np.ndarray) -> dict[str, float]:
    """Skew/Fisher excess kurtosis on daily agg for documentation (joint recompute aid)."""
    x = np.asarray(daily_pnls_usd, dtype=np.float64).ravel()
    if x.size < 3:
        return {
            "n": float(x.size),
            "skew_fisher": float("nan"),
            "kurtosis_excess": float("nan"),
        }
    skew = float(stats.skew(x, bias=False))
    k_ex = float(stats.kurtosis(x, fisher=True, bias=False))
    sd = float(np.std(x, ddof=1))
    mu = float(np.mean(x))
    return {
        "n": float(x.size),
        "mean": mu,
        "std_ddof1": sd,
        "skew_fisher": skew,
        "kurtosis_excess": k_ex,
    }
