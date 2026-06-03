"""Core conversation primitives exchanged with an :class:`LLMProvider`.

Every model is frozen — trace-vault treats agent state as immutable data and
always builds new objects instead of mutating existing ones.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Role = Literal["system", "user", "assistant", "tool"]


class ToolCall(BaseModel):
    """A request from the model to invoke a tool."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class Message(BaseModel):
    """One turn in the conversation sent to / received from the provider."""

    model_config = ConfigDict(frozen=True)

    role: Role
    content: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    # Populated only for role == "tool": which call this observation answers.
    tool_call_id: str | None = None
    name: str | None = None


class ToolSpec(BaseModel):
    """A tool advertised to the model (name + JSON-schema-style parameters)."""

    model_config = ConfigDict(frozen=True)

    name: str
    description: str = ""
    parameters: dict[str, Any] = Field(default_factory=dict)


class Completion(BaseModel):
    """A single provider response: free-text ``content`` and/or ``tool_calls``."""

    model_config = ConfigDict(frozen=True)

    content: str = ""
    tool_calls: tuple[ToolCall, ...] = ()

    @property
    def is_final(self) -> bool:
        """A completion with no tool calls terminates the agent loop."""
        return len(self.tool_calls) == 0
