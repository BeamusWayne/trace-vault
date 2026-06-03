"""The reference scenario suite.

Each scenario is recorded once (from a scripted FakeProvider) into a cassette and
then replayed offline. The five scenarios are chosen to land in every cell of the
determinism x faithfulness grid:

    good      booking.write_room      determinism 1.0  faithfulness 1.0
    good      research.cite_source    determinism 1.0  faithfulness 1.0
    good      refund.transfer_once    determinism 1.0  faithfulness 1.0
    BAD       report.flaky_plan       determinism <1   faithfulness 1.0   <- flaky but harmless
    BAD       booking.unfaithful_write determinism 1.0 faithfulness 0.0   <- reliable but WRONG

The last two are why the axes are gated separately.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from ..agent.loop import Agent
from ..agent.tools import default_registry
from ..agent.world import World
from ..cassette.recorder import record_run
from ..eval.runner import Case
from ..providers import CassetteProvider, FakeProvider, StochasticFakeProvider
from ..schemas.cassette import Cassette
from ..schemas.messages import Completion, ToolCall
from ..schemas.scenario import ExpectedToolCall, OutcomeCheck, Scenario, WorldSpec

_AGENT = Agent(default_registry())


def _record(scenario: Scenario, script: list[Completion]) -> Cassette:
    """Record a scenario's scripted run into a cassette (offline, throwaway world)."""
    with tempfile.TemporaryDirectory() as tmp:
        world = World(Path(tmp) / "rec", scenario.world)
        _, cassette = record_run(
            _AGENT, scenario.goal, FakeProvider(script), world, name=scenario.name
        )
        world.close()
    return cassette


def _replay_case(scenario: Scenario, script: list[Completion]) -> Case:
    cassette = _record(scenario, script)
    return Case(scenario=scenario, make_provider=lambda i: CassetteProvider(cassette))


# --- good scenarios ---------------------------------------------------------


def booking_case() -> Case:
    scenario = Scenario(
        name="booking.write_room",
        goal="Book room 'A' at 15% off the 100 rack rate, then confirm.",
        world=WorldSpec(sql_setup=("CREATE TABLE bookings (room TEXT, price REAL);",)),
        expected_tools=(
            ExpectedToolCall(name="calculator", args={"expression": "100*0.85"}),
            ExpectedToolCall(name="db_insert"),
        ),
        outcome_checks=(
            OutcomeCheck(kind="db_row_exists", params={"table": "bookings", "where": {"room": "A"}}),
            OutcomeCheck(
                kind="db_value_equals",
                params={"table": "bookings", "column": "price", "where": {"room": "A"}, "expected": 85.0},
            ),
        ),
        evidence=("85",),
    )
    script = [
        Completion(tool_calls=(ToolCall(id="b1", name="calculator", arguments={"expression": "100*0.85"}),)),
        Completion(
            tool_calls=(
                ToolCall(id="b2", name="db_insert", arguments={"table": "bookings", "values": {"room": "A", "price": 85}}),
            )
        ),
        Completion(content="Booked room A at 85 (15% off the 100 rack rate)."),
    ]
    return _replay_case(scenario, script)


def research_case() -> Case:
    scenario = Scenario(
        name="research.cite_source",
        goal="Find the capital of Eldoria in the knowledge base and write it to answer.txt.",
        world=WorldSpec(
            sql_setup=(
                "CREATE TABLE documents (id INTEGER, title TEXT, body TEXT);",
                "INSERT INTO documents VALUES (1, 'Eldoria', 'The capital of Eldoria is Vmark, founded 1410.');",
            )
        ),
        expected_tools=(ExpectedToolCall(name="search"), ExpectedToolCall(name="write_file")),
        outcome_checks=(
            OutcomeCheck(kind="file_contains", params={"path": "answer.txt", "substring": "Vmark"}),
        ),
        evidence=("Vmark",),
    )
    script = [
        Completion(tool_calls=(ToolCall(id="r1", name="search", arguments={"query": "Eldoria capital"}),)),
        Completion(
            tool_calls=(
                ToolCall(id="r2", name="write_file", arguments={"path": "answer.txt", "content": "The capital of Eldoria is Vmark."}),
            )
        ),
        Completion(content="The capital of Eldoria is Vmark; wrote it to answer.txt."),
    ]
    return _replay_case(scenario, script)


