"""Bar-level simulators for Wave 1 Stage 1 Track 1 MNQ hypotheses (coarse screening)."""

from __future__ import annotations

import datetime as dt
from collections import deque

import polars as pl

from quant_research.research_wave1.track1_metrics import (
    GATE_EVAL_YEARS,
    MNQ_USD_PER_POINT_QTY1,
    TradeRow,
)

_EASTERN = "America/New_York"

T_ET_OPEN = dt.time(9, 30)
T_ET_OR30_END = dt.time(10, 0)
# Minutes 31–90 after 09:30 ET → [10:00, 12:00) ET
T_ET_DRIVE_START = dt.time(10, 0)
T_ET_DRIVE_END = dt.time(12, 0)
T_ET_LUNCH_START = dt.time(11, 30)
T_ET_LUNCH_END = dt.time(13, 30)
T_ET_H11_OR_END = dt.time(9, 45)
T_ET_H11_BREAKOUT_END = dt.time(10, 30)
T_ET_H11_TIME_EXIT = dt.time(11, 0)
T_ET_SESSION_END_GATE = dt.time(16, 0)


def _usd_from_points(direction: int, entry: float, exit_px: float) -> float:
    return float(direction * (exit_px - entry) * MNQ_USD_PER_POINT_QTY1)


def _iterate_bar_conflict(
    direction: int,
    stop_px: float,
    target_px: float,
    o: float,
    high: float,
    low: float,
    *,
    pessimistic_conflict: bool = True,
) -> tuple[bool, str, float]:
    """Return (hit_exit, tag, exit_price_fill). pessimistic_conflict: dual touch → stop first."""
    if direction == 1:
        hit_stop = low <= stop_px
        hit_t = high >= target_px
        if hit_stop and hit_t:
            return (True, "stop", stop_px) if pessimistic_conflict else (True, "target", target_px)
        if hit_stop:
            return True, "stop", stop_px
        if hit_t:
            return True, "target", target_px
        return False, "open", o
    if direction == -1:
        hit_stop = high >= stop_px
        hit_t = low <= target_px
        if hit_stop and hit_t:
            return (True, "stop", stop_px) if pessimistic_conflict else (True, "target", target_px)
        if hit_stop:
            return True, "stop", stop_px
        if hit_t:
            return True, "target", target_px
        return False, "open", o
    msg = "direction must be +1/-1"
    raise ValueError(msg)


def simulate_trade_intraday(
    bars: pl.DataFrame,
    *,
    entry_idx_offset: int,
    direction: int,
    stop_px: float,
    target_px: float,
    entry_price: float,
    cme_session_date: dt.date,
    pessimistic_conflict: bool = True,
    max_et_time_exit: dt.time | None = None,
    exit_tag_time: str = "time_et",
) -> TradeRow | None:
    """Walk minute bars starting at ``entry_idx_offset`` (usually entry bar)."""
    n = bars.height
    if entry_idx_offset >= n:
        return None
    px_in = bars["close"][entry_idx_offset]
    if abs(px_in - entry_price) > 25.0:
        entry_price = float(px_in)
    last_ts_et = bars["ts_et"][n - 1]
    for i in range(entry_idx_offset, n):
        o = float(bars["open"][i])
        hhi = float(bars["high"][i])
        lw = float(bars["low"][i])
        clo = float(bars["close"][i])
        ts_et = bars["ts_et"][i]
        done, _tag, xp = _iterate_bar_conflict(
            direction,
            stop_px,
            target_px,
            o,
            hhi,
            lw,
            pessimistic_conflict=pessimistic_conflict,
        )
        if done:
            pnl_usd = _usd_from_points(direction, entry_price, xp)
            return TradeRow(
                exit_et_date=ts_et.date(),
                cme_session_date=cme_session_date,
                pnl_usd_qty1=float(pnl_usd),
                gross_points=float(direction * (xp - entry_price)),
                exit_reason=str(_tag),
            )
        et_t = ts_et.time()
        if max_et_time_exit is not None and et_t >= max_et_time_exit:
            pnl_usd = _usd_from_points(direction, entry_price, clo)
            return TradeRow(
                exit_et_date=ts_et.date(),
                cme_session_date=cme_session_date,
                pnl_usd_qty1=float(pnl_usd),
                gross_points=float(direction * (clo - entry_price)),
                exit_reason=str(exit_tag_time),
            )
    clo = float(bars["close"][n - 1])
    pnl_usd = _usd_from_points(direction, entry_price, clo)
    return TradeRow(
        exit_et_date=last_ts_et.date(),
        cme_session_date=cme_session_date,
        pnl_usd_qty1=float(pnl_usd),
        gross_points=float(direction * (clo - entry_price)),
        exit_reason="session_end",
    )


