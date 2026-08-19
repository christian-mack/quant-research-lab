"""Geometry-guard causality and selection-bias analysis for OTE setups."""

from __future__ import annotations

import datetime as dt
import statistics
from dataclasses import dataclass
from typing import Any, Literal

import polars as pl

from quant_research.backtest.geometry import (
    REJECT_STOP_WRONG_SIDE,
    check_trade_geometry,
)
from quant_research.ict import fvg as fvg_mod
from quant_research.ict import pd_arrays as pd_mod
from quant_research.ict.ote_execution import (
    OteExecutedTrade,
    execute_setup,
    ote_research_backtest_config,
)
from quant_research.ict.ote_strategy import (
    DIRECTION_LONG,
    DIRECTION_SHORT,
    OteSetup,
    OteStrategyConfig,
    _build_setup_partial,
    _reference_levels,
    detect_sweep,
)

MNQ_POINT_VALUE = 2.0
TICK_SIZE = 0.25
COMMISSION_RT = 1.98
SLIP_STOP_TIME = 0.50
SLIP_TARGET = 0.25

OutcomeKind = Literal["kept", "rejected", "incomplete"]


@dataclass(frozen=True)
class OteAttemptRecord:
    """One sweep-chain attempt through setup assembly."""

    outcome: OutcomeKind
    reject_reason: str | None
    session_date: dt.date | None
    direction: str | None
    entry_price: float | None
    stop_price: float | None
    target_price: float | None
    entry_fill_index: int | None
    swept_extreme: float | None
    displacement_low: float | None
    displacement_high: float | None
    sweep_depth_ticks: float | None
    entry_vs_stop_ticks: float | None
    setup: OteSetup | None = None


def scan_ote_attempts(
    df: pl.DataFrame,
    *,
    config: OteStrategyConfig | None = None,
) -> list[OteAttemptRecord]:
    """Walk all sessions; emit kept, rejected, and incomplete attempts."""
    cfg = config or OteStrategyConfig()
    work = df.sort("timestamp")
    if pd_mod.PDH_COL not in work.columns:
        work = pd_mod.add_pd_arrays(work)

    records: list[OteAttemptRecord] = []
    for sess in work["cme_session_date"].unique().sort().to_list():
        if sess is None:
            continue
        sess_df = work.filter(pl.col("cme_session_date") == sess)
        if cfg.rth_only:
            from quant_research.ict.ote_strategy import _filter_rth

            sess_df = _filter_rth(sess_df, timestamp="timestamp")
        if sess_df.height < 5:
            continue
        pdh = float(sess_df[pd_mod.PDH_COL][0]) if sess_df[pd_mod.PDH_COL][0] is not None else None
        pdl = float(sess_df[pd_mod.PDL_COL][0]) if sess_df[pd_mod.PDL_COL][0] is not None else None
        sess_date = sess if isinstance(sess, dt.date) else None
        records.extend(
            _session_attempts(
                sess_df,
                config=cfg,
                session_date=sess_date,
                pdh=pdh,
                pdl=pdl,
            )
        )
    return records


