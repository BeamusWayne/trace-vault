"""M3 unit: order-tolerant trajectory grading."""

from __future__ import annotations

import pytest

from trace_vault.eval.trajectory import is_subsequence, score_trajectory
from trace_vault.schemas.messages import ToolCall
from trace_vault.schemas.scenario import ExpectedToolCall
from trace_vault.schemas.transcript import Step, Transcript


def _transcript(*calls: tuple[str, dict]) -> Transcript:
    steps = tuple(
        Step(index=i, tool_call=ToolCall(id=f"c{i}", name=name, arguments=args))
        for i, (name, args) in enumerate(calls)
    )
    return Transcript(scenario="t", steps=steps, final_answer="done")


@pytest.mark.unit
def test_is_subsequence() -> None:
    assert is_subsequence(["a", "c"], ["a", "b", "c"])
    assert not is_subsequence(["c", "a"], ["a", "b", "c"])


@pytest.mark.unit
def test_perfect_trajectory_scores_one() -> None:
    transcript = _transcript(("search", {"query": "x"}), ("db_insert", {"table": "t"}))
    expected = [
        ExpectedToolCall(name="search", args={"query": "x"}),
        ExpectedToolCall(name="db_insert", args={"table": "t"}),
    ]
    score = score_trajectory(transcript, expected)
    assert score.tool_selection_accuracy == 1.0
    assert score.arg_match_rate == 1.0
    assert score.order_ok is True
    assert score.step_efficiency == 1.0


@pytest.mark.unit
def test_extra_steps_lower_efficiency_but_keep_selection() -> None:
    transcript = _transcript(("search", {}), ("calculator", {}), ("db_insert", {}))
    expected = [ExpectedToolCall(name="search"), ExpectedToolCall(name="db_insert")]
    score = score_trajectory(transcript, expected)
    assert score.tool_selection_accuracy == 1.0
    assert score.order_ok is True  # search ... db_insert is a subsequence
    assert score.step_efficiency == pytest.approx(2 / 3)


@pytest.mark.unit
def test_wrong_order_and_arg_mismatch_are_detected() -> None:
    transcript = _transcript(("db_insert", {"table": "wrong"}), ("search", {}))
    expected = [
        ExpectedToolCall(name="search"),
        ExpectedToolCall(name="db_insert", args={"table": "right"}),
    ]
    score = score_trajectory(transcript, expected)
    assert score.order_ok is False
    assert score.arg_match_rate == pytest.approx(0.5)  # search ok, db_insert args wrong


@pytest.mark.unit
def test_empty_expectation_is_vacuously_perfect() -> None:
    score = score_trajectory(_transcript(("search", {})), [])
    assert score.tool_selection_accuracy == 1.0
    assert score.expected_tools == 0
    assert score.actual_tools == 1
