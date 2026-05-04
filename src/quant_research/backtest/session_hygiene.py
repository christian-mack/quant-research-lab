"""CME / NT8-style daily maintenance window (ET wall-clock) for intraday backtests.

Mirrors the practical effect of NT8 **TradingHours** templates that **break at end of
session**: flat before the Globex maintenance gap; no new entries during the gap.
"""

from __future__ import annotations

from typing import Any

from zoneinfo import ZoneInfo

from quant_research.backtest.specs import IntradaySessionHygieneSpec

_ET = ZoneInfo("America/New_York")


def time_et(ts: Any) -> tuple[int, int]:
    """Hour and minute in **America/New_York** (no separate date check)."""
    if not hasattr(ts, "astimezone"):
        msg = "timestamp must be timezone-aware for session hygiene"
        raise TypeError(msg)
    t = ts.astimezone(_ET)
    return t.hour, t.minute


def is_flatten_time_et(ts: Any, hygiene: IntradaySessionHygieneSpec) -> bool:
    """True on bars whose ET wall-clock is exactly ``hygiene.flatten_time_et``."""
    if not hygiene.enabled:
        return False
    h, m = time_et(ts)
    return h == hygiene.flatten_time_et.hour and m == hygiene.flatten_time_et.minute


def in_entry_deadzone_et(ts: Any, hygiene: IntradaySessionHygieneSpec) -> bool:
    """Half-open ``[start, end)`` in ET — includes Sunday / ETH if bars exist."""
    if not hygiene.enabled:
        return False
    t = time_et(ts)
    tup = (t[0] * 60 + t[1])
    lo = hygiene.entry_deadzone_start_et.hour * 60 + hygiene.entry_deadzone_start_et.minute
    hi = hygiene.entry_deadzone_end_et.hour * 60 + hygiene.entry_deadzone_end_et.minute
    return lo <= tup < hi
