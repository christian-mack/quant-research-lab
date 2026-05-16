"""Tests for Apex-style EOD trailing simulation helpers."""

from __future__ import annotations

from datetime import date

import numpy as np
import pytest

from quant_research.statistics.apex_eod_trailing import (
    block_bootstrap_resample_trades,
    collapse_trades_to_session_streaks,
    max_drawdown_closed_trade_pnl,
    simulate_apex_50k_eod_two_phase,
    simulate_apex_eod_trailing,
    simulate_eval_window_50k_eod,
    trades_to_daily_pnls_chronological,
)


def test_simulate_pure_trailing_no_breach_flat() -> None:
    r = simulate_apex_eod_trailing(np.array([100.0, -200.0, 50.0]), mode="pure_trailing")
    assert r.breach_session_count == 0
    assert r.final_equity == 50_000.0 + 100 - 200 + 50
    assert r.n_sessions == 3


def test_simulate_funded_lock_freezes_floor() -> None:
    """After HWM crosses start+100, floor stays at first-lock level."""
    # Start 50k; +150 first day -> hwm 50150, lock floor 47150.
    # Second day -4000: equity 46150 < 47150 -> breach
    r = simulate_apex_eod_trailing(np.array([150.0, -4_000.0]), mode="funded_lock")
    assert r.breach_session_count >= 1
    assert r.min_margin_to_floor < 0


def test_trades_to_daily_sums_and_sorts() -> None:
    from datetime import date

    d1 = date(2020, 1, 2)
    d2 = date(2020, 1, 3)
    xs, ys = trades_to_daily_pnls_chronological(
        [d2, d1, d1],
        np.array([10.0, 100.0, 50.0]),
    )
    assert xs == [d1, d2]
    assert np.allclose(ys, np.array([150.0, 10.0]))

def test_collapse_session_streaks() -> None:
    d = [1, 1, 2, 2, 2, 3]
    p = [10.0, -5.0, 1.0, 2.0, 3.0, -1.0]
    ds, tot = collapse_trades_to_session_streaks(d, p)
    assert ds == [1, 2, 3]
    assert np.allclose(tot, np.array([5.0, 6.0, -1.0]))


def test_max_drawdown_closed_matches_known_path() -> None:
    p = np.array([100.0, -400.0, 200.0])
    dd = max_drawdown_closed_trade_pnl(p)
    assert dd == pytest.approx(-400.0)  # cum path 0,100,-300,-100 → -400 vs peak 100


def test_apex_50k_pre_lock_breach() -> None:
    """Equity lands $2K below HWM → breach (floor 48K when HWM 50K)."""
    ny = [date(2020, 1, d) for d in range(1, 6)]
    r = simulate_apex_50k_eod_two_phase(
        np.array([-2_100.0, 0.0, 0.0, 0.0, 0.0]),
        ny,
    )
    assert not r.survived
    assert r.trail_breach_sessions >= 1


def test_apex_50k_post_lock_breach() -> None:
    """HWM reaches 52K then equity below 50K → post-lock failure."""
    ny = [date(2020, 1, d) for d in range(1, 5)]
    r = simulate_apex_50k_eod_two_phase(
        np.array([2_500.0, -2_600.0, 0.0, 0.0]),
        ny,
    )
    assert r.locked_achieved
    assert not r.survived
    assert r.trail_breach_sessions >= 1


def test_apex_50k_pre_lock_survives_small_wiggle() -> None:
    ny = [date(2020, 1, 1), date(2020, 1, 2)]
    r = simulate_apex_50k_eod_two_phase(
        np.array([-500.0, 600.0]),
        ny,
    )
    assert r.survived
    assert r.trail_breach_sessions == 0


def test_eval_window_50k_pass_and_trailing_fail() -> None:
    good = simulate_eval_window_50k_eod(
        np.array([500.0, 3_000.0]),
        [date(2020, 1, 1), date(2020, 1, 2)],
        [1, 2],
    )
    assert good["outcome"] == "pass"
    bad = simulate_eval_window_50k_eod(
        np.array([-2_100.0]),
        [date(2020, 1, 1)],
        [1],
    )
    assert bad["outcome"] == "fail"
    assert bad["mode"] == "trailing_dd"


def test_block_bootstrap_shape_and_determinism() -> None:
    pnl = np.arange(12, dtype=np.float64)
    dates = list(range(12))
    rng = np.random.default_rng(0)
    c1, e1 = block_bootstrap_resample_trades(
        pnl,
        dates,
        block_len=3,
        n_target_trades=12,
        n_iterations=20,
        rng=rng,
    )
    assert c1.shape == (20,)
    assert e1.shape == (20,)
    rng2 = np.random.default_rng(0)
    c2, e2 = block_bootstrap_resample_trades(
        pnl,
        dates,
        block_len=3,
        n_target_trades=12,
        n_iterations=20,
        rng=rng2,
    )
    assert np.allclose(c1, c2)
    assert np.allclose(e1, e2)
