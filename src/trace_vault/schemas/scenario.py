"""Schema for a reference scenario (a.k.a. task): the declarative, serializable
description of the world, the goal, and how to grade a run.

Scenarios are pure data so they can live in YAML and be unit-tested without
executing an agent.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

CheckKind = Literal[
    "db_row_exists",
    "db_row_absent",
    "db_value_equals",
    "file_exists",
    "file_contains",
    "scalar_equals",
]


class WorldSpec(BaseModel):
    """Initial state of the assertable world: SQLite DDL/seed + seed files."""

    model_config = ConfigDict(frozen=True)

    sql_setup: tuple[str, ...] = ()
    files: dict[str, str] = Field(default_factory=dict)


class OutcomeCheck(BaseModel):
    """A declarative faithfulness assertion against the *real* world state."""

    model_config = ConfigDict(frozen=True)

    kind: CheckKind
    params: dict[str, Any] = Field(default_factory=dict)
    describe: str = ""


class ExpectedToolCall(BaseModel):
    """An expected step for trajectory grading."""

    model_config = ConfigDict(frozen=True)

    name: str
    args: dict[str, Any] = Field(default_factory=dict)


class Scenario(BaseModel):
    """A complete reference task: goal + initial world + graders + cassette."""

    model_config = ConfigDict(frozen=True)

    name: str
    goal: str
    world: WorldSpec = WorldSpec()
    expected_tools: tuple[ExpectedToolCall, ...] = ()
    outcome_checks: tuple[OutcomeCheck, ...] = ()
    evidence: tuple[str, ...] = ()
    cassette: str = ""
    max_steps: int = 12
