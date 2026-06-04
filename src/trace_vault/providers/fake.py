"""Deterministic, offline providers, the CI default test doubles.

* :class:`FakeProvider` replays a fixed script of completions in order.
* :class:`KeyedFakeProvider` answers by normalized request key (same input ->
  same output, regardless of call order).
* :class:`StochasticFakeProvider` models temperature>0 sampling *deterministically*
  given a seed, so we can manufacture, and then exactly measure, non-determinism.

None of them touch the network. All of them are reproducible.
"""

from __future__ import annotations

import random
from collections.abc import Sequence

from ..cassette.normalize import request_key
from ..schemas.messages import Completion, Message, ToolSpec


class FakeProvider:
    """Returns a fixed list of completions in order. Reset to replay again."""

    name = "fake"

    def __init__(self, script: Sequence[Completion]) -> None:
        self._script: tuple[Completion, ...] = tuple(script)
        self._cursor = 0

    def complete(
        self, messages: Sequence[Message], tools: Sequence[ToolSpec] = ()
    ) -> Completion:
        if self._cursor >= len(self._script):
            raise IndexError(
                f"FakeProvider script exhausted after {len(self._script)} step(s); "
                "the agent asked for another completion."
            )
        completion = self._script[self._cursor]
        self._cursor += 1
        return completion

    def reset(self) -> None:
        self._cursor = 0


class KeyedFakeProvider:
    """Answers by normalized request key, order-independent and idempotent."""

    name = "fake-keyed"

    def __init__(
        self,
        rules: dict[str, Completion],
        default: Completion | None = None,
    ) -> None:
        self._rules = dict(rules)
        self._default = default

    def complete(
        self, messages: Sequence[Message], tools: Sequence[ToolSpec] = ()
    ) -> Completion:
        key = request_key(messages, tools)
        if key in self._rules:
            return self._rules[key]
        if self._default is not None:
            return self._default
        raise KeyError(f"No scripted completion for request key {key!r}")


class StochasticFakeProvider:
    """Models sampling noise deterministically.

    ``variants`` is a per-step list of completion options. Given a seed, the
    provider makes the *same* choices every time, so a fleet of seeds 0..N-1
    produces a reproducible distribution of trajectories that the determinism
    axis can measure exactly.
    """

    name = "fake-stochastic"

    def __init__(
        self,
        variants: Sequence[Sequence[Completion]],
        seed: int,
        weights: Sequence[Sequence[float]] | None = None,
    ) -> None:
        self._variants = [tuple(step) for step in variants]
        self._weights = [list(w) for w in weights] if weights is not None else None
        self._rng = random.Random(seed)
        self._cursor = 0

    def complete(
        self, messages: Sequence[Message], tools: Sequence[ToolSpec] = ()
    ) -> Completion:
        if self._cursor >= len(self._variants):
            raise IndexError("StochasticFakeProvider variants exhausted")
        options = self._variants[self._cursor]
        weights = self._weights[self._cursor] if self._weights is not None else None
        self._cursor += 1
        if len(options) == 1:
            return options[0]
        return self._rng.choices(options, weights=weights, k=1)[0]
