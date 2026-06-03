"""A dependency-free, in-memory tracer.

Records one span per tool step using GenAI-style attribute names, so the agent's
behavior is inspectable and *asserted* in tests without requiring an OpenTelemetry
install. (An optional real OTel adapter lives in ``observability.otel``.)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..agent.tools.base import ToolResult
from ..schemas.messages import ToolCall


@dataclass(frozen=True)
class Span:
    name: str
    index: int
    attributes: dict[str, Any]


class InMemoryTracer:
    """Captures a span per tool invocation."""

    def __init__(self) -> None:
        self._spans: list[Span] = []

    def step(self, index: int, call: ToolCall, result: ToolResult) -> None:
        self._spans = [
            *self._spans,
            Span(
                name=f"gen_ai.tool.{call.name}",
                index=index,
                attributes={
                    "gen_ai.tool.name": call.name,
                    "gen_ai.tool.call.id": call.id,
                    "trace_vault.tool.ok": result.ok,
                    "trace_vault.tool.output_chars": len(result.content),
                },
            ),
        ]

    @property
    def spans(self) -> tuple[Span, ...]:
        return tuple(self._spans)

    def tool_names(self) -> tuple[str, ...]:
        return tuple(str(s.attributes["gen_ai.tool.name"]) for s in self._spans)