def prepare_et_frame(mnq_rth: pl.DataFrame) -> pl.DataFrame:
    return (
        mnq_rth.sort("timestamp")
        .filter(pl.col("cme_session_date").is_not_null())
        .filter(
            pl.col("cme_session_date")
            .dt.year()
            .is_between(
                GATE_EVAL_YEARS[0],
                GATE_EVAL_YEARS[-1],
            )
        )
        .with_columns(
            pl.col("timestamp").dt.convert_time_zone(_EASTERN).alias("ts_et"),
        )
    )


def simulate_h1(mnq_et: pl.DataFrame, sweep_points: tuple[int, ...]) -> dict[int, list[TradeRow]]:
    """Opening-drive exhaustion fade; normalized OR triggers; drive window 10:00–12:00 ET."""
    out: dict[int, list[TradeRow]] = {x: [] for x in sweep_points}
    hist_prior_or = deque[float](maxlen=14)

    uniq = sorted(pl.Series(mnq_et["cme_session_date"].unique().drop_nulls()).to_list())
    for sdate in uniq:
        sdf_all = mnq_et.filter(pl.col("cme_session_date") == sdate).sort("timestamp")
        if sdf_all.height < 20:
            continue
        tc = sdf_all["ts_et"]
        form = sdf_all.filter((tc.dt.time() >= T_ET_OPEN) & (tc.dt.time() < T_ET_OR30_END))
        if form.height < 15:
            continue
        or_hi = float(form["high"].max())
        or_lo = float(form["low"].min())
        or_size = or_hi - or_lo
        if len(hist_prior_or) < 14:
            hist_prior_or.append(or_size)
            continue
        avg14 = sum(hist_prior_or) / 14.0
        hist_prior_or.append(or_size)
        if avg14 <= 0 or or_size / avg14 <= 1.2:
            continue

        rth_open = float(form["open"][0])
        drv = sdf_all.filter((tc.dt.time() >= T_ET_DRIVE_START) & (tc.dt.time() < T_ET_DRIVE_END))
        if drv.height == 0:
            continue

        for x_drive in sweep_points:
            drive_hi = rth_open
            drive_lo = rth_open
            trig_ix: int | None = None
            side = ""
            for ii in range(drv.height):
                drive_hi = max(drive_hi, float(drv["high"][ii]))
                drive_lo = min(drive_lo, float(drv["low"][ii]))
                up_exc = drive_hi - rth_open
                down_exc = rth_open - drive_lo
                if up_exc >= float(x_drive):
                    trig_ix = ii
                    side = "short"
                    break
                if down_exc >= float(x_drive):
                    trig_ix = ii
                    side = "long"
                    break
            if trig_ix is None:
                continue

            trig_bar_time = drv["ts_et"][trig_ix]
            entry_px = float(drv["close"][trig_ix])
            if side == "short":
                ext = drive_hi
                stop_px = ext + 2.0
                target_px = rth_open + 0.5 * (ext - rth_open)
                dir_ = -1
            else:
                ext = drive_lo
                stop_px = ext - 2.0
                target_px = rth_open - 0.5 * (rth_open - ext)
                dir_ = 1

            rest = sdf_all.filter(pl.col("ts_et") >= trig_bar_time)
            tr = simulate_trade_intraday(
                rest,
                entry_idx_offset=0,
                direction=dir_,
                stop_px=float(stop_px),
                target_px=float(target_px),
                entry_price=float(entry_px),
                cme_session_date=sdate if isinstance(sdate, dt.date) else dt.date.today(),
                max_et_time_exit=None,
                exit_tag_time="rth_flat",
            )
            if tr is not None:
                out[int(x_drive)].append(tr)
    return out


def _true_range(high: float, low: float, prev_close: float) -> float:
    return float(max(high - low, abs(high - prev_close), abs(low - prev_close)))


