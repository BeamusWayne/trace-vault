"""M1 integration: the thin agent loop drives real tools against a real World."""

from __future__ import annotations

from pathlib import Path

import pytest

from trace_vault.agent import Agent, default_registry
from trace_vault.agent.world import World
from trace_vault.errors import MaxStepsExceeded
from trace_vault.providers import FakeProvider
from trace_vault.schemas.messages import Completion, ToolCall
from trace_vault.schemas.scenario import WorldSpec


def _booking_world(root: Path) -> World:
    spec = WorldSpec(
        sql_setup=("CREATE TABLE bookings (room TEXT, price REAL);",),
    )
    return World(root, spec)


@pytest.mark.integration
def test_agent_runs_tools_and_mutates_world(tmp_path: Path) -> None:
    world = _booking_world(tmp_path)
    script = [
        Completion(
            tool_calls=(
                ToolCall(id="a1", name="calculator", arguments={"expression": "100*0.85"}),
            )
        ),
        Completion(
            tool_calls=(
                ToolCall(
                    id="a2",
                    name="db_insert",
                    arguments={"table": "bookings", "values": {"room": "A", "price": 85}},
                ),
            )
        ),
        Completion(content="Booked room A for 85."),
    ]
    agent = Agent(default_registry())

    transcript = agent.run(
        "Book room A at 15% off 100", FakeProvider(script), world, name="booking"
    )

    assert transcript.tool_sequence == ("calculator", "db_insert")
    assert "Booked" in transcript.final_answer
    # Faithfulness ground truth: the row actually exists in the world.
    assert world.row_count("bookings", "room = ?", ["A"]) == 1
    world.close()


@pytest.mark.integration
def test_agent_raises_when_script_exhausts_without_final(tmp_path: Path) -> None:
    world = _booking_world(tmp_path)
    # Only tool calls, never a final answer -> the loop should hit its budget.
    script = [
        Completion(
            tool_calls=(ToolCall(id=f"c{i}", name="calculator", arguments={"expression": "1+1"}),)
        )
        for i in range(3)
    ]
    agent = Agent(default_registry(), max_steps=3)
    with pytest.raises(MaxStepsExceeded):
        agent.run("loop forever", FakeProvider(script), world, name="loop")
    world.close()
