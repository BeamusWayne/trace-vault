"""Use trace-vault on your own agent — a complete, runnable example.

    python examples/use_on_your_agent.py     # prints the gate report, exits 0/1

The four steps below are the whole workflow:

  1. describe the task as DATA (world + goal + graders that check REAL state),
  2. capture your agent's behavior once into a cassette (here: a scripted stand-in
     for your real LLM — in production you'd record your live provider),
  3. build a Case and replay it N times to score Determinism + Faithfulness,
  4. gate it against a baseline and exit non-zero on a regression.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from trace_vault.agent import Agent, World, default_registry
from trace_vault.cassette.recorder import record_run
from trace_vault.eval.runner import Case, run_case
from trace_vault.gate import Baseline, evaluate_gate, render_gate
from trace_vault.providers import CassetteProvider, FakeProvider
from trace_vault.schemas import (
    Completion,
    ExpectedToolCall,
    OutcomeCheck,
    Scenario,
    ToolCall,
    WorldSpec,
)

# 1) DESCRIBE THE TASK AS DATA ------------------------------------------------
#    The world your tools act on, the goal, the plan you expect, and — crucially
#    — outcome checks that assert REAL state (a row's value), not the transcript.
scenario = Scenario(
    name="discount.apply",
    goal="Apply 20% off order 1001 (rack total 200) and persist the new total.",
    world=WorldSpec(sql_setup=("CREATE TABLE order_totals (id INTEGER, total REAL);",)),
    expected_tools=(ExpectedToolCall(name="calculator"), ExpectedToolCall(name="db_insert")),
    outcome_checks=(
        OutcomeCheck(
            kind="db_value_equals",
            params={"table": "order_totals", "column": "total", "where": {"id": 1001}, "expected": 160.0},
        ),
    ),
    evidence=("160",),
)

# 2) CAPTURE THE AGENT'S BEHAVIOR ONCE ----------------------------------------
#    In production: `record_run(agent, goal, YourRealProvider(), world, name=...)`
#    then `save_cassette(cassette, "cassettes/discount.apply.yaml")`.
#    Here a scripted FakeProvider stands in for the LLM so the example is offline.
agent = Agent(default_registry())
script = [
    Completion(tool_calls=(ToolCall(id="c1", name="calculator", arguments={"expression": "200*0.8"}),)),
    Completion(
        tool_calls=(
            ToolCall(id="c2", name="db_insert", arguments={"table": "order_totals", "values": {"id": 1001, "total": 160}}),
        )
    ),
    Completion(content="Order 1001 total is 160 after 20% off."),
]

with tempfile.TemporaryDirectory() as tmp:
    rec_world = World(Path(tmp) / "rec", scenario.world)
    _, cassette = record_run(agent, scenario.goal, FakeProvider(script), rec_world, name=scenario.name)
    rec_world.close()

    # 3) REPLAY N TIMES AND SCORE BOTH AXES -----------------------------------
    case = Case(scenario=scenario, make_provider=lambda i: CassetteProvider(cassette))
    report = run_case(case, agent, root=Path(tmp) / "runs", runs=20, k=5)

    # 4) GATE IT --------------------------------------------------------------
    gate = evaluate_gate([report], Baseline())  # default thresholds: all 1.0

print(render_gate(gate))
sys.exit(0 if gate.passed else 1)