def _simulate_h2_one_stop(sp: float, mnq_et: pl.DataFrame) -> list[TradeRow]:
    trades: list[TradeRow] = []
    uniq = sorted(pl.Series(mnq_et["cme_session_date"].unique().drop_nulls()).to_list())
    for sdate in uniq:
        sdf = mnq_et.filter(pl.col("cme_session_date") == sdate).sort("timestamp")
        if sdf.height < 30:
            continue
        tc = sdf["ts_et"]
        pre = sdf.filter((tc.dt.time() >= T_ET_OPEN) & (tc.dt.time() < T_ET_LUNCH_START))
        lun = sdf.filter((tc.dt.time() >= T_ET_LUNCH_START) & (tc.dt.time() < T_ET_LUNCH_END))
        if pre.height < 20 or lun.height == 0:
            continue
        pv = 0.0
        vv = 0.0
        for row in pre.iter_rows(named=True):
            tp = float((row["high"] + row["low"] + row["close"]) / 3.0)
            vv += float(row["volume"])
            pv += tp * float(row["volume"])
        if vv <= 0:
            continue
        vwap_m = pv / vv
        trs: list[float] = []
        prev_c = float(pre["close"][0])
        for row in pre.iter_rows(named=True):
            h, lw, clo = float(row["high"]), float(row["low"]), float(row["close"])
            trs.append(_true_range(h, lw, prev_c))
            prev_c = clo
        atr_m = sum(trs[-14:]) / float(len(trs[-14:]))
        upper = vwap_m + 1.5 * atr_m
        lower = vwap_m - 1.5 * atr_m
        fired = False
        for _j, lar in enumerate(lun.iter_rows(named=True)):
            if fired:
                break
            clo = float(lar["close"])
            tsb = lar["ts_et"]
            if clo > upper:
                direction = -1
                entry_px = clo
                stop_px = entry_px + sp
                target_px = vwap_m
                rest = sdf.filter(pl.col("ts_et") >= tsb)
                tr = simulate_trade_intraday(
                    rest,
                    entry_idx_offset=0,
                    direction=direction,
                    stop_px=float(stop_px),
                    target_px=float(target_px),
                    entry_price=float(entry_px),
                    cme_session_date=sdate if isinstance(sdate, dt.date) else dt.date.today(),
                    max_et_time_exit=T_ET_LUNCH_END,
                )
                fired = True
                if tr is not None:
                    trades.append(tr)
            elif clo < lower:
                direction = 1
                entry_px = clo
                stop_px = entry_px - sp
                target_px = vwap_m
                rest = sdf.filter(pl.col("ts_et") >= tsb)
                tr = simulate_trade_intraday(
                    rest,
                    entry_idx_offset=0,
                    direction=direction,
                    stop_px=float(stop_px),
                    target_px=float(target_px),
                    entry_price=float(entry_px),
                    cme_session_date=sdate if isinstance(sdate, dt.date) else dt.date.today(),
                    max_et_time_exit=T_ET_LUNCH_END,
                )
                fired = True
                if tr is not None:
                    trades.append(tr)
    return trades


def simulate_h2(
    mnq_et: pl.DataFrame,
    stop_sweep_points: tuple[float, ...],
) -> dict[float, list[TradeRow]]:
    return {float(sp): _simulate_h2_one_stop(float(sp), mnq_et) for sp in stop_sweep_points}


