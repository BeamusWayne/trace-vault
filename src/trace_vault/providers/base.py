"""The provider seam — the one interface every model plugs into.

A provider turns the conversation-so-far plus the available tools into a single
:class:`Completion`. That is the entire contract. ``FakeProvider`` and
``CassetteProvider`` satisfy it offline; the optional real adapters satisfy it
against a live API. Nothing above this layer knows which is in use.
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
