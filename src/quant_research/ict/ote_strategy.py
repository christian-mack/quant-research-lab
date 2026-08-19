"""Wave 1 Track 2 — Phase 3: standalone OTE strategy assembly (Spec A).

Self-contained liquidity-sweep → MSS → displacement → FVG → OTE entry detector.
Direction is set by the sweep/MSS sequence only — **no bias-module gate** in this
build (overlap analysis is step 4).

Mechanical rules follow ``notebooks/validation/2026-06-06_wave1_track2_phase3_step0_definitions.md``
(D0.1–D0.6). Pre-registered variant axes (not swept beyond these four):

- **Target:** ``nearest`` (primary) vs ``far``
- **Stop arm:** ``swept_extreme`` (primary) vs ``fvg_c2``
- **OTE entry:** ``ote_705`` (primary) vs ``ote_62``
- **FVG tie-break:** ``earliest`` (primary) vs ``nearest_ote``

Structural constants (fixed): ``penetration_ticks=1``, ``close_back_within_bars=3``,
OTE band 62–79%, 3-bar fractal, 100-bar MSS lookback fallback.

Unconstrained collection: all RTH bars (09:30–16:00 ET), multiple setups per session,
no session-window cap, no one-setup-per-session limit.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Final, Literal
from zoneinfo import ZoneInfo

import polars as pl

from quant_research.backtest.geometry import check_trade_geometry
from quant_research.ict import fvg as fvg_mod
from quant_research.ict import liquidity_sweep as sweep_mod
from quant_research.ict import mss as mss_mod
from quant_research.ict import pd_arrays as pd_mod
from quant_research.ict.liquidity_sweep import (
    SIDE_HIGH,
    SIDE_LOW,
    SweepConfig,
    SweepResult,
    detect_sweep,
    recent_swing_level,
)
from quant_research.ict.mss import (
    DEFAULT_MAX_LOOKBACK_FALLBACK_BARS,
    MssConfig,
    confirmed_fractal_swings,
    detect_mss_after_sweep,
)

DIRECTION_LONG: Final[str] = "long"
DIRECTION_SHORT: Final[str] = "short"

TARGET_NEAREST: Final[str] = "nearest"
TARGET_FAR: Final[str] = "far"

STOP_SWEPT_EXTREME: Final[str] = "swept_extreme"
STOP_FVG_C2: Final[str] = "fvg_c2"

ENTRY_OTE_705: Final[str] = "ote_705"
ENTRY_OTE_62: Final[str] = "ote_62"

FVG_EARLIEST: Final[str] = "earliest"
FVG_NEAREST_OTE: Final[str] = "nearest_ote"

DEFAULT_TICK_SIZE: Final[float] = 0.25
DEFAULT_OTE_PRIMARY: Final[float] = 0.705
DEFAULT_OTE_VARIANT: Final[float] = 0.62
DEFAULT_OTE_BAND_LOW: Final[float] = 0.62
DEFAULT_OTE_BAND_HIGH: Final[float] = 0.79
DEFAULT_SWING_REF_LOOKBACK: Final[int] = 20
DEFAULT_FAR_TARGET_LOOKBACK: Final[int] = 100
DEFAULT_FVG_OTE_CONFLICT_TICKS: Final[int] = 4

ET = ZoneInfo("America/New_York")
RTH_OPEN_ET: Final[dt.time] = dt.time(9, 30)
RTH_CLOSE_ET: Final[dt.time] = dt.time(16, 0)

TargetMode = Literal["nearest", "far"]
StopArm = Literal["swept_extreme", "fvg_c2"]
EntryMode = Literal["ote_705", "ote_62"]
FvgTiebreak = Literal["earliest", "nearest_ote"]
EntryStyle = Literal["combined", "ote_only", "fvg_only"]

ENTRY_COMBINED: Final[str] = "combined"
ENTRY_OTE_ONLY: Final[str] = "ote_only"
ENTRY_FVG_ONLY: Final[str] = "fvg_only"


@dataclass(frozen=True)
class OteStrategyConfig:
    """Standalone OTE strategy configuration.

    Only the four pre-registered variant axes below are swept in step 4. All other
    fields are structural constants carried for auditability.

    Attributes:
        tick_size: Instrument tick size (MNQ = 0.25).
        penetration_ticks: [MANUAL OBS] sweep depth (Phase 1 default 1).
        close_back_within_bars: [MANUAL OBS] sweep close-back window (default 3).
        mss_max_lookback_fallback_bars: D0.4 fallback cap (default 100).
        swing_ref_lookback: Bars for recent swing high/low sweep references.
        far_target_lookback_bars: Bounded lookback for far-target fractal pools.
        target_mode: ``nearest`` (primary) or ``far``.
        stop_arm: ``swept_extreme`` (primary) or ``fvg_c2``.
        entry_mode: ``ote_705`` (primary) or ``ote_62``.
        fvg_tiebreak: ``earliest`` (primary) or ``nearest_ote``.
        stop_buffer_ticks: Ticks beyond stop reference (1 primary; 2 for B variant).
        fvg_ote_conflict_ticks: Log conflict when OTE limit is this many ticks
            outside the selected FVG zone.
        rth_only: Restrict scan to 09:30–16:00 America/New_York.
        ote_primary_level: 70.5% fib level (structural constant).
        ote_variant_level: 62% first-touch level (pre-reg variant).
        entry_style: ``combined`` (step-2 default), ``ote_only`` (D0.1 only), or
            ``fvg_only`` (D0.2 zone-touch only; targets at FVG entry).
    """

    tick_size: float = DEFAULT_TICK_SIZE
    penetration_ticks: int = sweep_mod.DEFAULT_PENETRATION_TICKS
    close_back_within_bars: int = sweep_mod.DEFAULT_CLOSE_BACK_WITHIN_BARS
    mss_max_lookback_fallback_bars: int = DEFAULT_MAX_LOOKBACK_FALLBACK_BARS
    swing_ref_lookback: int = DEFAULT_SWING_REF_LOOKBACK
    far_target_lookback_bars: int = DEFAULT_FAR_TARGET_LOOKBACK
    target_mode: TargetMode = TARGET_NEAREST
    stop_arm: StopArm = STOP_SWEPT_EXTREME
    entry_mode: EntryMode = ENTRY_OTE_705
    fvg_tiebreak: FvgTiebreak = FVG_EARLIEST
    stop_buffer_ticks: int = 1
    fvg_ote_conflict_ticks: int = DEFAULT_FVG_OTE_CONFLICT_TICKS
    rth_only: bool = True
    ote_primary_level: float = DEFAULT_OTE_PRIMARY
    ote_variant_level: float = DEFAULT_OTE_VARIANT
    entry_style: EntryStyle = ENTRY_COMBINED

    @property
    def sweep_config(self) -> SweepConfig:
        """Sweep parameters from structural constants."""
        return SweepConfig(
            tick_size=self.tick_size,
            penetration_ticks=self.penetration_ticks,
            close_back_within_bars=self.close_back_within_bars,
        )

    @property
    def mss_config(self) -> MssConfig:
        """MSS parameters from structural constants."""
        return MssConfig(max_lookback_fallback_bars=self.mss_max_lookback_fallback_bars)


@dataclass(frozen=True)
class OteSetup:
    """One detected standalone OTE trade opportunity.

    Both stop arms and both target variants are always populated for step-3 tagging;
    ``stop_price`` / ``target_price`` reflect the active config variant.
    """

    direction: str
    session_date: dt.date | None
    sweep_level: float
    sweep_side: str
    sweep_penetration_index: int
    sweep_close_back_index: int
    swept_extreme: float
    mss_index: int
    mss_swing_broken: float
    displacement_low: float
    displacement_high: float
    equilibrium: float
    fvg_top: float
    fvg_bottom: float
    fvg_c2_index: int
    fvg_ote_conflict: bool
    fvg_ote_distance_ticks: float | None
    entry_price: float
    ote_level_pct: float
    entry_fill_index: int | None
    entry_fill_timestamp: dt.datetime | None
    stop_arm_a: float
    stop_arm_b: float
    stop_price: float
    target_nearest: float
    target_nearest_kind: str
    target_far: float
    target_far_kind: str
    target_price: float
    signal_index: int
    signal_timestamp: dt.datetime | None


@dataclass(frozen=True)
class OteScanResult:
    """Setup scan output with geometry reject accounting."""

    setups: list[OteSetup]
    setups_detected: int
    geometry_rejects: dict[str, int]

    @property
    def geometry_reject_total(self) -> int:
        return sum(self.geometry_rejects.values())

    @property
    def geometry_reject_rate(self) -> float:
        if self.setups_detected == 0:
            return 0.0
        return self.geometry_reject_total / self.setups_detected


def ote_fib_price(
    direction: str,
    displacement_low: float,
    displacement_high: float,
    level_pct: float,
) -> float:
    """Return the OTE limit price on the displacement leg (D0.1).

    Long: anchor low (0%) → high (100%); entry at ``low + level_pct * range``.
    Short: anchor high (0%) → low (100%); entry at ``high - level_pct * range``.
    """
    rng = displacement_high - displacement_low
    if direction == DIRECTION_LONG:
        return displacement_low + level_pct * rng
    if direction == DIRECTION_SHORT:
        return displacement_high - level_pct * rng
    raise ValueError(f"direction must be 'long' or 'short'; got {direction!r}")


def mss_direction_to_trade(mss_direction: str) -> str:
    """Map MSS/sweep reversal direction to trade direction."""
    if mss_direction == mss_mod.DIRECTION_BULLISH:
        return DIRECTION_LONG
    if mss_direction == mss_mod.DIRECTION_BEARISH:
        return DIRECTION_SHORT
    raise ValueError(f"unexpected MSS direction: {mss_direction!r}")


def select_entry_fvg(
    fvgs: pl.DataFrame,
    *,
    displacement_start: int,
    displacement_end: int,
    mss_index: int,
    direction: str,
    equilibrium: float,
    ote_price: float,
    tiebreak: FvgTiebreak,
    df: pl.DataFrame,
    high: str = "high",
    low: str = "low",
    fvg_confirm_grace_bars: int = 1,
) -> dict[str, float | int] | None:
    """Select the entry FVG per D0.2.

    Eligible: ``c2_index`` inside displacement leg, midpoint on correct PD side,
    direction matches trade. FVG is causal when ``c3_index <= mss_index + grace``
    (c3 close may print up to one bar after the MSS bar when c2 is the MSS candle).
    """
    if fvgs.height == 0:
        return None

    want = fvg_mod.DIRECTION_BULLISH if direction == DIRECTION_LONG else fvg_mod.DIRECTION_BEARISH
    c3_max = mss_index + fvg_confirm_grace_bars
    eligible = fvgs.filter(
        (pl.col("direction") == want)
        & (pl.col("c2_index") >= displacement_start)
        & (pl.col("c2_index") <= displacement_end)
        & (pl.col("c3_index") <= c3_max)
    )
    if eligible.height == 0:
        return None

    if direction == DIRECTION_LONG:
        eligible = eligible.filter(pl.col("midpoint") < equilibrium)
    else:
        eligible = eligible.filter(pl.col("midpoint") > equilibrium)

    if eligible.height == 0:
        return None

    if tiebreak == FVG_EARLIEST:
        row = eligible.sort("c2_index").row(0, named=True)
    else:
        rows = eligible.to_dicts()
        best = min(
            rows,
            key=lambda r: abs(_fvg_touch_price(r, direction, df, high=high, low=low) - ote_price),
        )
        row = best

    return {
        "top": float(row["top"]),
        "bottom": float(row["bottom"]),
        "c2_index": int(row["c2_index"]),
        "midpoint": float(row["midpoint"]),
    }


def build_setup_from_sweep(
    df: pl.DataFrame,
    sweep: SweepResult,
    *,
    config: OteStrategyConfig | None = None,
    session_date: dt.date | None = None,
    pdh: float | None = None,
    pdl: float | None = None,
    fvgs: pl.DataFrame | None = None,
    timestamp: str = "timestamp",
    open_: str = "open",
    high: str = "high",
    low: str = "low",
    close: str = "close",
) -> OteSetup | None:
    """Assemble one OTE setup from a confirmed sweep (steps 2–7).

    Returns ``None`` when MSS, FVG, or entry fill preconditions fail.
    """
    if not sweep.swept or sweep.penetration_index is None or sweep.close_back_index is None:
        return None
    if sweep.penetration_extreme is None or sweep.reversal_direction is None:
        return None

    cfg = config or OteStrategyConfig()
    work = df.sort(timestamp) if timestamp in df.columns else df
    times = work[timestamp].to_list() if timestamp in work.columns else [None] * work.height

    mss = detect_mss_after_sweep(
        work,
        sweep,
        config=cfg.mss_config,
        timestamp=timestamp,
        open_=open_,
        high=high,
        low=low,
        close=close,
    )
    if not mss.fired or mss.displacement is None or mss.fired_index is None:
        return None

    direction = mss_direction_to_trade(mss.direction)
    if direction != mss_direction_to_trade(sweep.reversal_direction):
        return None

    disp = mss.displacement
    equilibrium = (disp.low + disp.high) / 2.0
    ote_pct = cfg.ote_primary_level if cfg.entry_mode == ENTRY_OTE_705 else cfg.ote_variant_level
    ote_price = ote_fib_price(direction, disp.low, disp.high, ote_pct)

    fvg_table = (
        fvgs
        if fvgs is not None
        else fvg_mod.detect_fvgs(
            work,
            timestamp=timestamp,
            high=high,
            low=low,
        )
    )
    fvg: dict[str, float | int] | None = None
    if cfg.entry_style != ENTRY_OTE_ONLY:
        fvg = select_entry_fvg(
            fvg_table,
            displacement_start=disp.start_index,
            displacement_end=disp.end_index,
            mss_index=mss.fired_index,
            direction=direction,
            equilibrium=equilibrium,
            ote_price=ote_price,
            tiebreak=cfg.fvg_tiebreak,
            df=work,
            high=high,
            low=low,
        )
        if fvg is None:
            return None

    if cfg.entry_style == ENTRY_FVG_ONLY:
        entry_price = float(fvg["top"]) if direction == DIRECTION_LONG else float(fvg["bottom"])
        ote_level_pct = ote_pct
    else:
        entry_price = ote_price
        ote_level_pct = ote_pct

    fvg_top = float(fvg["top"]) if fvg is not None else entry_price
    fvg_bottom = float(fvg["bottom"]) if fvg is not None else entry_price
    conflict, dist_ticks = (
        _fvg_ote_conflict(
            direction=direction,
            entry_price=entry_price,
            fvg_top=fvg_top,
            fvg_bottom=fvg_bottom,
            tick_size=cfg.tick_size,
            threshold_ticks=cfg.fvg_ote_conflict_ticks,
        )
        if fvg is not None and cfg.entry_style == ENTRY_COMBINED
        else (False, None)
    )

    fill_idx, fill_ts = _find_entry_fill(
        work,
        direction=direction,
        entry_price=entry_price,
        start_index=mss.fired_index + 1,
        timestamp=timestamp,
        high=high,
        low=low,
    )
    if fill_idx is None:
        return None

    c2_idx = int(fvg["c2_index"]) if fvg is not None else mss.fired_index
    c2_low = float(work[low][c2_idx])
    c2_high = float(work[high][c2_idx])

    stop_a, stop_b = _compute_stop_arms(
        direction=direction,
        swept_extreme=sweep.penetration_extreme,
        c2_low=c2_low,
        c2_high=c2_high,
        tick_size=cfg.tick_size,
        buffer_ticks=cfg.stop_buffer_ticks,
    )
    stop_price = stop_a if cfg.stop_arm == STOP_SWEPT_EXTREME else stop_b

    nearest, nearest_kind, far, far_kind = resolve_targets(
        work,
        direction=direction,
        signal_index=mss.fired_index,
        entry_price=entry_price,
        pdh=pdh,
        pdl=pdl,
        far_lookback=cfg.far_target_lookback_bars,
        high=high,
        low=low,
    )
    target_price = nearest if cfg.target_mode == TARGET_NEAREST else far

    reject = check_trade_geometry(direction, entry_price, stop_price, target_price)
    if reject is not None:
        return None

    return OteSetup(
        direction=direction,
        session_date=session_date,
        sweep_level=sweep.level,
        sweep_side=sweep.side,
        sweep_penetration_index=sweep.penetration_index,
        sweep_close_back_index=sweep.close_back_index,
        swept_extreme=sweep.penetration_extreme,
        mss_index=mss.fired_index,
        mss_swing_broken=float(mss.swing_level_broken or 0.0),
        displacement_low=disp.low,
        displacement_high=disp.high,
        equilibrium=equilibrium,
        fvg_top=fvg_top,
        fvg_bottom=fvg_bottom,
        fvg_c2_index=c2_idx,
        fvg_ote_conflict=conflict,
        fvg_ote_distance_ticks=dist_ticks,
        entry_price=entry_price,
        ote_level_pct=ote_level_pct,
        entry_fill_index=fill_idx,
        entry_fill_timestamp=fill_ts,
        stop_arm_a=stop_a,
        stop_arm_b=stop_b,
        stop_price=stop_price,
        target_nearest=nearest,
        target_nearest_kind=nearest_kind,
        target_far=far,
        target_far_kind=far_kind,
        target_price=target_price,
        signal_index=mss.fired_index,
        signal_timestamp=times[mss.fired_index],
    )


def scan_setups_with_stats(
    df: pl.DataFrame,
    *,
    config: OteStrategyConfig | None = None,
    session_date_col: str = pd_mod.DEFAULT_SESSION_DATE_COL,
    timestamp: str = "timestamp",
    open_: str = "open",
    high: str = "high",
    low: str = "low",
    close: str = "close",
) -> OteScanResult:
    """Scan bars for OTE setups; count geometry rejects separately."""
    cfg = config or OteStrategyConfig()
    if df.height == 0:
        return OteScanResult(setups=[], setups_detected=0, geometry_rejects={})

    work = df.sort(timestamp) if timestamp in df.columns else df
    if session_date_col not in work.columns or pd_mod.PDH_COL not in work.columns:
        work = pd_mod.add_pd_arrays(
            work,
            session_date_col=session_date_col,
            timestamp=timestamp,
            open_=open_,
            high=high,
            low=low,
            close=close,
        )

    sessions = work[session_date_col].unique().sort().to_list()
    setups: list[OteSetup] = []
    reject_counts: dict[str, int] = {}
    detected = 0

    for sess in sessions:
        if sess is None:
            continue
        sess_df = work.filter(pl.col(session_date_col) == sess)
        if cfg.rth_only:
            sess_df = _filter_rth(sess_df, timestamp=timestamp)
        if sess_df.height < 5:
            continue

        pdh_val = sess_df[pd_mod.PDH_COL][0]
        pdl_val = sess_df[pd_mod.PDL_COL][0]
        pdh = float(pdh_val) if pdh_val is not None else None
        pdl = float(pdl_val) if pdl_val is not None else None
        sess_date = sess if isinstance(sess, dt.date) else None

        sess_setups, sess_rejects, sess_detected = _scan_session_with_stats(
            sess_df,
            config=cfg,
            session_date=sess_date,
            pdh=pdh,
            pdl=pdl,
            timestamp=timestamp,
            open_=open_,
            high=high,
            low=low,
            close=close,
        )
        setups.extend(sess_setups)
        detected += sess_detected
        for reason, count in sess_rejects.items():
            reject_counts[reason] = reject_counts.get(reason, 0) + count

    return OteScanResult(
        setups=setups,
        setups_detected=detected,
        geometry_rejects=reject_counts,
    )


def scan_setups(
    df: pl.DataFrame,
    *,
    config: OteStrategyConfig | None = None,
    session_date_col: str = pd_mod.DEFAULT_SESSION_DATE_COL,
    timestamp: str = "timestamp",
    open_: str = "open",
    high: str = "high",
    low: str = "low",
    close: str = "close",
) -> list[OteSetup]:
    """Scan bars for all standalone OTE setups (unconstrained collection)."""
    return scan_setups_with_stats(
        df,
        config=config,
        session_date_col=session_date_col,
        timestamp=timestamp,
        open_=open_,
        high=high,
        low=low,
        close=close,
    ).setups


def _scan_session_with_stats(
    df: pl.DataFrame,
    *,
    config: OteStrategyConfig,
    session_date: dt.date | None,
    pdh: float | None,
    pdl: float | None,
    timestamp: str,
    open_: str,
    high: str,
    low: str,
    close: str,
) -> tuple[list[OteSetup], dict[str, int], int]:
    """Walk one session; return setups, reject counts, and pre-geometry detections."""
    n = df.height
    setups: list[OteSetup] = []
    reject_counts: dict[str, int] = {}
    detected = 0
    cursor = 2
    session_fvgs = fvg_mod.detect_fvgs(df, timestamp=timestamp, high=high, low=low)

    while cursor < n - 2:
        levels = _reference_levels(
            df,
            cursor,
            pdh=pdh,
            pdl=pdl,
            lookback=config.swing_ref_lookback,
            high=high,
            low=low,
            timestamp=timestamp,
        )
        advanced = False
        for level, side in levels:
            sweep = detect_sweep(
                df,
                level=level,
                side=side,
                config=config.sweep_config,
                search_start_index=cursor,
                timestamp=timestamp,
                high=high,
                low=low,
                close=close,
            )
            if not sweep.swept or sweep.close_back_index is None:
                continue
            detected += 1
            setup = _build_setup_or_reject(
                df,
                sweep,
                config=config,
                session_date=session_date,
                pdh=pdh,
                pdl=pdl,
                fvgs=session_fvgs,
                timestamp=timestamp,
                open_=open_,
                high=high,
                low=low,
                close=close,
                reject_counts=reject_counts,
            )
            if setup is not None:
                setups.append(setup)
                cursor = max(setup.entry_fill_index or setup.mss_index, setup.mss_index) + 1
                advanced = True
                break
        if not advanced:
            cursor += 1

    return setups, reject_counts, detected


def _build_setup_or_reject(
    df: pl.DataFrame,
    sweep: SweepResult,
    *,
    config: OteStrategyConfig | None = None,
    session_date: dt.date | None = None,
    pdh: float | None = None,
    pdl: float | None = None,
    fvgs: pl.DataFrame | None = None,
    timestamp: str = "timestamp",
    open_: str = "open",
    high: str = "high",
    low: str = "low",
    close: str = "close",
    reject_counts: dict[str, int],
) -> OteSetup | None:
    """Like :func:`build_setup_from_sweep` but records geometry rejects."""
    setup = build_setup_from_sweep(
        df,
        sweep,
        config=config,
        session_date=session_date,
        pdh=pdh,
        pdl=pdl,
        fvgs=fvgs,
        timestamp=timestamp,
        open_=open_,
        high=high,
        low=low,
        close=close,
    )
    if setup is not None:
        return setup
    partial = _build_setup_partial(
        df,
        sweep,
        config=config,
        session_date=session_date,
        pdh=pdh,
        pdl=pdl,
        fvgs=fvgs,
        timestamp=timestamp,
        open_=open_,
        high=high,
        low=low,
        close=close,
    )
    if partial is not None:
        direction, entry, stop, target = partial
        reject = check_trade_geometry(direction, entry, stop, target)
        if reject is not None:
            reject_counts[reject.reason] = reject_counts.get(reject.reason, 0) + 1
    return None


def _build_setup_partial(
    df: pl.DataFrame,
    sweep: SweepResult,
    *,
    config: OteStrategyConfig | None = None,
    session_date: dt.date | None = None,
    pdh: float | None = None,
    pdl: float | None = None,
    fvgs: pl.DataFrame | None = None,
    timestamp: str = "timestamp",
    open_: str = "open",
    high: str = "high",
    low: str = "low",
    close: str = "close",
) -> tuple[str, float, float, float] | None:
    """Return direction/entry/stop/target when chain succeeds except geometry."""
    del session_date
    if not sweep.swept or sweep.penetration_index is None or sweep.close_back_index is None:
        return None
    if sweep.penetration_extreme is None or sweep.reversal_direction is None:
        return None
    cfg = config or OteStrategyConfig()
    work = df.sort(timestamp) if timestamp in df.columns else df

    mss = detect_mss_after_sweep(
        work,
        sweep,
        config=cfg.mss_config,
        timestamp=timestamp,
        open_=open_,
        high=high,
        low=low,
        close=close,
    )
    if not mss.fired or mss.displacement is None or mss.fired_index is None:
        return None

    direction = mss_direction_to_trade(mss.direction)
    if direction != mss_direction_to_trade(sweep.reversal_direction):
        return None

    disp = mss.displacement
    equilibrium = (disp.low + disp.high) / 2.0
    ote_pct = cfg.ote_primary_level if cfg.entry_mode == ENTRY_OTE_705 else cfg.ote_variant_level
    ote_price = ote_fib_price(direction, disp.low, disp.high, ote_pct)

    fvg_table = (
        fvgs
        if fvgs is not None
        else fvg_mod.detect_fvgs(
            work,
            timestamp=timestamp,
            high=high,
            low=low,
        )
    )
    fvg: dict[str, float | int] | None = None
    if cfg.entry_style != ENTRY_OTE_ONLY:
        fvg = select_entry_fvg(
            fvg_table,
            displacement_start=disp.start_index,
            displacement_end=disp.end_index,
            mss_index=mss.fired_index,
            direction=direction,
            equilibrium=equilibrium,
            ote_price=ote_price,
            tiebreak=cfg.fvg_tiebreak,
            df=work,
            high=high,
            low=low,
        )
        if fvg is None:
            return None

    if cfg.entry_style == ENTRY_FVG_ONLY:
        assert fvg is not None
        entry_price = float(fvg["top"]) if direction == DIRECTION_LONG else float(fvg["bottom"])
    else:
        entry_price = ote_price

    fill_idx, _ = _find_entry_fill(
        work,
        direction=direction,
        entry_price=entry_price,
        start_index=mss.fired_index + 1,
        timestamp=timestamp,
        high=high,
        low=low,
    )
    if fill_idx is None:
        return None

    c2_idx = int(fvg["c2_index"]) if fvg is not None else mss.fired_index
    c2_low = float(work[low][c2_idx])
    c2_high = float(work[high][c2_idx])
    stop_a, stop_b = _compute_stop_arms(
        direction=direction,
        swept_extreme=sweep.penetration_extreme,
        c2_low=c2_low,
        c2_high=c2_high,
        tick_size=cfg.tick_size,
        buffer_ticks=cfg.stop_buffer_ticks,
    )
    stop_price = stop_a if cfg.stop_arm == STOP_SWEPT_EXTREME else stop_b
    nearest, _, far, _ = resolve_targets(
        work,
        direction=direction,
        signal_index=mss.fired_index,
        entry_price=entry_price,
        pdh=pdh,
        pdl=pdl,
        far_lookback=cfg.far_target_lookback_bars,
        high=high,
        low=low,
    )
    target_price = nearest if cfg.target_mode == TARGET_NEAREST else far
    return direction, entry_price, stop_price, target_price


def _scan_session(
    df: pl.DataFrame,
    *,
    config: OteStrategyConfig,
    session_date: dt.date | None,
    pdh: float | None,
    pdl: float | None,
    timestamp: str,
    open_: str,
    high: str,
    low: str,
    close: str,
) -> list[OteSetup]:
    """Walk one session forward, emitting non-overlapping setups."""
    setups, _, _ = _scan_session_with_stats(
        df,
        config=config,
        session_date=session_date,
        pdh=pdh,
        pdl=pdl,
        timestamp=timestamp,
        open_=open_,
        high=high,
        low=low,
        close=close,
    )
    return setups


def resolve_targets(
    df: pl.DataFrame,
    *,
    direction: str,
    signal_index: int,
    entry_price: float,
    pdh: float | None,
    pdl: float | None,
    far_lookback: int,
    high: str = "high",
    low: str = "low",
) -> tuple[float, str, float, str]:
    """Resolve nearest and far target pools per D0.6 (causal at ``signal_index``)."""
    highs = df[high].to_list()
    lows = df[low].to_list()
    session_high_max = max(highs[: signal_index + 1])
    session_low_min = min(lows[: signal_index + 1])

    if direction == DIRECTION_LONG:
        pools = _long_target_pools(
            df,
            signal_index=signal_index,
            entry_price=entry_price,
            pdh=pdh,
            session_high_max=session_high_max,
            far_lookback=far_lookback,
            high=high,
        )
    else:
        pools = _short_target_pools(
            df,
            signal_index=signal_index,
            entry_price=entry_price,
            pdl=pdl,
            session_low_min=session_low_min,
            far_lookback=far_lookback,
            low=low,
        )

    if not pools:
        fallback = entry_price + (50.0 if direction == DIRECTION_LONG else -50.0)
        return fallback, "fallback", fallback, "fallback"

    nearest = min(pools, key=lambda p: p[1])
    far = max(pools, key=lambda p: p[1])
    return nearest[0], nearest[2], far[0], far[2]


def _reference_levels(
    df: pl.DataFrame,
    end_index: int,
    *,
    pdh: float | None,
    pdl: float | None,
    lookback: int,
    high: str,
    low: str,
    timestamp: str,
) -> list[tuple[float, str]]:
    """Candidate sweep reference levels at ``end_index`` (causal)."""
    out: list[tuple[float, str]] = []
    if pdl is not None:
        out.append((pdl, SIDE_LOW))
    if pdh is not None:
        out.append((pdh, SIDE_HIGH))
    sh = recent_swing_level(
        df, side=SIDE_HIGH, lookback=lookback, end_index=end_index, timestamp=timestamp, high=high
    )
    sl = recent_swing_level(
        df, side=SIDE_LOW, lookback=lookback, end_index=end_index, timestamp=timestamp, low=low
    )
    if sh is not None:
        out.append((sh, SIDE_HIGH))
    if sl is not None:
        out.append((sl, SIDE_LOW))
    # Deduplicate levels keeping first side preference (PD arrays first).
    seen: set[float] = set()
    deduped: list[tuple[float, str]] = []
    for lvl, side in out:
        key = round(lvl, 8)
        if key in seen:
            continue
        seen.add(key)
        deduped.append((lvl, side))
    return deduped


def _long_target_pools(
    df: pl.DataFrame,
    *,
    signal_index: int,
    entry_price: float,
    pdh: float | None,
    session_high_max: float,
    far_lookback: int,
    high: str,
) -> list[tuple[float, float, str]]:
    """Opposing liquidity above entry for longs: (price, distance, kind)."""
    highs = df[high].to_list()
    pools: list[tuple[float, float, str]] = []
    for sw in confirmed_fractal_swings(df, side="high", up_to_index=signal_index + 1):
        if sw.level <= entry_price:
            continue
        post = highs[sw.confirmation_index + 1 : signal_index + 1]
        if post and max(post) >= sw.level:
            continue
        pools.append((sw.level, sw.level - entry_price, "fractal_high"))

    if pdh is not None and pdh > entry_price and session_high_max < pdh:
        pools.append((pdh, pdh - entry_price, "pdh"))

    start = max(0, signal_index - far_lookback)
    far_swings = [
        sw
        for sw in confirmed_fractal_swings(df, side="high", up_to_index=signal_index + 1)
        if sw.center_index >= start
        and sw.level > entry_price
        and (
            not highs[sw.confirmation_index + 1 : signal_index + 1]
            or max(highs[sw.confirmation_index + 1 : signal_index + 1]) < sw.level
        )
    ]
    if far_swings and not any(k == "pdh" for _, _, k in pools):
        furthest = max(far_swings, key=lambda s: s.level)
        pools.append((furthest.level, furthest.level - entry_price, "fractal_high_far"))

    return pools


def _short_target_pools(
    df: pl.DataFrame,
    *,
    signal_index: int,
    entry_price: float,
    pdl: float | None,
    session_low_min: float,
    far_lookback: int,
    low: str,
) -> list[tuple[float, float, str]]:
    """Opposing liquidity below entry for shorts: (price, distance, kind)."""
    lows = df[low].to_list()
    pools: list[tuple[float, float, str]] = []
    for sw in confirmed_fractal_swings(df, side="low", up_to_index=signal_index + 1):
        if sw.level >= entry_price:
            continue
        post = lows[sw.confirmation_index + 1 : signal_index + 1]
        if post and min(post) <= sw.level:
            continue
        pools.append((sw.level, entry_price - sw.level, "fractal_low"))

    if pdl is not None and pdl < entry_price and session_low_min > pdl:
        pools.append((pdl, entry_price - pdl, "pdl"))

    start = max(0, signal_index - far_lookback)
    far_swings = [
        sw
        for sw in confirmed_fractal_swings(df, side="low", up_to_index=signal_index + 1)
        if sw.center_index >= start
        and sw.level < entry_price
        and (
            not lows[sw.confirmation_index + 1 : signal_index + 1]
            or min(lows[sw.confirmation_index + 1 : signal_index + 1]) > sw.level
        )
    ]
    if far_swings and not any(k == "pdl" for _, _, k in pools):
        furthest = min(far_swings, key=lambda s: s.level)
        pools.append((furthest.level, entry_price - furthest.level, "fractal_low_far"))

    return pools


def _compute_stop_arms(
    *,
    direction: str,
    swept_extreme: float,
    c2_low: float,
    c2_high: float,
    tick_size: float,
    buffer_ticks: int,
) -> tuple[float, float]:
    """Stop arms A (swept extreme) and B (FVG c2) per D0.5."""
    buf = buffer_ticks * tick_size
    if direction == DIRECTION_LONG:
        return swept_extreme - buf, c2_low - buf
    return swept_extreme + buf, c2_high + buf


def _find_entry_fill(
    df: pl.DataFrame,
    *,
    direction: str,
    entry_price: float,
    start_index: int,
    timestamp: str,
    high: str,
    low: str,
) -> tuple[int | None, dt.datetime | None]:
    """First bar after MSS where a limit at ``entry_price`` would fill."""
    times = df[timestamp].to_list() if timestamp in df.columns else [None] * df.height
    for i in range(start_index, df.height):
        lo = float(df[low][i])
        hi = float(df[high][i])
        if direction == DIRECTION_LONG and lo <= entry_price:
            return i, times[i]
        if direction == DIRECTION_SHORT and hi >= entry_price:
            return i, times[i]
    return None, None


def _fvg_ote_conflict(
    *,
    direction: str,
    entry_price: float,
    fvg_top: float,
    fvg_bottom: float,
    tick_size: float,
    threshold_ticks: int,
) -> tuple[bool, float | None]:
    """True when OTE limit lies materially outside the selected FVG zone."""
    tol = threshold_ticks * tick_size
    if fvg_bottom - tol <= entry_price <= fvg_top + tol:
        return False, None
    if entry_price < fvg_bottom:
        dist = (fvg_bottom - entry_price) / tick_size
    else:
        dist = (entry_price - fvg_top) / tick_size
    return True, dist


def _fvg_touch_price(
    row: dict[str, float | int],
    direction: str,
    df: pl.DataFrame,
    *,
    high: str,
    low: str,
) -> float:
    """Price level used for nearest-OTE tie-break (top for long, bottom for short)."""
    return float(row["top"]) if direction == DIRECTION_LONG else float(row["bottom"])


def _filter_rth(df: pl.DataFrame, *, timestamp: str) -> pl.DataFrame:
    """Keep bars with timestamp in [09:30, 16:00] America/New_York."""
    if timestamp not in df.columns:
        return df

    def in_rth(ts: dt.datetime) -> bool:
        local = ts.astimezone(ET)
        t = local.time()
        return RTH_OPEN_ET <= t < RTH_CLOSE_ET

    mask = [in_rth(ts) for ts in df[timestamp].to_list()]
    return df.filter(pl.Series("_rth", mask))
