"""Edge cases: provider modes, tool error handling, and IO failures.

These harden the boundaries (bad input, missing files, path escapes, injection-
shaped SQL identifiers) and exercise the order-tolerant subset match mode.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from trace_vault.agent.tools import safe_eval
from trace_vault.agent.tools.base import ToolRegistry
from trace_vault.agent.tools.calculator import CalculatorTool
from trace_vault.agent.tools.database import DBInsertTool
from trace_vault.agent.tools.files import ReadFileTool
from trace_vault.agent.tools.transfer import TransferTool
from trace_vault.agent.world import World
from trace_vault.cassette.matcher import CassetteCursor
from trace_vault.cassette.normalize import normalize_request, request_key
from trace_vault.cassette.store import load_cassette
from trace_vault.errors import CassetteError, DivergenceError, ToolError, TraceVaultError
from trace_vault.gate.baseline import load_baseline
from trace_vault.providers import KeyedFakeProvider, StochasticFakeProvider
from trace_vault.schemas.cassette import Cassette, Interaction
from trace_vault.schemas.messages import Completion, Message
from trace_vault.schemas.scenario import WorldSpec

# --- providers --------------------------------------------------------------


@pytest.mark.unit
def test_keyed_fake_provider_routes_by_key_and_default() -> None:
    msgs = [Message(role="user", content="hi")]
    key = request_key(msgs)
    keyed = KeyedFakeProvider({key: Completion(content="routed")}, default=Completion(content="fallback"))
    assert keyed.complete(msgs).content == "routed"
    assert keyed.complete([Message(role="user", content="other")]).content == "fallback"


@pytest.mark.unit
def test_keyed_fake_provider_raises_without_default() -> None:
    keyed = KeyedFakeProvider({})
    with pytest.raises(KeyError):
        keyed.complete([Message(role="user", content="x")])


@pytest.mark.unit
def test_stochastic_provider_is_reproducible_per_seed() -> None:
    variants = [[Completion(content="a"), Completion(content="b")]]
    first = StochasticFakeProvider(variants, seed=3).complete([])
    again = StochasticFakeProvider(variants, seed=3).complete([])
    assert first.content == again.content


# --- subset match mode ------------------------------------------------------


@pytest.mark.unit
def test_subset_mode_tolerates_extra_history() -> None:
    recorded = [Message(role="user", content="ping")]
    interaction = Interaction(
        index=0,
        request_key=request_key(recorded),
        request_digest=normalize_request(recorded),
        completion=Completion(content="pong"),
    )
    cassette = Cassette(name="c", match_mode="subset", interactions=(interaction,))
    cursor = CassetteCursor(cassette)

    # A longer history whose LAST turn matches still resolves under subset.
    longer = [Message(role="system", content="preamble"), Message(role="user", content="ping")]
    assert cursor.next_completion(longer).content == "pong"


@pytest.mark.unit
def test_unordered_mode_exhausts_with_divergence() -> None:
    msgs = [Message(role="user", content="only")]
    interaction = Interaction(
        index=0,
        request_key=request_key(msgs),
        request_digest=normalize_request(msgs),
        completion=Completion(content="ok"),
    )
    cursor = CassetteCursor(Cassette(name="c", match_mode="unordered", interactions=(interaction,)))
    assert cursor.next_completion(msgs).content == "ok"
    with pytest.raises(DivergenceError):
        cursor.next_completion([Message(role="user", content="unrecorded")])


# --- tool error handling ----------------------------------------------------


@pytest.mark.unit
def test_calculator_rejects_non_arithmetic() -> None:
    assert safe_eval("2 ** 10") == 1024
    with pytest.raises(ToolError):
        safe_eval("__import__('os').system('echo hi')")
    with pytest.raises(ToolError):
        safe_eval("1 +")


@pytest.mark.unit
def test_db_insert_validates_identifiers_and_tables(tmp_path: Path) -> None:
    world = World(tmp_path, WorldSpec(sql_setup=("CREATE TABLE t (a TEXT);",)))
    tool = DBInsertTool()
    # Unknown table -> graceful failure result.
    assert tool.run({"table": "nope", "values": {"a": "1"}}, world).ok is False
    # Injection-shaped identifier -> hard ToolError.
    with pytest.raises(ToolError):
        tool.run({"table": "t); DROP TABLE t;--", "values": {"a": "1"}}, world)
    # Unknown column -> ToolError.
    with pytest.raises(ToolError):
        tool.run({"table": "t", "values": {"ghost": "1"}}, world)
    world.close()


@pytest.mark.unit
def test_transfer_guards(tmp_path: Path) -> None:
    world = World(
        tmp_path,
        WorldSpec(
            sql_setup=(
                "CREATE TABLE accounts (account TEXT PRIMARY KEY, balance REAL);",
                "INSERT INTO accounts VALUES ('a', 10), ('b', 0);",
                "CREATE TABLE transfers (from_account TEXT, to_account TEXT, amount REAL, idem TEXT);",
            )
        ),
    )
    tool = TransferTool()
    assert tool.run({"from_account": "a", "to_account": "b", "amount": -1}, world).ok is False
    assert tool.run({"from_account": "ghost", "to_account": "b", "amount": 1}, world).ok is False
    assert tool.run({"from_account": "a", "to_account": "b", "amount": 999}, world).ok is False
    world.close()


@pytest.mark.unit
def test_missing_tool_and_duplicate_registry() -> None:
    reg = ToolRegistry([CalculatorTool()])
    with pytest.raises(ToolError):
        reg.get("nope")
    with pytest.raises(ToolError):
        ToolRegistry([CalculatorTool(), CalculatorTool()])


@pytest.mark.unit
def test_world_refuses_path_escape(tmp_path: Path) -> None:
    world = World(tmp_path, None)
    with pytest.raises(ValueError):
        world.write_file("../escape.txt", "nope")
    assert ReadFileTool().run({"path": "missing.txt"}, world).ok is False
    world.close()


# --- IO failures ------------------------------------------------------------


@pytest.mark.unit
def test_load_cassette_missing_raises() -> None:
    with pytest.raises(CassetteError):
        load_cassette("/nonexistent/cassette.yaml")


@pytest.mark.unit
def test_load_baseline_missing_raises() -> None:
    with pytest.raises(TraceVaultError):
        load_baseline("/nonexistent/baseline.json")
