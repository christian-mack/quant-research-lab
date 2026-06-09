"""Bar-level simulators for P2-W2 hypotheses H-1 … H-4, H-6, H-7."""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator
from dataclasses import dataclass

import polars as pl

from quant_research.ict import pd_arrays as pd_mod
from quant_research.research_p2w2.p2_execution import P2ExecutionBatch, execute_setups, session_frames
from quant_research.research_p2w2.p2_setup import P2Setup

_EASTERN = "America/New_York"

T_ET_OPEN = dt.time(9, 30)
T_ET_0945 = dt.time(9, 45)
T_ET_1000 = dt.time(10, 0)
T_ET_1030 = dt.time(10, 30)
T_ET_1200 = dt.time(12, 0)
T_ET_LUNCH_START = dt.time(11, 30)
T_ET_LUNCH_END = dt.time(13, 30)
T_ET_SESSION_END = dt.time(16, 0)

# Pre-registered stop caps (upper bound of each range).
H1_STOP_CAP = 9.0
H2_STOP_CAP = 8.0
H3_STOP_CAP = 10.0
H4_STOP_CAP = 10.0
H6_STOP_CAP = 8.0
H7_STOP_PTS = 10.0
H7_TARGET_PTS = 20.0


@dataclass(frozen=True, slots=True)
class H3H7ReclaimSignal:
    """Shared OR-extreme false-breakout reclaim trigger for H-3 (fade) and H-7 (continuation)."""

    cme_session_date: dt.date
    session_bars: pl.DataFrame
    anchor_ts: object
    entry_px: float
    false_dir: int
    false_extreme: float
    or_hi: float
    or_lo: float
    or_mid: float


def iter_h3_h7_reclaim_signals(mnq_et: pl.DataFrame) -> Iterator[H3H7ReclaimSignal]:
    """Yield at most one reclaim signal per session (H-3 / H-7 shared trigger)."""
    for sdate in sorted(mnq_et["cme_session_date"].unique().drop_nulls().to_list()):
        sdf = mnq_et.filter(pl.col("cme_session_date") == sdate).sort("timestamp")
        if sdf.height < 40:
            continue
        or_bars = sdf.filter(
            (pl.col("ts_et").dt.time() >= T_ET_OPEN)
            & (pl.col("ts_et").dt.time() < T_ET_1000)
        )
        if or_bars.height < 10:
            continue
        or_hi = float(or_bars["high"].max())
        or_lo = float(or_bars["low"].min())
        or_mid = 0.5 * (or_hi + or_lo)
        if or_hi - or_lo < 2.0:
            continue

        bars5 = (
            sdf.with_columns(pl.col("ts_et").dt.truncate("5m").alias("b5"))
            .group_by("b5", maintain_order=True)
            .agg(
                pl.first("timestamp").alias("anchor_ts"),
                pl.first("ts_et").alias("anchor_et"),
                pl.max("high").alias("h5"),
                pl.min("low").alias("l5"),
                pl.last("close").alias("c5"),
            )
        )
        false_extreme = 0.0
        false_dir = 0
        fired = False
        for k in range(bars5.height):
            if fired:
                break
            tb = bars5["b5"][k]
            if tb.time() < T_ET_1000:
                continue
            cc = float(bars5["c5"][k])
            anchors = bars5["anchor_ts"][k]
            if false_dir == 0:
                if cc > or_hi:
                    false_dir = 1
                    false_extreme = float(bars5["h5"][k])
                elif cc < or_lo:
                    false_dir = -1
                    false_extreme = float(bars5["l5"][k])
                continue
            if false_dir == 1 and cc <= or_hi:
                yield H3H7ReclaimSignal(
                    cme_session_date=sdate,
                    session_bars=sdf,
                    anchor_ts=anchors,
                    entry_px=cc,
                    false_dir=false_dir,
                    false_extreme=false_extreme,
                    or_hi=or_hi,
                    or_lo=or_lo,
                    or_mid=or_mid,
                )
                fired = True
            elif false_dir == -1 and cc >= or_lo:
                yield H3H7ReclaimSignal(
                    cme_session_date=sdate,
                    session_bars=sdf,
                    anchor_ts=anchors,
                    entry_px=cc,
                    false_dir=false_dir,
                    false_extreme=false_extreme,
                    or_hi=or_hi,
                    or_lo=or_lo,
                    or_mid=or_mid,
                )
                fired = True
            else:
                if false_dir == 1:
                    false_extreme = max(false_extreme, float(bars5["h5"][k]))
                else:
                    false_extreme = min(false_extreme, float(bars5["l5"][k]))


