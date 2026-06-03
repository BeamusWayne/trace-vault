"""M5 integration: the in-memory tracer captures a span per tool step."""

from __future__ import annotations

from pathlib import Path

import pytest

from trace_vault.agent import Agent, default_registry
from trace_vault.agent.world import World
from trace_vault.observability import InMemoryTracer
from trace_vault.providers import FakeProvider
from trace_vault.schemas.messages import Completion, ToolCall
from trace_vault.schemas.scenario import WorldSpec


@pytest.mark.integration
def test_in_memory_tracer_records_one_span_per_tool(tmp_path: Path) -> None:
    world = World(tmp_path, WorldSpec(sql_setup=("CREATE TABLE bookings (room TEXT, price REAL);",)))
    script = [
        Completion(tool_calls=(ToolCall(id="a", name="calculator", arguments={"expression": "1+1"}),)),
        Completion(
            tool_calls=(
                ToolCall(id="b", name="db_insert", arguments={"table": "bookings", "values": {"room": "A", "price": 2}}),
            )
        ),
        Completion(content="done"),
    ]
    tracer = InMemoryTracer()
    Agent(default_registry()).run("g", FakeProvider(script), world, tracer=tracer)

    assert tracer.tool_names() == ("calculator", "db_insert")
    assert tracer.spans[0].name == "gen_ai.tool.calculator"
    assert all(s.attributes["trace_vault.tool.ok"] for s in tracer.spans)
    world.close()
