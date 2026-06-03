"""The Determinism axis: does the agent take the same trajectory every replay?

Operates on trajectory *signatures* (a canonical fingerprint of the tool calls).
A run "passes" if its signature equals the canonical one; a diverged/errored run
(signature ``None``) never passes.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence

from ..schemas.report import DeterminismScore, Interval
from .stats import bootstrap_ci, min_runs_for_halfwidth, pass_at_k, pass_caret_k

Signature = tuple[tuple[str, str], ...]


def modal_signature(signatures: Sequence[Signature | None]) -> Signature | None:
    """The most common non-divergent trajectory (the de-facto canonical run)."""
    counts = Counter(s for s in signatures if s is not None)
    if not counts:
        return None
    return counts.most_common(1)[0][0]


def score_determinism(
    signatures: Sequence[Signature | None],
    *,
    k: int = 5,
    canonical: Signature | None = None,
    n_boot: int = 1000,
    seed: int = 0,
    halfwidth: float = 0.1,
) -> DeterminismScore:
    runs = len(signatures)
    if canonical is None:
        canonical = modal_signature(signatures)
    outcomes = [1.0 if (s is not None and s == canonical) else 0.0 for s in signatures]
    passing = int(sum(outcomes))
    rate = passing / runs if runs else 0.0
    low, high = bootstrap_ci(outcomes, n_boot=n_boot, seed=seed)
    return DeterminismScore(
        runs=runs,
        passing=passing,
        rate=rate,
        k=k,
        pass_caret_k=pass_caret_k(runs, passing, k),
        pass_at_k=pass_at_k(runs, passing, k),
        ci=Interval(low=low, high=high),
        min_runs_hint=min_runs_for_halfwidth(rate, halfwidth),
    )
