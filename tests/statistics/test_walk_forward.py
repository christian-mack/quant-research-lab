"""Tests for :mod:`quant_research.statistics.walk_forward`."""

from __future__ import annotations

import numpy as np

from quant_research.statistics.walk_forward import (
    WalkForwardConfig,
    WalkForwardMode,
    iter_walk_forward_indices,
    run_walk_forward,
)


def test_rolling_walk_forward_window_count() -> None:
    cfg = WalkForwardConfig(train_size=20, test_size=5, step=5, mode=WalkForwardMode.ROLLING)
    windows = list(iter_walk_forward_indices(50, cfg))
    assert len(windows) == 6
    assert windows[0].train == tuple(range(0, 20))
    assert windows[0].test == tuple(range(20, 25))
    assert windows[1].train == tuple(range(5, 25))


def test_anchored_walk_forward_expands_train() -> None:
    cfg = WalkForwardConfig(train_size=10, test_size=4, step=5, mode=WalkForwardMode.ANCHORED)
    windows = list(iter_walk_forward_indices(40, cfg))
    assert windows[0].train == tuple(range(0, 10))
    assert windows[1].train == tuple(range(0, 15))


def test_synthetic_mean_shift_detected_in_walk_forward() -> None:
    """Train has +mu, test has -mu on excess metric — aggregate test mean lower."""
    rng = np.random.default_rng(0)
    n = 300
    series = np.concatenate(
        [
            rng.normal(2.0, 0.5, size=n // 2),
            rng.normal(-2.0, 0.5, size=n // 2),
        ],
    )

    def eval_fn(tr: tuple[int, ...], te: tuple[int, ...]) -> dict[str, float]:
        return {
            "train_mean": float(np.mean(series[list(tr)])),
            "test_mean": float(np.mean(series[list(te)])),
        }

    cfg = WalkForwardConfig(train_size=40, test_size=15, step=20, mode=WalkForwardMode.ROLLING)
    out = run_walk_forward(n, cfg, eval_fn)
    assert len(out.windows) >= 3
    assert any(
        p["test_mean"] < p["train_mean"] - 0.5 for p in out.per_window
    )