def count_h3_h7_reclaim_triggers(mnq_et: pl.DataFrame) -> int:
    """Count shared reclaim triggers (parity check for H-3 vs H-7 detection)."""
    return sum(1 for _ in iter_h3_h7_reclaim_signals(mnq_et))


def _bar_index_at_ts(sdf: pl.DataFrame, ts: object) -> int:
    for i in range(sdf.height):
        if sdf["timestamp"][i] == ts:
            return i
    for i in range(sdf.height):
        if sdf["timestamp"][i] >= ts:
            return i
    return max(0, sdf.height - 1)


def _reclaim_entry_index(sig: H3H7ReclaimSignal) -> int:
    """Last minute of reclaim 5m bucket (entry decision bar)."""
    sdf = sig.session_bars.sort("timestamp")
    bucket = sdf.filter(pl.col("timestamp") >= sig.anchor_ts).head(5)
    if bucket.is_empty():
        return _bar_index_at_ts(sdf, sig.anchor_ts)
    return _bar_index_at_ts(sdf, bucket["timestamp"][-1])


def prepare_et_frame(mnq_rth: pl.DataFrame) -> pl.DataFrame:
    """Sort RTH bars and attach America/New_York timestamps."""
    return (
        mnq_rth.sort("timestamp")
        .filter(pl.col("cme_session_date").is_not_null())
        .with_columns(pl.col("timestamp").dt.convert_time_zone(_EASTERN).alias("ts_et"))
    )


def _true_range(high: float, low: float, prev_close: float) -> float:
    return float(max(high - low, abs(high - prev_close), abs(low - prev_close)))


def _morning_vwap_atr(pre: pl.DataFrame) -> tuple[float, float, float] | None:
    """VWAP and ATR14 over morning bars (caller filters window)."""
    if pre.height < 14:
        return None
    pv = 0.0
    vv = 0.0
    trs: list[float] = []
    prev_c = float(pre["close"][0])
    for row in pre.iter_rows(named=True):
        tp = float((row["high"] + row["low"] + row["close"]) / 3.0)
        vv += float(row["volume"])
        pv += tp * float(row["volume"])
        h, lw, clo = float(row["high"]), float(row["low"]), float(row["close"])
        trs.append(_true_range(h, lw, prev_c))
        prev_c = clo
    if vv <= 0:
        return None
    atr = sum(trs[-14:]) / float(min(14, len(trs)))
    return pv / vv, atr, vv / float(pre.height)


