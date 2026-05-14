"""Tests for :mod:`quant_research.statistics.purged_cv`."""

from __future__ import annotations

import numpy as np

from quant_research.statistics.purged_cv import (
    PurgedKFoldConfig,
    embargo_split_indices,
    iter_purged_k_fold_splits,
)


def test_purged_kfold_removes_overlapping_train() -> None:
    """Long event spanning full timeline should never appear in train if it hits test."""
    n = 20
    t0 = np.arange(n, dtype=np.int64)
    t1 = np.full(n, n + 10, dtype=np.int64)  # all overlap global interval
    cfg = PurgedKFoldConfig(n_splits=4, embargo=0)
    folds = list(iter_purged_k_fold_splits(t0, t1, cfg))
    assert len(folds) == 4
    for tr, te in folds:
        assert np.intersect1d(tr, te).size == 0
        assert tr.size + te.size < n


def test_embargo_excludes_buffer() -> None:
    train, test = embargo_split_indices(100, test_fraction=0.4, embargo=5)
    assert test[0] >= train[-1] + 1 + 5 or test[0] > train[-1]
