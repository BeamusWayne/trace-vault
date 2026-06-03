"""M3 unit: faithfulness graders assert real world state."""

from __future__ import annotations

from pathlib import Path

import pytest

from trace_vault.agent.world import World
from trace_vault.eval.faithfulness import (
    aggregate_faithfulness,
    evidence_overlap,
    grade_check,
    grade_run,
)
from trace_vault.schemas.scenario import OutcomeCheck, Scenario, WorldSpec
from trace_vault.schemas.transcript import Transcript


@pytest.fixture
def world(tmp_path: Path) -> World:
    spec = WorldSpec(
        sql_setup=(
            "CREATE TABLE bookings (room TEXT, price REAL);",
            "INSERT INTO bookings VALUES ('A', 85);",
        )
    )
    return World(tmp_path, spec)


@pytest.mark.unit
def test_db_row_exists_and_absent(world: World) -> None:
    exists = OutcomeCheck(kind="db_row_exists", params={"table": "bookings", "where": {"room": "A"}})
    absent = OutcomeCheck(kind="db_row_absent", params={"table": "bookings", "where": {"room": "Z"}})
    assert grade_check(world, exists)[0] is True
    assert grade_check(world, absent)[0] is True


@pytest.mark.unit
def test_db_value_equals(world: World) -> None:
    check = OutcomeCheck(
        kind="db_value_equals",
        params={"table": "bookings", "column": "price", "where": {"room": "A"}, "expected": 85.0},
    )
    assert grade_check(world, check)[0] is True


@pytest.mark.unit
def test_file_contains(tmp_path: Path) -> None:
    spec = WorldSpec(files={"out/report.txt": "total: 85 booked"})
    w = World(tmp_path, spec)
    ok = OutcomeCheck(kind="file_contains", params={"path": "out/report.txt", "substring": "85 booked"})
    miss = OutcomeCheck(kind="file_contains", params={"path": "out/report.txt", "substring": "refunded"})
    assert grade_check(w, ok)[0] is True
    assert grade_check(w, miss)[0] is False
    w.close()


@pytest.mark.unit
def test_evidence_overlap() -> None:
    assert evidence_overlap("the price is 85 dollars", ("85",)) == 1.0
    assert evidence_overlap("nothing here", ("85", "room A")) == 0.0
    assert evidence_overlap("room A only", ("85", "room A")) == pytest.approx(0.5)
    assert evidence_overlap("anything", ()) == 1.0


@pytest.mark.unit
def test_grade_run_faithful_vs_unfaithful(world: World) -> None:
    scenario = Scenario(
        name="booking",
        goal="book A",
        outcome_checks=(
            OutcomeCheck(kind="db_row_exists", params={"table": "bookings", "where": {"room": "A"}}),
        ),
        evidence=("85",),
    )
    # Faithful: world has the row and the answer cites the evidence.
    faithful = grade_run(world, Transcript(scenario="booking", final_answer="booked A for 85"), scenario)
    assert faithful.faithful is True
    assert faithful.evidence_overlap == 1.0

    # A scenario asserting a row that does NOT exist -> unfaithful despite a
    # confident answer.
    ghost = Scenario(
        name="ghost",
        goal="book Z",
        outcome_checks=(
            OutcomeCheck(kind="db_row_exists", params={"table": "bookings", "where": {"room": "Z"}}),
        ),
    )
    unfaithful = grade_run(world, Transcript(scenario="ghost", final_answer="booked Z!"), ghost)
    assert unfaithful.faithful is False


@pytest.mark.unit
def test_diverged_run_is_never_faithful(world: World) -> None:
    scenario = Scenario(name="x", goal="g")  # no checks -> vacuously faithful...
    grade = grade_run(world, Transcript(scenario="x", diverged=True), scenario)
    assert grade.faithful is False  # ...except a diverged run never passes


@pytest.mark.unit
def test_aggregate_faithfulness_rate() -> None:
    from trace_vault.eval.faithfulness import RunGrade

    grades = [RunGrade(True, 1.0, 1.0)] * 15 + [RunGrade(False, 0.0, 0.0)] * 5
    score = aggregate_faithfulness(grades)
    assert score.faithful == 15
    assert score.rate == pytest.approx(0.75)
