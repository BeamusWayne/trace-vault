"""Reliability statistics, exact where it can be, honest where it can't.

* ``pass_at_k`` / ``pass_caret_k`` use the unbiased combinatorial estimators, so
  they're tested against hand-computed closed-form values.
* ``bootstrap_ci`` is seeded, so a confidence interval is reproducible.
* ``min_runs_for_halfwidth`` answers "did I even run enough times?", a guard
  against celebrating a 2-point "win" that is really sampling noise.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np


def pass_at_k(n: int, c: int, k: int) -> float:
    """Unbiased estimate of P(at least one of k sampled runs passes).

    ``n`` total runs, ``c`` of them passing. This is the classic Codex/HumanEval
    estimator ``1 - C(n-c, k) / C(n, k)``.
    """
    if n <= 0 or k <= 0:
        return 0.0
    k = min(k, n)
    if c >= n:
        return 1.0
    if n - c < k:
        return 1.0
    return 1.0 - math.comb(n - c, k) / math.comb(n, k)


def pass_caret_k(n: int, c: int, k: int) -> float:
    """Estimate of P(k sampled runs ALL pass) = ``C(c, k) / C(n, k)``.

    This is the metric that exposes hidden flakiness: pass@k can look healthy
    while pass^k collapses.
    """
    if n <= 0 or k <= 0:
        return 0.0
    k = min(k, n)
    if c < k:
        return 0.0
    return math.comb(c, k) / math.comb(n, k)


def bootstrap_ci(
    outcomes: Sequence[float],
    *,
    n_boot: int = 1000,
    seed: int = 0,
    alpha: float = 0.05,
) -> tuple[float, float]:
    """A seeded percentile bootstrap CI for the mean of binary ``outcomes``."""
    arr = np.asarray(outcomes, dtype=float)
    n = arr.size
    if n == 0:
        return (0.0, 0.0)
    rng = np.random.default_rng(seed)
    samples = arr[rng.integers(0, n, size=(n_boot, n))].mean(axis=1)
    low = float(np.percentile(samples, 100 * alpha / 2))
    high = float(np.percentile(samples, 100 * (1 - alpha / 2)))
    return (low, high)


def min_runs_for_halfwidth(p: float, halfwidth: float = 0.1, z: float = 1.96) -> int:
    """How many runs to estimate a rate to +/- ``halfwidth`` at confidence ``z``.

    At the boundaries (p == 0 or 1) the Wald variance is degenerate, so we fall
    back to the rule of three.
    """
    p = min(max(p, 0.0), 1.0)
    if halfwidth <= 0:
        raise ValueError("halfwidth must be positive")
    if p in (0.0, 1.0):
        return max(1, math.ceil(3.0 / halfwidth))
    return max(1, math.ceil((z * z * p * (1 - p)) / (halfwidth * halfwidth)))
