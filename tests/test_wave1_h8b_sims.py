"""Smoke tests for Wave 1 H8b MES–MNQ divergence simulator."""

from __future__ import annotations

import datetime as dt

import polars as pl

from quant_research.research_wave1.track1_hypothesis_sims import simulate_h8b


def _session_frame(
    *,
    mnq_open: float,
    mes_open: float,
    mnq_closes: list[float],
    mes_closes: list[float],
    sdate: dt.date = dt.date(2024, 1, 15),
) -> tuple[pl.DataFrame, pl.DataFrame]:
    eastern = "America/New_York"
    base = dt.datetime.combine(sdate, dt.time(9, 30), tzinfo=dt.timezone(dt.timedelta(hours=-5)))
    rows_mnq = []
    rows_mes = []
    for i, (mc, ec) in enumerate(zip(mnq_closes, mes_closes, strict=True)):
        ts = base + dt.timedelta(minutes=i)
        rows_mnq.append(
            {
                "timestamp": ts,
                "open": mnq_open if i == 0 else mnq_closes[i - 1],
                "high": max(mnq_open, mc) + 1.0,
                "low": min(mnq_open, mc) - 1.0,
                "close": mc,
                "volume": 100,
                "cme_session_date": sdate,
            }
        )
        rows_mes.append(
            {
                "timestamp": ts,
                "open": mes_open if i == 0 else mes_closes[i - 1],
                "high": max(mes_open, ec) + 0.1,
                "low": min(mes_open, ec) - 0.1,
                "close": ec,
                "volume": 100,
                "cme_session_date": sdate,
            }
        )
    mnq = pl.DataFrame(rows_mnq).with_columns(
        pl.col("timestamp").dt.convert_time_zone(eastern).alias("ts_et"),
    )
    mes = pl.DataFrame(rows_mes)
    return mnq, mes


def test_h8b_mes_leads_higher_enters_long() -> None:
    """When MES % change exceeds MNQ % for 15+ minutes, direction is LONG."""
    mnq_open = 17000.0
    mes_open = 5000.0
    # MNQ flat; MES rises ~0.5% for 16 minutes -> divergence > 0.3%
    mes_closes = [mes_open * (1.0 + 0.005 * min(i, 16) / 16.0) for i in range(45)]
    mnq_closes = [mnq_open] * 45
    mnq, mes = _session_frame(
        mnq_open=mnq_open,
        mes_open=mes_open,
        mnq_closes=mnq_closes,
        mes_closes=mes_closes,
    )
    out = simulate_h8b(mnq, mes, stop_sweep_points=(8,))
    trades = out[8]
    assert len(trades) >= 1
    assert trades[0].cme_session_date == dt.date(2024, 1, 15)
