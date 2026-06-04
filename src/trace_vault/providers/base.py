"""The provider interface.

A provider turns the conversation so far plus the available tools into one
:class:`Completion`. ``FakeProvider`` and ``CassetteProvider`` implement it
offline; the optional real adapters implement it against a live API. Nothing
above this layer knows which one is in use.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from ..schemas.messages import Completion, Message, ToolSpec


@runtime_checkable
class LLMProvider(Protocol):
    """Anything that can produce the next :class:`Completion` for a conversation."""

    name: str

    def complete(
        self, messages: Sequence[Message], tools: Sequence[ToolSpec] = ()
    ) -> Completion:
        """Return the model's next step given the conversation and tool specs."""
        ...
