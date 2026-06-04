# Tutorial: your first reliability check

About ten minutes, fully offline, no API key. By the end you will have written a
task, scored an agent on both axes, and watched the gate catch a real bug on each
one. Every code block here is copy-paste runnable.

The task we will use: *add a 15% tip to a $40 bill and save the new total.* The
correct total is `46`.

---

## 1. Install

```bash
git clone https://github.com/BeamusWayne/trace-vault
cd trace-vault
uv venv && uv pip install -e .
# without uv: python -m venv .venv && .venv/bin/pip install -e .
```

Use the project's virtualenv for the commands below (`uv run python ...`, or
activate `.venv`).

## 2. See where you are headed

```bash
vault demo
```

This runs a small reference suite: four scenarios pass, then three deliberately
broken ones get caught on two different scores (determinism and faithfulness).
You are about to build the smallest version of that from scratch.

## 3. Run the agent once and look at what it did

Create `tip_check.py`:

```python
"""tip_check.py: run the agent once and look at what it did."""
import tempfile
from pathlib import Path

from trace_vault.agent import Agent, World, default_registry
from trace_vault.providers import FakeProvider
from trace_vault.schemas import Completion, ToolCall, WorldSpec

# The world: an empty `bills` table the tools can write to.
world_spec = WorldSpec(sql_setup=("CREATE TABLE bills (id INTEGER, total REAL);",))

# The model's behavior, scripted. In production this is a real LLM; here a fixed
# three-step script stands in so everything runs offline.
script = [
    Completion(tool_calls=(ToolCall(id="1", name="calculator",
        arguments={"expression": "40 * 1.15"}),)),
    Completion(tool_calls=(ToolCall(id="2", name="db_insert",
        arguments={"table": "bills", "values": {"id": 1, "total": 46}}),)),
    Completion(content="Saved bill 1 with total 46 (40 + 15% tip)."),
]

agent = Agent(default_registry())
with tempfile.TemporaryDirectory() as tmp:
    world = World(Path(tmp), world_spec)
    transcript = agent.run("Add a 15% tip to a $40 bill and save the new total.",
                           FakeProvider(script), world, name="tip")
    print("tools used: ", transcript.tool_sequence)
    print("final answer:", transcript.final_answer)
    print("bills row:   ", world.query("SELECT * FROM bills"))
```

Run it:

```bash
python tip_check.py
```

```text
tools used:  ('calculator', 'db_insert')
final answer: Saved bill 1 with total 46 (40 + 15% tip).
bills row:    [{'id': 1, 'total': 46.0}]
```

What happened: the `World` is a real in-memory SQLite database. The `FakeProvider`
played the model's three steps in order. The agent loop ran the real `calculator`
and `db_insert` tools, so the row in `bills` is real, with `total = 46.0`. That row
is what the faithfulness score will read later. Nothing called the network.

## 4. Turn it into a scenario and score it

A single run isn't enough to talk about reliability. Replace `tip_check.py` with a
version that describes the task as a `Scenario` and replays it 20 times:

```python
"""tip_check.py: score the task on both axes, then gate it."""
import tempfile

from trace_vault.agent import Agent, default_registry
from trace_vault.eval.runner import Case, run_case
from trace_vault.gate import Baseline, evaluate_gate, render_gate
from trace_vault.providers import FakeProvider
from trace_vault.schemas import (Completion, ToolCall, WorldSpec, Scenario,
                                 ExpectedToolCall, OutcomeCheck)

# The task as data: the starting world, the goal, the plan we expect, and a check
# that reads the real saved total (not the transcript).
scenario = Scenario(
    name="tip.save",
    goal="Add a 15% tip to a $40 bill and save the new total.",
    world=WorldSpec(sql_setup=("CREATE TABLE bills (id INTEGER, total REAL);",)),
    expected_tools=(ExpectedToolCall(name="calculator"), ExpectedToolCall(name="db_insert")),
    outcome_checks=(OutcomeCheck(
        kind="db_value_equals",
        params={"table": "bills", "column": "total", "where": {"id": 1}, "expected": 46.0}),),
    evidence=("46",),
)

def script():
    return [
        Completion(tool_calls=(ToolCall(id="1", name="calculator",
            arguments={"expression": "40 * 1.15"}),)),
        Completion(tool_calls=(ToolCall(id="2", name="db_insert",
            arguments={"table": "bills", "values": {"id": 1, "total": 46}}),)),
        Completion(content="Saved bill 1 with total 46 (40 + 15% tip)."),
    ]

agent = Agent(default_registry())
# A Case pairs the task with how to produce the model's behavior for each run.
case = Case(scenario=scenario, make_provider=lambda i: FakeProvider(script()))

with tempfile.TemporaryDirectory() as tmp:
    report = run_case(case, agent, root=tmp, runs=20, k=5)

print("determinism: ", report.determinism.rate)
print("faithfulness:", report.faithfulness.rate)
print(render_gate(evaluate_gate([report], Baseline())))
```

Run it:

```bash
python tip_check.py
```

```text
determinism:  1.0
faithfulness: 1.0
trace-vault gate · 1 scenario

scenario                     determ.  faithful.    traj.  verdict
-----------------------------------------------------------------
tip.save                       1.00       1.00     1.00   PASS

GATE: PASS  (1/1 scenarios within thresholds)   exit 0
```

`run_case` ran the agent 20 times, each against a fresh world. Determinism is 1.0
because every run took the same path. Faithfulness is 1.0 because every run left
`bills.total = 46`, which is what the outcome check asked for. `evaluate_gate` with
a default `Baseline()` requires every score to be 1.0, so the gate passes and exits
0. In a real project you commit a baseline JSON and run `vault gate` in CI.

