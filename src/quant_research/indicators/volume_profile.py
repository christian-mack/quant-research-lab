"""Basic volume-at-price (volume profile) within session groups.

**Deviation from the ``atr`` template:** the natural output is a *long*
table — one row per ``(group, bin)`` — not a column aligned 1:1 with
input bars. There is no meaningful ``volume_profile_expr``. The entry
point is :func:`volume_profile`.

Algorithm
---------
1. Drop rows with null ``group`` (e.g. null ``cme_session_date``).
2. Within each ``group``, assign integer ``bin_id`` in ``0 .. n_bins-1``
   by flooring ``(price - pmin) / (pmax - pmin) * n_bins`` where
   ``pmin`` / ``pmax`` are the group's min/max ``price`` (``close`` by
   default). A tiny epsilon guards the zero-span case.
3. Aggregate ``sum(volume)`` per ``(group, bin_id)``, plus the actual
   min/max trade price in the bin as ``bin_price_low`` /
   ``bin_price_high``.

This is research-grade scaffolding — not a full NT8 / Sierra Chart VP
with tick resolution or time-at-price.

Typical call: pass ``group="cme_session_date"`` after
:func:`quant_research.data.session.assign_cme_session_date`.
"""

from __future__ import annotations

from typing import Final

import polars as pl

DEFAULT_N_BINS: Final[int] = 50


def volume_profile(
    df: pl.DataFrame,
    *,
    group: str = "cme_session_date",
    price: str = "close",
    volume: str = "volume",
    n_bins: int = DEFAULT_N_BINS,
) -> pl.DataFrame:
    """Return a long DataFrame of per-group volume histogram bins.

    Args:
        df: Input bars.
        group: Column to partition by (e.g. ``cme_session_date``).
        price: Price column to bin (usually ``close`` or mid).
        volume: Volume column.
        n_bins: Number of equal-width bins between group min and max price.

    Returns:
        Columns: ``group`` (same name as arg), ``bin_id``, ``volume``,
        ``bin_price_low``, ``bin_price_high`` — sorted by group then bin.

    Raises:
        ValueError: If columns missing or ``n_bins < 1``.
    """
    if n_bins < 1:
        raise ValueError(f"`n_bins` must be >= 1; got {n_bins}")
    for c in (group, price, volume):
        if c not in df.columns:
            raise ValueError(f"missing required column: {c!r}")

    p = pl.col(price)
    pmin = p.min().over(group)
    pmax = p.max().over(group)
    span = pmax - pmin + 1e-12
    bin_id = (
        ((p - pmin) / span * float(n_bins))
        .floor()
        .cast(pl.Int32)
        .clip(0, n_bins - 1)
        .alias("_bin_id")
    )

    work = (
        df.filter(pl.col(group).is_not_null())
        .with_columns(bin_id)
        .group_by(group, "_bin_id")
        .agg(
            pl.col(volume).sum().alias("volume"),
            p.min().alias("bin_price_low"),
            p.max().alias("bin_price_high"),
        )
        .rename({"_bin_id": "bin_id"})
        .sort(group, "bin_id")
    )
    return work
