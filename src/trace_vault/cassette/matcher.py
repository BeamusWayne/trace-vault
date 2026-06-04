"""Replay matching and divergence classification.

A :class:`CassetteCursor` consumes a cassette during replay under one of three
match modes:

* **strict**, interactions must replay in the recorded order; any difference is
  an immediate, classified :class:`DivergenceError`.
* **unordered**, the same set of requests may arrive in any order.
* **subset**, match only the latest turn, tolerating differences in earlier
  history (useful when only the most recent observation should drive the step).

When a request doesn't match, we don't just say "miss", we classify *why*
(``tool-name`` / ``call-order`` / ``arg-mismatch`` / ``prompt-hash``), because a
useful reliability gate tells you what changed.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from ..errors import CassetteError, DivergenceError, DivergenceKind
from ..schemas.cassette import Cassette, Interaction
from ..schemas.messages import Completion, Message, ToolSpec
from .normalize import normalize_request, request_key, tail_key, tail_key_of_digest


def _extract_calls(digest: dict[str, Any]) -> list[tuple[str, str]]:
    """Pull the ``(tool_name, canonical_args)`` sequence out of a request digest."""
    calls: list[tuple[str, str]] = []
    for message in digest.get("messages", []):
        for call in message.get("tool_calls", []):
            args = json.dumps(call.get("arguments", {}), sort_keys=True, ensure_ascii=False)
            calls.append((call["name"], args))
    return calls


def classify_divergence(
    current: dict[str, Any], recorded: dict[str, Any]
) -> tuple[DivergenceKind, str]:
    """Explain how a replayed request differs from what was recorded."""
    cur = _extract_calls(current)
    rec = _extract_calls(recorded)
    cur_names = [c[0] for c in cur]
    rec_names = [r[0] for r in rec]
    if sorted(cur_names) != sorted(rec_names):
        return "tool-name", f"tool set diverged: recorded {rec_names}, replay made {cur_names}"
    if cur_names != rec_names:
        return "call-order", f"tool order diverged: recorded {rec_names}, replay made {cur_names}"
    if cur != rec:
        return "arg-mismatch", "same tools in the same order but different arguments"
    return "prompt-hash", "request text changed outside of tool calls"


class CassetteCursor:
    """Stateful position in a cassette during one replay."""

    def __init__(self, cassette: Cassette) -> None:
        self.cassette = cassette
        self.mode = cassette.match_mode
        self._pos = 0
        self._consumed: set[int] = set()

    def next_completion(
        self, messages: Sequence[Message], tools: Sequence[ToolSpec] = ()
    ) -> Completion:
        if self.mode == "strict":
            return self._strict(messages, tools)
        if self.mode == "unordered":
            return self._by_key(messages, tools, tail=False)
        if self.mode == "subset":
            return self._by_key(messages, tools, tail=True)
        raise CassetteError(f"unknown match mode: {self.mode!r}")

    # -- modes ---------------------------------------------------------------

    def _strict(
        self, messages: Sequence[Message], tools: Sequence[ToolSpec]
    ) -> Completion:
        interactions = self.cassette.interactions
        if self._pos >= len(interactions):
            raise DivergenceError(
                "exhausted",
                f"replay requested step {self._pos} but only "
                f"{len(interactions)} interaction(s) were recorded",
                step=self._pos,
            )
        interaction = interactions[self._pos]
        if request_key(messages, tools) != interaction.request_key:
            self._raise_divergence(messages, tools, interaction, step=self._pos)
        self._pos += 1
        return interaction.completion

    def _by_key(
        self, messages: Sequence[Message], tools: Sequence[ToolSpec], *, tail: bool
    ) -> Completion:
        want = tail_key(messages, tools) if tail else request_key(messages, tools)
        for index, interaction in enumerate(self.cassette.interactions):
            if index in self._consumed:
                continue
            have = (
                tail_key_of_digest(interaction.request_digest)
                if tail
                else interaction.request_key
            )
            if have == want:
                self._consumed.add(index)
                return interaction.completion
        reference = self._first_unconsumed()
        if reference is None:
            raise DivergenceError(
                "exhausted", "no unconsumed interactions remain to match", step=-1
            )
        self._raise_divergence(messages, tools, reference, step=len(self._consumed))

    # -- helpers -------------------------------------------------------------

    def _first_unconsumed(self) -> Interaction | None:
        for index, interaction in enumerate(self.cassette.interactions):
            if index not in self._consumed:
                return interaction
        return None

    def _raise_divergence(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec],
        interaction: Interaction,
        *,
        step: int,
    ) -> None:
        current = normalize_request(messages, tools)
        kind, detail = classify_divergence(current, interaction.request_digest)
        raise DivergenceError(
            kind, detail, step=step, expected=interaction.request_digest, actual=current
        )
