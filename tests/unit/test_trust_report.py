"""Trust Report v0 emitter: the gate verdict in the cross-tool shape.

Pins two invariants: (1) the report's verdict agrees with the gate (no drift
between ``evaluate._scenario_failures`` and ``trust_report._scenario_checks``),
and (2) the envelope matches the spec (BeamusWayne/agent-trust-layer).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from trace_vault.agent import Agent, default_registry
from trace_vault.gate import load_baseline, run_gate
from trace_vault.gate.baseline import Baseline
from trace_vault.gate.trust_report import to_trust_report
from trace_vault.suite import full_suite, good_suite

_REPO_ROOT = Path(__file__).resolve().parents[2]
_BASELINE = _REPO_ROOT / "examples" / "baseline.json"
_RUNS = 8
_NOW = datetime(2026, 6, 13, tzinfo=UTC)


@pytest.mark.unit
def test_passing_gate_maps_to_all_pass_report(tmp_path: Path) -> None:
    baseline = load_baseline(_BASELINE)
    gate = run_gate(good_suite(), Agent(default_registry()), baseline, root=tmp_path, runs=_RUNS)

    report = to_trust_report(gate, baseline, version="0.2.0", now=_NOW)

    assert gate.passed is True
    assert report.trust_report_version == "0"
    assert report.producer.name == "trace-vault"
    assert report.subject.kind == "suite"
    assert report.verdict == "pass"
    assert all(c.verdict == "pass" for c in report.checks)
    # three axes per scenario, every scenario covered
    assert len(report.checks) == 3 * len(gate.tasks)
    assert report.generated_at == "2026-06-13T00:00:00Z"


@pytest.mark.unit
def test_failing_gate_maps_to_failing_checks_on_the_same_axes(tmp_path: Path) -> None:
    baseline = Baseline()
    gate = run_gate(full_suite(), Agent(default_registry()), baseline, root=tmp_path, runs=_RUNS)

    report = to_trust_report(gate, baseline, version="0.2.0", now=_NOW)

    assert gate.passed is False
    assert report.verdict == "fail"
    by_id = {c.id: c for c in report.checks}
    # the two seeded regressions land on their own axes — and only there
    assert by_id["determinism.report.flaky_plan"].verdict == "fail"
    assert by_id["faithfulness.booking.unfaithful_write"].verdict == "fail"
    assert by_id["faithfulness.report.flaky_plan"].verdict == "pass"
    assert by_id["determinism.booking.unfaithful_write"].verdict == "pass"


@pytest.mark.unit
def test_report_verdict_always_agrees_with_the_gate(tmp_path: Path) -> None:
    """The no-drift pin: trust report fail <=> gate fail."""
    baseline = load_baseline(_BASELINE)
    for suite, root in ((good_suite(), "good"), (full_suite(), "full")):
        gate = run_gate(
            suite, Agent(default_registry()), baseline, root=tmp_path / root, runs=_RUNS
        )
        report = to_trust_report(gate, baseline, version="0.2.0", now=_NOW)
        assert (report.verdict == "pass") == gate.passed
