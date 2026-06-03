"""M3 integration: run_case produces the two axes over N replays."""

from __future__ import annotations

from pathlib import Path

import pytest

from trace_vault.agent import Agent, default_registry
from trace_vault.agent.world import World
from trace_vault.cassette.recorder import record_run
from trace_vault.eval.runner import Case, run_case
from trace_vault.providers import CassetteProvider, FakeProvider, StochasticFakeProvider
from trace_vault.schemas.messages import Completion, ToolCall
from trace_vault.schemas.scenario import ExpectedToolCall, OutcomeCheck, Scenario, WorldSpec

_SPEC = WorldSpec(sql_setup=("CREATE TABLE bookings (room TEXT, price REAL);",))
_SCRIPT = [
    Completion(tool_calls=(ToolCall(id="a1", name="calculator", arguments={"expression": "100*0.85"}),)),
    Completion(
        tool_calls=(
            ToolCall(id="a2", name="db_insert", arguments={"table": "bookings", "values": {"room": "A", "price": 85}}),
        )
    ),
    Completion(content="Booked room A for 85."),
]


@pytest.mark.integration
def test_run_case_deterministic_cassette_scores_both_axes(tmp_path: Path) -> None:
    agent = Agent(default_registry())
    rec_world = World(tmp_path / "rec", _SPEC)
    recorded, cassette = record_run(agent, "book A", FakeProvider(_SCRIPT), rec_world, name="booking")
    rec_world.close()

    scenario = Scenario(
        name="booking",
        goal="book A",
        world=_SPEC,
        expected_tools=(
            ExpectedToolCall(name="calculator", args={"expression": "100*0.85"}),
            ExpectedToolCall(name="db_insert"),
        ),
        outcome_checks=(
            OutcomeCheck(kind="db_row_exists", params={"table": "bookings", "where": {"room": "A"}}),
        ),
        evidence=("85",),
    )
    case = Case(
        scenario=scenario,
        make_provider=lambda i: CassetteProvider(cassette),
        canonical=recorded.signature(),
    )
    report = run_case(case, agent, root=tmp_path / "runs", runs=10, k=5)

    assert report.determinism.rate == 1.0
    assert report.determinism.pass_caret_k == 1.0
    assert report.faithfulness.rate == 1.0
    assert report.faithfulness.evidence_overlap == 1.0
    assert report.trajectory.tool_selection_accuracy == 1.0
    assert report.diverged is False


@pytest.mark.integration
def test_flaky_provider_lowers_determinism(tmp_path: Path) -> None:
    agent = Agent(default_registry())
    # Step 0 randomly picks between two different (but valid) calculations;
    # step 1 finishes. Two trajectories -> determinism < 1.
    variants = [
        [
            Completion(tool_calls=(ToolCall(id="a", name="calculator", arguments={"expression": "100*0.85"}),)),
            Completion(tool_calls=(ToolCall(id="a", name="calculator", arguments={"expression": "120*0.85"}),)),
        ],
        [Completion(content="done")],
    ]
    scenario = Scenario(name="flaky", goal="compute", world=WorldSpec())
    case = Case(
        scenario=scenario,
        make_provider=lambda i: StochasticFakeProvider(variants, seed=i),
    )
    report = run_case(case, agent, root=tmp_path / "runs", runs=20, k=5)

    assert 0.0 < report.determinism.rate < 1.0
    # pass^k should expose the flakiness far more sharply than the raw rate.
    assert report.determinism.pass_caret_k < report.determinism.rate
