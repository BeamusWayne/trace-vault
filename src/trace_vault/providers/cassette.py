"""Record and replay providers.

* :class:`RecordingProvider` wraps any inner provider and captures each
  ``request -> completion`` (normalized) into a cassette.
* :class:`CassetteProvider` replays a cassette with zero network access, raising
  a classified :class:`DivergenceError` the instant the agent strays from the
  recording.

The replay provider has no network code at all, "offline" is a structural
property here, not a runtime flag.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..cassette.matcher import CassetteCursor
from ..cassette.normalize import normalize_request, request_key
from ..schemas.cassette import Cassette, Interaction, MatchMode
from ..schemas.messages import Completion, Message, ToolSpec
from .base import LLMProvider


class RecordingProvider:
    """Wraps an inner provider and records the normalized exchange."""

    name = "cassette-record"

    def __init__(
        self,
        inner: LLMProvider,
        *,
        name: str = "recording",
        match_mode: MatchMode = "strict",
    ) -> None:
        self.inner = inner
        self._name = name
        self._mode = match_mode
        self._interactions: list[Interaction] = []

    def complete(
        self, messages: Sequence[Message], tools: Sequence[ToolSpec] = ()
    ) -> Completion:
        completion = self.inner.complete(messages, tools)
        self._interactions.append(
            Interaction(
                index=len(self._interactions),
                request_key=request_key(messages, tools),
                request_digest=normalize_request(messages, tools),
                completion=completion,
            )
        )
        return completion

    def cassette(self) -> Cassette:
        return Cassette(
            name=self._name,
            match_mode=self._mode,
            interactions=tuple(self._interactions),
        )


class CassetteProvider:
    """Serves recorded completions; raises on divergence; never goes online."""

    name = "cassette-replay"

    def __init__(self, cassette: Cassette) -> None:
        self.cassette = cassette
        self._cursor = CassetteCursor(cassette)

    def complete(
        self, messages: Sequence[Message], tools: Sequence[ToolSpec] = ()
    ) -> Completion:
        return self._cursor.next_completion(messages, tools)

    def reset(self) -> None:
        """Rewind to the start of the cassette for another replay."""
        self._cursor = CassetteCursor(self.cassette)
