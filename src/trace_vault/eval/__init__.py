"""The evaluation layer: two independent axes + trajectory grading."""

from __future__ import annotations

from .determinism import modal_signature, score_determinism
from .faithfulness import (
    RunGrade,
    aggregate_faithfulness,
    evidence_overlap,
    grade_check,
    grade_run,
)
from .runner import Case, run_case
from .stats import (
    bootstrap_ci,
    min_runs_for_halfwidth,
    pass_at_k,
    pass_caret_k,
)
from .trajectory import is_subsequence, score_trajectory

__all__ = [
    "Case",
    "RunGrade",
    "aggregate_faithfulness",
    "bootstrap_ci",
    "evidence_overlap",
    "grade_check",
    "grade_run",
    "is_subsequence",
    "min_runs_for_halfwidth",
    "modal_signature",
    "pass_at_k",
    "pass_caret_k",
    "run_case",
    "score_determinism",
    "score_trajectory",
]
