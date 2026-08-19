"""Tests for :mod:`quant_research.ict.bias_module` (Phase 2 — daily bias assembly).

Synthetic sessions are built on the pairing timeframe (5m) to exercise the
confirmation chain sweep → CISD → EQ-respect → (SMT). The continuation and
reversal day-types are faithful to the TTrades worked examples cited in
``docs/ict/bias_module_spec.md`` (continuation @193/258s: trade lower first,
respect EQ, expand through PDH; reversal @45/64s: trade into PDH, reverse, back
toward EQ/PDL).
"""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import polars as pl
import pytest

from quant_research.ict.bias_module import (
    BIAS_LONG,
    BIAS_NONE,
    BIAS_SHORT,
    BiasConfig,
    PathDiagnostics,
    classify_session,
    emit_bias,
    path_completed,
    run_bias_series,
)

CT = ZoneInfo("America/Chicago")
SESSION_DATE = dt.date(2024, 6, 10)
RTH_OPEN = dt.datetime(2024, 6, 10, 8, 30, tzinfo=CT)  # 9:30 ET

# Prior-day reference levels shared by the controlled scenarios.
PDH = 110.0
PDL = 90.0
P_EQ = 100.0

# OR-disabled config keeps only PDL/PDH as sweep references for clean control.
CFG = BiasConfig(pairing_timeframe="5m", smt_required=False, opening_range_minutes=0)
CFG_SMT = BiasConfig(pairing_timeframe="5m", smt_required=True, opening_range_minutes=0)


def _bars(
    rows: list[tuple[float, float, float, float]],
    *,
    base: dt.datetime = RTH_OPEN,
    session_date: dt.date | None = None,
) -> pl.DataFrame:
    """Build 5m OHLC bars from (open, high, low, close) tuples."""
    data = {
        "timestamp": [base + dt.timedelta(minutes=5 * i) for i in range(len(rows))],
        "open": [r[0] for r in rows],
        "high": [r[1] for r in rows],
        "low": [r[2] for r in rows],
        "close": [r[3] for r in rows],
    }
    df = pl.DataFrame(data)
    if session_date is not None:
        df = df.with_columns(pl.lit(session_date).alias("cme_session_date"))
    return df


# ---------------------------------------------------------------------------
# Worked-example day types (continuation / reversal) — stop-condition (e).
# ---------------------------------------------------------------------------

# Continuation (bullish): trade lower first → sweep PDL → bullish CISD → reclaim &
# respect EQ → expand through PDH.
CONTINUATION_BULL = [
    (101.0, 101.0, 99.0, 99.5),    # 0 down-close
    (99.5, 99.5, 95.0, 95.5),      # 1 down-close
    (95.5, 95.5, 89.5, 91.0),      # 2 sweep PDL (low 89.5 < 89.75), closes back > 90
    (91.0, 98.0, 90.5, 97.0),      # 3 up-close, no CISD yet (97 < level 101)
    (97.0, 103.0, 96.5, 102.0),    # 4 bullish CISD fires (102 > 101)
    (102.0, 106.0, 101.0, 105.0),  # 5 holds above EQ
    (105.0, 109.5, 104.0, 108.5),  # 6 expands toward PDH (no PDH sweep)
]

# Reversal (bullish→bearish): trade into PDH → sweep buyside → reverse → back
# toward EQ/PDL.
REVERSAL_BEAR = [
    (99.0, 101.0, 98.5, 100.5),    # 0 up-close
    (100.5, 105.0, 100.0, 104.5),  # 1 up-close
    (104.5, 110.5, 104.0, 108.0),  # 2 sweep PDH (high 110.5 > 110.25), closes back < 110
    (108.0, 109.0, 102.0, 103.0),  # 3 down-close, no CISD yet (103 > level 99)
    (103.0, 104.0, 97.0, 98.0),    # 4 bearish CISD fires (98 < 99)
    (98.0, 99.0, 92.0, 93.0),      # 5 holds below EQ
    (93.0, 94.0, 90.5, 91.0),      # 6 expands toward PDL (no PDL sweep)
]


def test_continuation_day_emits_long() -> None:
    """Worked example: bullish continuation → long."""
    sb = classify_session(
        _bars(CONTINUATION_BULL), session_date=SESSION_DATE,
        pdh=PDH, pdl=PDL, p_eq=P_EQ, config=CFG,
    )
    assert sb.bias == BIAS_LONG
    assert sb.bullish.sweep and sb.bullish.cisd and sb.bullish.eq_respected
    assert sb.bullish.swept_reference == "PDL"
    assert sb.bullish.cisd_level == pytest.approx(101.0)
    assert not sb.bearish.cisd


def test_reversal_day_emits_short() -> None:
    """Worked example: bullish→bearish reversal → short."""
    sb = classify_session(
        _bars(REVERSAL_BEAR), session_date=SESSION_DATE,
        pdh=PDH, pdl=PDL, p_eq=P_EQ, config=CFG,
    )
    assert sb.bias == BIAS_SHORT
    assert sb.bearish.sweep and sb.bearish.cisd and sb.bearish.eq_respected
    assert sb.bearish.swept_reference == "PDH"
    assert sb.bearish.cisd_level == pytest.approx(99.0)
    assert not sb.bullish.cisd