def scan_h1(mnq_et: pl.DataFrame) -> list[P2Setup]:
    """H-1: trend micro-pullback continuation (stop cap 9pt, 1 trade/session)."""
    setups: list[P2Setup] = []
    for sdate in sorted(mnq_et["cme_session_date"].unique().drop_nulls().to_list()):
        sdf = mnq_et.filter(pl.col("cme_session_date") == sdate).sort("timestamp")
        if sdf.height < 40:
            continue
        open_bars = sdf.filter(
            (pl.col("ts_et").dt.time() >= T_ET_OPEN)
            & (pl.col("ts_et").dt.time() < T_ET_1030)
        )
        if open_bars.height < 20:
            continue
        rth_open = float(open_bars["open"][0])
        by_1030 = open_bars.filter(pl.col("ts_et").dt.time() <= T_ET_1030)
        hi_1030 = float(by_1030["high"].max())
        lo_1030 = float(by_1030["low"].min())
        up_move = hi_1030 - rth_open
        dn_move = rth_open - lo_1030
        trend_dir = 0
        leg = 0.0
        if up_move >= 12.0 and up_move > dn_move and lo_1030 >= rth_open - 1.0:
            trend_dir = 1
            leg = up_move
        elif dn_move >= 12.0 and dn_move > up_move and hi_1030 <= rth_open + 1.0:
            trend_dir = -1
            leg = dn_move
        if trend_dir == 0:
            continue

        scan = sdf.filter(
            (pl.col("ts_et").dt.time() >= T_ET_1000)
            & (pl.col("ts_et").dt.time() < T_ET_1200)
        )
        if scan.height < 5:
            continue
        peak = hi_1030 if trend_dir == 1 else lo_1030
        trough = lo_1030 if trend_dir == 1 else hi_1030
        fired = False
        for j in range(1, scan.height):
            if fired:
                break
            prev_c = float(scan["close"][j - 1])
            clo = float(scan["close"][j])
            hhi = float(scan["high"][j])
            lw = float(scan["low"][j])
            if trend_dir == 1:
                peak = max(peak, hhi)
                retrace = peak - lw
                if leg <= 0 or retrace < 0.25 * leg or retrace > 0.60 * leg:
                    continue
                if clo <= prev_c:
                    continue
                if clo < peak - 0.15 * leg:
                    continue
                entry_px = clo
                stop_px = entry_px - H1_STOP_CAP
                target_px = entry_px + 1.5 * H1_STOP_CAP
                entry_idx = _bar_index_at_ts(sdf, scan["timestamp"][j])
                setups.append(
                    P2Setup(
                        hypothesis_id="H-1",
                        cme_session_date=sdate,
                        entry_fill_index=entry_idx,
                        entry_price=entry_px,
                        stop_price=stop_px,
                        target_price=target_px,
                        direction="long",
                        time_stop_et=T_ET_1200,
                    )
                )
                fired = True
            else:
                trough = min(trough, lw)
                retrace = hhi - trough
                if leg <= 0 or retrace < 0.25 * leg or retrace > 0.60 * leg:
                    continue
                if clo >= prev_c:
                    continue
                if clo > trough + 0.15 * leg:
                    continue
                entry_px = clo
                stop_px = entry_px + H1_STOP_CAP
                target_px = entry_px - 1.5 * H1_STOP_CAP
                entry_idx = _bar_index_at_ts(sdf, scan["timestamp"][j])
                setups.append(
                    P2Setup(
                        hypothesis_id="H-1",
                        cme_session_date=sdate,
                        entry_fill_index=entry_idx,
                        entry_price=entry_px,
                        stop_price=stop_px,
                        target_price=target_px,
                        direction="short",
                        time_stop_et=T_ET_1200,
                    )
                )
                fired = True
    return setups


def scan_h2(mnq_et: pl.DataFrame) -> list[P2Setup]:
    """H-2: liquidity-vacuum lunch reversion (stop cap 8pt, ≤2 trades/window)."""
    setups: list[P2Setup] = []
    for sdate in sorted(mnq_et["cme_session_date"].unique().drop_nulls().to_list()):
        sdf = mnq_et.filter(pl.col("cme_session_date") == sdate).sort("timestamp")
        if sdf.height < 40:
            continue
        morning = sdf.filter(
            (pl.col("ts_et").dt.time() >= T_ET_OPEN)
            & (pl.col("ts_et").dt.time() < T_ET_LUNCH_START)
        )
        lunch = sdf.filter(
            (pl.col("ts_et").dt.time() >= T_ET_LUNCH_START)
            & (pl.col("ts_et").dt.time() < T_ET_LUNCH_END)
        )
        if morning.height < 20 or lunch.height == 0:
            continue
        stats = _morning_vwap_atr(morning)
        if stats is None:
            continue
        vwap_m, atr_m, morning_vpm = stats
        lunch_vpm = float(lunch["volume"].sum()) / float(lunch.height)
        if morning_vpm <= 0 or lunch_vpm > 0.45 * morning_vpm:
            continue
        upper = vwap_m + 1.0 * atr_m
        lower = vwap_m - 1.0 * atr_m
        window_trades = 0
        for row in lunch.iter_rows(named=True):
            if window_trades >= 2:
                break
            clo = float(row["close"])
            tsb = row["ts_et"]
            direction = 0
            if clo > upper + 2.0:
                direction = -1
            elif clo < lower - 2.0:
                direction = 1
            if direction == 0:
                continue
            entry_px = clo
            dir_str = "long" if direction == 1 else "short"
            if direction == 1:
                stop_px = entry_px - H2_STOP_CAP
                target_px = vwap_m
            else:
                stop_px = entry_px + H2_STOP_CAP
                target_px = vwap_m
            entry_idx = _bar_index_at_ts(sdf, row["timestamp"])
            setups.append(
                P2Setup(
                    hypothesis_id="H-2",
                    cme_session_date=sdate,
                    entry_fill_index=entry_idx,
                    entry_price=entry_px,
                    stop_price=stop_px,
                    target_price=target_px,
                    direction=dir_str,
                    time_stop_et=T_ET_LUNCH_END,
                )
            )
            window_trades += 1
    return setups


