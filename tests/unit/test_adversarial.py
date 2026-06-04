"""Adversarial and boundary tests for the core modules.

These target invariants (pass^k <= pass@k, key-order invariance, exactly-once
effects) and edge cases (path escapes, exhausted cursors, regressions vs a
baseline) rather than happy paths.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from trace_vault.agent.tools.base import ToolResult
from trace_vault.agent.world import World
from trace_vault.cassette.matcher import CassetteCursor, classify_divergence
from trace_vault.cassette.normalize import (
    normalize_messages,
    normalize_request,
    request_key,
    scrub_text,
)
from trace_vault.errors import DivergenceError
from trace_vault.eval.stats import (
    bootstrap_ci,
    min_runs_for_halfwidth,
    pass_at_k,
    pass_caret_k,
)
from trace_vault.eval.trajectory import score_trajectory
from trace_vault.gate import Baseline, ScenarioBaseline, evaluate_gate
from trace_vault.ledger import EffectLedger
from trace_vault.schemas.cassette import Cassette, Interaction
from trace_vault.schemas.messages import Completion, Message, ToolCall
from trace_vault.schemas.report import (
    DeterminismScore,
    FaithfulnessScore,
    GateThresholds,
    Interval,
    TaskReport,
    TrajectoryScore,
)
from trace_vault.schemas.scenario import ExpectedToolCall
from trace_vault.schemas.transcript import Step, Transcript

_COMBOS = [(20, 8, 5), (10, 3, 4), (5, 5, 3), (5, 0, 2), (100, 50, 5), (7, 7, 7), (20, 1, 5)]


# --- stats: invariants that must hold for every input ----------------------


@pytest.mark.unit
@pytest.mark.parametrize("n,c,k", _COMBOS)
def test_pass_caret_k_never_exceeds_pass_at_k(n: int, c: int, k: int) -> None:
    # P(all k pass) <= P(at least one of k passes), always.
    assert pass_caret_k(n, c, k) <= pass_at_k(n, c, k) + 1e-12


@pytest.mark.unit
@pytest.mark.parametrize("n,c,k", _COMBOS)
def test_pass_rates_stay_in_unit_interval(n: int, c: int, k: int) -> None:
    for value in (pass_at_k(n, c, k), pass_caret_k(n, c, k)):
        assert 0.0 <= value <= 1.0


@pytest.mark.unit
def test_k1_collapses_both_estimators_to_the_rate() -> None:
    for n, c in [(5, 2), (10, 7), (3, 0)]:
        assert pass_at_k(n, c, 1) == pytest.approx(c / n)
        assert pass_caret_k(n, c, 1) == pytest.approx(c / n)


@pytest.mark.unit
def test_k_is_clamped_above_n() -> None:
    assert pass_at_k(5, 3, 10) == pass_at_k(5, 3, 5)
    assert pass_caret_k(5, 3, 10) == pass_caret_k(5, 3, 5)


@pytest.mark.unit
def test_pass_at_k_is_monotonic_in_passes() -> None:
    rates = [pass_at_k(20, c, 5) for c in range(0, 21, 4)]
    assert rates == sorted(rates)


@pytest.mark.unit
def test_bootstrap_ci_is_bounded_seeded_and_degenerate_on_constants() -> None:
    outcomes = [1, 0, 1, 1, 0, 1, 0, 0, 1, 1]
    low, high = bootstrap_ci(outcomes, seed=3)
    assert 0.0 <= low <= high <= 1.0
    assert bootstrap_ci(outcomes, seed=3) == bootstrap_ci(outcomes, seed=3)
    assert bootstrap_ci([1.0] * 5, seed=1) == (1.0, 1.0)


@pytest.mark.unit
def test_min_runs_grows_as_halfwidth_shrinks_and_rejects_nonpositive() -> None:
    assert min_runs_for_halfwidth(0.5, 0.05) > min_runs_for_halfwidth(0.5, 0.1)
    assert min_runs_for_halfwidth(0.0, 0.1) == 30  # rule of three
    with pytest.raises(ValueError):
        min_runs_for_halfwidth(0.5, 0.0)


# --- normalize: scrub recursively, hash invariant to key order -------------


@pytest.mark.unit
def test_scrub_recurses_into_nested_arguments() -> None:
    uid = "550e8400-e29b-41d4-a716-446655440000"
    messages = [
        Message(
            role="assistant",
            tool_calls=(
                ToolCall(id="x", name="t", arguments={"o": {"inner": [uid, "2026-06-04T11:30:00Z"]}}),
            ),
        )
    ]
    args = normalize_messages(messages)[0]["tool_calls"][0]["arguments"]
    assert "<UUID>" in str(args)
    assert "<TS>" in str(args)


@pytest.mark.unit
def test_request_key_is_invariant_to_argument_key_order() -> None:
    a = [Message(role="assistant", tool_calls=(ToolCall(id="x", name="t", arguments={"a": 1, "b": 2}),))]
    b = [Message(role="assistant", tool_calls=(ToolCall(id="x", name="t", arguments={"b": 2, "a": 1}),))]
    assert request_key(a) == request_key(b)


@pytest.mark.unit
def test_scrub_does_not_over_match_plain_text() -> None:
    assert scrub_text("price 85 in room A") == "price 85 in room A"
    assert scrub_text("deadbeef cafe") == "deadbeef cafe"  # short hex is not a UUID


# --- matcher: exhaustion and duplicate keys --------------------------------


def _interaction(messages: list[Message], completion: Completion, index: int) -> Interaction:
    return Interaction(
        index=index,
        request_key=request_key(messages),
        request_digest=normalize_request(messages),
        completion=completion,
    )


@pytest.mark.unit
def test_subset_cursor_exhausts_after_consuming_its_only_match() -> None:
    recorded = [Message(role="user", content="ping")]
    cassette = Cassette(
        name="c", match_mode="subset",
        interactions=(_interaction(recorded, Completion(content="pong"), 0),),
    )
    cursor = CassetteCursor(cassette)
    longer = [Message(role="system", content="x"), Message(role="user", content="ping")]
    assert cursor.next_completion(longer).content == "pong"
    with pytest.raises(DivergenceError) as exc:
        cursor.next_completion([Message(role="user", content="ping")])
    assert exc.value.kind == "exhausted"


@pytest.mark.unit
def test_unordered_cursor_consumes_duplicate_keys_once_each() -> None:
    m = [Message(role="user", content="A")]
    cassette = Cassette(
        name="c", match_mode="unordered",
        interactions=(
            _interaction(m, Completion(content="r0"), 0),
            _interaction(m, Completion(content="r1"), 1),
        ),
    )
    cursor = CassetteCursor(cassette)
    assert cursor.next_completion(m).content == "r0"
    assert cursor.next_completion(m).content == "r1"
    with pytest.raises(DivergenceError):
        cursor.next_completion(m)


@pytest.mark.unit
def test_classify_arg_mismatch_on_nested_values() -> None:
    def digest(arg: object) -> dict:
        return {
            "messages": [
                {"role": "assistant", "content": "",
                 "tool_calls": [{"id": "call_0", "name": "t", "arguments": {"x": arg}}],
                 "tool_call_id": None, "name": None}
            ],
            "tools": [],
        }

    kind, _ = classify_divergence(digest([1, 2]), digest([1, 3]))
    assert kind == "arg-mismatch"


# --- ledger: keying and exactly-once ---------------------------------------


@pytest.mark.unit
def test_ledger_keys_by_arguments_when_no_idempotency_key() -> None:
    ledger = EffectLedger()
    runs: list[int] = []

    def run() -> ToolResult:
        runs.append(1)
        return ToolResult(content="done")

    ledger.run_effect(ToolCall(id="a", name="transfer", arguments={"to": "x", "amount": 10}), run)
    ledger.run_effect(ToolCall(id="b", name="transfer", arguments={"to": "y", "amount": 10}), run)
    assert ledger.executions == 2  # different args -> different effects

    replay = ledger.run_effect(
        ToolCall(id="c", name="transfer", arguments={"to": "x", "amount": 10}), run
    )
    assert ledger.executions == 2  # same args -> deduped
    assert replay.content == "done"  # content stable
    assert replay.data.get("ledger_replayed") is True


@pytest.mark.unit
def test_ledger_idempotency_key_dedupes_even_with_different_args() -> None:
    ledger = EffectLedger()
    runs: list[int] = []

    def run() -> ToolResult:
        runs.append(1)
        return ToolResult(content="ok")

    ledger.run_effect(ToolCall(id="a", name="t", arguments={"amount": 1, "idempotency_key": "k1"}), run)
    ledger.run_effect(ToolCall(id="b", name="t", arguments={"amount": 999, "idempotency_key": "k1"}), run)
    assert ledger.executions == 1


# --- world: path-escape defense --------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("bad", ["../x", "../../y", "sub/../../z", "/etc/passwd"])
def test_world_refuses_path_escapes(tmp_path: Path, bad: str) -> None:
    world = World(tmp_path)
    with pytest.raises(ValueError):
        world.write_file(bad, "data")
    world.close()


@pytest.mark.unit
def test_world_allows_nested_paths_within_root(tmp_path: Path) -> None:
    world = World(tmp_path)
    world.write_file("a/b/c.txt", "ok")
    assert world.read_file("a/b/c.txt") == "ok"
    world.close()


# --- gate: regression vs baseline, and order enforcement -------------------


def _report(name: str, det: float, faith: float, *, order_ok: bool = True, expected_tools: int = 1) -> TaskReport:
    return TaskReport(
        scenario=name,
        determinism=DeterminismScore(
            runs=10, passing=int(det * 10), rate=det, k=5, pass_caret_k=det, pass_at_k=det,
            ci=Interval(low=det, high=det), min_runs_hint=10,
        ),
        faithfulness=FaithfulnessScore(
            runs=10, faithful=int(faith * 10), rate=faith, outcome_rate=faith,
            evidence_overlap=1.0, ci=Interval(low=faith, high=faith),
        ),
        trajectory=TrajectoryScore(
            tool_selection_accuracy=1.0, arg_match_rate=1.0, order_ok=order_ok,
            step_efficiency=1.0, expected_tools=expected_tools, actual_tools=expected_tools,
        ),
    )


@pytest.mark.unit
def test_gate_catches_regression_below_baseline_even_above_absolute_threshold() -> None:
    # Absolute bar is loose (0.5); the scenario was 0.90, now 0.70, tolerance 0.10.
    # 0.70 clears 0.5 but is a regression below 0.90 - 0.10 = 0.80.
    thresholds = GateThresholds(min_determinism=0.5, min_faithfulness=0.5, min_trajectory=0.5, require_order=False)
    baseline = Baseline(
        thresholds=thresholds, tolerance=0.1,
        scenarios={"s": ScenarioBaseline(determinism=0.9, faithfulness=1.0, trajectory=1.0)},
    )
    gate = evaluate_gate([_report("s", det=0.7, faith=1.0)], baseline)
    assert gate.passed is False
    assert any("regressed" in f for f in gate.failures)


@pytest.mark.unit
def test_gate_require_order_fails_on_out_of_order_trajectory() -> None:
    thresholds = GateThresholds(min_determinism=0.0, min_faithfulness=0.0, min_trajectory=0.0, require_order=True)
    gate = evaluate_gate(
        [_report("s", det=1.0, faith=1.0, order_ok=False, expected_tools=2)],
        Baseline(thresholds=thresholds),
    )
    assert gate.passed is False
    assert any("order" in f for f in gate.failures)


# --- trajectory: duplicates, extras, emptiness -----------------------------


def _transcript(*names: str) -> Transcript:
    steps = tuple(
        Step(index=i, tool_call=ToolCall(id=f"c{i}", name=n)) for i, n in enumerate(names)
    )
    return Transcript(scenario="t", steps=steps, final_answer="done")


@pytest.mark.unit
def test_trajectory_duplicate_expected_tool_is_half_matched() -> None:
    score = score_trajectory(
        _transcript("transfer"),
        (ExpectedToolCall(name="transfer"), ExpectedToolCall(name="transfer")),
    )
    assert score.tool_selection_accuracy == 0.5


@pytest.mark.unit
def test_trajectory_extra_actual_tools_lower_efficiency_only() -> None:
    score = score_trajectory(_transcript("a", "b", "c"), (ExpectedToolCall(name="a"),))
    assert score.tool_selection_accuracy == 1.0
    assert score.step_efficiency == pytest.approx(1 / 3)


@pytest.mark.unit
def test_trajectory_empty_actual_against_expectation_scores_zero() -> None:
    score = score_trajectory(Transcript(scenario="t", final_answer="x"), (ExpectedToolCall(name="a"),))
    assert score.tool_selection_accuracy == 0.0
    assert score.step_efficiency == 0.0