def refund_case() -> Case:
    scenario = Scenario(
        name="refund.transfer_once",
        goal="Refund 30 from merchant 'acme' to customer 'cust1' (idempotency key refund-INV-1).",
        world=WorldSpec(
            sql_setup=(
                "CREATE TABLE accounts (account TEXT PRIMARY KEY, balance REAL);",
                "INSERT INTO accounts VALUES ('acme', 100), ('cust1', 0);",
                "CREATE TABLE transfers (from_account TEXT, to_account TEXT, amount REAL, idem TEXT);",
            )
        ),
        expected_tools=(ExpectedToolCall(name="transfer"),),
        outcome_checks=(
            OutcomeCheck(
                kind="db_value_equals",
                params={"table": "accounts", "column": "balance", "where": {"account": "cust1"}, "expected": 30.0},
            ),
            OutcomeCheck(kind="db_row_exists", params={"table": "transfers", "where": {"idem": "refund-INV-1"}}),
        ),
        evidence=("30",),
    )
    script = [
        Completion(
            tool_calls=(
                ToolCall(
                    id="t1",
                    name="transfer",
                    arguments={"from_account": "acme", "to_account": "cust1", "amount": 30, "idempotency_key": "refund-INV-1"},
                ),
            )
        ),
        Completion(content="Refunded 30 from acme to cust1."),
    ]
    return _replay_case(scenario, script)


# --- bad scenarios (used by the demo / red-path tests) ----------------------


def flaky_case() -> Case:
    """Reliable on faithfulness, FLAKY on determinism: step 0 samples between two
    different (valid) calculations, so the trajectory isn't reproducible."""
    scenario = Scenario(name="report.flaky_plan", goal="Summarize the Q2 figures.", world=WorldSpec())
    variants = [
        [
            Completion(tool_calls=(ToolCall(id="f", name="calculator", arguments={"expression": "120*0.85"}),)),
            Completion(tool_calls=(ToolCall(id="f", name="calculator", arguments={"expression": "100*0.85"}),)),
        ],
        [Completion(content="Q2 summary complete.")],
    ]
    return Case(scenario=scenario, make_provider=lambda i: StochasticFakeProvider(variants, seed=i))


def unfaithful_case() -> Case:
    """Perfectly reproducible and perfectly WRONG: the agent reliably writes the
    booking to a staging table that nobody reads, so the trajectory looks fine
    but the real `bookings` table stays empty. determinism 1.0, faithfulness 0.0."""
    scenario = Scenario(
        name="booking.unfaithful_write",
        goal="Book room 'B' at 90 and confirm.",
        world=WorldSpec(
            sql_setup=(
                "CREATE TABLE bookings (room TEXT, price REAL);",
                "CREATE TABLE pending_bookings (room TEXT, price REAL);",
            )
        ),
        expected_tools=(ExpectedToolCall(name="db_insert"),),
        outcome_checks=(
            OutcomeCheck(kind="db_row_exists", params={"table": "bookings", "where": {"room": "B"}}),
        ),
    )
    script = [
        Completion(
            tool_calls=(
                ToolCall(id="g1", name="db_insert", arguments={"table": "pending_bookings", "values": {"room": "B", "price": 90}}),
            )
        ),
        Completion(content="Booked room B for 90."),
    ]
    return _replay_case(scenario, script)


# --- suites -----------------------------------------------------------------


def good_suite() -> list[Case]:
    """The scenarios the committed baseline expects to pass (CI stays green)."""
    return [booking_case(), research_case(), refund_case()]


def full_suite() -> list[Case]:
    """Every scenario, including the two the gate is meant to catch."""
    return [*good_suite(), flaky_case(), unfaithful_case()]
