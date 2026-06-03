"""The gate: compare a suite run to a frozen baseline and render the verdict."""

from __future__ import annotations

from .baseline import Baseline, ScenarioBaseline, load_baseline, save_baseline
from .evaluate import evaluate_gate, run_gate, trajectory_metric
from .render import render_gate

__all__ = [
    "Baseline",
    "ScenarioBaseline",
    "evaluate_gate",
    "load_baseline",
    "render_gate",
    "run_gate",
    "save_baseline",
    "trajectory_metric",
]