def test_consolidation_range_day_emits_no_clear_bias() -> None:
    """A day that never sweeps PDL/PDH starts no directional path → no-clear-bias."""
    rng = [
        (100.0, 102.0, 98.0, 101.0),
        (101.0, 103.0, 99.0, 100.0),
        (100.0, 102.5, 98.5, 99.0),
        (99.0, 101.0, 97.5, 100.5),
        (100.5, 103.0, 99.5, 101.5),
        (101.5, 102.0, 98.0, 99.5),
        (99.5, 101.0, 98.5, 100.0),
    ]
    sb = classify_session(
        _bars(rng), session_date=SESSION_DATE, pdh=PDH, pdl=PDL, p_eq=P_EQ, config=CFG,
    )
    assert sb.bias == BIAS_NONE
    assert not sb.bullish.sweep and not sb.bearish.sweep


def test_opposing_eq_closure_invalidates_forming_bias() -> None:
    """A bullish sweep+CISD that then closes back below EQ is invalidated."""
    rows = [
        (101.0, 101.0, 99.0, 99.5),
        (99.5, 99.5, 95.0, 95.5),
        (95.5, 95.5, 89.5, 91.0),    # sweep PDL
        (91.0, 98.0, 90.5, 97.0),
        (97.0, 103.0, 96.5, 102.0),  # bullish CISD fires; reclaim EQ
        (102.0, 102.5, 96.0, 97.0),  # close 97 < EQ 100 → opposing EQ closure
        (97.0, 98.0, 95.0, 96.0),
    ]
    sb = classify_session(
        _bars(rows), session_date=SESSION_DATE, pdh=PDH, pdl=PDL, p_eq=P_EQ, config=CFG,
    )
    assert sb.bullish.sweep and sb.bullish.cisd
    assert sb.bullish.eq_respected is False
    assert sb.bias == BIAS_NONE


def test_first_session_no_prior_levels_is_no_clear_bias() -> None:
    """No prior-day levels (first session) → no-clear-bias regardless of action."""
    sb = classify_session(
        _bars(CONTINUATION_BULL), session_date=SESSION_DATE,
        pdh=None, pdl=None, p_eq=None, config=CFG,
    )
    assert sb.bias == BIAS_NONE
    assert "first session" in sb.reason


# ---------------------------------------------------------------------------
# Opening-range "recent short-term low" reference (Primitive 5).
# ---------------------------------------------------------------------------

def test_opening_range_low_sweep_emits_long() -> None:
    """When PDL/PDH are far away, a sweep of the opening-range low can form bias."""
    cfg_or = BiasConfig(pairing_timeframe="5m", smt_required=False, opening_range_minutes=10)
    rows = [
        (100.0, 101.0, 98.0, 99.0),   # 0 OR
        (99.0, 99.5, 97.0, 97.5),     # 1 OR -> OR-low = 97
        (97.5, 97.5, 96.0, 96.5),     # 2 sweep OR-low (96 < 96.75)
        (96.5, 98.0, 96.0, 97.8),     # 3 closes back inside (> 97)
        (97.8, 101.0, 97.5, 100.5),   # 4 bullish CISD fires (100.5 > 100); reclaim EQ
        (100.5, 104.0, 100.0, 103.0),
        (103.0, 106.0, 102.0, 105.0),
    ]
    sb = classify_session(
        _bars(rows), session_date=SESSION_DATE,
        pdh=130.0, pdl=70.0, p_eq=100.0, config=cfg_or,
    )
    assert sb.bias == BIAS_LONG
    assert sb.bullish.swept_reference == "OR_low"


# ---------------------------------------------------------------------------
# SMT configurable tier.
# ---------------------------------------------------------------------------

def _smt_frame(lows: list[float]) -> pl.DataFrame:
    """Correlated-instrument 5m bars; only `low` matters for bullish SMT."""
    rows = [(low + 1.0, low + 2.0, low, low + 1.0) for low in lows]
    return _bars(rows)


def test_smt_required_fires_when_divergence_present() -> None:
    """smt_required=True still emits long when correlated instruments diverge (hold)."""
    mnq = _bars(CONTINUATION_BULL)
    # MNQ takes out (current low 89.5 < prior 95); MES/MYM hold (current 96 > prior 95).
    mes = _smt_frame([95.0, 95.5, 96.0, 96.5, 96.0, 97.0, 98.0])
    mym = _smt_frame([95.0, 95.5, 96.0, 96.2, 96.1, 97.0, 98.0])
    frames = {"MNQ": mnq, "MES": mes, "MYM": mym}
    sb = classify_session(
        mnq, session_date=SESSION_DATE, pdh=PDH, pdl=PDL, p_eq=P_EQ,
        config=CFG_SMT, smt_frames=frames,
    )
    assert sb.bullish.smt_evaluable is True
    assert sb.bullish.smt_present is True
    assert sb.bias == BIAS_LONG