def _session_attempts(
    df: pl.DataFrame,
    *,
    config: OteStrategyConfig,
    session_date: dt.date | None,
    pdh: float | None,
    pdl: float | None,
) -> list[OteAttemptRecord]:
    from quant_research.ict.ote_strategy import build_setup_from_sweep

    n = df.height
    out: list[OteAttemptRecord] = []
    cursor = 2
    session_fvgs = fvg_mod.detect_fvgs(df)

    while cursor < n - 2:
        levels = _reference_levels(
            df,
            cursor,
            pdh=pdh,
            pdl=pdl,
            lookback=config.swing_ref_lookback,
            high="high",
            low="low",
            timestamp="timestamp",
        )
        advanced = False
        for level, side in levels:
            sweep = detect_sweep(
                df,
                level=level,
                side=side,
                config=config.sweep_config,
                search_start_index=cursor,
            )
            if not sweep.swept or sweep.close_back_index is None:
                continue
            setup = build_setup_from_sweep(
                df,
                sweep,
                config=config,
                session_date=session_date,
                pdh=pdh,
                pdl=pdl,
                fvgs=session_fvgs,
            )
            if setup is not None:
                out.append(_record_from_setup(setup, outcome="kept"))
                cursor = max(setup.entry_fill_index or setup.mss_index, setup.mss_index) + 1
                advanced = True
                break
            partial = _build_setup_partial(
                df,
                sweep,
                config=config,
                session_date=session_date,
                pdh=pdh,
                pdl=pdl,
                fvgs=session_fvgs,
            )
            if partial is None:
                out.append(
                    OteAttemptRecord(
                        outcome="incomplete",
                        reject_reason=None,
                        session_date=session_date,
                        direction=None,
                        entry_price=None,
                        stop_price=None,
                        target_price=None,
                        entry_fill_index=None,
                        swept_extreme=sweep.penetration_extreme,
                        displacement_low=None,
                        displacement_high=None,
                        sweep_depth_ticks=_sweep_depth(sweep),
                        entry_vs_stop_ticks=None,
                    )
                )
            else:
                direction, entry, stop, target = partial
                reject = check_trade_geometry(direction, entry, stop, target)
                if reject is not None:
                    out.append(
                        OteAttemptRecord(
                            outcome="rejected",
                            reject_reason=reject.reason,
                            session_date=session_date,
                            direction=direction,
                            entry_price=entry,
                            stop_price=stop,
                            target_price=target,
                            entry_fill_index=_fill_idx_from_mss(df, direction, entry, sweep),
                            swept_extreme=sweep.penetration_extreme,
                            displacement_low=None,
                            displacement_high=None,
                            sweep_depth_ticks=_sweep_depth(sweep),
                            entry_vs_stop_ticks=(entry - stop) / TICK_SIZE
                            if direction == DIRECTION_LONG
                            else (stop - entry) / TICK_SIZE,
                        )
                    )
        if not advanced:
            cursor += 1
    return out


def _record_from_setup(setup: OteSetup, *, outcome: OutcomeKind) -> OteAttemptRecord:
    disp = setup.displacement_high - setup.displacement_low
    return OteAttemptRecord(
        outcome=outcome,
        reject_reason=None,
        session_date=setup.session_date,
        direction=setup.direction,
        entry_price=setup.entry_price,
        stop_price=setup.stop_price,
        target_price=setup.target_price,
        entry_fill_index=setup.entry_fill_index,
        swept_extreme=setup.swept_extreme,
        displacement_low=setup.displacement_low,
        displacement_high=setup.displacement_high,
        sweep_depth_ticks=abs(setup.swept_extreme - setup.sweep_level) / TICK_SIZE,
        entry_vs_stop_ticks=(setup.entry_price - setup.stop_price) / TICK_SIZE
        if setup.direction == DIRECTION_LONG
        else (setup.stop_price - setup.entry_price) / TICK_SIZE,
        setup=setup,
    )


def _sweep_depth(sweep: Any) -> float | None:
    if sweep.penetration_extreme is None or sweep.level is None:
        return None
    return abs(sweep.penetration_extreme - sweep.level) / TICK_SIZE


def _fill_idx_from_mss(
    df: pl.DataFrame,
    direction: str,
    entry: float,
    sweep: Any,
) -> int | None:
    from quant_research.ict.ote_strategy import _find_entry_fill, detect_mss_after_sweep

    mss = detect_mss_after_sweep(df, sweep)
    if not mss.fired or mss.fired_index is None:
        return None
    idx, _ = _find_entry_fill(
        df,
        direction=direction,
        entry_price=entry,
        start_index=mss.fired_index + 1,
        timestamp="timestamp",
        high="high",
        low="low",
    )
    return idx


def simulate_bespoke_exit(
    sess: pl.DataFrame,
    *,
    fill_idx: int,
    direction: str,
    entry: float,
    stop: float,
    target: float,
) -> tuple[str, float, float]:
    """Legacy stop-first bar walker (step 3c); returns reason, exit_price, gross_usd."""
    highs = sess["high"].to_list()
    lows = sess["low"].to_list()
    closes = sess["close"].to_list()
    is_long = direction == DIRECTION_LONG
    exit_reason = "time"
    exit_price = closes[-1]
    for i in range(fill_idx, sess.height):
        if is_long:
            if lows[i] <= stop:
                exit_reason, exit_price = "stop", stop
                break
            if highs[i] >= target:
                exit_reason, exit_price = "target", target
                break
        else:
            if highs[i] >= stop:
                exit_reason, exit_price = "stop", stop
                break
            if lows[i] <= target:
                exit_reason, exit_price = "target", target
                break
    pts = (exit_price - entry) if is_long else (entry - exit_price)
    return exit_reason, exit_price, pts * MNQ_POINT_VALUE


