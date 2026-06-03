"""The agent loop — a deliberately thin ReAct-style controller.

``plan -> act -> observe -> answer``. It asks the provider for the next step,
runs any requested tools against the World, threads the observations back, and
stops on a tool-free completion. It is intentionally minimal (~1 screen): the
*harness* around it is the contribution, and a thin loop is easy to swap.

Two optional seams keep the loop honest without bloating it:

* ``ledger`` — guards ``effectful`` tools so they fire exactly once (replay-safe).
* ``tracer`` — receives a structured event per step (e.g. OTel spans).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from ..errors import MaxStepsExceeded
from ..schemas.messages import Completion, Message, ToolCall
from ..schemas.transcript import Step, Transcript
from .tools.base import ToolRegistry, ToolResult
from .world import World

SYSTEM_PROMPT = (
    "You are a careful, tool-using agent. Use the provided tools to accomplish "
    "the user's goal, then give a short final answer. Only claim an action is "
    "complete after a tool result confirms it."
)


class LedgerProtocol(Protocol):
    """Structural type for the optional irreversible-effect ledger."""

    def run_effect(
        self, call: ToolCall, run: Callable[[], ToolResult]
    ) -> ToolResult: ...


class TracerProtocol(Protocol):
    """Structural type for the optional step tracer."""

    def step(self, index: int, call: ToolCall, result: ToolResult) -> None: ...


class Agent:
    """Runs a goal to completion against a provider and a World."""

    def __init__(self, registry: ToolRegistry, max_steps: int = 12) -> None:
        self.registry = registry
        self.max_steps = max_steps

    def run(
        self,
        goal: str,
        provider: object,
        world: World,
        *,
        name: str = "run",
        ledger: LedgerProtocol | None = None,
        tracer: TracerProtocol | None = None,
        max_steps: int | None = None,
    ) -> Transcript:
        limit = max_steps or self.max_steps
        specs = self.registry.specs()
        messages: tuple[Message, ...] = (
            Message(role="system", content=SYSTEM_PROMPT),
            Message(role="user", content=goal),
        )
        steps: list[Step] = []

        for _ in range(limit):
            completion: Completion = provider.complete(messages, specs)  # type: ignore[attr-defined]
            if completion.is_final:
                return Transcript(
                    scenario=name,
                    steps=tuple(steps),
                    final_answer=completion.content,
                )
            messages = (
                *messages,
                Message(
                    role="assistant",
                    content=completion.content,
                    tool_calls=completion.tool_calls,
                ),
            )
            for call in completion.tool_calls:
                result = self._invoke(call, world, ledger)
                if tracer is not None:
                    tracer.step(len(steps), call, result)
                steps.append(
                    Step(index=len(steps), tool_call=call, observation=result.content)
                )
                messages = (
                    *messages,
                    Message(
                        role="tool",
                        content=result.content,
                        tool_call_id=call.id,
                        name=call.name,
                    ),
                )

        raise MaxStepsExceeded(
            f"agent '{name}' exceeded its step budget of {limit} without finishing"
        )

    def _invoke(
        self, call: ToolCall, world: World, ledger: LedgerProtocol | None
    ) -> ToolResult:
        tool = self.registry.get(call.name)

        def _run() -> ToolResult:
            return tool.run(dict(call.arguments), world)

        if tool.effectful and ledger is not None:
            return ledger.run_effect(call, _run)
        return _run()
