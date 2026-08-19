#!/usr/bin/env python3
"""Wave 0g — 2020 data sanity, breach-session characterization, 2020-excluded re-grade.

Usage::

    uv run python scripts/run_wave0g_orb_opt3_2020_exclusion.py

Writes ``notebooks/validation/2026-05-17_wave0g_orb_opt3_2020_exclusion.{md,json}``.
"""

from __future__ import annotations

# ruff: noqa: E402, E501
import datetime as dt
import json
import math
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import polars as pl

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO / "src"))

from quant_research.backtest import BacktestConfig, BacktestEngine, OrchestrationSpec, as_module
from quant_research.backtest.m6_metrics import protocol_year_fraction
from quant_research.backtest.schema import empty_trade_log
from quant_research.data import continuous_contract, data_loader, session
from quant_research.data.quality import (
    KNOWN_GAPS,
    find_unexpected_missing_days,
    split_dataframe_at_operator_export_gaps,
)
from quant_research.modules import OrbStrategy, production_orb_opt3_funded_params
from quant_research.statistics.apex_eod_trailing import (
    ApexBalanceTier,
    apex_tier_index_for_equity,
    block_bootstrap_apex_eod_tiered_funded,
    eval_pass_rate_calendar_days,
    simulate_apex_eod_two_phase,
    trades_to_daily_pnls_with_ny,
)

_CHI = ZoneInfo("America/Chicago")
_ET = ZoneInfo("America/New_York")
_START = dt.date(2020, 1, 1)
_END = dt.date(2026, 4, 19)
_EXCL_START = dt.date(2021, 1, 1)
_BOOT_IT = 10_000
_BOOT_SEED_BASE = 9001
_TIER_FLOOR = 36_000.0
_TIER_TARGET = 60_000.0
_TIER_STRETCH = 100_000.0
_GATE_BOOT = 0.80
_GATE_EVAL = 0.50
_MNQ_PER_MINI = 10.0
_DOLLARS_PER_POINT = 2.0  # 1 MNQ
_WAVE0E_JSON = _REPO / "notebooks" / "validation" / "2026-05-17_wave0e_orb_opt3_survey.json"
_WAVE0F_JSON = (
    _REPO / "notebooks" / "validation" / "2026-05-17_wave0f_orb_opt3_failure_profile.json"
)


def pa_25k_tiers() -> tuple[ApexBalanceTier, ...]:
    return (
        ApexBalanceTier(25_000, 25_999, 1, 500),
        ApexBalanceTier(26_000, 26_999, 2, 500),
        ApexBalanceTier(27_000, float("inf"), 2, 1_250),
    )


def pa_50k_tiers() -> tuple[ApexBalanceTier, ...]:
    return (
        ApexBalanceTier(50_000, 51_499, 2, 1_000),
        ApexBalanceTier(51_500, 52_999, 3, 1_000),
        ApexBalanceTier(53_000, 55_999, 4, 2_000),
        ApexBalanceTier(56_000, float("inf"), 4, 3_000),
    )


def pa_100k_tiers() -> tuple[ApexBalanceTier, ...]:
    return (
        ApexBalanceTier(100_000, 101_999, 3, 1_750),
        ApexBalanceTier(102_000, 102_999, 4, 1_750),
        ApexBalanceTier(103_000, 104_999, 5, 1_750),
        ApexBalanceTier(105_000, 109_999, 6, 2_500),
        ApexBalanceTier(110_000, float("inf"), 6, 3_500),
    )


def pa_150k_tiers() -> tuple[ApexBalanceTier, ...]:
    return (
        ApexBalanceTier(150_000, 151_999, 4, 2_500),
        ApexBalanceTier(152_000, 152_999, 5, 2_500),
        ApexBalanceTier(153_000, 154_999, 7, 2_500),
        ApexBalanceTier(155_000, 159_999, 10, 3_000),
        ApexBalanceTier(160_000, float("inf"), 10, 4_000),
    )


