"""In-sample / out-of-sample split helpers for :class:`polars.DataFrame` trade logs."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import polars as pl


@dataclass(frozen=True, slots=True)
class IsoSplitConfig:
    """IS/OOS configuration."""

    is_fraction: float = 0.6
    #: ``"trade_count"`` = first/last fraction of rows by ``exit_time``;
    #: ``"time"`` = split calendar at datetime quantile.
    mode: str = "trade_count"

    def __post_init__(self) -> None:
        if not 0.0 < self.is_fraction < 1.0:
            msg = "is_fraction must be in (0, 1)"
            raise ValueError(msg)
        if self.mode not in ("trade_count", "time"):
            msg = "mode must be 'trade_count' or 'time'"
            raise ValueError(msg)


def split_trade_log_is_oos(
    trade_log: pl.DataFrame,
    config: IsoSplitConfig | None = None,
    *,
    split_time: object | None = None,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """
    Split ``trade_log`` into (IS, OOS).

    - **trade_count (default):** sort by ``exit_time``, first ``is_fraction`` of **rows** IS.
    - **time:** ``split_time`` must be timezone-aware compatible with ``exit_time``;
      rows with ``exit_time <= split_time`` → IS, else OOS. If ``split_time`` is
      ``None``, use the ``is_fraction`` **quantile** of ``exit_time`` (empirical).
    """
    cfg = config or IsoSplitConfig()
    if trade_log.height == 0:
        msg = "trade_log is empty"
        raise ValueError(msg)
    required = {"exit_time"}
    if missing := required - set(trade_log.columns):
        msg = f"trade_log missing columns: {sorted(missing)}"
        raise ValueError(msg)

    sorted_df = trade_log.sort("exit_time")
    n = sorted_df.height

    if cfg.mode == "trade_count":
        k = int(n * cfg.is_fraction)
        k = max(1, min(k, n - 1))
        is_df = sorted_df.head(k)
        oos_df = sorted_df.tail(n - k)
        return is_df, oos_df

    if split_time is None:
        idx_break = int(np.floor((n - 1) * cfg.is_fraction))
        idx_break = max(0, min(idx_break, n - 1))
        boundary = sorted_df.slice(idx_break, 1).get_column("exit_time").item()
    else:
        boundary = split_time

    is_df = sorted_df.filter(pl.col("exit_time") <= boundary)
    oos_df = sorted_df.filter(pl.col("exit_time") > boundary)
    if is_df.height == 0 or oos_df.height == 0:
        msg = "time split produced empty IS or OOS; adjust split_time or is_fraction"
        raise ValueError(msg)
    return is_df, oos_df
