"""M5 integration: the irreversible-effect ledger fires an effect exactly once."""

from __future__ import annotations

from pathlib import Path

import pytest

from trace_vault.agent import Agent, default_registry
from trace_vault.agent.world import World
from trace_vault.ledger import EffectLedger
from trace_vault.providers import FakeProvider
from trace_vault.schemas.messages import Completion, ToolCall
from trace_vault.schemas.scenario import WorldSpec

_SPEC = WorldSpec(
    sql_setup=(
        "CREATE TABLE accounts (account TEXT PRIMARY KEY, balance REAL);",
        "INSERT INTO accounts VALUES ('acme', 100), ('cust1', 0);",
        "CREATE TABLE transfers (from_account TEXT, to_account TEXT, amount REAL, idem TEXT);",
    )
)


def _refund_script() -> list[Completion]:
    call = ToolCall(
        id="t",
        name="transfer",
        arguments={"from_account": "acme", "to_account": "cust1", "amount": 30, "idempotency_key": "r-1"},
    )
    return [Completion(tool_calls=(call,)), Completion(content="refunded")]


def _cust1(world: World) -> float:
    return world.scalar("SELECT balance FROM accounts WHERE account = 'cust1'")


@pytest.mark.integration
def test_ledger_executes_effect_once_across_retries(tmp_path: Path) -> None:
    agent = Agent(default_registry())
    world = World(tmp_path, _SPEC)
    ledger = EffectLedger()

    # Two identical runs (a retry) against the same world, sharing one ledger.
    agent.run("refund", FakeProvider(_refund_script()), world, ledger=ledger)
    agent.run("refund", FakeProvider(_refund_script()), world, ledger=ledger)

    assert ledger.executions == 1  # the wire fired exactly once
    assert _cust1(world) == 30  # ...so the customer is refunded exactly once
    assert world.row_count("transfers") == 1
    world.close()


@pytest.mark.integration
def test_without_ledger_the_same_retry_double_charges(tmp_path: Path) -> None:
    # The contrast that proves the ledger is load-bearing.
    agent = Agent(default_registry())
    world = World(tmp_path, _SPEC)

    agent.run("refund", FakeProvider(_refund_script()), world)
    agent.run("refund", FakeProvider(_refund_script()), world)

    assert _cust1(world) == 60  # double-charged without the ledger
    world.close()
