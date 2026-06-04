"""Schema for recorded cassettes, the normalized record of an agent's
LLM exchanges that lets the whole suite replay offline.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .messages import Completion

MatchMode = str  # one of: "strict" | "unordered" | "subset"


class Interaction(BaseModel):
    """A recorded ``request -> completion`` pair.

    ``request_key`` is the canonical hash of the normalized request (messages +
    tools) at record time; ``request_digest`` keeps the normalized snapshot so a
    divergence can be explained field-by-field rather than as an opaque hash miss.
    """

    model_config = ConfigDict(frozen=True)

    index: int
    request_key: str
    request_digest: dict[str, Any] = Field(default_factory=dict)
    completion: Completion


class Cassette(BaseModel):
    """An ordered, normalized recording of one agent run's provider calls."""

    model_config = ConfigDict(frozen=True)

    name: str
    schema_version: int = 1
    match_mode: MatchMode = "strict"
    interactions: tuple[Interaction, ...] = ()
    meta: dict[str, Any] = Field(default_factory=dict)

    def with_interactions(self, interactions: tuple[Interaction, ...]) -> Cassette:
        """Return a new cassette with replaced interactions (immutable update)."""
        return self.model_copy(update={"interactions": interactions})
