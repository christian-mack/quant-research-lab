"""Wave 1 Track 2 — Phase 2: daily bias module (assembly of the ICT primitives).

A daily **state machine** that emits ``long`` / ``short`` / ``no-clear-bias`` per
CME equity-index session, assembling the five Phase-1 primitives
(``pd_arrays``, ``fvg``/``resample_ohlc``, ``cisd``, ``smt``, ``liquidity_sweep``)
into the TTrades mechanical daily-bias framework (``docs/ict/bias_module_spec.md``).

Strategy-chat decisions encoded here (research-log 2026-06-05 pre-registration):

- **Direction is confirmed, not seeded.** No ex-ante continuation-vs-reversal
  prediction. Both directions are armed each session; whichever path completes
  its confirmation chain via CISD dictates the bias.
- **EQ-respect is canonical** = closure past 50% of the **prior-day** range
  against bias = invalidation (not the operator's FVG-midpoint variant, which is
  a separately tested Phase-3 extension).
- **No-clear-bias day → emit ``no-clear-bias``** (the strategy stands down).

Confirmation chain (per direction, in causal order, no look-ahead):

    sweep  →  CISD  →  EQ-respect  →  (SMT, configurable tier)

- **Bullish:** sweep a downside reference (PDL or the opening-range low) →
  bullish CISD on the pairing TF after the sweep → prior-day EQ respected →
  ideally bullish SMT divergence at the low.
- **Bearish:** the mirror (sweep PDH / OR-high → bearish CISD → EQ respected →
  bearish SMT at the high).

SMT is a **configurable confirmation tier** (the pre-registered variant axis):
``smt_required=False`` (primary) fires on sweep+CISD+EQ and logs SMT
present/absent; ``smt_required=True`` only fires with SMT confirmation.

No look-ahead: the bias for session ``D`` uses only session ``D``'s intraday bars
(on the pairing timeframe) plus the prior-day PDH/PDL/EQ (known at ``D``'s open).
Within the session the stages are strictly time-ordered (CISD scanned after the
sweep, EQ-respect after the CISD fire, SMT over the sweep→CISD leg).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Final

import polars as pl

from quant_research.ict import cisd as cisd_mod
from quant_research.ict import fvg as fvg_mod
from quant_research.ict import liquidity_sweep as sweep_mod
from quant_research.ict import smt as smt_mod

BIAS_LONG: Final[str] = "long"
BIAS_SHORT: Final[str] = "short"
BIAS_NONE: Final[str] = "no-clear-bias"

DIRECTION_BULLISH: Final[str] = "bullish"
DIRECTION_BEARISH: Final[str] = "bearish"

DEFAULT_PAIRING_TIMEFRAME: Final[str] = "5m"
DEFAULT_TICK_SIZE: Final[float] = 0.25  # MNQ
DEFAULT_OPENING_RANGE_MINUTES: Final[int] = 30
DEFAULT_SMT_INSTRUMENTS: Final[tuple[str, ...]] = ("MNQ", "MES", "MYM")
PRIMARY_INSTRUMENT: Final[str] = "MNQ"


@dataclass(frozen=True)
class BiasConfig:
    """Configuration for the daily bias state machine.

    Only ``pairing_timeframe`` and ``smt_required`` are the pre-registered
    variant axes. Everything else is a documented structural constant carried
    here for auditability (not swept):

    Attributes:
        pairing_timeframe: Polars duration for the intraday confirmation TF the
            CISD is detected on. Pre-registered: ``"5m"`` (primary) or ``"15m"``.
        smt_required: If ``True``, a bias only fires with SMT confirmation on the
            winning path. If ``False`` (primary), the bias fires on
            sweep+CISD+EQ and SMT is logged present/absent but does not gate.
        tick_size: Instrument tick size (MNQ = 0.25), for the sweep penetration
            threshold.
        penetration_ticks: [MANUAL OBS] sweep depth (Primitive 5 default = 1).
        close_back_within_bars: [MANUAL OBS] sweep close-back window in pairing-TF
            bars (Primitive 5 default = 3).
        opening_range_minutes: Length of the early-session opening range whose
            low/high are used as the "recent short-term" sweep references, in
            addition to PDL/PDH. Structural (per spec "30-min early in session").
        smt_instruments: Instruments compared for SMT divergence; the first is the
            primary execution instrument (MNQ).
    """

    pairing_timeframe: str = DEFAULT_PAIRING_TIMEFRAME
    smt_required: bool = False
    tick_size: float = DEFAULT_TICK_SIZE
    penetration_ticks: int = sweep_mod.DEFAULT_PENETRATION_TICKS
    close_back_within_bars: int = sweep_mod.DEFAULT_CLOSE_BACK_WITHIN_BARS
    opening_range_minutes: int = DEFAULT_OPENING_RANGE_MINUTES
    smt_instruments: tuple[str, ...] = DEFAULT_SMT_INSTRUMENTS

    def __post_init__(self) -> None:
        if self.opening_range_minutes < 0:
            raise ValueError(
                f"opening_range_minutes must be >= 0; got {self.opening_range_minutes}"
            )
        if len(self.smt_instruments) < 2:
            raise ValueError("smt_instruments needs at least two instruments for SMT")
        if self.smt_instruments[0] != PRIMARY_INSTRUMENT:
            raise ValueError(
                f"smt_instruments[0] must be the primary instrument {PRIMARY_INSTRUMENT!r}"
            )

    @property
    def sweep_config(self) -> sweep_mod.SweepConfig:
        """The Primitive-5 :class:`~quant_research.ict.liquidity_sweep.SweepConfig`."""
        return sweep_mod.SweepConfig(
            tick_size=self.tick_size,
            penetration_ticks=self.penetration_ticks,
            close_back_within_bars=self.close_back_within_bars,
        )


@dataclass(frozen=True)
class PathDiagnostics:
    """Per-direction confirmation-chain diagnostics for one session.

    The booleans record how far the chain progressed; ``completed`` is derived via
    :func:`path_completed` given a ``smt_required`` choice, so the same
    diagnostics serve both SMT variants.

    Attributes:
        direction: ``"bullish"`` or ``"bearish"``.
        sweep: A confirmed sweep of a downside (bullish) / upside (bearish)
            reference occurred.
        cisd: A CISD in ``direction`` fired after the sweep.
        eq_respected: Prior-day EQ was respected after the CISD fire
            (``None`` if the chain did not reach this stage / no prior EQ).
        smt_evaluable: SMT could be evaluated (>=2 instruments with bars in both
            windows).
        smt_present: SMT divergence present on the sweep→CISD leg
            (``None`` if not evaluable / chain too short).
        swept_reference: ``"PDL"``/``"PDH"``/``"OR_low"``/``"OR_high"`` — which
            reference was swept (``None`` if no sweep).
        sweep_index: Pairing-TF bar index of the sweep penetration (``None``).
        cisd_index: Pairing-TF bar index of the CISD fire (``None``).
        cisd_level: The CISD level (first opposing-close candle's open).
        diverged_instruments: SMT diverging (held) instruments, for provenance.
    """

    direction: str
    sweep: bool = False
    cisd: bool = False
    eq_respected: bool | None = None
    smt_evaluable: bool = False
    smt_present: bool | None = None
    swept_reference: str | None = None
    sweep_index: int | None = None
    cisd_index: int | None = None
    cisd_level: float | None = None
    diverged_instruments: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SessionBias:
    """The emitted bias and full diagnostics for one session.

    Attributes:
        session_date: The CME session date.
        bias: ``"long"`` / ``"short"`` / ``"no-clear-bias"`` for ``config``'s
            ``smt_required``.
        bullish: Bullish-path diagnostics.
        bearish: Bearish-path diagnostics.
        pdh: Prior-day high (``None`` for the first session).
        pdl: Prior-day low (``None`` for the first session).
        p_eq: Prior-day EQ (``None`` for the first session).
        n_pairing_bars: Number of pairing-TF bars in the session.
        reason: Short human-readable classification reason.
    """

    session_date: dt.date
    bias: str
    bullish: PathDiagnostics
    bearish: PathDiagnostics
    pdh: float | None
    pdl: float | None
    p_eq: float | None
    n_pairing_bars: int
    reason: str


def path_completed(path: PathDiagnostics, *, smt_required: bool) -> bool:
    """Whether a path's confirmation chain is complete given the SMT tier.

    Args:
        path: The per-direction diagnostics.
        smt_required: If ``True``, SMT divergence must also be present.

    Returns:
        ``True`` iff sweep + CISD + EQ-respect (and, when ``smt_required``, SMT)
        all hold.
    """
    base = bool(path.sweep) and bool(path.cisd) and bool(path.eq_respected)
    if not smt_required:
        return base
    return base and bool(path.smt_present)


def emit_bias(
    bullish: PathDiagnostics,
    bearish: PathDiagnostics,
    *,
    smt_required: bool,
) -> tuple[str, str]:
    """Combine the two path diagnostics into a single bias label.

    Args:
        bullish: Bullish-path diagnostics.
        bearish: Bearish-path diagnostics.
        smt_required: SMT tier for completion.

    Returns:
        ``(bias, reason)`` where ``bias`` is one of :data:`BIAS_LONG`,
        :data:`BIAS_SHORT`, :data:`BIAS_NONE`.
    """
    bull_ok = path_completed(bullish, smt_required=smt_required)
    bear_ok = path_completed(bearish, smt_required=smt_required)
    if bull_ok and not bear_ok:
        return BIAS_LONG, "bullish chain complete"
    if bear_ok and not bull_ok:
        return BIAS_SHORT, "bearish chain complete"
    if bull_ok and bear_ok:
        return BIAS_NONE, "both chains complete (ambiguous)"
    return BIAS_NONE, "no chain completed"


def _parse_tf_minutes(timeframe: str) -> int:
    """Parse a simple polars minute/hour duration into minutes (``"5m"``→5)."""
    tf = timeframe.strip().lower()
    if tf.endswith("m"):
        return int(tf[:-1])
    if tf.endswith("h"):
        return int(tf[:-1]) * 60
    raise ValueError(f"unsupported pairing_timeframe {timeframe!r} (use e.g. '5m', '15m', '1h')")


def _eq_respected(
    closes: list[float],
    cisd_fire_index: int,
    p_eq: float,
    *,
    direction: str,
) -> bool:
    """Evaluate the canonical EQ-respect rule from the CISD fire to session end.

    Bullish: from ``cisd_fire_index`` onward some bar must **close at/above**
    ``p_eq`` (reclaim/hold the prior-day midpoint), and from that first reclaim
    through the end no bar may **close strictly below** ``p_eq``. Bearish mirrors
    (reclaim = close at/below ``p_eq``; invalidation = close strictly above).
    """
    is_bull = direction == DIRECTION_BULLISH
    reclaim_at: int | None = None
    for i in range(cisd_fire_index, len(closes)):
        reclaimed = closes[i] >= p_eq if is_bull else closes[i] <= p_eq
        if reclaimed:
            reclaim_at = i
            break
    if reclaim_at is None:
        return False
    for i in range(reclaim_at + 1, len(closes)):
        violated = closes[i] < p_eq if is_bull else closes[i] > p_eq
        if violated:
            return False
    return True


def _resample_session(
    session_bars: pl.DataFrame,
    *,
    timeframe: str,
    timestamp: str = "timestamp",
) -> pl.DataFrame:
    """Resample one session's bars to the pairing timeframe (sorted)."""
    if session_bars.height == 0:
        return session_bars
    return fvg_mod.resample_ohlc(session_bars, every=timeframe, timestamp=timestamp)


def _detect_path(
    bars: pl.DataFrame,
    *,
    direction: str,
    pdh: float | None,
    pdl: float | None,
    p_eq: float | None,
    config: BiasConfig,
    smt_frames: dict[str, pl.DataFrame] | None,
    timestamp: str = "timestamp",
    open_: str = "open",
    high: str = "high",
    low: str = "low",
    close: str = "close",
) -> PathDiagnostics:
    """Run one direction's sweep → CISD → EQ-respect → SMT chain on pairing-TF bars."""
    is_bull = direction == DIRECTION_BULLISH
    diag = PathDiagnostics(direction=direction)

    n = bars.height
    if n == 0 or p_eq is None:
        return diag

    highs = bars[high].to_list()
    lows = bars[low].to_list()
    closes = bars[close].to_list()
    times = bars[timestamp].to_list()

    # 1. Sweep references: the prior-day level and the opening-range extreme.
    or_minutes = config.opening_range_minutes
    or_end_index = 0
    or_level: float | None = None
    if or_minutes > 0 and n > 0:
        or_end_ts = times[0] + dt.timedelta(minutes=or_minutes)
        or_idx = [i for i, t in enumerate(times) if t < or_end_ts]
        if or_idx:
            or_end_index = or_idx[-1] + 1
            or_level = (
                min(lows[i] for i in or_idx) if is_bull else max(highs[i] for i in or_idx)
            )

    side = sweep_mod.SIDE_LOW if is_bull else sweep_mod.SIDE_HIGH
    prior_level = pdl if is_bull else pdh
    prior_label = "PDL" if is_bull else "PDH"
    or_label = "OR_low" if is_bull else "OR_high"

    candidates: list[tuple[int, str, sweep_mod.SweepResult]] = []
    if prior_level is not None:
        res = sweep_mod.detect_sweep(
            bars, level=prior_level, side=side, config=config.sweep_config,
            search_start_index=0, timestamp=timestamp, high=high, low=low, close=close,
        )
        if res.swept and res.penetration_index is not None:
            candidates.append((res.penetration_index, prior_label, res))
    if or_level is not None and or_end_index < n:
        res = sweep_mod.detect_sweep(
            bars, level=or_level, side=side, config=config.sweep_config,
            search_start_index=or_end_index, timestamp=timestamp, high=high, low=low, close=close,
        )
        if res.swept and res.penetration_index is not None:
            candidates.append((res.penetration_index, or_label, res))

    if not candidates:
        return diag
    # Earliest penetration wins; PDL/PDH breaks ties (listed first).
    candidates.sort(key=lambda c: c[0])
    sweep_index, swept_reference, _sweep_res = candidates[0]
    diag = PathDiagnostics(
        direction=direction, sweep=True, swept_reference=swept_reference,
        sweep_index=sweep_index,
    )

    # 2. CISD in `direction` anchored at the sweep extreme; scans forward from it.
    cisd_res = cisd_mod.detect_cisd(
        bars, direction=direction, anchor_index=sweep_index,
        timestamp=timestamp, open_=open_, high=high, low=low, close=close,
    )
    if not cisd_res.fired or cisd_res.fired_index is None:
        return diag
    cisd_index = cisd_res.fired_index
    diag = PathDiagnostics(
        direction=direction, sweep=True, cisd=True, swept_reference=swept_reference,
        sweep_index=sweep_index, cisd_index=cisd_index, cisd_level=cisd_res.cisd_level,
    )

    # 3. EQ-respect from the CISD fire through session end.
    eq_ok = _eq_respected(closes, cisd_index, p_eq, direction=direction)

    # 4. SMT over the sweep → CISD leg (always computed when possible; gates only
    #    under smt_required, applied downstream via path_completed).
    smt_evaluable, smt_present, diverged = _evaluate_smt(
        smt_frames=smt_frames, direction=direction,
        sweep_ts=times[sweep_index], cisd_ts=times[cisd_index],
        timeframe=config.pairing_timeframe, timestamp=timestamp, high=high, low=low,
    )

    return PathDiagnostics(
        direction=direction, sweep=True, cisd=True, eq_respected=eq_ok,
        smt_evaluable=smt_evaluable, smt_present=smt_present,
        swept_reference=swept_reference, sweep_index=sweep_index,
        cisd_index=cisd_index, cisd_level=cisd_res.cisd_level,
        diverged_instruments=diverged,
    )


def _evaluate_smt(
    *,
    smt_frames: dict[str, pl.DataFrame] | None,
    direction: str,
    sweep_ts: dt.datetime,
    cisd_ts: dt.datetime,
    timeframe: str,
    timestamp: str,
    high: str,
    low: str,
) -> tuple[bool, bool | None, list[str]]:
    """Evaluate SMT divergence on the sweep→CISD leg across aligned instruments.

    Returns ``(evaluable, present, diverged_instruments)``. Not evaluable when
    fewer than two instrument frames are supplied, or any frame lacks bars in the
    prior/current windows.
    """
    if smt_frames is None or len(smt_frames) < 2:
        return False, None, []
    tf_delta = dt.timedelta(minutes=_parse_tf_minutes(timeframe))
    instruments = list(smt_frames)
    # Prior window: session open up to the sweep bar. Current: sweep bar to CISD fire.
    session_open = min(
        df[timestamp].min() for df in smt_frames.values() if df.height > 0
    ) if any(df.height > 0 for df in smt_frames.values()) else None
    if session_open is None or session_open >= sweep_ts:
        return False, None, []
    prior_window = (session_open, sweep_ts)
    current_window = (sweep_ts, cisd_ts + tf_delta)
    try:
        res = smt_mod.detect_smt_from_frames(
            {k: smt_frames[k] for k in instruments},
            direction=direction,
            prior_window=prior_window,
            current_window=current_window,
            timestamp=timestamp,
            high=high,
            low=low,
        )
    except ValueError:
        return False, None, []
    return True, res.present, list(res.diverged_instruments)


def classify_session(
    pairing_bars: pl.DataFrame,
    *,
    session_date: dt.date,
    pdh: float | None,
    pdl: float | None,
    p_eq: float | None,
    config: BiasConfig,
    smt_frames: dict[str, pl.DataFrame] | None = None,
    timestamp: str = "timestamp",
    open_: str = "open",
    high: str = "high",
    low: str = "low",
    close: str = "close",
) -> SessionBias:
    """Classify one session's bias from its pairing-TF bars and prior-day levels.

    Args:
        pairing_bars: One session's OHLC bars **already on the pairing timeframe**
            (see :func:`run_bias_series`, which resamples), sorted by timestamp.
        session_date: The CME session date being classified.
        pdh: Prior-day high (``None`` → no prior day → ``no-clear-bias``).
        pdl: Prior-day low.
        p_eq: Prior-day EQ.
        config: :class:`BiasConfig`.
        smt_frames: Optional dict ``{instrument: pairing-TF bars for this session}``
            (must include the correlated instruments) for SMT; ``None`` disables.
        timestamp: Timestamp column name.
        open_: Open column name.
        high: High column name.
        low: Low column name.
        close: Close column name.

    Returns:
        A :class:`SessionBias`.
    """
    bars = pairing_bars.sort(timestamp) if timestamp in pairing_bars.columns else pairing_bars
    bullish = _detect_path(
        bars, direction=DIRECTION_BULLISH, pdh=pdh, pdl=pdl, p_eq=p_eq,
        config=config, smt_frames=smt_frames,
        timestamp=timestamp, open_=open_, high=high, low=low, close=close,
    )
    bearish = _detect_path(
        bars, direction=DIRECTION_BEARISH, pdh=pdh, pdl=pdl, p_eq=p_eq,
        config=config, smt_frames=smt_frames,
        timestamp=timestamp, open_=open_, high=high, low=low, close=close,
    )
    if p_eq is None:
        bias, reason = BIAS_NONE, "no prior-day levels (first session)"
    else:
        bias, reason = emit_bias(bullish, bearish, smt_required=config.smt_required)
    return SessionBias(
        session_date=session_date,
        bias=bias,
        bullish=bullish,
        bearish=bearish,
        pdh=pdh,
        pdl=pdl,
        p_eq=p_eq,
        n_pairing_bars=bars.height,
        reason=reason,
    )


def run_bias_series(
    mnq_rth: pl.DataFrame,
    *,
    config: BiasConfig,
    correlated_rth: dict[str, pl.DataFrame] | None = None,
    session_date_col: str = "cme_session_date",
    timestamp: str = "timestamp",
    open_: str = "open",
    high: str = "high",
    low: str = "low",
    close: str = "close",
) -> list[SessionBias]:
    """Run the bias state machine over a full multi-session RTH dataset.

    Computes prior-day PDH/PDL/EQ once (Primitive 1), then for each session
    resamples the MNQ (and correlated) bars to the pairing timeframe and calls
    :func:`classify_session`. Only the prior-day levels cross the session
    boundary, so there is no look-ahead.

    Args:
        mnq_rth: MNQ RTH bars with ``timestamp``/OHLC and ``cme_session_date``.
        config: :class:`BiasConfig`.
        correlated_rth: Optional ``{instrument: RTH bars}`` for SMT (e.g.
            ``{"MES": ..., "MYM": ...}``); MNQ is added automatically as the
            primary. ``None`` disables SMT (it will be logged not-evaluable).
        session_date_col: Session grouping key.
        timestamp: Timestamp column name.
        open_: Open column name.
        high: High column name.
        low: Low column name.
        close: Close column name.

    Returns:
        One :class:`SessionBias` per session, ordered by session date.

    Raises:
        ValueError: If required columns are missing.
    """
    from quant_research.ict import pd_arrays as pd_mod

    missing = [c for c in (timestamp, open_, high, low, close) if c not in mnq_rth.columns]
    if missing:
        raise ValueError(f"mnq_rth missing required columns: {missing}")
    if session_date_col not in mnq_rth.columns:
        raise ValueError(f"mnq_rth missing session-date column {session_date_col!r}")

    daily = pd_mod.daily_pd_arrays(
        mnq_rth, session_date_col=session_date_col, timestamp=timestamp,
        open_=open_, high=high, low=low, close=close,
    ).select(session_date_col, pd_mod.PDH_COL, pd_mod.PDL_COL, pd_mod.PRIOR_EQ_COL)
    levels = {
        row[session_date_col]: (row[pd_mod.PDH_COL], row[pd_mod.PDL_COL], row[pd_mod.PRIOR_EQ_COL])
        for row in daily.iter_rows(named=True)
    }

    mnq_by_session = _partition_by_session(mnq_rth, session_date_col, timestamp)
    corr_by_session: dict[str, dict[dt.date, pl.DataFrame]] = {}
    if correlated_rth:
        for inst, df in correlated_rth.items():
            corr_by_session[inst] = _partition_by_session(df, session_date_col, timestamp)

    results: list[SessionBias] = []
    for session_date in sorted(mnq_by_session):
        raw = mnq_by_session[session_date]
        pairing = _resample_session(raw, timeframe=config.pairing_timeframe, timestamp=timestamp)
        smt_frames = _build_smt_frames(
            session_date, pairing, corr_by_session, config, timestamp,
        )
        pdh, pdl, p_eq = levels.get(session_date, (None, None, None))
        results.append(
            classify_session(
                pairing, session_date=session_date, pdh=pdh, pdl=pdl, p_eq=p_eq,
                config=config, smt_frames=smt_frames,
                timestamp=timestamp, open_=open_, high=high, low=low, close=close,
            )
        )
    return results


def _partition_by_session(
    df: pl.DataFrame, session_date_col: str, timestamp: str
) -> dict[dt.date, pl.DataFrame]:
    """Split a frame into ``{session_date: bars}`` (null session dates dropped)."""
    if session_date_col not in df.columns:
        return {}
    sub = df.filter(pl.col(session_date_col).is_not_null())
    if sub.height == 0:
        return {}
    out: dict[dt.date, pl.DataFrame] = {}
    for part in sub.partition_by(session_date_col, maintain_order=False):
        key = part[session_date_col][0]
        out[key] = part.sort(timestamp) if timestamp in part.columns else part
    return out


def _build_smt_frames(
    session_date: dt.date,
    mnq_pairing: pl.DataFrame,
    corr_by_session: dict[str, dict[dt.date, pl.DataFrame]],
    config: BiasConfig,
    timestamp: str,
) -> dict[str, pl.DataFrame] | None:
    """Assemble per-session pairing-TF frames for SMT (MNQ + correlated)."""
    if not corr_by_session:
        return None
    frames: dict[str, pl.DataFrame] = {PRIMARY_INSTRUMENT: mnq_pairing}
    for inst in config.smt_instruments[1:]:
        per = corr_by_session.get(inst, {})
        raw = per.get(session_date)
        if raw is None or raw.height == 0:
            continue
        frames[inst] = _resample_session(
            raw, timeframe=config.pairing_timeframe, timestamp=timestamp
        )
    if len(frames) < 2:
        return None
    return frames
