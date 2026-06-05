"""Primitive 4 — SMT detection (Smart Money Technique / cross-instrument divergence).

Implements the TTrades SMT definition (video ``q1NmxUTm4n4``, ingested as the
``cisd_smt`` corpus): correlated instruments "generally have the same structure",
and an SMT is a **divergence** between them at a swing point.

- *"when es is making a lower low ym and Q should be making a lower low as well ...
  what happens when you get an smt is when you get a divergence ... instead of
  making a lower low ... one of the assets makes a higher low"* (@11–44s)
- *"bullish smt since the smt is occurring at the lows ... for a bearish smt this
  smt would occur at the highs"* (@51–71s)
- bearish example: *"s p puts in a lower high while the dow puts in a higher high
  ... structure diverge"* (@95–114s)
- *"NASDAQ is not breaking the low while s p is taking this low ... then we have
  an smt"* (@154–168s); *"at 8 35 NASDAQ takes these lows or creates that smt at
  the lows"* (@312–321s)

Computable definition
---------------------
Given two or more correlated instruments and, per instrument, a **prior swing
level** and the **current swing extreme**:

- **Bullish SMT** (at lows): at least one instrument makes a **lower low**
  (current low < prior low — takes out its prior low) while at least one makes a
  **higher low** (current low > prior low — fails to take its prior low).
- **Bearish SMT** (at highs): at least one instrument makes a **higher high**
  (current high > prior high) while at least one makes a **lower high**
  (current high < prior high).

The diverging instrument(s) — those that *failed* to take the level (higher low
at lows / lower high at highs) — carry the reversal signal.

Instruments for MNQ (Nasdaq): compare against MES (S&P) and MYM (Dow) at micro
size. If MYM is unavailable/short, two-instrument MES-vs-MNQ is fully supported
(``n >= 2``). MYM coverage was verified additive for Wave 1 Track 2 (1,551
MNQ∩MES∩MYM overlapping sessions; see ``docs/research-log.md``).

Two layers
----------
- :func:`smt_divergence` — pure core over already-extracted prior/current levels.
- :func:`detect_smt_from_frames` — extract the prior level (per instrument) from a
  ``prior_window`` and the current extreme from a ``current_window`` over
  timestamp-aligned bar frames, then call the core.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Final

import polars as pl

DIRECTION_BULLISH: Final[str] = "bullish"
DIRECTION_BEARISH: Final[str] = "bearish"

TimeWindow = tuple[dt.datetime, dt.datetime]
"""``[start, end)`` half-open timestamp window."""


@dataclass(frozen=True)
class SmtResult:
    """Outcome of an SMT divergence check across instruments.

    Attributes:
        present: Whether a cross-instrument divergence exists.
        direction: ``"bullish"`` (lows) or ``"bearish"`` (highs).
        prior_levels: Per-instrument prior swing level (low for bullish, high for
            bearish).
        current_extremes: Per-instrument current swing extreme.
        took_out: Per-instrument flag — did it take out its prior level (lower low
            for bullish / higher high for bearish)?
        diverged_instruments: Instruments that did **not** take out the level
            (higher low / lower high) — the SMT signal side. Empty when not present.
        swing_window: The ``current_window`` the swing extreme was measured over,
            for provenance. ``None`` when the core function was called directly.
    """

    present: bool
    direction: str
    prior_levels: dict[str, float]
    current_extremes: dict[str, float]
    took_out: dict[str, bool]
    diverged_instruments: list[str]
    swing_window: TimeWindow | None


def smt_divergence(
    prior_levels: dict[str, float],
    current_extremes: dict[str, float],
    *,
    direction: str,
    swing_window: TimeWindow | None = None,
) -> SmtResult:
    """Determine SMT divergence from per-instrument prior and current swing levels.

    Args:
        prior_levels: Instrument -> prior swing level (prior low for bullish,
            prior high for bearish).
        current_extremes: Instrument -> current swing extreme (current low for
            bullish, current high for bearish).
        direction: ``"bullish"`` (lows) or ``"bearish"`` (highs).
        swing_window: Optional provenance for the current swing window.

    Returns:
        An :class:`SmtResult`. ``present`` is true iff at least one instrument
        took out its prior level and at least one strictly did not (exact ties
        count as neither, matching "lower low" / "higher low" being strict).

    Raises:
        ValueError: If ``direction`` is invalid, fewer than two instruments are
            given, or the two mappings have different instrument keys.
    """
    if direction not in (DIRECTION_BULLISH, DIRECTION_BEARISH):
        raise ValueError(f"direction must be 'bullish' or 'bearish'; got {direction!r}")
    if set(prior_levels) != set(current_extremes):
        raise ValueError("prior_levels and current_extremes must have the same instruments")
    if len(prior_levels) < 2:
        raise ValueError("SMT needs at least two instruments")

    took_out: dict[str, bool] = {}
    held: dict[str, bool] = {}  # strictly failed to take the level (the divergence side)
    for inst in prior_levels:
        prior = prior_levels[inst]
        cur = current_extremes[inst]
        if direction == DIRECTION_BULLISH:
            took_out[inst] = cur < prior  # lower low
            held[inst] = cur > prior  # higher low
        else:
            took_out[inst] = cur > prior  # higher high
            held[inst] = cur < prior  # lower high

    any_took = any(took_out.values())
    any_held = any(held.values())
    present = any_took and any_held
    diverged = [i for i, h in held.items() if h] if present else []

    return SmtResult(
        present=present,
        direction=direction,
        prior_levels=dict(prior_levels),
        current_extremes=dict(current_extremes),
        took_out=took_out,
        diverged_instruments=diverged,
        swing_window=swing_window,
    )


def detect_smt_from_frames(
    frames: dict[str, pl.DataFrame],
    *,
    direction: str,
    prior_window: TimeWindow,
    current_window: TimeWindow,
    timestamp: str = "timestamp",
    high: str = "high",
    low: str = "low",
) -> SmtResult:
    """Extract swing levels from aligned bar frames and check SMT divergence.

    For each instrument, the prior level is the extreme over ``prior_window``
    (min ``low`` for bullish, max ``high`` for bearish) and the current extreme is
    the analogous extreme over ``current_window``. Windows are half-open
    ``[start, end)`` on ``timestamp`` and should be the same wall-clock windows for
    every instrument (pass timestamp-aligned / inner-joined frames).

    Args:
        frames: Instrument name -> OHLC bars with ``timestamp``/``high``/``low``.
        direction: ``"bullish"`` (lows) or ``"bearish"`` (highs).
        prior_window: ``[start, end)`` window containing each instrument's prior
            swing.
        current_window: ``[start, end)`` window containing the current swing.
        timestamp: Timestamp column name.
        high: High column name.
        low: Low column name.

    Returns:
        An :class:`SmtResult` with ``swing_window`` set to ``current_window``.

    Raises:
        ValueError: If fewer than two instruments are given, ``direction`` is
            invalid, or any instrument has no bars in either window.
    """
    if direction not in (DIRECTION_BULLISH, DIRECTION_BEARISH):
        raise ValueError(f"direction must be 'bullish' or 'bearish'; got {direction!r}")
    if len(frames) < 2:
        raise ValueError("SMT needs at least two instruments")

    extreme_col = low if direction == DIRECTION_BULLISH else high

    def window_extreme(df: pl.DataFrame, window: TimeWindow, label: str, inst: str) -> float:
        sub = df.filter(
            (pl.col(timestamp) >= window[0]) & (pl.col(timestamp) < window[1])
        )
        if sub.height == 0:
            raise ValueError(f"instrument {inst!r} has no bars in the {label} window {window}")
        if direction == DIRECTION_BULLISH:
            return float(sub[extreme_col].min())
        return float(sub[extreme_col].max())

    prior_levels: dict[str, float] = {}
    current_extremes: dict[str, float] = {}
    for inst, df in frames.items():
        prior_levels[inst] = window_extreme(df, prior_window, "prior", inst)
        current_extremes[inst] = window_extreme(df, current_window, "current", inst)

    return smt_divergence(
        prior_levels,
        current_extremes,
        direction=direction,
        swing_window=current_window,
    )
