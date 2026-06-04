"""Schema for an agent run transcript, the observable trajectory used by the
trajectory grader and the determinism axis.
"""

from __future__ import annotations

import json

from pydantic import BaseModel, ConfigDict

from .messages import ToolCall


class Step(BaseModel):
    """One observable step in a run: a tool call + its observation, or the final
    answer (``is_final``)."""

    model_config = ConfigDict(frozen=True)

    index: int
    tool_call: ToolCall | None = None
    observation: str = ""
    is_final: bool = False


class Transcript(BaseModel):
    """The full trajectory of a single agent run."""

    model_config = ConfigDict(frozen=True)

    scenario: str
    steps: tuple[Step, ...] = ()
    final_answer: str = ""
    diverged: bool = False
    divergence_reason: str | None = None

    @property
    def tool_sequence(self) -> tuple[str, ...]:
        """The ordered names of tools actually invoked."""
        return tuple(s.tool_call.name for s in self.steps if s.tool_call is not None)

    @property
    def tool_calls(self) -> tuple[ToolCall, ...]:
        return tuple(s.tool_call for s in self.steps if s.tool_call is not None)

    @property
    def num_tool_steps(self) -> int:
        return len(self.tool_calls)

    def signature(self) -> tuple[tuple[str, str], ...]:
        """A canonical, comparable fingerprint of the trajectory: an ordered
        tuple of ``(tool_name, sorted-args-json)`` pairs. Two runs are
        trajectory-identical iff their signatures are equal."""
        out: list[tuple[str, str]] = []
        for call in self.tool_calls:
            args = json.dumps(call.arguments, sort_keys=True, ensure_ascii=False)
            out.append((call.name, args))
        return tuple(out)
