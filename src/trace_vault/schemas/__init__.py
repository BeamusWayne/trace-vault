"""Immutable Pydantic schemas shared across every trace-vault layer."""

from __future__ import annotations

from .cassette import Cassette, Interaction, MatchMode
from .messages import Completion, Message, Role, ToolCall, ToolSpec
from .report import (
    DeterminismScore,
    FaithfulnessScore,
    GateReport,
    GateThresholds,
    Interval,
    TaskReport,
    TrajectoryScore,
)
from .scenario import CheckKind, ExpectedToolCall, OutcomeCheck, Scenario, WorldSpec
from .transcript import Step, Transcript

__all__ = [
    "Cassette",
    "CheckKind",
    "Completion",
    "DeterminismScore",
    "ExpectedToolCall",
    "FaithfulnessScore",
    "GateReport",
    "GateThresholds",
    "Interaction",
    "Interval",
    "MatchMode",
    "Message",
    "OutcomeCheck",
    "Role",
    "Scenario",
    "Step",
    "TaskReport",
    "ToolCall",
    "ToolSpec",
    "Transcript",
    "TrajectoryScore",
    "WorldSpec",
]
