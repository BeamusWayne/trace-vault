"""The Faithfulness axis: did the run actually change the world as claimed?

Graders assert real state, SQLite rows, files, scalar values, never transcript
strings. An "I booked it" with no row is exactly the failure this axis exists to
catch, and it is *independent* of whether the run was deterministic.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..agent.world import World
from ..schemas.report import FaithfulnessScore, Interval
from ..schemas.scenario import OutcomeCheck, Scenario
from ..schemas.transcript import Transcript
from .stats import bootstrap_ci

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _ident(name: object) -> str:
    text = str(name)
    if not _IDENT.match(text):
        raise ValueError(f"unsafe SQL identifier in outcome check: {text!r}")
    return text


def _where(filters: dict) -> tuple[str, list]:
    if not filters:
        return "", []
    cols = [_ident(c) for c in filters]
    return " AND ".join(f"{c} = ?" for c in cols), list(filters.values())


def grade_check(world: World, check: OutcomeCheck) -> tuple[bool, str]:
    """Evaluate one declarative outcome check against the real world."""
    params = check.params
    if check.kind in ("db_row_exists", "db_row_absent"):
        table = _ident(params["table"])
        clause, values = _where(dict(params.get("where", {})))
        count = world.row_count(table, clause, values)
        if check.kind == "db_row_exists":
            return count >= 1, f"{table}: {count} matching row(s)"
        return count == 0, f"{table}: {count} matching row(s) (want 0)"
    if check.kind == "db_value_equals":
        table = _ident(params["table"])
        column = _ident(params["column"])
        clause, values = _where(dict(params.get("where", {})))
        where = f" WHERE {clause}" if clause else ""
        value = world.scalar(f"SELECT {column} FROM {table}{where}", values)
        ok = value == params["expected"]
        return ok, f"{table}.{column}={value!r} (want {params['expected']!r})"
    if check.kind == "file_exists":
        return world.file_exists(str(params["path"])), f"exists {params['path']}"
    if check.kind == "file_contains":
        content = world.read_file(str(params["path"])) or ""
        sub = str(params["substring"])
        return sub in content, f"{params['path']} contains {sub!r}"
    if check.kind == "scalar_equals":
        value = world.scalar(str(params["sql"]), list(params.get("params", [])))
        return value == params["expected"], f"scalar={value!r}"
    raise ValueError(f"unknown outcome check kind: {check.kind!r}")


def evidence_overlap(answer: str, evidence: tuple[str, ...]) -> float:
    """Fraction of required evidence strings the final answer actually cites."""
    if not evidence:
        return 1.0
    low = answer.lower()
    hits = sum(1 for item in evidence if str(item).lower() in low)
    return hits / len(evidence)


@dataclass(frozen=True)
class RunGrade:
    """Per-run faithfulness signal, gathered while the world is still open."""

    faithful: bool
    outcome_rate: float
    evidence_overlap: float


def grade_run(world: World, transcript: Transcript, scenario: Scenario) -> RunGrade:
    checks = scenario.outcome_checks
    results = [grade_check(world, c)[0] for c in checks]
    outcome_rate = sum(results) / len(results) if results else 1.0
    faithful = all(results) if results else True
    if transcript.diverged:
        faithful = False
    return RunGrade(
        faithful=faithful,
        outcome_rate=outcome_rate,
        evidence_overlap=evidence_overlap(transcript.final_answer, scenario.evidence),
    )


def aggregate_faithfulness(
    grades: list[RunGrade], *, n_boot: int = 1000, seed: int = 0
) -> FaithfulnessScore:
    runs = len(grades)
    faithful = sum(1 for g in grades if g.faithful)
    rate = faithful / runs if runs else 0.0
    outcome_rate = sum(g.outcome_rate for g in grades) / runs if runs else 0.0
    overlap = sum(g.evidence_overlap for g in grades) / runs if runs else 0.0
    low, high = bootstrap_ci(
        [1.0 if g.faithful else 0.0 for g in grades], n_boot=n_boot, seed=seed
    )
    return FaithfulnessScore(
        runs=runs,
        faithful=faithful,
        rate=rate,
        outcome_rate=outcome_rate,
        evidence_overlap=overlap,
        ci=Interval(low=low, high=high),
    )
