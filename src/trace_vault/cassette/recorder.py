"""Convenience: run an agent once and capture its cassette.

Kept out of ``cassette/__init__`` so importing the cassette package never pulls
the agent layer in — this module is the one place the two meet.
"""

from __future__ import annotations

from ..agent.loop import Agent
from ..agent.world import World
from ..providers.base import LLMProvider
from ..providers.cassette import RecordingProvider
from ..schemas.cassette import Cassette, MatchMode
from ..schemas.transcript import Transcript


def record_run(
    agent: Agent,
    goal: str,
    inner: LLMProvider,
    world: World,
    *,
    name: str = "recording",
    match_mode: MatchMode = "strict",
) -> tuple[Transcript, Cassette]:
    """Run ``agent`` against ``inner`` while recording, returning the transcript
    and the resulting cassette."""
    recorder = RecordingProvider(inner, name=name, match_mode=match_mode)
    transcript = agent.run(goal, recorder, world, name=name)
    return transcript, recorder.cassette()
