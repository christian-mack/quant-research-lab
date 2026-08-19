"""H-W4-7 quarterly close-location continuation — signal module for M4.

Clock-anchored 4h quarters in America/New_York. Strategy emits market entries
and defensive 50/50 brackets; all fills route through ``BacktestEngine``.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any
from zoneinfo import ZoneInfo

import polars as pl

from quant_research.backtest.specs import (
    BacktestConfig,
    CommissionSpec,
    FillModelSpec,
    IntradaySessionHygieneSpec,
    LimitFillMode,
    SessionSpec,
    SlippageMode,
    SlippageSpec,
    StopLimitIntrabarPolicy,
    TagSlippageOverride,
)
from quant_research.backtest.types import (
    BarContext,
    OrderRequest,
    OrderSide,
    OrderType,
)
from quant_research.backtest.validation import ValidationThresholds
from quant_research.ict.fvg import resample_ohlc

EASTERN = ZoneInfo("America/New_York")
MODULE_ID = "qcl"

BLOCK_1800_2200 = "18:00-22:00"
BLOCK_2200_0200 = "22:00-02:00"
BLOCK_0200_0600 = "02:00-06:00"
BLOCK_0600_1000 = "06:00-10:00"
BLOCK_1000_1400 = "10:00-14:00"
BLOCK_1400_1700 = "14:00-17:00"

QUARTER_BLOCKS: tuple[str, ...] = (
    BLOCK_1800_2200,
    BLOCK_2200_0200,
    BLOCK_0200_0600,
    BLOCK_0600_1000,
    BLOCK_1000_1400,
    BLOCK_1400_1700,
)

STOP_POINTS = 50.0
TARGET_POINTS = 50.0
ENTRY_TAG = "qcl_entry"
STOP_TAG = "stop"
TARGET_TAG = "target"

# 50-pt target = 200 MNQ ticks gross. Default V4 surface (15 ticks) is ORB-scale
# and would false-fail this pre-registered 1R structure. 250 still flags multi-R bugs.
QCL_V4_TICK_THRESHOLD = 250.0


def quarter_block_id_et(ts: Any) -> str | None:
    """Map an ET-aware timestamp to one of the six clock-anchored blocks.

    Returns ``None`` in the CME maintenance deadzone ``[17:00, 18:00)`` ET.
    """
    if not hasattr(ts, "astimezone"):
        msg = "timestamp must be timezone-aware"
        raise TypeError(msg)
    t = ts.astimezone(EASTERN)
    minutes = t.hour * 60 + t.minute
    if 18 * 60 <= minutes < 22 * 60:
        return BLOCK_1800_2200
    if minutes >= 22 * 60 or minutes < 2 * 60:
        return BLOCK_2200_0200
    if 2 * 60 <= minutes < 6 * 60:
        return BLOCK_0200_0600
    if 6 * 60 <= minutes < 10 * 60:
        return BLOCK_0600_1000
    if 10 * 60 <= minutes < 14 * 60:
        return BLOCK_1000_1400
    if 14 * 60 <= minutes < 17 * 60:
        return BLOCK_1400_1700
    return None


def close_location(close: float, high: float, low: float) -> float | None:
    """Return (close − low) / (high − low), or ``None`` if the range is degenerate."""
    rng = high - low
    if rng <= 0.0:
        return None
    return (close - low) / rng


def signal_from_close_location(loc: float | None) -> str | None:
    """``long`` if loc > 0.50, ``short`` if loc < 0.50, else no trade."""
    if loc is None:
        return None
    if loc > 0.50:
        return "long"
    if loc < 0.50:
        return "short"
    return None


def tier_bucket(loc: float | None) -> str | None:
    """Primary-spec tier labels used by the frequency screen (not a filter)."""
    if loc is None:
        return None
    if loc >= 0.75:
        return "ge_0.75"
    if loc > 0.50:
        return "0.50_to_0.75"
    if loc == 0.50:
        return "eq_0.50"
    if loc <= 0.25:
        return "le_0.25"
    return "0.25_to_0.50"


def resample_to_15m_et(bars: pl.DataFrame) -> pl.DataFrame:
    """Convert timestamps to ET and resample to 15-min bars (left-labeled)."""
    if bars.is_empty():
        return bars
    et = bars.with_columns(pl.col("timestamp").dt.convert_time_zone("America/New_York"))
    extra: list[pl.Expr] = []
    if "cme_session_date" in et.columns:
        extra.append(pl.col("cme_session_date").last().alias("cme_session_date"))
    if "session" in et.columns:
        extra.append(pl.col("session").last().alias("session"))
    sampled = resample_ohlc(et, every="15m")
    if not extra:
        return sampled
    joined = et.sort("timestamp").group_by_dynamic("timestamp", every="15m").agg(extra)
    return sampled.join(joined, on="timestamp", how="left").sort("timestamp")


def _quarter_block_expr(timestamp_col: str = "timestamp") -> pl.Expr:
    """Vectorized ET wall-clock → quarter block (null in the 17:00–18:00 deadzone)."""
    et = pl.col(timestamp_col).dt.convert_time_zone("America/New_York")
    minutes = et.dt.hour().cast(pl.Int32) * 60 + et.dt.minute().cast(pl.Int32)
    return (
        pl.when((minutes >= 18 * 60) & (minutes < 22 * 60))
        .then(pl.lit(BLOCK_1800_2200))
        .when((minutes >= 22 * 60) | (minutes < 2 * 60))
        .then(pl.lit(BLOCK_2200_0200))
        .when((minutes >= 2 * 60) & (minutes < 6 * 60))
        .then(pl.lit(BLOCK_0200_0600))
        .when((minutes >= 6 * 60) & (minutes < 10 * 60))
        .then(pl.lit(BLOCK_0600_1000))
        .when((minutes >= 10 * 60) & (minutes < 14 * 60))
        .then(pl.lit(BLOCK_1000_1400))
        .when((minutes >= 14 * 60) & (minutes < 17 * 60))
        .then(pl.lit(BLOCK_1400_1700))
        .otherwise(pl.lit(None))
        .alias("quarter_block")
    )


def annotate_quarters(bars_15m: pl.DataFrame) -> pl.DataFrame:
    """Add ``quarter_block`` from ET wall-clock. Deadzone bars get null."""
    if bars_15m.is_empty():
        return bars_15m.with_columns(pl.lit(None).cast(pl.Utf8).alias("quarter_block"))
    return bars_15m.with_columns(_quarter_block_expr())


def completed_quarter_stats(bars_15m: pl.DataFrame) -> pl.DataFrame:
    """One row per completed ``(cme_session_date, quarter_block)`` with range stats."""
    annotated = annotate_quarters(bars_15m)
    if "cme_session_date" not in annotated.columns:
        msg = "completed_quarter_stats requires cme_session_date"
        raise ValueError(msg)
    valid = annotated.filter(pl.col("quarter_block").is_not_null())
    if valid.is_empty():
        return pl.DataFrame(
            schema={
                "cme_session_date": pl.Date,
                "quarter_block": pl.Utf8,
                "q_high": pl.Float64,
                "q_low": pl.Float64,
                "q_close": pl.Float64,
                "q_range": pl.Float64,
                "close_loc": pl.Float64,
                "signal": pl.Utf8,
                "tier": pl.Utf8,
                "n_bars": pl.Int64,
                "last_bar_time": annotated["timestamp"].dtype,
            }
        )
    grouped = (
        valid.sort("timestamp")
        .group_by(["cme_session_date", "quarter_block"], maintain_order=True)
        .agg(
            pl.col("high").max().alias("q_high"),
            pl.col("low").min().alias("q_low"),
            pl.col("close").last().alias("q_close"),
            pl.len().alias("n_bars"),
            pl.col("timestamp").last().alias("last_bar_time"),
        )
        .with_columns((pl.col("q_high") - pl.col("q_low")).alias("q_range"))
    )
    locs: list[float | None] = []
    sigs: list[str | None] = []
    tiers: list[str | None] = []
    for row in grouped.iter_rows(named=True):
        loc = close_location(float(row["q_close"]), float(row["q_high"]), float(row["q_low"]))
        locs.append(loc)
        sigs.append(signal_from_close_location(loc))
        tiers.append(tier_bucket(loc))
    return grouped.with_columns(
        pl.Series("close_loc", locs, dtype=pl.Float64),
        pl.Series("signal", sigs, dtype=pl.Utf8),
        pl.Series("tier", tiers, dtype=pl.Utf8),
    )


def qcl_backtest_config() -> BacktestConfig:
    """Standard costs; hygiene on; V4 surface raised for the 50-pt bracket."""
    return BacktestConfig(
        commission=CommissionSpec(per_contract_per_fill=0.99),
        slippage=SlippageSpec(
            mode=SlippageMode.FIXED_TICKS,
            ticks=1.0,
            tag_overrides=(
                TagSlippageOverride(ENTRY_TAG, SlippageMode.NONE, ticks=0.0),
                TagSlippageOverride(TARGET_TAG, SlippageMode.FIXED_TICKS, ticks=0.5),
            ),
        ),
        fill_model=FillModelSpec(
            stop_limit_intrabar=StopLimitIntrabarPolicy.STOP_BEFORE_TARGET,
            limit_fill_mode=LimitFillMode.TOUCH,
            same_bar_exit_after_entry=False,
        ),
        session=SessionSpec(intraday_hygiene=IntradaySessionHygieneSpec(enabled=True)),
        enforce_trade_geometry=True,
    )


def qcl_validation_thresholds() -> ValidationThresholds:
    return ValidationThresholds(implausible_net_ticks_per_trade=QCL_V4_TICK_THRESHOLD)


@dataclass
class QuarterContinuationStrategy:
    """Emit continuation entries at the first bar of the quarter after a close-location signal.

    M4 fill mapping (forced): market submitted on the closed first 15-min bar of
    the following quarter → fill at **open of the next 15-min bar**.
    """

    quantity: int = 1
    stop_points: float = STOP_POINTS
    target_points: float = TARGET_POINTS
    skip_count: int = 0
    signal_count: int = 0
    suppress_skip_count: int = 0

    def __post_init__(self) -> None:
        self._q_high = float("-inf")
        self._q_low = float("inf")
        self._q_close: float | None = None
        self._q_key: tuple[Any, str] | None = None

    def on_bar(self, ctx: BarContext) -> list[OrderRequest]:
        block = quarter_block_id_et(ctx.timestamp)
        if block is None:
            if ctx.position_qty != 0:
                return self._manage_open(ctx)
            return []

        key = (ctx.session_date, block)
        changed = self._q_key is not None and key != self._q_key
        orders: list[OrderRequest] = []

        if changed and self._q_close is not None:
            loc = close_location(self._q_close, self._q_high, self._q_low)
            sig = signal_from_close_location(loc)
            if sig is not None:
                self.signal_count += 1
                if ctx.position_qty != 0:
                    self.skip_count += 1
                elif ctx.suppress_entry:
                    self.suppress_skip_count += 1
                    self.skip_count += 1
                else:
                    orders = self._entry_orders(ctx, sig)

        if changed or self._q_key is None:
            self._q_high = ctx.high
            self._q_low = ctx.low
            self._q_close = ctx.close
            self._q_key = key
        else:
            self._q_high = max(self._q_high, ctx.high)
            self._q_low = min(self._q_low, ctx.low)
            self._q_close = ctx.close

        if ctx.position_qty != 0:
            return self._manage_open(ctx)
        return orders

    def _entry_orders(self, ctx: BarContext, direction: str) -> list[OrderRequest]:
        entry_est = float(ctx.close)
        if direction == "long":
            side = OrderSide.BUY
            stop = entry_est - self.stop_points
            target = entry_est + self.target_points
        else:
            side = OrderSide.SELL
            stop = entry_est + self.stop_points
            target = entry_est - self.target_points
        return [
            OrderRequest(
                side,
                self.quantity,
                OrderType.MARKET,
                module_id=MODULE_ID,
                tag=ENTRY_TAG,
                bracket_entry=entry_est,
                bracket_stop=stop,
                bracket_target=target,
                bracket_direction=direction,
            )
        ]

    def _manage_open(self, ctx: BarContext) -> list[OrderRequest]:
        entry = ctx.avg_entry_price
        q = abs(ctx.position_qty)
        if entry is None or q == 0:
            return []
        if ctx.position_qty > 0:
            direction = "long"
            exit_side = OrderSide.SELL
            stop = entry - self.stop_points
            target = entry + self.target_points
        else:
            direction = "short"
            exit_side = OrderSide.BUY
            stop = entry + self.stop_points
            target = entry - self.target_points
        common = {
            "quantity": q,
            "module_id": MODULE_ID,
            "bracket_entry": entry,
            "bracket_stop": stop,
            "bracket_target": target,
            "bracket_direction": direction,
        }
        return [
            OrderRequest(
                exit_side,
                order_type=OrderType.STOP,
                stop_price=stop,
                tag=STOP_TAG,
                dedupe_tag="qcl_stop",
                **common,
            ),
            OrderRequest(
                exit_side,
                order_type=OrderType.LIMIT,
                limit_price=target,
                tag=TARGET_TAG,
                dedupe_tag="qcl_target",
                **common,
            ),
        ]


def holds_cross_maintenance_et(entry_time: Any, exit_time: Any) -> bool:
    """True if [entry, exit] strictly contains a 17:00 ET CME session close."""
    if entry_time is None or exit_time is None:
        return False
    start = entry_time.astimezone(EASTERN)
    end = exit_time.astimezone(EASTERN)
    if end <= start:
        return False
    day = start.date()
    last = end.date()
    while day <= last:
        close_et = dt.datetime(day.year, day.month, day.day, 17, 0, tzinfo=EASTERN)
        if start < close_et < end:
            return True
        day = day + dt.timedelta(days=1)
    return False