def scan_h3(mnq_et: pl.DataFrame) -> list[P2Setup]:
    """H-3: failed-breakout fast reclaim (stop cap 10pt, 1 trade/session)."""
    setups: list[P2Setup] = []
    for sig in iter_h3_h7_reclaim_signals(mnq_et):
        entry_px = sig.entry_px
        if sig.false_dir == 1:
            stop_px = entry_px + min(
                H3_STOP_CAP, max(2.0, sig.false_extreme + 2.0 - entry_px)
            )
            direction = "short"
        else:
            stop_px = entry_px - min(
                H3_STOP_CAP, max(2.0, entry_px - (sig.false_extreme - 2.0))
            )
            direction = "long"
        setups.append(
            P2Setup(
                hypothesis_id="H-3",
                cme_session_date=sig.cme_session_date,
                entry_fill_index=_reclaim_entry_index(sig),
                entry_price=entry_px,
                stop_price=stop_px,
                target_price=sig.or_mid,
                direction=direction,
                time_stop_et=T_ET_1200,
            )
        )
    return setups


def scan_h7(mnq_et: pl.DataFrame) -> list[P2Setup]:
    """H-7: OR-extreme reclaim continuation — H-3 trigger, inverted direction, fixed 10/20."""
    setups: list[P2Setup] = []
    for sig in iter_h3_h7_reclaim_signals(mnq_et):
        entry_px = sig.entry_px
        if sig.false_dir == 1:
            direction = "long"
            stop_px = entry_px - H7_STOP_PTS
            target_px = entry_px + H7_TARGET_PTS
        else:
            direction = "short"
            stop_px = entry_px + H7_STOP_PTS
            target_px = entry_px - H7_TARGET_PTS
        setups.append(
            P2Setup(
                hypothesis_id="H-7",
                cme_session_date=sig.cme_session_date,
                entry_fill_index=_reclaim_entry_index(sig),
                entry_price=entry_px,
                stop_price=stop_px,
                target_price=target_px,
                direction=direction,
                time_stop_et=T_ET_1200,
            )
        )
    return setups


def scan_h4(mnq_et: pl.DataFrame) -> list[P2Setup]:
    """H-4: opening-auction imbalance fade (stop cap 10pt, 1 trade/session)."""
    setups: list[P2Setup] = []
    for sdate in sorted(mnq_et["cme_session_date"].unique().drop_nulls().to_list()):
        sdf = mnq_et.filter(pl.col("cme_session_date") == sdate).sort("timestamp")
        if sdf.height < 30:
            continue
        opening = sdf.filter(
            (pl.col("ts_et").dt.time() >= T_ET_OPEN)
            & (pl.col("ts_et").dt.time() < T_ET_0945)
        )
        after = sdf.filter(pl.col("ts_et").dt.time() >= T_ET_0945)
        if opening.height < 5 or after.height == 0:
            continue
        rth_open = float(opening["open"][0])
        win_hi = float(opening["high"].max())
        win_lo = float(opening["low"].min())
        win_close = float(opening["close"][-1])
        move = win_close - rth_open
        if abs(move) < 10.0:
            continue
        if move > 0 and win_close < win_hi - 2.0:
            continue
        if move < 0 and win_close > win_lo + 2.0:
            continue
        dir_str = "short" if move > 0 else "long"
        entry_px = float(after["close"][0])
        if dir_str == "long":
            stop_px = entry_px - H4_STOP_CAP
            target_px = rth_open + 0.5 * move
        else:
            stop_px = entry_px + H4_STOP_CAP
            target_px = rth_open + 0.5 * move
        entry_idx = _bar_index_at_ts(sdf, after["timestamp"][0])
        setups.append(
            P2Setup(
                hypothesis_id="H-4",
                cme_session_date=sdate,
                entry_fill_index=entry_idx,
                entry_price=entry_px,
                stop_price=stop_px,
                target_price=target_px,
                direction=dir_str,
                time_stop_et=T_ET_1200,
            )
        )
    return setups


