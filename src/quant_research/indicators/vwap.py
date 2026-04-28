"""Session-anchored VWAP (typical price × volume / cumulative volume).

**Deviation from the pure ``*_expr`` template** (:mod:`quant_research.indicators.atr`):

Session VWAP is inherently *DataFrame-scoped*: it needs a grouping key
(``cme_session_date``) derived from a time-series join to the CME
schedule, then a cumulative sum partitioned by that key. Expressing
this as a single stateless ``pl.Expr`` on arbitrary renamed columns
would either (a) require the grouping column to already exist and be
passed through every ``with_columns`` chain — error-prone — or (b)
duplicate the schedule join inside an expression (impossible without
context). The public API is therefore *wrapper-first*:
:func:`add_session_vwap` is the primary entry point;
:func:`typical_price_expr` is the only trivial expression helper
(HLC3). If this pattern repeats for other session-cumulative indicators
(cumulative delta, session OHLC), consider a shared
``session_cumulative`` helper in ``quant_research.data.session`` — that
would be a charter-level abstraction worth a lessons-log entry; a
one-off VWAP deviation does not need one.

Definition
----------
``typical_price = (high + low + close) / 3`` (same as pandas-ta
``hlc3`` / TradingView VWAP numerator convention).

``session_vwap = cumsum(tp × volume) / cumsum(volume)`` reset at each
change of ``cme_session_date`` from :func:`quant_research.data.session.assign_cme_session_date`.

Bars with null ``cme_session_date`` (maintenance break, weekend,
holiday) get null VWAP.

Validation
----------
pandas-ta ``vwap`` defaults to calendar ``anchor="D"`` on the series
*index* (UTC or naive); that is **not** the same as the CME equity-index
session key used here. Cross-checks in tests therefore use a *hand-built*
pandas reference: group the polars ``cme_session_date`` column in
pandas and apply the same cumulative formula — not ``ta.vwap``.
"""

from __future__ import annotations

from typing import Final

import polars as pl

from quant_research.data import session as session_mod

DEFAULT_VWAP_OUTPUT: Final[str] = "session_vwap"


def typical_price_expr(
    *,
    high: str = "high",
    low: str = "low",
    close: str = "close",
) -> pl.Expr:
    """HLC3 / typical price."""
    return (pl.col(high) + pl.col(low) + pl.col(close)) / 3


def add_session_vwap(
    df: pl.DataFrame,
    *,
    high: str = "high",
    low: str = "low",
    close: str = "close",
    volume: str = "volume",
    timestamp: str = "timestamp",
    calendar_name: str = session_mod.CME_EQUITY_CALENDAR,
    session_date_col: str = "cme_session_date",
    output: str = DEFAULT_VWAP_OUTPUT,
) -> pl.DataFrame:
    """Append session-anchored VWAP; add ``cme_session_date`` if missing.

    Args:
        df: Must include ``timestamp`` and OHLCV columns.
        high, low, close, volume: Column names.
        timestamp: Timestamp column (tz-aware).
        calendar_name: Passed to :func:`~quant_research.data.session.assign_cme_session_date`.
        session_date_col: Grouping key; populated via
            ``assign_cme_session_date`` if not already in ``df``.
        output: VWAP column name.

    Returns:
        ``df`` sorted by ``timestamp``, with ``session_date_col`` (if
        newly added) and ``output``.

    Raises:
        ValueError: If required columns are missing.
    """
    missing = [c for c in (timestamp, high, low, close, volume) if c not in df.columns]
    if missing:
        raise ValueError(f"missing required columns: {missing}")

    out = df.sort(timestamp)
    if session_date_col not in out.columns:
        out = session_mod.assign_cme_session_date(
            out, calendar_name=calendar_name, output=session_date_col
        )

    sd = pl.col(session_date_col)
    tp = typical_price_expr(high=high, low=low, close=close)

    in_sess = out.filter(sd.is_not_null()).with_columns(tp.alias("_tp"))
    cum = in_sess.with_columns(
        (pl.col("_tp") * pl.col(volume)).cum_sum().over(session_date_col).alias("_vn"),
        pl.col(volume).cum_sum().over(session_date_col).alias("_vd"),
    ).with_columns((pl.col("_vn") / pl.col("_vd")).alias(output))

    return out.join(cum.select(timestamp, output), on=timestamp, how="left")
