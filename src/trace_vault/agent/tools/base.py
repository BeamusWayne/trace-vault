"""Tool framework: the :class:`Tool` contract, results, and a registry.

Tools are *behavior* over the :class:`World`, not data. Each declares whether it
is ``effectful`` (has an irreversible side effect) so the ledger can protect it.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from ...errors import ToolError
from ...schemas.messages import ToolSpec
from ..world import World


class ToolResult(BaseModel):
    """The immutable outcome of running a tool."""

    model_config = ConfigDict(frozen=True)

    ok: bool = True
    content: str = ""
    data: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def fail(cls, message: str) -> ToolResult:
        return cls(ok=False, content=message)


class Tool:
    """Base class for tools. Subclasses set the class attributes and implement
    :meth:`run`."""

    name: str = ""
    description: str = ""
    parameters: ClassVar[dict[str, Any]] = {}
    effectful: bool = False

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name, description=self.description, parameters=self.parameters
        )

    def run(self, args: dict[str, Any], world: World) -> ToolResult:  # pragma: no cover
        raise NotImplementedError

    # small shared helper for argument validation at the boundary
    def _require(self, args: dict[str, Any], *names: str) -> None:
        missing = [n for n in names if n not in args]
        if missing:
            raise ToolError(
                f"{self.name}: missing required argument(s): {', '.join(missing)}"
            )


class ToolRegistry:
    """An immutable lookup of available tools."""

    def __init__(self, tools: Sequence[Tool]) -> None:
        self._tools: dict[str, Tool] = {}
        for tool in tools:
            if not tool.name:
                raise ToolError(f"tool {tool!r} has no name")
            if tool.name in self._tools:
                raise ToolError(f"duplicate tool name: {tool.name!r}")
            self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        if name not in self._tools:
            raise ToolError(f"unknown tool: {name!r}")
        return self._tools[name]

    def has(self, name: str) -> bool:
        return name in self._tools

    def names(self) -> tuple[str, ...]:
        return tuple(self._tools)

    def specs(self) -> tuple[ToolSpec, ...]:
        return tuple(tool.spec() for tool in self._tools.values())