def scan_h6(mnq_pd: pl.DataFrame) -> list[P2Setup]:
    """H-6: PDH/PDL first-test rejection (stop cap 8pt, ≤2 trades/session)."""
    setups: list[P2Setup] = []
    for sdate in sorted(mnq_pd["cme_session_date"].unique().drop_nulls().to_list()):
        sdf = mnq_pd.filter(pl.col("cme_session_date") == sdate).sort("timestamp")
        if sdf.height < 20:
            continue
        pdh = sdf["pdh"][0]
        pdl = sdf["pdl"][0]
        peq = sdf["p_eq"][0]
        if pdh is None or pdl is None or peq is None:
            continue
        pdh_f = float(pdh)
        pdl_f = float(pdl)
        peq_f = float(peq)
        pdh_tested = False
        pdl_tested = False
        session_trades = 0
        for j in range(2, sdf.height):
            if session_trades >= 2:
                break
            hhi = float(sdf["high"][j])
            lw = float(sdf["low"][j])
            clo = float(sdf["close"][j])
            tsb = sdf["ts_et"][j]
            if not pdh_tested and hhi >= pdh_f - 0.5:
                pdh_tested = True
                if clo < pdh_f - 0.5:
                    entry_px = clo
                    stop_px = entry_px + H6_STOP_CAP
                    entry_idx = _bar_index_at_ts(sdf, sdf["timestamp"][j])
                    setups.append(
                        P2Setup(
                            hypothesis_id="H-6",
                            cme_session_date=sdate,
                            entry_fill_index=entry_idx,
                            entry_price=entry_px,
                            stop_price=stop_px,
                            target_price=peq_f,
                            direction="short",
                            time_stop_et=T_ET_SESSION_END,
                        )
                    )
                    session_trades += 1
            if session_trades >= 2:
                break
            if not pdl_tested and lw <= pdl_f + 0.5:
                pdl_tested = True
                if clo > pdl_f + 0.5:
                    entry_px = clo
                    stop_px = entry_px - H6_STOP_CAP
                    entry_idx = _bar_index_at_ts(sdf, sdf["timestamp"][j])
                    setups.append(
                        P2Setup(
                            hypothesis_id="H-6",
                            cme_session_date=sdate,
                            entry_fill_index=entry_idx,
                            entry_price=entry_px,
                            stop_price=stop_px,
                            target_price=peq_f,
                            direction="long",
                            time_stop_et=T_ET_SESSION_END,
                        )
                    )
                    session_trades += 1
    return setups


_SCANNERS: dict[str, object] = {
    "H-1": scan_h1,
    "H-2": scan_h2,
    "H-3": scan_h3,
    "H-4": scan_h4,
    "H-6": scan_h6,
    "H-7": scan_h7,
}


def scan_setups(hypothesis_id: str, mnq_et: pl.DataFrame) -> list[P2Setup]:
    """Scan one hypothesis on a prepared ET frame."""
    if hypothesis_id == "H-6":
        mnq_pd = pd_mod.add_pd_arrays(mnq_et)
        return scan_h6(mnq_pd)
    scanner = _SCANNERS.get(hypothesis_id)
    if scanner is None:
        msg = f"unknown hypothesis: {hypothesis_id}"
        raise ValueError(msg)
    return scanner(mnq_et)  # type: ignore[operator]


def run_hypothesis_m4(
    hypothesis_id: str,
    segments: list[pl.DataFrame],
) -> P2ExecutionBatch:
    """Scan + execute one hypothesis across gap-split segments via M4 engine."""
    all_setups: list[P2Setup] = []
    session_map: dict[dt.date, pl.DataFrame] = {}
    for seg in segments:
        if seg.is_empty():
            continue
        mnq_et = prepare_et_frame(seg)
        if mnq_et.is_empty():
            continue
        all_setups.extend(scan_setups(hypothesis_id, mnq_et))
        session_map.update(session_frames(mnq_et))
    return execute_setups(all_setups, session_map, hypothesis_id=hypothesis_id)