def coherent_stop(direction: str, entry: float, stop: float) -> float:
    """Mirror stop to loss side using same risk distance."""
    if direction == DIRECTION_LONG and stop >= entry:
        return entry - max(abs(stop - entry), TICK_SIZE)
    if direction == DIRECTION_SHORT and stop <= entry:
        return entry + max(abs(entry - stop), TICK_SIZE)
    return stop


def net_with_costs(gross_usd: float, exit_reason: str) -> float:
    cost = COMMISSION_RT
    if exit_reason in ("stop", "time"):
        cost += SLIP_STOP_TIME
    elif exit_reason == "target":
        cost += SLIP_TARGET
    return gross_usd - cost


def characterize_populations(
    records: list[OteAttemptRecord],
    sessions: dict[dt.date, pl.DataFrame],
) -> dict[str, Any]:
    """A2: compare kept vs rejected hypothetical outcomes."""
    kept = [r for r in records if r.outcome == "kept" and r.setup is not None]
    rejected = [r for r in records if r.outcome == "rejected"]

    def _sim_frame(recs: list[OteAttemptRecord], *, stop_mode: str) -> dict[str, Any]:
        grosses: list[float] = []
        nets: list[float] = []
        for r in recs:
            if r.session_date is None or r.entry_fill_index is None:
                continue
            if r.direction is None or r.entry_price is None:
                continue
            sess = sessions.get(r.session_date)
            if sess is None:
                continue
            stop = r.stop_price if r.stop_price is not None else r.entry_price
            target = r.target_price if r.target_price is not None else r.entry_price
            if stop_mode == "coherent":
                stop = coherent_stop(r.direction, r.entry_price, stop)
            reason, _, gross = simulate_bespoke_exit(
                sess,
                fill_idx=r.entry_fill_index,
                direction=r.direction,
                entry=r.entry_price,
                stop=stop,
                target=target,
            )
            grosses.append(gross)
            nets.append(net_with_costs(gross, reason))
        return _econ(grosses, nets, stop_mode)

    kept_recs = [_record_from_setup(r.setup, outcome="kept") for r in kept if r.setup]
    kept_econ = _sim_frame(kept_recs, stop_mode="actual")
    rejected_econ_wrong = _sim_frame(rejected, stop_mode="wrong_side")
    rejected_econ_coherent = _sim_frame(rejected, stop_mode="coherent")

    return {
        "kept": kept_econ,
        "rejected_wrong_side": rejected_econ_wrong,
        "rejected_coherent_stop": rejected_econ_coherent,
        "structural": _structural_compare(kept_recs, rejected),
        "counts": {
            "kept": len(kept),
            "rejected": len(rejected),
            "incomplete": sum(1 for r in records if r.outcome == "incomplete"),
        },
    }


def _econ(grosses: list[float], nets: list[float], label: str) -> dict[str, Any]:
    if not grosses:
        return {"label": label, "n": 0}
    wins = sum(1 for g in grosses if g > 0)
    return {
        "label": label,
        "n": len(grosses),
        "total_gross_usd": sum(grosses),
        "total_net_usd": sum(nets),
        "avg_gross_usd": statistics.mean(grosses),
        "avg_net_usd": statistics.mean(nets),
        "win_rate_gross": wins / len(grosses),
        "win_rate_net": sum(1 for n in nets if n > 0) / len(nets),
    }


