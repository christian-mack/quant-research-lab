"""Tests for Apex-style EOD trailing simulation helpers."""

from __future__ import annotations

from datetime import date
from typing import cast

import numpy as np
import pytest

from quant_research.statistics.apex_eod_trailing import (
    ApexBalanceTier,
    apex_tier_index_for_equity,
    block_bootstrap_resample_trades,
    collapse_trades_to_session_streaks,
    max_drawdown_closed_trade_pnl,
    simulate_apex_50k_eod_two_phase,
    simulate_apex_eod_trailing,
    simulate_apex_eod_two_phase,
    simulate_apex_eod_two_phase_tiered_with_trace,
    simulate_eval_window_50k_eod,
    simulate_eval_window_eod,
    trades_to_daily_pnls_chronological,
)


def test_apex_tier_equity_below_table_uses_bottom_band() -> None:
    tiers = (
        ApexBalanceTier(25_000, 25_999, 1, 500),
        ApexBalanceTier(26_000, float("inf"), 2, 1_250),
    )
    idx, row = apex_tier_index_for_equity(24_150.0, tiers)
    assert idx == 0
    assert row.dll_limit == 500


def test_apex_tier_gap_between_bands_uses_lower_band() -> None:
    tiers = (
        ApexBalanceTier(25_000, 25_999, 1, 500),
        ApexBalanceTier(26_000, 26_999, 2, 500),
    )
    idx, row = apex_tier_index_for_equity(25_999.5, tiers)
    assert idx == 0
    assert row.max_contracts_mini == 1


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


def test_dll_pause_survives_and_terminal_fails_50k() -> None:
    """DLL day then recovery: pause survives; legacy terminal kills run."""
    # Same NY day: two sessions net past DLL; next day large win to 53K+.
    ny = [date(2020, 1, 1), date(2020, 1, 1), date(2020, 1, 2)]
    pnl = np.array([-600.0, -600.0, 5_200.0])
    pause = simulate_apex_50k_eod_two_phase(pnl, ny)
    assert pause.survived
    assert pause.dll_failure_days == 1
    assert not pause.dll_fail
    assert pause.final_equity == pytest.approx(50_000.0 - 1_200.0 + 5_200.0)

    term = simulate_apex_50k_eod_two_phase(pnl, ny, dll_terminates_run=True)
    assert not term.survived
    assert term.dll_fail


def test_dll_pause_eval_passes_terminal_fails() -> None:
    ny = [date(2020, 1, 1), date(2020, 1, 1), date(2020, 1, 2)]
    sess = [100, 100, 200]
    pnl = np.array([-600.0, -600.0, 5_200.0])
    ok = simulate_eval_window_50k_eod(pnl, ny, sess)
    assert ok["outcome"] == "pass"

    bad = simulate_eval_window_50k_eod(pnl, ny, sess, dll_terminates_run=True)
    assert bad["outcome"] == "fail"
    assert bad["mode"] == "dll"


def test_dll_pause_then_trailing_breach_failure_mode() -> None:
    """After DLL pause, a later day can still breach trailing — not DLL."""
    ny = [date(2020, 1, 1), date(2020, 1, 2), date(2020, 1, 3)]
    # Day1 DLL to 48,900; day2 −901 stays above −1K DLL but breaches 48K floor
    pnl = np.array([-1_100.0, -901.0, 0.0])
    r = simulate_apex_50k_eod_two_phase(pnl, ny)
    assert not r.survived
    assert r.trail_breach_sessions >= 1
    assert r.dll_failure_days == 1
    assert not r.dll_fail


def test_no_dll_hits_pause_matches_terminal_equity() -> None:
    ny = [date(2020, 1, 1), date(2020, 1, 2)]
    pnl = np.array([-400.0, 200.0])
    a = simulate_apex_50k_eod_two_phase(pnl, ny)
    b = simulate_apex_50k_eod_two_phase(pnl, ny, dll_terminates_run=True)
    assert a.survived == b.survived
    assert a.final_equity == pytest.approx(b.final_equity)
    assert a.dll_failure_days == 0
    assert not a.dll_fail


def test_generalized_25k_lock_floor() -> None:
    """$25K EOD: TDD $1K, lock at $26K (May 2026 operator table)."""
    ny = [date(2020, 1, 1), date(2020, 1, 2)]
    r = simulate_apex_eod_two_phase(
        np.array([1_000.0, 0.0]),
        ny,
        starting_balance=25_000.0,
        trailing_dd=1_000.0,
        dll_limit=500.0,
        lock_equity_threshold=26_000.0,
        post_lock_floor=25_000.0,
    )
    assert r.locked_achieved
    assert r.starting_balance == 25_000.0


