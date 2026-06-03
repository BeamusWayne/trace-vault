"""Render a :class:`GateReport` as a compact, scannable text table.

The two axes sit side by side on purpose — the whole point is to *see* a run that
is perfectly deterministic and yet unfaithful (or vice-versa) at a glance.
"""

from __future__ import annotations

from ..schemas.report import GateReport
from .evaluate import trajectory_metric


def _failures_by_scenario(report: GateReport) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for failure in report.failures:
        name = failure.split(":", 1)[0]
        grouped.setdefault(name, []).append(failure)
    return grouped


def _cell(value: float, flagged: bool) -> str:
    return f"{value:.2f}{'*' if flagged else ' '}"


def render_gate(report: GateReport) -> str:
    n = len(report.tasks)
    grouped = _failures_by_scenario(report)

    header = (
        f"{'scenario':<26} {'determ.':>9}  {'faithful.':>9}  {'traj.':>7}  verdict"
    )
    lines = [
        f"trace-vault gate · {n} scenario{'s' if n != 1 else ''}",
        "",
        header,
        "-" * len(header),
    ]

    for task in report.tasks:
        failures = grouped.get(task.scenario, [])
        det_bad = any("determinism" in f for f in failures)
        faith_bad = any("faithfulness" in f for f in failures)
        traj_bad = any(("trajectory" in f or "order" in f) for f in failures)
        verdict = "FAIL" if failures else "PASS"
        lines.append(
            f"{task.scenario:<26} "
            f"{_cell(task.determinism.rate, det_bad):>9}  "
            f"{_cell(task.faithfulness.rate, faith_bad):>9}  "
            f"{_cell(trajectory_metric(task.trajectory), traj_bad):>7}  "
            f"{verdict}"
        )

    lines.append("")
    if report.passed:
        lines.append(f"GATE: PASS  ({n}/{n} scenarios within thresholds)   exit 0")
    else:
        failed = len(grouped)
        lines.append(f"GATE: FAIL  ({failed}/{n} scenario(s) below threshold)   exit 1")
        lines.append("")
        lines += [f"  x {failure}" for failure in report.failures]
    lines.append("")
    lines.append("  (* = the axis that breached its threshold)")
    return "\n".join(lines)