def simulate_h11(mnq_et: pl.DataFrame) -> list[TradeRow]:
    """15-minute OR breakout; 5m closes 09:45–10:30 ET."""
    trades: list[TradeRow] = []
    uniq = sorted(pl.Series(mnq_et["cme_session_date"].unique().drop_nulls()).to_list())
    for sdate in uniq:
        sdf = mnq_et.filter(pl.col("cme_session_date") == sdate).sort("timestamp")
        if sdf.height < 30:
            continue
        tc = sdf["ts_et"]
        m15 = sdf.filter((tc.dt.time() >= T_ET_OPEN) & (tc.dt.time() < T_ET_H11_OR_END))
        if m15.height == 0:
            continue
        m15_hi = float(m15["high"].max())
        m15_lo = float(m15["low"].min())
        rng_pts = float(m15_hi - m15_lo)
        if rng_pts < 0.5:
            continue

        bars5 = (
            sdf.with_columns(pl.col("ts_et").dt.truncate("5m").alias("b5"))
            .group_by(
                "b5",
                maintain_order=True,
            )
            .agg(
                pl.first("timestamp").alias("anchor_ts"),
                pl.first("open").alias("o5"),
                pl.max("high").alias("h5"),
                pl.min("low").alias("l5"),
                pl.last("close").alias("c5"),
            )
        )
        if bars5.height < 4:
            continue
        trig = False
        for kk in range(bars5.height):
            if trig:
                break
            tb = bars5["b5"][kk]
            ct = tb.time()
            if ct < T_ET_H11_OR_END:
                continue
            if ct > T_ET_H11_BREAKOUT_END:
                break
            cc = float(bars5["c5"][kk])
            anchors = bars5["anchor_ts"][kk]
            if cc > m15_hi:
                rest = sdf.filter(pl.col("timestamp") >= anchors)
                tr = simulate_trade_intraday(
                    rest,
                    entry_idx_offset=0,
                    direction=1,
                    stop_px=m15_lo,
                    target_px=m15_hi + rng_pts,
                    entry_price=cc,
                    cme_session_date=sdate if isinstance(sdate, dt.date) else dt.date.today(),
                    max_et_time_exit=T_ET_H11_TIME_EXIT,
                )
                if tr is not None:
                    trades.append(tr)
                trig = True
            elif cc < m15_lo:
                rest = sdf.filter(pl.col("timestamp") >= anchors)
                tr = simulate_trade_intraday(
                    rest,
                    entry_idx_offset=0,
                    direction=-1,
                    stop_px=m15_hi,
                    target_px=m15_lo - rng_pts,
                    entry_price=cc,
                    cme_session_date=sdate if isinstance(sdate, dt.date) else dt.date.today(),
                    max_et_time_exit=T_ET_H11_TIME_EXIT,
                )
                if tr is not None:
                    trades.append(tr)
                trig = True
    return trades


H8B_DIVERGENCE_THRESHOLD = 0.003
H8B_PERSISTENCE_MINUTES = 15
H8B_MAX_TRADES_PER_SESSION = 2


def _prepare_et_frame_cross(mnq_rth: pl.DataFrame) -> pl.DataFrame:
    """Like :func:`prepare_et_frame` but keeps all RTH rows (no year pre-filter)."""
    return (
        mnq_rth.sort("timestamp")
        .filter(pl.col("cme_session_date").is_not_null())
        .with_columns(
            pl.col("timestamp").dt.convert_time_zone(_EASTERN).alias("ts_et"),
        )
    )


def _simulate_h8b_trade_from_entry(
    session_bars: pl.DataFrame,
    *,
    entry_row_idx: int,
    direction: int,
    entry_price: float,
    entry_gap_pct: float,
    stop_pts: float,
    cme_session_date: dt.date,
) -> tuple[TradeRow, int] | None:
    """Walk joined MNQ/MES session bars after entry; stop in points, target = 50% gap close."""
    n = session_bars.height
    if entry_row_idx >= n:
        return None

    stop_px = entry_price - float(direction) * float(stop_pts)
    entry_abs_gap = abs(float(entry_gap_pct))
    last_ts_et = session_bars["ts_et"][n - 1]

    for i in range(entry_row_idx, n):
        hhi = float(session_bars["mnq_high"][i])
        lw = float(session_bars["mnq_low"][i])
        clo = float(session_bars["mnq_close"][i])
        ts_et = session_bars["ts_et"][i]
        mnq_pct = float(session_bars["mnq_pct"][i])
        mes_pct = float(session_bars["mes_pct"][i])
        current_gap = mnq_pct - mes_pct
        gap_target_hit = abs(current_gap) <= 0.5 * entry_abs_gap

        if direction == 1:
            hit_stop = lw <= stop_px
            hit_t = gap_target_hit
        else:
            hit_stop = hhi >= stop_px
            hit_t = gap_target_hit

        if hit_stop and hit_t:
            xp, tag = stop_px, "stop"
        elif hit_stop:
            xp, tag = stop_px, "stop"
        elif hit_t:
            xp, tag = clo, "target_gap_half"
        elif ts_et.time() >= T_ET_SESSION_END_GATE:
            xp, tag = clo, "time_rth"
        else:
            continue

        pnl = _usd_from_points(direction, entry_price, xp)
        return (
            TradeRow(
                exit_et_date=ts_et.date(),
                cme_session_date=cme_session_date,
                pnl_usd_qty1=float(pnl),
                gross_points=float(direction * (xp - entry_price)),
                exit_reason=tag,
            ),
            i,
        )

    clo = float(session_bars["mnq_close"][n - 1])
    pnl = _usd_from_points(direction, entry_price, clo)
    return (
        TradeRow(
            exit_et_date=last_ts_et.date(),
            cme_session_date=cme_session_date,
            pnl_usd_qty1=float(pnl),
            gross_points=float(direction * (clo - entry_price)),
            exit_reason="session_end",
        ),
        n - 1,
    )


