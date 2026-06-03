"""Optional OpenTelemetry adapter.

Only used when the ``otel`` extra is installed. Emits GenAI-convention spans to an
``InMemorySpanExporter`` so observability is asserted in tests rather than assumed.
Kept off the default path: the core tracer in ``observability.tracer`` has no
third-party dependency, so the offline suite never needs this.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..agent.tools.base import ToolResult
from ..schemas.messages import ToolCall

if TYPE_CHECKING:  # pragma: no cover
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )


class OTelTracer:
    """Adapts the agent's ``tracer.step`` hook onto OpenTelemetry spans."""

    def __init__(self, tracer: Any, exporter: InMemorySpanExporter) -> None:
        self._tracer = tracer
        self.exporter = exporter

    def step(self, index: int, call: ToolCall, result: ToolResult) -> None:
        with self._tracer.start_as_current_span(f"gen_ai.tool.{call.name}") as span:
            span.set_attribute("gen_ai.operation.name", "execute_tool")
            span.set_attribute("gen_ai.tool.name", call.name)
            span.set_attribute("gen_ai.tool.call.id", call.id)
            span.set_attribute("trace_vault.tool.ok", result.ok)
            span.set_attribute("trace_vault.step.index", index)


def build_in_memory_otel() -> tuple[OTelTracer, InMemorySpanExporter]:
    """Construct an OTel tracer wired to an in-memory exporter."""
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return OTelTracer(provider.get_tracer("trace_vault"), exporter), exporter
