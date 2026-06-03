"""M2 integration: record once, replay forever — and catch any tampering."""

from __future__ import annotations

from pathlib import Path

import pytest

from trace_vault.agent import Agent, default_registry
from trace_vault.agent.world import World
from trace_vault.cassette.recorder import record_run
from trace_vault.cassette.store import load_cassette, save_cassette
from trace_vault.errors import DivergenceError
from trace_vault.providers import CassetteProvider, FakeProvider
from trace_vault.schemas.messages import Completion, ToolCall
from trace_vault.schemas.scenario import WorldSpec

_GOAL = "Book room A at 15% off 100"
_SPEC = WorldSpec(sql_setup=("CREATE TABLE bookings (room TEXT, price REAL);",))
_SCRIPT = [
    Completion(tool_calls=(ToolCall(id="a1", name="calculator", arguments={"expression": "100*0.85"}),)),
    Completion(
        tool_calls=(
            ToolCall(
                id="a2",
                name="db_insert",
                arguments={"table": "bookings", "values": {"room": "A", "price": 85}},
            ),
        )
    ),
    Completion(content="Booked room A for 85."),
]


def _record(tmp_path: Path):
    agent = Agent(default_registry())
    world = World(tmp_path / "rec", _SPEC)
    transcript, cassette = record_run(
        agent, _GOAL, FakeProvider(_SCRIPT), world, name="booking"
    )
    world.close()
    return agent, transcript, cassette


@pytest.mark.integration
def test_replay_reproduces_the_recorded_trajectory(tmp_path: Path) -> None:
    agent, recorded, cassette = _record(tmp_path)
    assert len(cassette.interactions) == 3

    # Replay against a FRESH world: the tools run for real again.
    world = World(tmp_path / "replay", _SPEC)
    replayed = agent.run(_GOAL, CassetteProvider(cassette), world, name="booking")

    assert replayed.signature() == recorded.signature()
    assert world.row_count("bookings", "room = ?", ["A"]) == 1
    world.close()


@pytest.mark.integration
def test_cassette_yaml_roundtrip_is_stable(tmp_path: Path) -> None:
    _, _, cassette = _record(tmp_path)
    path = save_cassette(cassette, tmp_path / "booking.yaml")
    loaded = load_cassette(path)
    assert loaded.model_dump() == cassette.model_dump()


@pytest.mark.integration
def test_tampered_cassette_flips_replay_red(tmp_path: Path) -> None:
    agent, _, cassette = _record(tmp_path)

    # Tamper: make step 0 call a DIFFERENT tool than was recorded.
    poisoned = Completion(
        tool_calls=(ToolCall(id="x", name="db_query", arguments={"table": "bookings"}),)
    )
    i0 = cassette.interactions[0].model_copy(update={"completion": poisoned})
    tampered = cassette.with_interactions((i0, *cassette.interactions[1:]))

    world = World(tmp_path / "tampered", _SPEC)
    with pytest.raises(DivergenceError) as exc:
        agent.run(_GOAL, CassetteProvider(tampered), world, name="booking")
    # The agent took the bait at step 0, so the request at step 1 diverges.
    assert exc.value.kind == "tool-name"
    assert exc.value.step == 1
    world.close()
