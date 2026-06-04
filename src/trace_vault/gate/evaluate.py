"""The gate verdict: run a suite, compare to the baseline, pass or fail.

The two axes are checked *independently*, a scenario can fail on determinism,
on faithfulness, or on trajectory, and the failure message says which. That
separation is the whole thesis made operational.
"""

from __future__ import annotations

from pathlib import Path

from ..agent.loop import Agent
from ..eval.runner import Case, run_case
from ..schemas.report import GateReport, TaskReport, TrajectoryScore
from .baseline import Baseline


def trajectory_metric(trajectory: TrajectoryScore) -> float:
    """Single scalar for gating: the weakest of selection / argument match."""
    return min(trajectory.tool_selection_accuracy, trajectory.arg_match_rate)


def _scenario_failures(report: TaskReport, baseline: Baseline) -> list[str]:
    th = baseline.thresholds
    name = report.scenario
    out: list[str] = []

    det = report.determinism.rate
    faith = report.faithfulness.rate
    traj = trajectory_metric(report.trajectory)

    if det < th.min_determinism:
        out.append(f"{name}: determinism {det:.2f} < {th.min_determinism:.2f}")
    if faith < th.min_faithfulness:
        out.append(f"{name}: faithfulness {faith:.2f} < {th.min_faithfulness:.2f}")
    if traj < th.min_trajectory:
        out.append(f"{name}: trajectory {traj:.2f} < {th.min_trajectory:.2f}")
    if th.require_order and report.trajectory.expected_tools > 0 and not report.trajectory.order_ok:
        out.append(f"{name}: tool order diverged from the expected plan")

    base = baseline.scenarios.get(name)
    if base is not None:
        if det < base.determinism - baseline.tolerance:
            out.append(f"{name}: determinism regressed {base.determinism:.2f} -> {det:.2f}")
        if faith < base.faithfulness - baseline.tolerance:
            out.append(f"{name}: faithfulness regressed {base.faithfulness:.2f} -> {faith:.2f}")
    return out


def evaluate_gate(reports: list[TaskReport], baseline: Baseline) -> GateReport:
    failures: list[str] = []
    for report in reports:
        failures.extend(_scenario_failures(report, baseline))
    return GateReport(
        passed=len(failures) == 0,
        tasks=tuple(reports),
        failures=tuple(failures),
        thresholds=baseline.thresholds,
    )


def run_gate(
    cases: list[Case],
    agent: Agent,
    baseline: Baseline,
    *,
    root: str | Path,
    runs: int = 20,
    k: int = 5,
    seed: int = 0,
) -> GateReport:
    reports = [
        run_case(case, agent, root=Path(root) / case.scenario.name, runs=runs, k=k, seed=seed)
        for case in cases
    ]
    return evaluate_gate(reports, baseline)
