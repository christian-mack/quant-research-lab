"""Build a continuous price series from overlapping quarterly contracts.

The data loader (:mod:`quant_research.data.data_loader`) yields a DataFrame
where adjacent quarterly contracts overlap in time during the roll window.
For most research and backtest workflows we want a single continuous price
series — one bar per timestamp, with a clear rule for which contract is
"active" at each point.

Roll methodology
    Two methods are supported, with the second as a fallback:

    1. **Volume crossover (preferred when applicable).** For each adjacent
       pair of contracts (in chronological expiry order):

       a. Aggregate minute-bar volume to daily volume per contract.
       b. Restrict to the date range where both contracts have data (the
          overlap window).
       c. Find the first day ``D`` such that the next contract's daily
          volume has exceeded the current contract's for
          ``crossover_window`` consecutive days ending on ``D``
          (default ``N=3``).
       d. Roll happens at the start of the next calendar day after ``D``:
          from that timestamp forward, the next contract is active.

       This is the standard convention in futures research (see e.g.
       Carver, *Systematic Trading*, Ch. 4) and matches NT8's default.

    2. **Data boundary (fallback).** If the volume-crossover condition
       is never satisfied within the overlap window — or if the contracts
       don't overlap at all — roll at the moment the current contract's
       data ends: ``roll_at = current.last_bar_timestamp + 1µs``.

       For the present NT8 MNQ dataset, **all 25 inter-contract rolls
       fall through to this fallback.** NT8's default export contains
       each contract only during its dominant period (typically a 3-month
       window with ~5 days of overlap into the next contract). Within
       that overlap, the current contract's volume remains 50-1000x the
       next contract's for the first 4 days, then crashes by 90% on
       day 5 (the unwind day) while the next contract picks up. So
       3-consecutive-day crossover never triggers, but the data boundary
       itself is exactly the right place to roll. See lessons-log
       2026-04-26.

    Open-interest crossover would be more accurate than volume but is
    not available in the NT8 export — only OHLCV per minute. Calendar-
    based rolls (fixed N days before expiry) ignore actual market
    behavior and are not used here.

No back-adjustment
    The output keeps **raw prices**. This means a small price discontinuity
    can appear at the roll boundary (the "roll cost"), identifiable via
    the change in ``contract_symbol``. Reasons:

    - Diagnostic clarity: the discontinuity is real market structure
      (cost of carry, basis), not a data artifact, and downstream code
      can see exactly when the active contract changed.
    - The backtest engine (M4) will handle position rolls explicitly,
      so it can reconcile the price step at the roll boundary directly.
    - If a research workflow needs a back-adjusted series for indicator
      computation, it can be added as a separate transform that subtracts
      the roll-day basis cumulatively. Deferred until needed.

Output schema
    Same :data:`quant_research.data.data_loader.CANONICAL_COLUMNS`. The
    ``contract_symbol`` column on the output reflects the **active**
    contract for that bar, not just the source file. Output is sorted
    by ``timestamp`` ascending and contains no duplicate timestamps.

Worked example (synthetic, 3-day crossover):
    Day  | MNQ_curr_vol | MNQ_next_vol | next > curr | rolling 3-day count
    -----|--------------|--------------|-------------|--------------------
    D+0  | 100k         | 30k          | No          | 0
    D+1  | 95k          | 50k          | No          | 0
    D+2  | 80k          | 90k          | Yes         | 1
    D+3  | 60k          | 100k         | Yes         | 2
    D+4  | 40k          | 120k         | Yes         | 3  <-- trigger
    D+5  |   ...        |   ...        |   ...       |   ...

    Trigger day = D+4. Roll boundary = start of D+5 in the source
    timezone. Bars at timestamp >= D+5 00:00 use the next contract;
    bars before that use the current contract.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import NamedTuple

import polars as pl

from quant_research.data.data_loader import CANONICAL_COLUMNS, CME_TIMEZONE

DEFAULT_CROSSOVER_WINDOW = 3
"""Default N for the volume-crossover roll rule (consecutive days)."""

_CONTRACT_CODE_RE = re.compile(r"^(?P<symbol>[A-Z]+)\s(?P<month>\d{2})-(?P<year>\d{2})$")
"""Parses NT8 contract symbols like ``"MNQ 03-26"``."""


class ContractCode(NamedTuple):
    """Parsed contract symbol with sortable expiry."""

    symbol: str
    """Underlying instrument code (e.g. ``"MNQ"``, ``"ES"``)."""

    expiry_year: int
    """4-digit year (``20YY``)."""

    expiry_month: int
    """1-12; quarterly cycle is 3, 6, 9, 12."""

    @property
    def sort_key(self) -> tuple[int, int]:
        """Year-then-month, suitable for chronological sorting."""
        return (self.expiry_year, self.expiry_month)


class RollEvent(NamedTuple):
    """One roll boundary in the continuous series.

    A roll event marks the timestamp from which ``to_contract`` is active.
    Bars with ``timestamp < roll_at`` belong to ``from_contract`` (or an
    even earlier one); bars with ``timestamp >= roll_at`` belong to
    ``to_contract`` (or a later one, for subsequent rolls).
    """

    from_contract: str
    to_contract: str
    roll_at: dt.datetime
    """First timestamp at which ``to_contract`` is active (tz-aware)."""

    method: str
    """``"volume_crossover"`` or ``"data_boundary"``."""

    trigger_date: dt.date | None = None
    """Last day of the consecutive-crossover window. ``None`` for ``data_boundary``."""


def parse_contract_code(symbol: str) -> ContractCode:
    """Parse a NT8 contract symbol into a sortable :class:`ContractCode`.

    Args:
        symbol: NT8-style symbol, e.g. ``"MNQ 03-26"`` (instrument code,
            single space, two-digit month, ``-``, two-digit year).

    Returns:
        :class:`ContractCode` with 4-digit year (assumes ``20YY``).

    Raises:
        ValueError: If ``symbol`` does not match the expected format.
    """
    m = _CONTRACT_CODE_RE.match(symbol)
    if m is None:
        raise ValueError(f"Cannot parse contract symbol: {symbol!r}")
    return ContractCode(
        symbol=m["symbol"],
        expiry_year=2000 + int(m["year"]),
        expiry_month=int(m["month"]),
    )


def sort_contracts_chronologically(symbols: list[str]) -> list[str]:
    """Return ``symbols`` sorted by (expiry_year, expiry_month) ascending.

    Args:
        symbols: NT8 contract symbols, e.g.
            ``["MNQ 06-20", "MNQ 03-20", "MNQ 12-19"]``.

    Returns:
        New list, lexicographically *not* sufficient (string sort would
        place ``"MNQ 12-20"`` before ``"MNQ 03-21"``); this returns true
        chronological order.
    """
    return sorted(symbols, key=lambda s: parse_contract_code(s).sort_key)


def find_roll_dates(
    df: pl.DataFrame,
    *,
    crossover_window: int = DEFAULT_CROSSOVER_WINDOW,
) -> list[RollEvent]:
    """Detect volume-crossover roll boundaries between adjacent contracts.

    See module docstring for the methodology.

    Args:
        df: Multi-contract DataFrame with the canonical schema (output of
            :func:`quant_research.data.data_loader.load_all_contracts` or
            :func:`load_contracts`).
        crossover_window: ``N`` consecutive days the next contract must
            dominate before triggering a roll. Default 3.

    Returns:
        Roll events in chronological order, one per adjacent contract
        pair. If a contract pair has no overlap window, or the next
        contract never dominates for ``N`` consecutive days within the
        overlap, no event is emitted for that pair (the prior contract's
        active period extends to its last bar; the next contract's active
        period starts at *its* first bar).
    """
    if crossover_window < 1:
        raise ValueError(f"crossover_window must be >= 1, got {crossover_window}")

    if df.height == 0:
        return []

    symbols_in_df = df["contract_symbol"].unique().to_list()
    sorted_symbols = sort_contracts_chronologically(symbols_in_df)

    daily_volume = (
        df.with_columns(pl.col("timestamp").dt.date().alias("date"))
        .group_by(["contract_symbol", "date"])
        .agg(pl.col("volume").sum().alias("daily_volume"))
    )

    timezone = df.schema["timestamp"].time_zone or CME_TIMEZONE

    events: list[RollEvent] = []
    for current_sym, next_sym in zip(sorted_symbols, sorted_symbols[1:], strict=False):
        event = _detect_roll_for_pair(
            df,
            daily_volume,
            current_sym,
            next_sym,
            crossover_window=crossover_window,
            timezone=timezone,
        )
        if event is not None:
            events.append(event)
    return events


def _localize_naive(naive: dt.datetime, timezone: str) -> dt.datetime | None:
    """Localize a naive datetime to ``timezone`` via polars.

    The naive value is treated as wall-clock in ``timezone``. All call
    sites in this module construct midnight-aligned datetimes, which are
    always unambiguous, so DST gaps/overlaps cannot happen in practice;
    we still pass ``non_existent="null"`` defensively so a future caller
    that builds a non-midnight boundary doesn't crash.
    """
    return (
        pl.Series([naive])
        .cast(pl.Datetime("us"))
        .dt.replace_time_zone(timezone, non_existent="null", ambiguous="earliest")[0]
    )


def _detect_roll_for_pair(
    df: pl.DataFrame,
    daily_volume: pl.DataFrame,
    current_sym: str,
    next_sym: str,
    *,
    crossover_window: int,
    timezone: str,
) -> RollEvent | None:
    """Find the roll boundary for one (current, next) pair.

    Tries volume-crossover first; falls back to the data boundary
    (current contract's last bar timestamp + 1µs) if no crossover signal
    is present in the overlap window or there is no overlap.

    Returns ``None`` only if the current contract has no data at all
    (degenerate case).
    """
    current_daily = daily_volume.filter(pl.col("contract_symbol") == current_sym).select(
        pl.col("date"),
        pl.col("daily_volume").alias("current_volume"),
    )
    next_daily = daily_volume.filter(pl.col("contract_symbol") == next_sym).select(
        pl.col("date"),
        pl.col("daily_volume").alias("next_volume"),
    )

    overlap = (
        current_daily.join(next_daily, on="date", how="inner")
        .sort("date")
        .with_columns(
            (pl.col("next_volume") > pl.col("current_volume"))
            .cast(pl.Int64)
            .rolling_sum(window_size=crossover_window)
            .alias("consecutive_dominance"),
        )
    )

    triggers = overlap.filter(pl.col("consecutive_dominance") >= crossover_window).head(1)
    if triggers.height > 0:
        trigger_date: dt.date = triggers["date"][0]
        roll_at_naive = dt.datetime.combine(trigger_date + dt.timedelta(days=1), dt.time(0, 0))
        roll_at = _localize_naive(roll_at_naive, timezone)
        if roll_at is not None:
            return RollEvent(
                from_contract=current_sym,
                to_contract=next_sym,
                roll_at=roll_at,
                method="volume_crossover",
                trigger_date=trigger_date,
            )

    current_last_ts = df.filter(pl.col("contract_symbol") == current_sym)["timestamp"].max()
    if current_last_ts is None:
        return None
    roll_at = current_last_ts + dt.timedelta(microseconds=1)
    return RollEvent(
        from_contract=current_sym,
        to_contract=next_sym,
        roll_at=roll_at,
        method="data_boundary",
        trigger_date=None,
    )


def build_continuous_contract(
    df: pl.DataFrame,
    *,
    crossover_window: int = DEFAULT_CROSSOVER_WINDOW,
) -> pl.DataFrame:
    """Stitch a multi-contract DataFrame into a single continuous series.

    See module docstring for the methodology and rationale.

    Args:
        df: Multi-contract DataFrame with the canonical schema.
        crossover_window: ``N`` for the volume-crossover rule.

    Returns:
        DataFrame with the same canonical schema, sorted by ``timestamp``,
        with no duplicate timestamps. ``contract_symbol`` reflects the
        active contract for each bar.
    """
    if df.height == 0:
        return df.sort("timestamp")

    symbols = sort_contracts_chronologically(df["contract_symbol"].unique().to_list())
    rolls = find_roll_dates(df, crossover_window=crossover_window)
    rolls_by_from = {r.from_contract: r for r in rolls}

    active_pieces: list[pl.DataFrame] = []
    active_start: dt.datetime | None = None

    for i, sym in enumerate(symbols):
        is_last = i == len(symbols) - 1
        roll_out = rolls_by_from.get(sym)
        active_end = roll_out.roll_at if (roll_out is not None and not is_last) else None

        piece = df.filter(pl.col("contract_symbol") == sym)
        if active_start is not None:
            piece = piece.filter(pl.col("timestamp") >= active_start)
        if active_end is not None:
            piece = piece.filter(pl.col("timestamp") < active_end)

        if piece.height > 0:
            active_pieces.append(piece)

        active_start = active_end

    if not active_pieces:
        return df.head(0).sort("timestamp")
    return pl.concat(active_pieces, how="vertical").sort("timestamp").select(*CANONICAL_COLUMNS)
