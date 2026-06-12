"""Agent Trust Report v0 — the cross-tool verdict format of the trust layer.

One schema, three producers: trace-vault (``vault gate --trust-report``)
reports on a replay suite, Alfred (``ledger verify --trust-report``) on a
signed run receipt, NightWatch (``attest --trust-report``) on a recorded
session. CI consumes the same ``{verdict, checks[]}`` regardless of which
tool produced it — spec: https://github.com/BeamusWayne/agent-trust-layer
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from ..schemas.report import GateReport, TaskReport
from .baseline import Baseline
from .evaluate import trajectory_metric

TrustVerdict = Literal["pass", "warn", "fail"]


class TrustCheck(BaseModel):
    """One named verification with its verdict (id is a stable dotted path)."""

    model_config = ConfigDict(frozen=True)

    id: str
    verdict: TrustVerdict
    detail: str


class Producer(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    version: str


class Subject(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: Literal["session", "run", "suite"]
    id: str


class TrustReport(BaseModel):
    """The full cross-tool report (trust_report_version 0)."""

    model_config = ConfigDict(frozen=True)

    trust_report_version: Literal["0"]
    producer: Producer
    subject: Subject
    verdict: TrustVerdict
    checks: tuple[TrustCheck, ...]
    generated_at: str


def _worst(verdicts: list[TrustVerdict]) -> TrustVerdict:
    if "fail" in verdicts:
        return "fail"
    if "warn" in verdicts:
        return "warn"
    return "pass"


def _scenario_checks(report: TaskReport, baseline: Baseline) -> list[TrustCheck]:
    """Per-axis checks for one scenario.

    Mirrors ``evaluate._scenario_failures`` — the same thresholds, the same
    baseline-regression tolerance — expressed as named checks instead of
    failure strings. A drift between the two is pinned by the test suite.
    """
    th = baseline.thresholds
    name = report.scenario
    base = baseline.scenarios.get(name)

    det = report.determinism.rate
    det_floor = max(
        th.min_determinism,
        (base.determinism - baseline.tolerance) if base is not None else 0.0,
    )
    faith = report.faithfulness.rate
    faith_floor = max(
        th.min_faithfulness,
        (base.faithfulness - baseline.tolerance) if base is not None else 0.0,
    )
    traj = trajectory_metric(report.trajectory)
    order_required = th.require_order and report.trajectory.expected_tools > 0
    order_ok = report.trajectory.order_ok or not order_required

    return [
        TrustCheck(
            id=f"determinism.{name}",
            verdict="pass" if det >= det_floor else "fail",
            detail=f"rate {det:.2f} (floor {det_floor:.2f}, pass^k {report.determinism.pass_caret_k:.2f})",
        ),
        TrustCheck(
            id=f"faithfulness.{name}",
            verdict="pass" if faith >= faith_floor else "fail",
            detail=f"rate {faith:.2f} (floor {faith_floor:.2f}, world-state checked, not transcript)",
        ),
        TrustCheck(
            id=f"trajectory.{name}",
            verdict="pass" if traj >= th.min_trajectory and order_ok else "fail",
            detail=f"metric {traj:.2f} (floor {th.min_trajectory:.2f}), order {'ok' if order_ok else 'DIVERGED'}",
        ),
    ]


def to_trust_report(
    gate: GateReport,
    baseline: Baseline,
    *,
    version: str,
    suite_id: str = "reference-suite",
    now: datetime | None = None,
) -> TrustReport:
    """Map a gate verdict onto the cross-tool Trust Report v0 shape."""
    checks: list[TrustCheck] = []
    for task in gate.tasks:
        checks.extend(_scenario_checks(task, baseline))

    moment = now if now is not None else datetime.now(UTC)
    return TrustReport(
        trust_report_version="0",
        producer=Producer(name="trace-vault", version=version),
        subject=Subject(kind="suite", id=suite_id),
        verdict=_worst([c.verdict for c in checks]),
        checks=tuple(checks),
        generated_at=moment.isoformat().replace("+00:00", "Z"),
    )
