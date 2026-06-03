"""M3 unit: reliability statistics against hand-computed closed-form values."""

from __future__ import annotations

import pytest

from trace_vault.eval.determinism import modal_signature, score_determinism
from trace_vault.eval.stats import (
    bootstrap_ci,
    min_runs_for_halfwidth,
    pass_at_k,
    pass_caret_k,
)


@pytest.mark.unit
@pytest.mark.parametrize(
    "n,c,k,expected",
    [
        (5, 2, 1, 0.4),  # k=1 -> just the rate
        (5, 0, 1, 0.0),
        (5, 5, 3, 1.0),
        (10, 3, 5, 1.0 - 21 / 252),  # 1 - C(7,5)/C(10,5)
    ],
)
def test_pass_at_k_closed_form(n: int, c: int, k: int, expected: float) -> None:
    assert pass_at_k(n, c, k) == pytest.approx(expected)


@pytest.mark.unit
@pytest.mark.parametrize(
    "n,c,k,expected",
    [
        (5, 2, 2, 1 / 10),  # C(2,2)/C(5,2)
        (6, 3, 2, 3 / 15),  # C(3,2)/C(6,2)
        (4, 4, 2, 1.0),
        (10, 3, 5, 0.0),  # c < k
    ],
)
def test_pass_caret_k_closed_form(n: int, c: int, k: int, expected: float) -> None:
    assert pass_caret_k(n, c, k) == pytest.approx(expected)


@pytest.mark.unit
def test_pass_caret_k_exposes_flakiness_pass_at_k_hides_it() -> None:
    # 8/20 runs reproduce: pass@5 looks healthy, pass^5 collapses.
    assert pass_at_k(20, 8, 5) > 0.9
    assert pass_caret_k(20, 8, 5) < 0.01


@pytest.mark.unit
def test_min_runs_for_halfwidth() -> None:
    assert min_runs_for_halfwidth(0.5, 0.1) == 97  # ceil(1.96^2 * 0.25 / 0.01)
    assert min_runs_for_halfwidth(1.0, 0.1) == 30  # rule of three: ceil(3/0.1)


@pytest.mark.unit
def test_bootstrap_ci_is_seeded_and_degenerate_on_constants() -> None:
    assert bootstrap_ci([1.0, 1.0, 1.0], seed=0) == (1.0, 1.0)
    assert bootstrap_ci([0.0, 0.0], seed=0) == (0.0, 0.0)
    assert bootstrap_ci([1, 0, 1, 0], seed=7) == bootstrap_ci([1, 0, 1, 0], seed=7)


@pytest.mark.unit
def test_score_determinism_uses_modal_canonical() -> None:
    a: tuple = (("calc", "{}"),)
    b: tuple = (("search", "{}"),)
    signatures = [a] * 12 + [b] * 8
    assert modal_signature(signatures) == a

    score = score_determinism(signatures, k=5)
    assert score.runs == 20
    assert score.passing == 12
    assert score.rate == pytest.approx(0.6)


@pytest.mark.unit
def test_score_determinism_counts_divergence_as_failure() -> None:
    sig: tuple = (("calc", "{}"),)
    signatures = [sig] * 18 + [None, None]  # two diverged runs
    score = score_determinism(signatures, k=5, canonical=sig)
    assert score.passing == 18
    assert score.rate == pytest.approx(0.9)
