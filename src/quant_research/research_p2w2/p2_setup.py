"""P2 hypothesis setup record — signal geometry for M4 engine execution."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class P2Setup:
    """One detected entry opportunity (signal only; fills via M4 engine)."""

    hypothesis_id: str
    cme_session_date: dt.date
    entry_fill_index: int
    entry_price: float
    stop_price: float
    target_price: float
    direction: str
    time_stop_et: dt.time | None = None
