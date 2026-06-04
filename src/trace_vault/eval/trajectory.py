"""Trajectory grading: process-level quality of the canonical run.

Order-tolerant by design, many correct plans differ only in the order of
independent steps, so we grade tool *selection*, argument match, subsequence
*order*, and step *efficiency* separately rather than demanding an exact match.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence

from ..schemas.report import TrajectoryScore
from ..schemas.scenario import ExpectedToolCall
from ..schemas.transcript import Transcript


def is_subsequence(sub: Sequence[str], seq: Sequence[str]) -> bool:
    """Is ``sub`` an (order-preserving) subsequence of ``seq``?"""
    it = iter(seq)
    # A shared iterator advances across `want`s, giving the subsequence check.
    return all(any(have == want for have in it) for want in sub)


def _args_match(expected: dict, actual: dict) -> bool:
    """Expected args must be present in actual (actual may carry extras)."""
    return all(key in actual and actual[key] == value for key, value in expected.items())


def score_trajectory(
    transcript: Transcript,
    expected: Sequence[ExpectedToolCall],
    mode: str = "strict",
) -> TrajectoryScore:
    actual_calls = list(transcript.tool_calls)
    actual_names = [c.name for c in actual_calls]
    expected_names = [e.name for e in expected]
    n_expected = len(expected)

    if n_expected == 0:
        return TrajectoryScore(
            tool_selection_accuracy=1.0,
            arg_match_rate=1.0,
            order_ok=True,
            step_efficiency=1.0,
            expected_tools=0,
            actual_tools=len(actual_names),
        )

    # Tool selection: how many expected tools appear (multiset intersection).
    available = Counter(actual_names)
    selected = 0
    for name in expected_names:
        if available.get(name, 0) > 0:
            available[name] -= 1
            selected += 1

    # Argument match: pair each expected call to a distinct actual call.
    used = [False] * len(actual_calls)
    arg_hits = 0
    for exp in expected:
        for i, call in enumerate(actual_calls):
            if not used[i] and call.name == exp.name and _args_match(exp.args, dict(call.arguments)):
                used[i] = True
                arg_hits += 1
                break

    order_ok = is_subsequence(expected_names, actual_names)
    efficiency = min(1.0, n_expected / len(actual_names)) if actual_names else 0.0

    return TrajectoryScore(
        tool_selection_accuracy=selected / n_expected,
        arg_match_rate=arg_hits / n_expected,
        order_ok=order_ok,
        step_efficiency=efficiency,
        expected_tools=n_expected,
        actual_tools=len(actual_names),
    )