def simulate_h8b(
    mnq_et: pl.DataFrame,
    mes_et: pl.DataFrame,
    stop_sweep_points: tuple[int, ...] = (8, 10),
) -> dict[int, list[TradeRow]]:
    """MES–MNQ divergence: trade MNQ in leader direction when gap persists 15m.

    Operational spec (H8b): trade **with** divergence — if MES leads higher, MNQ
    LONG; if MES leads lower, MNQ SHORT. Target when signed MNQ%−MES% gap narrows
    by 50%; stop {8,10} MNQ points; RTH flat; max two entries per session.
    """
    mes_cols = mes_et.select(
        pl.col("cme_session_date"),
        pl.col("timestamp"),
        pl.col("open").alias("mes_open"),
        pl.col("high").alias("mes_high"),
        pl.col("low").alias("mes_low"),
        pl.col("close").alias("mes_close"),
    )
    merged = (
        mnq_et.sort("timestamp")
        .join(mes_cols, on=["cme_session_date", "timestamp"], how="inner")
        .with_columns(pl.col("timestamp").dt.convert_time_zone(_EASTERN).alias("ts_et"))
    )

    out: dict[int, list[TradeRow]] = {int(sp): [] for sp in stop_sweep_points}
    if merged.is_empty():
        return out

    uniq = sorted(pl.Series(merged["cme_session_date"].unique().drop_nulls()).to_list())
    for sdate in uniq:
        if not isinstance(sdate, dt.date):
            continue
        sdf = merged.filter(pl.col("cme_session_date") == sdate).sort("timestamp")
        if sdf.height < H8B_PERSISTENCE_MINUTES + 5:
            continue

        tc = sdf["ts_et"]
        open_bars = sdf.filter((tc.dt.time() >= T_ET_OPEN) & (tc.dt.time() < T_ET_OR30_END))
        if open_bars.height == 0:
            continue
        mnq_rth_open = float(open_bars["open"][0])
        mes_rth_open = float(open_bars["mes_open"][0])
        if mnq_rth_open <= 0 or mes_rth_open <= 0:
            continue

        sdf = sdf.with_columns(
            ((pl.col("close") - mnq_rth_open) / mnq_rth_open).alias("mnq_pct"),
            ((pl.col("mes_close") - mes_rth_open) / mes_rth_open).alias("mes_pct"),
            pl.col("open").alias("mnq_open"),
            pl.col("high").alias("mnq_high"),
            pl.col("low").alias("mnq_low"),
            pl.col("close").alias("mnq_close"),
        )

        rth = sdf.filter(
            (pl.col("ts_et").dt.time() >= T_ET_OPEN)
            & (pl.col("ts_et").dt.time() < T_ET_SESSION_END_GATE)
        )
        if rth.height < H8B_PERSISTENCE_MINUTES + 2:
            continue

        for stop_pts in stop_sweep_points:
            trades_today = 0
            scan_ix = 0
            while scan_ix < rth.height and trades_today < H8B_MAX_TRADES_PER_SESSION:
                consecutive = 0
                entry_ix: int | None = None
                for j in range(scan_ix, rth.height):
                    gap_abs = abs(float(rth["mnq_pct"][j]) - float(rth["mes_pct"][j]))
                    if gap_abs > H8B_DIVERGENCE_THRESHOLD:
                        consecutive += 1
                    else:
                        consecutive = 0
                    if consecutive >= H8B_PERSISTENCE_MINUTES:
                        entry_ix = j
                        break
                if entry_ix is None:
                    break

                mes_pct_e = float(rth["mes_pct"][entry_ix])
                mnq_pct_e = float(rth["mnq_pct"][entry_ix])
                direction = 1 if mes_pct_e > mnq_pct_e else -1
                entry_px = float(rth["mnq_close"][entry_ix])
                entry_gap = mnq_pct_e - mes_pct_e

                tr_out = _simulate_h8b_trade_from_entry(
                    rth,
                    entry_row_idx=entry_ix,
                    direction=direction,
                    entry_price=entry_px,
                    entry_gap_pct=entry_gap,
                    stop_pts=float(stop_pts),
                    cme_session_date=sdate,
                )
                if tr_out is not None:
                    tr, exit_ix = tr_out
                    out[int(stop_pts)].append(tr)
                    trades_today += 1
                    scan_ix = exit_ix + 1
                else:
                    scan_ix = entry_ix + 1

    return out