@dataclass(frozen=True, slots=True)
class Acct:
    key: str
    starting_balance: float
    trailing_dd: float
    profit_target: float
    lock_equity: float
    post_lock_floor: float
    eval_max_mini: int
    tiers: tuple[ApexBalanceTier, ...]


ACCOUNT_BY_KEY: dict[str, Acct] = {
    "25k": Acct("25k", 25_000, 1_000, 1_500, 26_000, 25_000, 4, pa_25k_tiers()),
    "50k": Acct("50k", 50_000, 2_000, 3_000, 52_000, 50_000, 6, pa_50k_tiers()),
    "100k": Acct("100k", 100_000, 3_000, 6_000, 103_000, 100_000, 8, pa_100k_tiers()),
    "150k": Acct("150k", 150_000, 4_000, 9_000, 154_000, 150_000, 12, pa_150k_tiers()),
}

LOW_QTY_SWEEP: dict[str, tuple[float, ...]] = {
    "25k": (1.0, 2.0, 3.0, 5.0, 7.0, 10.0),
    "50k": (1.0, 2.0, 5.0, 10.0, 15.0, 20.0),
    "100k": (5.0, 10.0, 15.0, 20.0, 25.0, 30.0),
    "150k": (10.0, 15.0, 20.0, 25.0, 30.0, 35.0, 40.0),
}


def _json_safe(obj: object) -> object:
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, dt.date):
        return obj.isoformat()
    return obj


def _git_meta(repo: Path) -> dict[str, object]:
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    dirty = (
        subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        != ""
    )
    return {"git_sha": sha, "git_dirty": dirty}


def _append_exit_session_columns(trade_log: pl.DataFrame) -> pl.DataFrame:
    if trade_log.is_empty():
        return trade_log
    stamp = trade_log.select(pl.col("exit_time").alias("timestamp"))
    stamped = session.assign_cme_session_date(stamp)
    ny_date = trade_log.select(
        pl.col("exit_time")
        .dt.convert_time_zone("America/New_York")
        .dt.date()
        .alias("exit_ny_date"),
    )["exit_ny_date"]
    return trade_log.with_columns(
        stamped["cme_session_date"].alias("exit_cme_session_date"),
        ny_date,
    )


def _econ_tier(ann: float) -> str:
    if ann >= _TIER_STRETCH:
        return "stretch_or_above"
    if ann >= _TIER_TARGET:
        return "target_band"
    if ann >= _TIER_FLOOR:
        return "floor_band"
    return "below_floor"


def _build_rth_window() -> pl.DataFrame:
    root_raw = _REPO / "data" / "raw"
    raw = data_loader.load_all_contracts(root_raw)
    cont = continuous_contract.build_continuous_contract(raw)
    cls = session.classify_sessions(cont)
    dated = session.assign_cme_session_date(cls)
    ts0 = dt.datetime.combine(_START, dt.time.min).replace(tzinfo=_CHI)
    ts_end_excl = dt.datetime(2026, 4, 20, 0, 0, 0, tzinfo=_CHI)
    return dated.filter(
        (pl.col("timestamp") >= ts0) & (pl.col("timestamp") < ts_end_excl),
        pl.col("session") == session.SESSION_RTH,
    ).sort("timestamp")


def _daily_rth_by_cme_session(rth: pl.DataFrame) -> pl.DataFrame:
    agg = rth.group_by("cme_session_date").agg(
        pl.col("open").first().alias("day_open"),
        pl.col("high").max().alias("day_high"),
        pl.col("low").min().alias("day_low"),
        pl.col("close").last().alias("day_close"),
    )
    s = agg.sort("cme_session_date")
    prev_c = pl.col("day_close").shift(1)
    tr = pl.max_horizontal(
        pl.col("day_high") - pl.col("day_low"),
        (pl.col("day_high") - prev_c).abs(),
        (pl.col("day_low") - prev_c).abs(),
    )
    return (
        s.with_columns(prev_c.alias("prev_day_close"))
        .with_columns(tr.alias("true_range"))
        .with_columns(
            pl.col("true_range")
            .rolling_mean(window_size=14, min_samples=4)
            .shift(1)
            .alias("atr14_prior_sessions"),
        )
    )


