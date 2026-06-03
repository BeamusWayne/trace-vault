"""M4 end-to-end: the gate runs the whole pipeline and renders a verdict.

These are the showcase tests — the full agent -> cassette -> eval -> gate path,
entirely offline, with the determinism != faithfulness thesis asserted directly.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from trace_vault.agent import Agent, default_registry
from trace_vault.cli import app
from trace_vault.gate import evaluate_gate, load_baseline, run_gate
from trace_vault.gate.baseline import Baseline
from trace_vault.suite import full_suite, good_suite

_REPO_ROOT = Path(__file__).resolve().parents[2]
_BASELINE = _REPO_ROOT / "examples" / "baseline.json"
_RUNS = 12


def _by_scenario(report) -> dict[str, object]:
    return {t.scenario: t for t in report.tasks}


@pytest.mark.e2e
def test_gate_passes_on_committed_baseline(tmp_path: Path) -> None:
    baseline = load_baseline(_BASELINE)
    report = run_gate(good_suite(), Agent(default_registry()), baseline, root=tmp_path, runs=_RUNS)
    assert report.passed is True
    assert report.failures == ()


@pytest.mark.e2e
def test_gate_catches_regressions_on_both_axes(tmp_path: Path) -> None:
    report = run_gate(full_suite(), Agent(default_registry()), Baseline(), root=tmp_path, runs=_RUNS)
    assert report.passed is False
    blob = "\n".join(report.failures)
    # one determinism failure, one faithfulness failure — different root causes.
    assert "report.flaky_plan: determinism" in blob
    assert "booking.unfaithful_write: faithfulness" in blob


@pytest.mark.e2e
def test_determinism_is_not_faithfulness(tmp_path: Path) -> None:
    """The thesis, asserted: a reliable run can be wrong, a flaky run can be right."""
    report = run_gate(full_suite(), Agent(default_registry()), Baseline(), root=tmp_path, runs=20)
    tasks = _by_scenario(report)

    unfaithful = tasks["booking.unfaithful_write"]
    assert unfaithful.determinism.rate == 1.0  # perfectly reproducible
    assert unfaithful.faithfulness.rate == 0.0  # ...and perfectly wrong

    flaky = tasks["report.flaky_plan"]
    assert flaky.determinism.rate < 1.0  # not reproducible
    assert flaky.faithfulness.rate == 1.0  # ...but harmless
    # pass^k punishes the flakiness far harder than the raw rate does.
    assert flaky.determinism.pass_caret_k < flaky.determinism.rate


@pytest.mark.e2e
def test_evaluate_gate_is_pure_over_reports(tmp_path: Path) -> None:
    # The gate verdict is a pure function of the reports + baseline.
    report = run_gate(good_suite(), Agent(default_registry()), Baseline(), root=tmp_path, runs=_RUNS)
    again = evaluate_gate(list(report.tasks), Baseline())
    assert again.passed is True


@pytest.mark.e2e
def test_cli_gate_exit_codes() -> None:
    runner = CliRunner()
    ok = runner.invoke(app, ["gate", "--baseline", str(_BASELINE), "--runs", "8"])
    assert ok.exit_code == 0
    assert "GATE: PASS" in ok.stdout

    red = runner.invoke(app, ["gate", "--baseline", str(_BASELINE), "--full", "--runs", "8"])
    assert red.exit_code == 1
    assert "GATE: FAIL" in red.stdout


@pytest.mark.e2e
def test_cli_demo_runs() -> None:
    result = CliRunner().invoke(app, ["demo", "--runs", "8"])
    assert result.exit_code == 0
    assert "determinism is not faithfulness" in result.stdout
    assert "FAITHFULNESS" in result.stdout
