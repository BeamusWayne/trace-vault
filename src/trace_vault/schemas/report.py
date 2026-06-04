"""Schema for evaluation results, the two independent axes (Determinism and
Faithfulness), trajectory grading, and the gate's pass/fail verdict.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class Interval(BaseModel):
    """A bootstrap confidence interval."""

    model_config = ConfigDict(frozen=True)

    low: float
    high: float


class DeterminismScore(BaseModel):
    """How reproducible the trajectory is across N replays."""

    model_config = ConfigDict(frozen=True)

    runs: int
    passing: int  # runs whose trajectory matched the canonical signature
    rate: float
    k: int
    pass_caret_k: float  # P(k randomly chosen runs ALL match), pass^k
    pass_at_k: float  # P(>=1 of k matches), pass@k
    ci: Interval
    min_runs_hint: int


class FaithfulnessScore(BaseModel):
    """Whether the run actually changed the world as claimed (not the transcript)."""

    model_config = ConfigDict(frozen=True)

    runs: int
    faithful: int  # runs that satisfied every outcome check
    rate: float
    outcome_rate: float  # fraction of individual outcome checks satisfied
    evidence_overlap: float  # [0, 1], did the answer cite the tool evidence
    ci: Interval


class TrajectoryScore(BaseModel):
    """Process-level grading of the canonical run against the expected plan."""

    model_config = ConfigDict(frozen=True)

    tool_selection_accuracy: float
    arg_match_rate: float
    order_ok: bool
    step_efficiency: float  # min(1.0, expected_steps / actual_steps)
    expected_tools: int
    actual_tools: int


class TaskReport(BaseModel):
    """The full dual-axis report for one scenario."""

    model_config = ConfigDict(frozen=True)

    scenario: str
    determinism: DeterminismScore
    faithfulness: FaithfulnessScore
    trajectory: TrajectoryScore
    diverged: bool = False
    notes: tuple[str, ...] = ()


class GateThresholds(BaseModel):
    """The bar each axis must clear for the gate to pass."""

    model_config = ConfigDict(frozen=True)

    min_determinism: float = 1.0
    min_faithfulness: float = 1.0
    min_trajectory: float = 1.0
    require_order: bool = True


class GateReport(BaseModel):
    """The gate verdict over a whole scenario suite."""

    model_config = ConfigDict(frozen=True)

    passed: bool
    tasks: tuple[TaskReport, ...] = ()
    failures: tuple[str, ...] = ()
    thresholds: GateThresholds = GateThresholds()