def test_smt_required_blocks_when_divergence_absent() -> None:
    """smt_required=True → no-clear-bias when correlated instruments all take out."""
    mnq = _bars(CONTINUATION_BULL)
    # All instruments take out their prior low → no divergence → SMT absent.
    mes = _smt_frame([95.0, 95.5, 90.0, 90.5, 90.0, 91.0, 92.0])
    mym = _smt_frame([95.0, 95.5, 89.0, 89.5, 89.0, 90.0, 91.0])
    frames = {"MNQ": mnq, "MES": mes, "MYM": mym}
    sb_required = classify_session(
        mnq, session_date=SESSION_DATE, pdh=PDH, pdl=PDL, p_eq=P_EQ,
        config=CFG_SMT, smt_frames=frames,
    )
    assert sb_required.bullish.smt_present is False
    assert sb_required.bias == BIAS_NONE
    # Same session, smt_required=False → still long (SMT logged, not gating).
    sb_optional = classify_session(
        mnq, session_date=SESSION_DATE, pdh=PDH, pdl=PDL, p_eq=P_EQ,
        config=CFG, smt_frames=frames,
    )
    assert sb_optional.bias == BIAS_LONG


def test_smt_not_evaluable_without_frames() -> None:
    """No correlated frames → SMT not evaluable; smt_required blocks the bias."""
    mnq = _bars(CONTINUATION_BULL)
    sb = classify_session(
        mnq, session_date=SESSION_DATE, pdh=PDH, pdl=PDL, p_eq=P_EQ,
        config=CFG_SMT, smt_frames=None,
    )
    assert sb.bullish.smt_evaluable is False
    assert sb.bias == BIAS_NONE


# ---------------------------------------------------------------------------
# Pure combinators.
# ---------------------------------------------------------------------------

def test_path_completed_smt_tier() -> None:
    base = PathDiagnostics(direction="bullish", sweep=True, cisd=True, eq_respected=True)
    assert path_completed(base, smt_required=False) is True
    assert path_completed(base, smt_required=True) is False
    with_smt = PathDiagnostics(
        direction="bullish", sweep=True, cisd=True, eq_respected=True,
        smt_evaluable=True, smt_present=True,
    )
    assert path_completed(with_smt, smt_required=True) is True


def test_emit_bias_both_complete_is_ambiguous() -> None:
    bull = PathDiagnostics(direction="bullish", sweep=True, cisd=True, eq_respected=True)
    bear = PathDiagnostics(direction="bearish", sweep=True, cisd=True, eq_respected=True)
    bias, reason = emit_bias(bull, bear, smt_required=False)
    assert bias == BIAS_NONE
    assert "ambiguous" in reason


# ---------------------------------------------------------------------------
# No look-ahead: session-N bias is independent of session N+1 bars.
# ---------------------------------------------------------------------------

def test_no_lookahead_session_bias_independent_of_future_sessions() -> None:
    d0 = dt.date(2024, 6, 10)
    d1 = dt.date(2024, 6, 11)
    d2 = dt.date(2024, 6, 12)
    base0 = dt.datetime(2024, 6, 10, 8, 30, tzinfo=CT)
    base1 = dt.datetime(2024, 6, 11, 8, 30, tzinfo=CT)
    base2 = dt.datetime(2024, 6, 12, 8, 30, tzinfo=CT)

    # Session 0 sets prior-day levels for session 1 (day_high=110, day_low=90).
    s0 = _bars(
        [(100.0, 110.0, 100.0, 105.0), (105.0, 106.0, 90.0, 95.0), (95.0, 96.0, 92.0, 94.0)],
        base=base0, session_date=d0,
    )
    s1 = _bars(CONTINUATION_BULL, base=base1, session_date=d1)  # → long
    s2 = _bars(REVERSAL_BEAR, base=base2, session_date=d2)      # arbitrary future

    full = pl.concat([s0, s1, s2])
    truncated = pl.concat([s0, s1])

    res_full = {sb.session_date: sb for sb in run_bias_series(full, config=CFG)}
    res_trunc = {sb.session_date: sb for sb in run_bias_series(truncated, config=CFG)}

    assert res_full[d1].bias == BIAS_LONG
    assert res_full[d1].bias == res_trunc[d1].bias
    assert res_full[d1].bullish.cisd_index == res_trunc[d1].bullish.cisd_index
    assert res_full[d1].bullish.swept_reference == res_trunc[d1].bullish.swept_reference
    assert res_full[d1].pdh == res_trunc[d1].pdh == pytest.approx(110.0)


def test_run_bias_series_missing_session_col_raises() -> None:
    bars = _bars(CONTINUATION_BULL)
    with pytest.raises(ValueError, match="session-date column"):
        run_bias_series(bars, config=CFG)