def simulate_h12(mnq_et: pl.DataFrame) -> list[TradeRow]:
    """Weekly midpoint mean reversion; Wed/Thu; 30m deviation + 5m rejection (~30%)."""
    trades: list[TradeRow] = []
    week_key: tuple[int, int] | None = None
    week_hi = float("-inf")
    week_lo = float("inf")

    uniq = sorted(pl.Series(mnq_et["cme_session_date"].unique().drop_nulls()).to_list())
    for sdate in uniq:
        if not isinstance(sdate, dt.date):
            continue
        wy, wn, _ = sdate.isocalendar()
        wk = (int(wy), int(wn))
        if week_key != wk:
            week_hi = float("-inf")
            week_lo = float("inf")
            week_key = wk

        sdf = mnq_et.filter(pl.col("cme_session_date") == sdate).sort("timestamp")
        if sdf.height == 0:
            continue
        dh = float(sdf["high"].max())
        dl = float(sdf["low"].min())
        week_hi = max(week_hi, dh)
        week_lo = min(week_lo, dl)
        midpoint = 0.5 * (week_hi + week_lo)

        if sdate.weekday() not in (2, 3):
            continue

        bars5 = (
            sdf.with_columns(pl.col("ts_et").dt.truncate("5m").alias("b5"))
            .group_by(
                "b5",
                maintain_order=True,
            )
            .agg(
                pl.first("timestamp").alias("anchor_ts"),
                pl.last("close").alias("c5"),
                pl.max("high").alias("h5"),
                pl.min("low").alias("l5"),
            )
        )
        if bars5.height < 6:
            continue

        dev_start_ts: object | None = None
        dev_side = ""
        extreme_ext: float | None = None

        for kk in range(bars5.height):
            c5 = float(bars5["c5"][kk])
            tsb = bars5["b5"][kk]
            if dev_start_ts is None:
                if c5 - midpoint > 20.0:
                    dev_side = "above"
                    dev_start_ts = tsb
                    extreme_ext = c5
                elif midpoint - c5 > 20.0:
                    dev_side = "below"
                    dev_start_ts = tsb
                    extreme_ext = c5
                continue

            assert dev_side in {"above", "below"}
            if dev_side == "above":
                if c5 - midpoint <= 20.0:
                    dev_start_ts = None
                    dev_side = ""
                    extreme_ext = None
                    continue
                minutes = (tsb - dev_start_ts).total_seconds() / 60.0
                extreme_ext = max(float(extreme_ext or c5), c5)
                retr = (
                    (float(extreme_ext) - c5) / max(float(extreme_ext) - midpoint, 1e-6)
                    if extreme_ext is not None
                    else 0.0
                )
                if minutes >= 30.0 and retr >= 0.3:
                    anchors = bars5["anchor_ts"][kk]
                    rest = sdf.filter(pl.col("timestamp") >= anchors)
                    stop_px = float(extreme_ext) + 2.0
                    tr = simulate_trade_intraday(
                        rest,
                        entry_idx_offset=0,
                        direction=-1,
                        stop_px=stop_px,
                        target_px=midpoint,
                        entry_price=c5,
                        cme_session_date=sdate,
                        max_et_time_exit=T_ET_SESSION_END_GATE,
                    )
                    if tr is not None:
                        trades.append(tr)
                    break
            else:
                if midpoint - c5 <= 20.0:
                    dev_start_ts = None
                    dev_side = ""
                    extreme_ext = None
                    continue
                minutes = (tsb - dev_start_ts).total_seconds() / 60.0
                extreme_ext = min(float(extreme_ext or c5), c5)
                retr = (c5 - float(extreme_ext)) / max(midpoint - float(extreme_ext), 1e-6)
                if minutes >= 30.0 and retr >= 0.3:
                    anchors = bars5["anchor_ts"][kk]
                    rest = sdf.filter(pl.col("timestamp") >= anchors)
                    stop_px = float(extreme_ext) - 2.0
                    tr = simulate_trade_intraday(
                        rest,
                        entry_idx_offset=0,
                        direction=1,
                        stop_px=stop_px,
                        target_px=midpoint,
                        entry_price=c5,
                        cme_session_date=sdate,
                        max_et_time_exit=T_ET_SESSION_END_GATE,
                    )
                    if tr is not None:
                        trades.append(tr)
                    break
    return trades