def _structural_compare(
    kept: list[OteAttemptRecord],
    rejected: list[OteAttemptRecord],
) -> dict[str, Any]:
    def _mean(vals: list[float]) -> float | None:
        return statistics.mean(vals) if vals else None

    def _disp_sizes(recs: list[OteAttemptRecord]) -> list[float]:
        out: list[float] = []
        for r in recs:
            if r.displacement_low is not None and r.displacement_high is not None:
                out.append(r.displacement_high - r.displacement_low)
        return out

    return {
        "kept_avg_sweep_depth_ticks": _mean(
            [r.sweep_depth_ticks for r in kept if r.sweep_depth_ticks is not None]
        ),
        "rejected_avg_sweep_depth_ticks": _mean(
            [r.sweep_depth_ticks for r in rejected if r.sweep_depth_ticks is not None]
        ),
        "kept_avg_entry_vs_stop_ticks": _mean(
            [r.entry_vs_stop_ticks for r in kept if r.entry_vs_stop_ticks is not None]
        ),
        "rejected_avg_entry_vs_stop_ticks": _mean(
            [r.entry_vs_stop_ticks for r in rejected if r.entry_vs_stop_ticks is not None]
        ),
        "kept_avg_displacement_pts": _mean(_disp_sizes(kept)),
    }


def classify_reject_mechanism(record: OteAttemptRecord) -> str:
    """A3 mechanism tag for a rejected attempt."""
    if record.reject_reason != REJECT_STOP_WRONG_SIDE:
        return "other_geometry"
    if record.entry_vs_stop_ticks is not None and record.entry_vs_stop_ticks < 0:
        return "shallow_retracement_vs_swept_stop"
    return "stop_placement_bug"


def trace_rejected_samples(
    rejected: list[OteAttemptRecord],
    sessions: dict[dt.date, pl.DataFrame],
    *,
    n: int = 20,
) -> list[dict[str, Any]]:
    """Return traced examples for A3."""
    samples = rejected[:n]
    traces: list[dict[str, Any]] = []
    for r in samples:
        gross = None
        reason = None
        if r.session_date and r.entry_fill_index is not None and r.direction:
            sess = sessions.get(r.session_date)
            if sess is not None and r.stop_price and r.target_price and r.entry_price:
                reason, exit_px, gross = simulate_bespoke_exit(
                    sess,
                    fill_idx=r.entry_fill_index,
                    direction=r.direction,
                    entry=r.entry_price,
                    stop=r.stop_price,
                    target=r.target_price,
                )
        traces.append(
            {
                "session": str(r.session_date),
                "direction": r.direction,
                "entry": r.entry_price,
                "stop": r.stop_price,
                "target": r.target_price,
                "entry_vs_stop_ticks": r.entry_vs_stop_ticks,
                "mechanism": classify_reject_mechanism(r),
                "hypothetical_wrong_side_gross": gross,
                "exit_if_traded": reason if gross is not None else None,
            }
        )
    return traces


def parity_kept_m4_vs_bespoke(
    kept: list[OteSetup],
    sessions: dict[dt.date, pl.DataFrame],
    *,
    sample_size: int = 500,
) -> dict[str, Any]:
    """Compare M4 vs bespoke on the same kept setups."""
    import random

    cfg = ote_research_backtest_config()
    sample = kept if len(kept) <= sample_size else random.sample(kept, sample_size)
    diffs: list[float] = []
    exact = 0
    for setup in sample:
        if setup.session_date is None or setup.entry_fill_index is None:
            continue
        sess = sessions.get(setup.session_date)
        if sess is None:
            continue
        m4 = execute_setup(setup, sess, config=cfg)
        if not isinstance(m4, OteExecutedTrade):
            continue
        reason, _, gross = simulate_bespoke_exit(
            sess,
            fill_idx=setup.entry_fill_index,
            direction=setup.direction,
            entry=setup.entry_price,
            stop=setup.stop_price,
            target=setup.target_price,
        )
        net_bespoke = net_with_costs(gross, reason)
        diffs.append(m4.net_pnl - net_bespoke)
        if abs(m4.gross_pnl - gross) < 1e-6 and abs(m4.net_pnl - net_bespoke) < 0.02:
            exact += 1
    return {
        "sampled": len(diffs),
        "exact_gross_and_net_matches": exact,
        "avg_net_diff_m4_minus_bespoke": statistics.mean(diffs) if diffs else None,
        "max_abs_net_diff": max(abs(d) for d in diffs) if diffs else None,
    }
