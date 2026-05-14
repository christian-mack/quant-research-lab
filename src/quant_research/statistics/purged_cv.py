"""Purged K-fold cross-validation for ordered event streams (López de Prado).

Each row is an **event** with ``[t0, t1]`` interval (e.g. trade entry/exit index or
timestamp). Rows must be **sorted by ``t0``**.

**Purge:** drop training samples whose ``[t0, t1]`` **overlaps** the test fold's
combined interval in **time** (information leakage).

**Embargo:** after the test fold's **last row index**, drop the next ``embargo``
row positions from the training set (default **0**).

This is a **research v1** implementation: correctness over speed; it does not yet
implement full *combinatorial* purged CV from AFML.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class PurgedKFoldConfig:
    n_splits: int
    embargo: int = 0

    def __post_init__(self) -> None:
        if self.n_splits < 2:
            msg = "n_splits must be >= 2"
            raise ValueError(msg)
        if self.embargo < 0:
            msg = "embargo must be >= 0"
            raise ValueError(msg)


def _interval_overlaps(
    t0_a: np.ndarray,
    t1_a: np.ndarray,
    t0_b: float,
    t1_b: float,
) -> np.ndarray:
    """Boolean vector: row overlaps [t0_b, t1_b] (closed interval overlap)."""
    return (t0_a <= t1_b) & (t1_a >= t0_b)


def iter_purged_k_fold_splits(
    t0: np.ndarray,
    t1: np.ndarray,
    config: PurgedKFoldConfig,
) -> Iterator[tuple[np.ndarray, np.ndarray]]:
    """
    Yield ``(train_indices, test_indices)`` with purge + embargo applied.

    ``t0``, ``t1`` are 1-D, same length, comparable (e.g. ``int64`` bar index or
    ``datetime64``); sorted by ``t0``.
    """
    n = t0.size
    if t1.size != n:
        msg = "t0 and t1 must have same length"
        raise ValueError(msg)
    if n < config.n_splits:
        msg = "not enough samples for n_splits"
        raise ValueError(msg)

    t0a = np.asarray(t0)
    t1a = np.asarray(t1)
    if not np.all(t0a[:-1] <= t0a[1:]):
        msg = "t0 must be sorted non-decreasing"
        raise ValueError(msg)
    if np.any(t1a < t0a):
        msg = "require t1 >= t0 row-wise"
        raise ValueError(msg)

    boundaries = np.linspace(0, n, config.n_splits + 1, dtype=int)
    for i in range(config.n_splits):
        start_b, end_b = int(boundaries[i]), int(boundaries[i + 1])
        if start_b >= end_b:
            continue
        test_idx = np.arange(start_b, end_b, dtype=np.int64)
        t0_test_min = float(np.min(t0a[test_idx]))
        t1_test_max = float(np.max(t1a[test_idx]))
        test_mask = np.zeros(n, dtype=bool)
        test_mask[test_idx] = True
        last_test_pos = int(np.max(test_idx))
        embargo_zone = np.zeros(n, dtype=bool)
        if config.embargo > 0:
            embargo_start = last_test_pos + 1
            if embargo_start < n:
                embargo_end = min(n, embargo_start + config.embargo)
                embargo_zone[embargo_start:embargo_end] = True

        overlap = _interval_overlaps(t0a, t1a, t0_test_min, t1_test_max)
        train_candidate = (~test_mask) & (~overlap) & (~embargo_zone)
        train_idx = np.flatnonzero(train_candidate)
        yield train_idx, test_idx


def embargo_split_indices(
    n_samples: int,
    test_fraction: float,
    embargo: int,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Single train/test split on row order with **embargo** after the train block.

    First ``(1-f)*n`` samples → train, next ``f*n`` → test; training rows whose
    index falls in ``(train_end - 1, train_end + embargo]`` are dropped if they
    would straddle — **v1**: train = ``[0 : train_end - embargo)``,
    test = ``[train_end : n)`` with ``train_end = floor((1-f)*n)`` (adjusted).

    **Simpler v1:** train = indices ``0 .. i-1`` excluding last ``embargo`` before
    ``i`` where ``i = floor((1-f)*n)``.
    """
    if not 0.0 < test_fraction < 1.0:
        msg = "test_fraction must be in (0, 1)"
        raise ValueError(msg)
    if n_samples < 3:
        msg = "n_samples must be >= 3"
        raise ValueError(msg)
    if embargo < 0:
        msg = "embargo must be >= 0"
        raise ValueError(msg)
    split = int(np.floor((1.0 - test_fraction) * n_samples))
    split = max(1, min(split, n_samples - 1))
    train_end = split - embargo
    train_end = max(1, train_end)
    train = np.arange(0, train_end, dtype=np.int64)
    test = np.arange(split, n_samples, dtype=np.int64)
    if test.size == 0:
        msg = "empty test set; increase n_samples or lower test_fraction"
        raise ValueError(msg)
    return train, test
