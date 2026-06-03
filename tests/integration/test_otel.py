"""M5 integration: optional OpenTelemetry adapter emits GenAI-convention spans.

Skipped automatically when the ``otel`` extra is not installed, so it never
threatens the offline-green invariant.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from trace_vault.agent import Agent, default_registry
from trace_vault.agent.world import World
from trace_vault.observability.otel import build_in_memory_otel
from trace_vault.providers import FakeProvider
from trace_vault.schemas.messages import Completion, ToolCall
from trace_vault.schemas.scenario import WorldSpec

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("opentelemetry") is None,
    reason="OpenTelemetry not installed (optional 'otel' extra)",
)


@pytest.mark.integration
def test_otel_emits_genai_spans(tmp_path: Path) -> None:
    tracer, exporter = build_in_memory_otel()
    world = World(tmp_path, WorldSpec())
    script = [
        Completion(tool_calls=(ToolCall(id="a", name="calculator", arguments={"expression": "2*3"}),)),
        Completion(content="6"),
    ]
    Agent(default_registry()).run("calc", FakeProvider(script), world, tracer=tracer)

    spans = exporter.get_finished_spans()
    assert [s.name for s in spans] == ["gen_ai.tool.calculator"]
    assert spans[0].attributes["gen_ai.tool.name"] == "calculator"
    world.close()