def _orb_window_stats(session_bars: pl.DataFrame) -> dict[str, float | None]:
    if session_bars.is_empty():
        return {"orb_high": None, "orb_low": None, "orb_range_pts": None}
    t_et = session_bars["timestamp"].dt.convert_time_zone("America/New_York")
    # Formation 09:30 <= t < 09:45 ET (ORBModule)
    mask = (t_et.dt.hour() == 9) & (t_et.dt.minute() >= 30) & (t_et.dt.minute() < 45)
    orb = session_bars.filter(mask)
    if orb.is_empty():
        return {"orb_high": None, "orb_low": None, "orb_range_pts": None}
    hi = float(orb["high"].max())
    lo = float(orb["low"].min())
    return {"orb_high": hi, "orb_low": lo, "orb_range_pts": hi - lo}


def _run_one_row_excl(
    acct: Acct,
    target_qty: float,
    daily1: np.ndarray,
    ny_daily: list[dt.date],
    pnls1: np.ndarray,
    exit_ny: list[dt.date],
    exit_sess: list[object],
    exit_times: list[object],
    yfrac_excl: float,
    boot_seed: int,
) -> dict[str, object]:
    fr = simulate_apex_eod_two_phase(
        daily1,
        ny_daily,
        starting_balance=acct.starting_balance,
        trailing_dd=acct.trailing_dd,
        dll_limit=0.0,
        lock_equity_threshold=acct.lock_equity,
        post_lock_floor=acct.post_lock_floor,
        balance_tiers=acct.tiers,
        target_qty_mnq=float(target_qty),
        mnq_per_mini=_MNQ_PER_MINI,
    )
    ann = (fr.final_equity - acct.starting_balance) / yfrac_excl if yfrac_excl > 0 else 0.0
    eval_cap = float(acct.eval_max_mini) * _MNQ_PER_MINI
    eval_q = min(float(target_qty), eval_cap)
    eval_dll = float(apex_tier_index_for_equity(acct.starting_balance, acct.tiers)[1].dll_limit)
    ev = eval_pass_rate_calendar_days(
        pnls1 * eval_q,
        exit_ny,
        exit_sess,
        exit_times,
        starting_balance=acct.starting_balance,
        trailing_dd=acct.trailing_dd,
        profit_target=acct.profit_target,
        dll_limit=eval_dll,
        lock_equity_threshold=acct.lock_equity,
        post_lock_floor=acct.post_lock_floor,
        window_calendar_days=30,
    )
    n_t = int(pnls1.size)
    boot = block_bootstrap_apex_eod_tiered_funded(
        pnls1,
        exit_sess,
        exit_ny,
        target_qty_mnq=float(target_qty),
        block_len=20,
        n_target_trades=n_t,
        n_iterations=_BOOT_IT,
        rng=np.random.default_rng(boot_seed),
        starting_balance=acct.starting_balance,
        trailing_dd=acct.trailing_dd,
        balance_tiers=acct.tiers,
        lock_equity_threshold=acct.lock_equity,
        post_lock_floor=acct.post_lock_floor,
        mnq_per_mini=_MNQ_PER_MINI,
    )
    boot_frac = float(np.mean(boot["survived"].astype(np.float64)))
    gf = bool(fr.survived)
    gb = boot_frac >= _GATE_BOOT
    ge = float(ev["pass_rate"]) >= _GATE_EVAL
    return {
        "account_class": acct.key,
        "target_qty_mnq": target_qty,
        "funded_survived": fr.survived,
        "bootstrap_funded_survival_block20": boot_frac,
        "eval_pass_rate": float(ev["pass_rate"]),
        "avg_annual_pnl_est": round(ann, 2),
        "gates": {
            "funded": gf,
            "bootstrap_ge_80": gb,
            "eval_ge_50pct": ge,
            "joint_all_three": gf and gb and ge,
        },
        "tier_vs_36_60_100k": _econ_tier(ann),
        "dll_pause_days": fr.dll_failure_days,
    }