You now have a green reliability check. The next two steps break it on purpose.

## 5. Catch a wrong answer (faithfulness)

Here is a bug a transcript check would miss. In `script()`, change the saved total
from `46` to `40` (the agent forgot to add the tip, but still reports success):

```python
        Completion(tool_calls=(ToolCall(id="2", name="db_insert",
            arguments={"table": "bills", "values": {"id": 1, "total": 40}}),)),  # bug: pre-tip amount
```

Run it again:

```text
determinism:  1.0
faithfulness: 0.0
tip.save                       1.00       0.00*    1.00   FAIL

GATE: FAIL  (1/1 scenario(s) below threshold)   exit 1
  x tip.save: faithfulness 0.00 < 1.00
```

The agent does this *reliably* (determinism is still 1.0), and its final answer
still says "Saved", so a test that searches the transcript for "Saved" would pass.
trace-vault reads the `bills` row instead, sees `40` where it expected `46`, and
fails on faithfulness. This is the kind of bug that reaches production.

Put `40` back to `46` before the next step.

## 6. Catch a flake (determinism)

Now the opposite: the answer is always right, but the agent reaches it two
different ways across runs. Swap the provider for a `StochasticFakeProvider`, which
picks among options per step using the run's seed. Replace the `script` function
and the `case` line with:

```python
from trace_vault.providers import StochasticFakeProvider

# Step 0 reaches 46 two different ways; steps 1 and 2 are fixed.
variants = [
    [Completion(tool_calls=(ToolCall(id="1", name="calculator",
        arguments={"expression": "40 * 1.15"}),)),
     Completion(tool_calls=(ToolCall(id="1", name="calculator",
        arguments={"expression": "40 + 6"}),))],
    [Completion(tool_calls=(ToolCall(id="2", name="db_insert",
        arguments={"table": "bills", "values": {"id": 1, "total": 46}}),))],
    [Completion(content="Saved bill 1 with total 46.")],
]
case = Case(scenario=scenario, make_provider=lambda i: StochasticFakeProvider(variants, seed=i))
```

Also print the two pass-rate statistics:

```python
d = report.determinism
print(f"determinism: {d.rate}  pass^5: {d.pass_caret_k:.3f}  pass@5: {d.pass_at_k:.3f}")
print("faithfulness:", report.faithfulness.rate)
print(render_gate(evaluate_gate([report], Baseline())))
```

Run it:

```text
determinism: 0.6  pass^5: 0.051  pass@5: 0.996
faithfulness: 1.0
tip.save                       0.60*      1.00     1.00   FAIL

GATE: FAIL  (1/1 scenario(s) below threshold)   exit 1
  x tip.save: determinism 0.60 < 1.00
```

Faithfulness stays 1.0 (both paths save 46), but the path isn't reproducible.
`pass@5` is 0.996, meaning "at least one of five runs agrees", which looks healthy.
`pass^5` is 0.051, meaning "all five agree", which exposes the flake. The second
number is closer to what you feel in production, and the gate fails on determinism.

These are the same two failures `vault demo` shows, now built by hand.

## 7. Record a cassette instead of scripting

So far the model has been a fixed script. The real workflow records one run of your
agent and replays that recording. The recording is a *cassette*, a YAML file you
commit. Put the good `script()` back, then:

```python
from pathlib import Path
from trace_vault.agent import World
from trace_vault.cassette.recorder import record_run
from trace_vault.cassette.store import save_cassette, load_cassette
from trace_vault.providers import CassetteProvider

with tempfile.TemporaryDirectory() as tmp:
    # Record once. Here we wrap a FakeProvider; in production you pass your real
    # provider (see src/trace_vault/providers/real.py for an OpenAI-style one).
    rec_world = World(Path(tmp) / "rec", scenario.world)
    _, cassette = record_run(agent, scenario.goal, FakeProvider(script()), rec_world, name="tip.save")
    rec_world.close()
    save_cassette(cassette, "cassettes/tip.save.yaml")

    # From now on, replay the cassette offline. No model, no key.
    loaded = load_cassette("cassettes/tip.save.yaml")
    case = Case(scenario=scenario, make_provider=lambda i: CassetteProvider(loaded))
    report = run_case(case, agent, root=Path(tmp) / "runs", runs=20, k=5)
    print("from cassette -> determinism:", report.determinism.rate,
          "faithfulness:", report.faithfulness.rate)
```

```text
from cassette -> determinism: 1.0 faithfulness: 1.0
```

Open `cassettes/tip.save.yaml` to see what was recorded: each step's request and the
model's response, with volatile fields (ids, timestamps) stripped so it still
matches on replay. Commit that file and the suite replays it forever, offline.

## 8. Where to go next

You have built a reliability check from scratch and seen the gate catch a wrong
answer (faithfulness) and a flake (determinism), two failures a single combined
score would have blurred together.

- **Bring your own tools.** The built-in toolset is small. Subclass `Tool` and
  register it; see [Bringing your own tools](../README.md#using-it-on-your-own-agent).
- **Make a side effect fire once.** For a tool that charges a card or sends an
  email, the effect ledger keeps a retry from doing it twice. See the
  `refund.idempotent_retry` scenario in `src/trace_vault/suite/scenarios.py`.
- **Read the design.** [`docs/ARCHITECTURE.md`](./ARCHITECTURE.md) covers the
  layers and the decisions behind them; [`docs/RESULTS.md`](./RESULTS.md) explains
  the reference numbers.
- **Browse the reference scenarios** in `src/trace_vault/suite/scenarios.py` for
  worked examples of each quadrant plus a prompt-injection case.
