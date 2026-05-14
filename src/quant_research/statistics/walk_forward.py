"""Walk-forward validation scaffolding (expanding / rolling train–test windows).

Indices are **integer positions** (e.g. trade row order or bar index). The caller
supplies a function that fits on ``train_indices`` and evaluates metrics on
``test_indices``.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import numpy as np


class WalkForwardMode(StrEnum):
    """``ROLLING``: fixed train length slides forward; ``ANCHORED``: train starts at 0 and grows."""

    ROLLING = "rolling"
    ANCHORED = "anchored"


@dataclass(frozen=True, slots=True)
class WalkForwardWindow:
    train: tuple[int, ...]
    test: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class WalkForwardConfig:
    train_size: int
    test_size: int
    step: int
    mode: WalkForwardMode = WalkForwardMode.ROLLING

    def __post_init__(self) -> None:
        if self.train_size < 2 or self.test_size < 1 or self.step < 1:
            msg = "require train_size>=2, test_size>=1, step>=1"
            raise ValueError(msg)


def iter_walk_forward_indices(
    n_samples: int,
    config: WalkForwardConfig,
) -> Iterator[WalkForwardWindow]:
    """
    Yield (train, test) index tuples until the test slice would pass ``n_samples``.

    - **ROLLING:** train = ``[t, t + train_size)``, test follows immediately.
    - **ANCHORED:** train = ``[0, train_size + k * step)`` where *k* increments,
      test = ``[train_end, train_end + test_size)``.
    """
    if n_samples < config.train_size + config.test_size:
        msg = (
            f"n_samples={n_samples} too small for train_size={config.train_size} "
            f"+ test_size={config.test_size}"
        )
        raise ValueError(msg)

    if config.mode == WalkForwardMode.ROLLING:
        t = 0
        while True:
            tr_end = t + config.train_size
            te_end = tr_end + config.test_size
            if te_end > n_samples:
                return
            train = tuple(range(t, tr_end))
            test = tuple(range(tr_end, te_end))
            yield WalkForwardWindow(train=train, test=test)
            t += config.step
    else:
        # Anchored expanding train: minimal first train, then grow by step each round
        train_len = config.train_size
        while True:
            tr_end = train_len
            te_end = tr_end + config.test_size
            if te_end > n_samples:
                return
            train = tuple(range(0, tr_end))
            test = tuple(range(tr_end, te_end))
            yield WalkForwardWindow(train=train, test=test)
            train_len += config.step


@dataclass(slots=True)
class WalkForwardResult:
    windows: list[WalkForwardWindow]
    per_window: list[dict[str, Any]]
    aggregate: dict[str, float]


def run_walk_forward(
    sample_positions: Sequence[int] | int,
    config: WalkForwardConfig,
    evaluate: Callable[[tuple[int, ...], tuple[int, ...]], dict[str, Any]],
) -> WalkForwardResult:
    """
    Run walk-forward over positions ``0 .. n-1`` (or explicit ``sample_positions``).

    ``evaluate(train_idx, test_idx)`` returns a **dict** of metrics for one window.
    Aggregate returns **mean** across windows for each numeric metric.
    """
    if isinstance(sample_positions, int):
        n = sample_positions
    else:
        pos = list(sample_positions)
        n = len(pos)
        if pos != list(range(n)):
            msg = "custom sample_positions not yet supported; pass int n"
            raise NotImplementedError(msg)

    windows_ = list(iter_walk_forward_indices(n, config))
    per: list[dict[str, Any]] = []
    for w in windows_:
        per.append(evaluate(w.train, w.test))

    aggregate: dict[str, float] = {}
    if per:
        keys = per[0].keys()
        for k in keys:
            vals: list[float] = []
            for p in per:
                v = p.get(k)
                if v is None or isinstance(v, str | bool):
                    continue
                if isinstance(v, int | float | np.floating | np.integer):
                    vals.append(float(v))
            if vals:
                aggregate[k] = float(np.mean(vals))

    return WalkForwardResult(windows=windows_, per_window=per, aggregate=aggregate)