def test_apex_50k_tiered_gain_and_demote() -> None:
    """PA tier change on balance; DLL tier from day-open tier."""
    tiers = (
        ApexBalanceTier(50_000, 51_499, 2, 1_000),
        ApexBalanceTier(51_500, 52_999, 3, 1_000),
        ApexBalanceTier(53_000, 55_999, 4, 2_000),
        ApexBalanceTier(56_000, float("inf"), 4, 3_000),
    )
    ny = [date(2020, 1, 1), date(2020, 1, 2), date(2020, 1, 3)]
    # Target 30 MNQ: tier0 cap 20 → +1500 on day1 at eff 20 → equity 51_500 (tier1 open day2)
    pnl = np.array([75.0, (-500.0 / 30.0), 0.0])
    r = simulate_apex_eod_two_phase(
        pnl,
        ny,
        starting_balance=50_000.0,
        trailing_dd=2_000.0,
        dll_limit=0.0,
        balance_tiers=tiers,
        target_qty_mnq=30.0,
        mnq_per_mini=10.0,
    )
    assert r.tier_summary is not None
    tr = r.tier_summary["tier_transitions"]
    assert len(cast(list, tr)) >= 1
    assert r.survived


def test_apex_50k_post_lock_floor_breach() -> None:
    """HWM ≥ 52K then equity < 50K fails post-lock."""
    ny = [date(2020, 1, d) for d in range(1, 5)]
    pnl = np.array([100.0, -130.0, 0.0, 0.0])
    tiers = (ApexBalanceTier(0.0, float("inf"), 50, 100_000.0),)
    r = simulate_apex_eod_two_phase(
        pnl,
        ny,
        starting_balance=50_000.0,
        trailing_dd=2_000.0,
        dll_limit=0.0,
        balance_tiers=tiers,
        target_qty_mnq=20.0,
    )
    assert r.locked_achieved
    assert not r.survived


def test_apex_50k_effective_qty_cap_40_mnq() -> None:
    tiers = (
        ApexBalanceTier(50_000, 51_499, 2, 1_000),
        ApexBalanceTier(51_500, 52_999, 3, 1_000),
        ApexBalanceTier(53_000, 55_999, 4, 2_000),
        ApexBalanceTier(56_000, float("inf"), 4, 3_000),
    )
    ny = [date(2020, 1, k) for k in range(1, 5)]
    pnl = np.array([75.0, 50.0, 10.0, 10.0])
    r = simulate_apex_eod_two_phase(
        pnl,
        ny,
        starting_balance=50_000.0,
        trailing_dd=2_000.0,
        dll_limit=0.0,
        balance_tiers=tiers,
        target_qty_mnq=40.0,
    )
    exp = 75.0 * 20 + 50.0 * 30 + 10.0 * 40 + 10.0 * 40
    assert r.final_equity == pytest.approx(50_000.0 + exp)
    assert r.tier_summary is not None


def test_tiered_session_trace_matches_plain_two_phase() -> None:
    tiers = (
        ApexBalanceTier(50_000, 51_499, 2, 1_000),
        ApexBalanceTier(51_500, 52_999, 3, 1_000),
        ApexBalanceTier(53_000, 55_999, 4, 2_000),
        ApexBalanceTier(56_000, float("inf"), 4, 3_000),
    )
    ny = [date(2020, 1, k) for k in range(1, 5)]
    pnl = np.array([75.0, 50.0, 10.0, 10.0])
    a, tr = simulate_apex_eod_two_phase_tiered_with_trace(
        pnl,
        ny,
        starting_balance=50_000.0,
        trailing_dd=2_000.0,
        balance_tiers=tiers,
        target_qty_mnq=40.0,
    )
    b = simulate_apex_eod_two_phase(
        pnl,
        ny,
        starting_balance=50_000.0,
        trailing_dd=2_000.0,
        dll_limit=0.0,
        balance_tiers=tiers,
        target_qty_mnq=40.0,
    )
    assert a.final_equity == pytest.approx(b.final_equity)
    assert a.survived == b.survived
    assert len(tr) == 4
    assert all("margin_to_floor_open" in row for row in tr)


def test_wave0c_regression_flat_matches_single_tier_mnq1() -> None:
    ny = [date(2020, 1, 1), date(2020, 1, 2)]
    daily = np.array([-400.0, 200.0])
    mega = (ApexBalanceTier(0.0, 1e24, 100_000, 1_000.0),)
    a = simulate_apex_eod_two_phase(
        daily,
        ny,
        starting_balance=50_000.0,
        trailing_dd=2_000.0,
        dll_limit=1_000.0,
        balance_tiers=mega,
        target_qty_mnq=1.0,
        mnq_per_mini=10.0,
    )
    b = simulate_apex_50k_eod_two_phase(daily, ny)
    assert a.final_equity == pytest.approx(b.final_equity)
    assert a.survived == b.survived


def test_eval_window_generalized_matches_50k_shorthand() -> None:
    ny = [date(2020, 1, 1)]
    sess = [1]
    p = np.array([3_000.0])
    a = simulate_eval_window_50k_eod(p, ny, sess)
    b = simulate_eval_window_eod(
        p,
        ny,
        sess,
        starting_balance=50_000.0,
        trailing_dd=2_000.0,
        profit_target=3_000.0,
        dll_limit=1_000.0,
        lock_equity_threshold=52_000.0,
        post_lock_floor=50_000.0,
    )
    assert a["outcome"] == b["outcome"] == "pass"


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