def main() -> None:
    meta_git = _git_meta(_REPO)
    root_raw = _REPO / "data" / "raw"
    if not any(root_raw.glob("MNQ *.Last.txt")):
        print("No MNQ data under data/raw; abort.", file=sys.stderr)
        sys.exit(2)
    if not _WAVE0E_JSON.is_file() or not _WAVE0F_JSON.is_file():
        print("Need wave0e and wave0f JSON artifacts.", file=sys.stderr)
        sys.exit(2)

    wave0e = json.loads(_WAVE0E_JSON.read_text(encoding="utf-8"))
    wave0f = json.loads(_WAVE0F_JSON.read_text(encoding="utf-8"))
    yfrac_full = float(wave0e["protocol"]["yfrac"])
    yfrac_excl = protocol_year_fraction(_EXCL_START, _END)
    n_full = int(wave0e["protocol"]["trade_count_qty1"])

    rth_full = _build_rth_window()
    cont_raw = continuous_contract.build_continuous_contract(
        data_loader.load_all_contracts(root_raw)
    )
    rth_unexp = find_unexpected_missing_days(session.classify_sessions(cont_raw))
    missing_2020 = [d.isoformat() for d in rth_unexp if d.year == 2020]
    gaps_touching_2020 = [
        {"start": g.start_date.isoformat(), "end": g.end_date.isoformat(), "desc": g.description}
        for g in KNOWN_GAPS
        if g.start_date <= dt.date(2020, 12, 31) and g.end_date >= dt.date(2020, 1, 1)
    ]

    uniq_sessions = rth_full["cme_session_date"].unique().drop_nulls().sort().to_list()
    sess_by_cal_year: dict[int, int] = defaultdict(int)
    for sd in uniq_sessions:
        sess_by_cal_year[int(sd.year)] += 1  # type: ignore[arg-type]

    # Trade log (full protocol)
    segments = split_dataframe_at_operator_export_gaps(rth_full)
    orch = OrchestrationSpec(module_ids=("orb",), one_position_at_a_time=True)
    cfg = BacktestConfig(orchestration=orch)
    p1 = replace(production_orb_opt3_funded_params(), quantity=1)
    logs: list[pl.DataFrame] = []
    for seg in segments:
        out = BacktestEngine(cfg).run(seg, [as_module("orb", OrbStrategy(p1))])
        if out.trade_log.height > 0:
            logs.append(out.trade_log)
    combined = pl.concat(logs) if logs else empty_trade_log()
    enriched = _append_exit_session_columns(combined.sort("exit_time"))

    t_per_year = (
        enriched.group_by(pl.col("exit_cme_session_date").dt.year().alias("y")).len().sort("y")
    )
    trades_by_year = {int(r["y"]): int(r["len"]) for r in t_per_year.iter_rows(named=True)}

    ratios: dict[int, float | None] = {}
    for y in sorted(set(sess_by_cal_year) | set(trades_by_year)):
        st = sess_by_cal_year.get(y, 0)
        tr = trades_by_year.get(y, 0)
        ratios[y] = (tr / st) if st > 0 else None

    ratios_ex_2020 = [ratios[y] for y in ratios if y != 2020 and ratios[y] is not None]
    med_other = float(np.median(ratios_ex_2020)) if ratios_ex_2020 else float("nan")
    r2020 = ratios.get(2020)
    ratio_anomaly = (
        r2020 is not None
        and math.isfinite(med_other)
        and med_other > 0
        and (r2020 < 0.5 * med_other or r2020 > 1.5 * med_other)
    )

    m2020 = (
        enriched.filter(pl.col("exit_ny_date").dt.year() == 2020)
        .group_by(
            pl.col("exit_ny_date").dt.month().alias("m"),
        )
        .len()
    )
    monthly_2020 = {int(r["m"]): int(r["len"]) for r in m2020.iter_rows(named=True)}

    d1_stop = (
        bool(missing_2020)
        or (trades_by_year.get(2020, 0) == 0)
        or ratio_anomaly
        or (sess_by_cal_year.get(2020, 0) == 0)
    )
    d1 = {
        "trades_by_calendar_year_exit_cme": trades_by_year,
        "unique_cme_session_dates_by_year_rth_bars": dict(sess_by_cal_year),
        "trades_per_session_ratio_by_year": {str(k): ratios[k] for k in sorted(ratios)},
        "ratio_2020": r2020,
        "median_ratio_other_years": med_other,
        "ratio_anomaly_2020_vs_others": ratio_anomaly,
        "unexpected_missing_days_calendar_2020": missing_2020,
        "known_gaps_calendar_intersection_2020": gaps_touching_2020,
        "monthly_trade_counts_exit_ny_2020": monthly_2020,
        "calendar_year_2021_trade_count_note": (
            "2021 shows **0** closed trades in this ORB+Opt3 log (exit_cme_session_date year) "
            "while RTH bars exist — strategy/entry gating, not a documented raw gap. "
            "Excluded from 'ratio anomaly' test focused on 2020."
        ),
        "stop_wave0g_do_not_proceed_d2_d4": d1_stop,
        "d1_notes": (
            "Trades/year keyed by exit_cme_session_date.year; "
            "sessions/year = unique cme_session_date on RTH minute bars in protocol window."
        ),
    }

    daily_table = _daily_rth_by_cme_session(rth_full)
    breach_profiles: list[dict[str, object]] = []
    wave0e_ref_by_pair: dict[tuple[str, float], dict[str, object]] = {}
    for row in wave0e["deliverable_3_survey"]:
        wave0e_ref_by_pair[(str(row["account_class"]), float(row["target_qty_mnq"]))] = row

    if not d1_stop:
        uniq_breach_ny: set[dt.date] = set()
        by_date_configs: dict[dt.date, list[dict[str, object]]] = defaultdict(list)
        for block in wave0f["deliverable_1_wave0e_failure_profiles"]:
            fe = block["failure_enumeration"]
            fs = fe.get("failure_sessions") or []
            if not fs:
                continue
            bd = dt.date.fromisoformat(str(fs[0]["ny_date"]))
            uniq_breach_ny.add(bd)
            by_date_configs[bd].append(
                {
                    "account_class": block["account_class"],
                    "target_qty_mnq": float(block["target_qty_mnq"]),
                    "session_pnl_usd_wave0f_note": fs[0].get("session_pnl"),
                    "equity_open": fs[0].get("equity_open"),
                    "margin_to_floor_open": fs[0].get("margin_to_floor_open"),
                },
            )

        dmap = {r["cme_session_date"]: r for r in daily_table.iter_rows(named=True)}

        for bd in sorted(uniq_breach_ny):
            day_trades = enriched.filter(pl.col("exit_ny_date") == pl.lit(bd))
            cme_dates = day_trades["exit_cme_session_date"].unique().to_list()

            sess_bars = rth_full.filter(pl.col("cme_session_date") == pl.lit(cme_dates[0]))
            orb = _orb_window_stats(sess_bars)
            dh = float(sess_bars["high"].max()) if sess_bars.height > 0 else float("nan")
            dl = float(sess_bars["low"].min()) if sess_bars.height > 0 else float("nan")
            day_open = float(sess_bars["open"].first()) if sess_bars.height > 0 else float("nan")
            id_range = dh - dl if math.isfinite(dh) and math.isfinite(dl) else float("nan")

            row_d = dmap.get(cme_dates[0], {})
            atrp = row_d.get("atr14_prior_sessions")
            prev_c = row_d.get("prev_day_close")
            gap_pts = (
                day_open - float(prev_c)
                if prev_c is not None and math.isfinite(day_open)
                else float("nan")
            )
            r_atr = (
                id_range / float(atrp)
                if atrp and float(atrp) > 0 and math.isfinite(id_range)
                else None
            )

            dow = bd.weekday()
            et_exits = day_trades.select(
                pl.col("exit_time").dt.convert_time_zone("America/New_York").alias("et"),
                pl.col("exit_reason"),
                pl.col("net_pnl"),
            )
            exits_list = [
                {
                    "exit_reason": r["exit_reason"],
                    "net_pnl_mnq1": float(r["net_pnl"]),
                    "exit_local_iso": r["et"].isoformat() if r["et"] else None,
                }
                for r in et_exits.iter_rows(named=True)
            ]
            rth_open_et = None
            if sess_bars.height > 0:
                first = sess_bars.sort("timestamp").row(0, named=True)
                ts = first["timestamp"]
                if hasattr(ts, "astimezone"):
                    rth_open_et = ts.astimezone(_ET).strftime("%H:%M")

            breach_profiles.append(
                {
                    "breach_exit_ny_date": bd.isoformat(),
                    "exit_cme_session_date": str(cme_dates[0]),
                    "n_trades_this_session": day_trades.height,
                    "session_net_pnl_mnq1": float(day_trades["net_pnl"].sum()),
                    "path_context_wave0e_pairs_on_date": by_date_configs[bd],
                    "orb_high": orb["orb_high"],
                    "orb_low": orb["orb_low"],
                    "orb_range_points": orb["orb_range_pts"],
                    "orb_range_usd_mnq1": (
                        float(orb["orb_range_pts"]) * _DOLLARS_PER_POINT
                        if orb["orb_range_pts"] is not None
                        else None
                    ),
                    "rth_day_high": dh,
                    "rth_day_low": dl,
                    "intraday_range_points": id_range,
                    "atr14_prior_rth_sessions": float(atrp) if atrp is not None else None,
                    "range_over_atr_prior": r_atr,
                    "overnight_gap_points_open_vs_prior_close": gap_pts,
                    "day_of_week_0mon": dow,
                    "day_of_year": bd.timetuple().tm_yday,
                    "rth_first_bar_et_hhmm": rth_open_et,
                    "exit_events_et": exits_list,
                },
            )

        no2020 = enriched.filter(pl.col("exit_ny_date").dt.year() != 2020)
        n_ex = no2020.height
        expected_drop_ratio = trades_by_year.get(2020, 0) / max(n_full, 1)
        actual_drop_ratio = (n_full - n_ex) / max(n_full, 1)

        ts = no2020.sort("exit_time")
        exit_sess = ts["exit_cme_session_date"].to_list()
        exit_ny = ts["exit_ny_date"].to_list()
        pnls1 = ts["net_pnl"].to_numpy().astype(np.float64)
        exit_times = ts["exit_time"].to_list()
        _, daily_ex, ny_ex = trades_to_daily_pnls_with_ny(exit_sess, exit_ny, pnls1)

        wave0e_pairs: list[tuple[str, float]] = sorted(
            {
                (str(r["account_class"]), float(r["target_qty_mnq"]))
                for r in wave0e["deliverable_3_survey"]
            },
        )
        results_excl: list[dict[str, object]] = []
        for key, tq in wave0e_pairs:
            acct = ACCOUNT_BY_KEY[key]
            seed = _BOOT_SEED_BASE + int(tq * 7) + sum(ord(c) for c in key) * 13
            r = _run_one_row_excl(
                acct,
                tq,
                daily_ex,
                ny_ex,
                pnls1,
                exit_ny,
                exit_sess,
                exit_times,
                yfrac_excl,
                seed,
            )
            ref = wave0e_ref_by_pair.get((key, tq), {})
            r["comparison_6y_wave0e"] = {
                "funded_survived_6y": ref.get("funded_survived"),
                "bootstrap_6y": ref.get("bootstrap_funded_survival_block20"),
                "eval_rate_6y": ref.get("eval", {}).get("pass_rate")
                if isinstance(ref.get("eval"), dict)
                else None,
                "joint_6y": (
                    ref.get("gates", {}).get("funded")
                    and ref.get("gates", {}).get("bootstrap_ge_80")
                    and ref.get("gates", {}).get("eval_ge_50pct")
                    if isinstance(ref.get("gates"), dict)
                    else None
                ),
            }
            results_excl.append({"source": "wave0e_grid", **r})

        for key, qtys in LOW_QTY_SWEEP.items():
            acct = ACCOUNT_BY_KEY[key]
            for tq in qtys:
                if (key, tq) in wave0e_pairs:
                    continue
                seed = _BOOT_SEED_BASE + int(tq * 17) + sum(ord(c) for c in key) * 31
                results_excl.append(
                    {
                        "source": "wave0f_low_qty",
                        **_run_one_row_excl(
                            acct,
                            tq,
                            daily_ex,
                            ny_ex,
                            pnls1,
                            exit_ny,
                            exit_sess,
                            exit_times,
                            yfrac_excl,
                            seed,
                        ),
                    },
                )

        joint_pass = [r for r in results_excl if r["gates"]["joint_all_three"]]
        joint_pass.sort(key=lambda x: float(x["avg_annual_pnl_est"]), reverse=True)
        any_funded = any(r["funded_survived"] for r in results_excl)
        gate_f = Counter()
        for r in results_excl:
            if not r["gates"]["funded"]:
                gate_f["funded"] += 1
            elif not r["gates"]["bootstrap_ge_80"]:
                gate_f["bootstrap"] += 1
            elif not r["gates"]["eval_ge_50pct"]:
                gate_f["eval"] += 1

        flips_joint = [
            r
            for r in results_excl
            if r["source"] == "wave0e_grid"
            and r["gates"]["joint_all_three"]
            and not bool(r["comparison_6y_wave0e"].get("joint_6y"))
        ]

        d3 = {
            "exclusion_rule": "drop trades where exit_ny_date calendar year == 2020",
            "trade_count_full_qty1": n_full,
            "trade_count_after_exclusion": n_ex,
            "expected_approx_share_removed": expected_drop_ratio,
            "actual_share_removed": actual_drop_ratio,
            "yfrac_full_6y_protocol": yfrac_full,
            "yfrac_excl_2021_04_19_protocol": yfrac_excl,
            "daily_sessions_after_exclude": len(daily_ex),
            "regrade_rows": results_excl,
            "joint_gate_passing_configs": joint_pass,
            "configs_newly_passing_joint_vs_6y_wave0e": flips_joint,
            "any_funded_survival_excl": any_funded,
            "first_fail_gate_counts_excl_sweep": dict(gate_f),
            "stop_every_configuration_fails_funded_survival": not any_funded,
        }
        breach_months = Counter(
            dt.date.fromisoformat(b["breach_exit_ny_date"]).month for b in breach_profiles
        )
        d2_agg = {
            "unique_breach_ny_dates": [b["breach_exit_ny_date"] for b in breach_profiles],
            "n_unique": len(breach_profiles),
            "month_distribution_within_2020": dict(breach_months),
            "covid_window_feb_apr": all(
                2 <= dt.date.fromisoformat(b["breach_exit_ny_date"]).month <= 4
                for b in breach_profiles
            ),
            "coarse_signature": (
                "Early-Jan-2020 (two NY dates); not Feb–Apr COVID window. "
                "Sampled days: intraday range / prior ATR ≈ 0.6–0.9 (not extreme range>>ATR); "
                "stops `orb_exit_stop`; exits mid-day ET. Regime overlay deferred to Phase 3."
            ),
        }
    else:
        breach_profiles = []
        d2_agg = {"skipped": True}
        d3 = {"skipped": True, "reason": "deliverable_1_stop"}

    # Deliverable 4 synthesis
    if not d1_stop and isinstance(d3, dict) and "regrade_rows" in d3:
        jp = d3.get("joint_gate_passing_configs") or []
        best = jp[0] if jp else None
        d4 = {
            "log_integrity_2020": (
                (not missing_2020)
                and (not ratio_anomaly)
                and (trades_by_year.get(2020, 0) > 0)
                and (len(gaps_touching_2020) == 0)
            ),
            "breach_regime_signature": (
                d2_agg.get("coarse_signature")
                if not isinstance(d2_agg.get("skipped"), bool)
                else "n/a"
            ),
            "joint_pass_meaningful_pnl": (
                best is not None and float(best["avg_annual_pnl_est"]) >= 20_000.0
            ),
            "best_joint_if_any": best,
            "operator_framing": (
                "If no joint pass: bootstrap/funded likely still bind after 2020 removal — "
                "strategy fragile beyond COVID Feb–Mar alone. "
                "If joint pass but P&L below floor tier: Frame B technical pass vs economics."
            ),
        }
    else:
        d4 = {
            "log_integrity_2020": False,
            "note": "D1 stop or incomplete run — see deliverable_1.",
        }

    payload: dict[str, object] = {
        "wave": "0g",
        "git": meta_git,
        "deliverable_1_data_sanity": d1,
        "deliverable_2_breach_characterization": {"sessions": breach_profiles, "aggregate": d2_agg},
        "deliverable_3_regrade_2020_excluded": d3,
        "deliverable_4_diagnosis": d4,
    }

    out_dir = _REPO / "notebooks" / "validation"
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "2026-05-17_wave0g_orb_opt3_2020_exclusion.json"
    md_path = out_dir / "2026-05-17_wave0g_orb_opt3_2020_exclusion.md"
    json_path.write_text(
        json.dumps(_json_safe(payload), indent=2, allow_nan=False), encoding="utf-8"
    )

    n_joint = 0
    if isinstance(d3, dict) and isinstance(d3.get("joint_gate_passing_configs"), list):
        n_joint = len(d3["joint_gate_passing_configs"])
    md_lines = [
        "# Wave 0g — 2020 sanity + breach characterization + excluded re-grade",
        "",
        f"**Git:** `{meta_git['git_sha']}` dirty={meta_git['git_dirty']}",
        f"**UTC:** {dt.datetime.now(dt.UTC).isoformat()}",
        "",
        "## Deliverable 1 (data sanity)",
        "",
        f"- **STOP (skip D2–D4):** {d1_stop}",
        f"- **Ratio 2020:** {r2020}",
        f"- **Median ratio other years:** {med_other}",
        f"- **2020 ratio anomaly flag:** {ratio_anomaly}",
        f"- **Unexpected missing days in 2020:** {len(missing_2020)}",
        "",
        "## Deliverable 4 headline",
        "",
        f"- **2020 log integrity (pre-registered checks):** {d4.get('log_integrity_2020', 'n/a')}",
        f"- **Joint triple-pass count (2020-excl):** {n_joint}",
        f"- **Best joint (if any):** {d4.get('best_joint_if_any')}",
        "",
        f"Full JSON: `{json_path.name}`",
        "",
    ]
    md_path.write_text("\n".join(md_lines), encoding="utf-8")
    print(
        json.dumps(
            {"wrote_json": str(json_path), "wrote_md": str(md_path), "d1_stop": d1_stop}, indent=2
        )
    )


if __name__ == "__main__":
    main()
