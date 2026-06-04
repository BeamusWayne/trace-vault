"""Execute a scenario N times and assemble its dual-axis :class:`TaskReport`.

A :class:`Case` pairs a *data* :class:`Scenario` (world, goal, graders) with the
*behavior* needed to run it: a provider factory keyed by run index (so a
deterministic case returns the same provider every time, and a flaky case can
vary by seed) and an optional ledger factory.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ..agent.loop import Agent, LedgerProtocol
from ..agent.world import World
from ..errors import DivergenceError, MaxStepsExceeded
from ..providers.base import LLMProvider
from ..schemas.report import TaskReport
from ..schemas.scenario import Scenario
from ..schemas.transcript import Transcript
from .determinism import Signature, modal_signature, score_determinism
from .faithfulness import aggregate_faithfulness, grade_run
from .trajectory import score_trajectory


@dataclass
class Case:
    """A runnable reference task."""

    scenario: Scenario
    make_provider: Callable[[int], LLMProvider]
    canonical: Signature | None = None
    ledger_factory: Callable[[], LedgerProtocol] | None = None


def _representative(
    transcripts: list[Transcript],
    signatures: list[Signature | None],
    canonical: Signature | None,
) -> Transcript:
    for transcript, signature in zip(transcripts, signatures, strict=True):
        if signature is not None and (canonical is None or signature == canonical):
            return transcript
    return transcripts[0] if transcripts else Transcript(scenario="empty")


def run_case(
    case: Case,
    agent: Agent,
    *,
    root: str | Path,
    runs: int = 20,
    k: int = 5,
    n_boot: int = 500,
    seed: int = 0,
) -> TaskReport:
    scenario = case.scenario
    signatures: list[Signature | None] = []
    transcripts: list[Transcript] = []
    grades = []
    diverged_any = False

    for i in range(runs):
        # Each replay gets its own world and ledger so runs can't bleed into one
        # another; make_provider(i) lets a flaky case vary its output by run index.
        world = World(Path(root) / f"{scenario.name}-{i}", scenario.world)
        ledger = case.ledger_factory() if case.ledger_factory else None
        try:
            transcript = agent.run(
                scenario.goal,
                case.make_provider(i),
                world,
                name=scenario.name,
                ledger=ledger,
                max_steps=scenario.max_steps,
            )
            signature: Signature | None = transcript.signature()
        except (DivergenceError, MaxStepsExceeded) as exc:
            # A run that diverges or runs out of steps has no comparable
            # trajectory, so its signature is None and it never counts as a match.
            diverged_any = True
            transcript = Transcript(
                scenario=scenario.name, diverged=True, divergence_reason=str(exc)
            )
            signature = None
        # Grade faithfulness while this run's world is still open, then close it.
        grades.append(grade_run(world, transcript, scenario))
        signatures.append(signature)
        transcripts.append(transcript)
        world.close()

    # The canonical trajectory is the one the case pins, or the most common one
    # across runs. Both determinism and trajectory grading compare against it.
    canonical = case.canonical or modal_signature(signatures)
    determinism = score_determinism(
        signatures, k=k, canonical=canonical, n_boot=n_boot, seed=seed
    )
    faithfulness = aggregate_faithfulness(grades, n_boot=n_boot, seed=seed)
    trajectory = score_trajectory(
        _representative(transcripts, signatures, canonical),
        scenario.expected_tools,
    )
    return TaskReport(
        scenario=scenario.name,
        determinism=determinism,
        faithfulness=faithfulness,
        trajectory=trajectory,
        diverged=diverged_any,
    )
