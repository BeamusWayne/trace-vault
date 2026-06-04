<div align="center">

# trace-vault 🎞️🔐

**A record/replay reliability gate for tool-using agents.**

*Record an agent run once into a normalized cassette. Replay it forever — offline,
deterministically, with zero API keys. Gate CI on two independent axes the field
keeps conflating: **Determinism** and **Faithfulness**.*

[![CI](https://github.com/BeamusWayne/trace-vault/actions/workflows/ci.yml/badge.svg)](https://github.com/BeamusWayne/trace-vault/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](./LICENSE)
[![Offline by design](https://img.shields.io/badge/network-blocked%20on%20replay-critical.svg)](#the-offline-green-invariant)

[English](#why-trace-vault) · [中文说明](#中文说明)

</div>

<p align="center">
  <img src="./docs/assets/gate-demo.svg" width="760"
       alt="vault gate --full: four PASS scenarios, then three FAIL — one flaky (determinism), two unfaithful (faithfulness)">
</p>

> One flaky scenario, two unfaithful ones — caught on **two independent axes**.
> The agent that scores `faithfulness 0.00` is *perfectly reproducible*; the one
> that scores `determinism 0.60` is *perfectly harmless*. A single score hides one.

---

## Why trace-vault

A production agent is a distributed system where the LLM is the planner. The
expensive failures aren't crashes — they're **non-reproducible tool orderings**
("it worked on my machine, once") and **looks-correct-but-wrong transcripts**
(the agent *says* it booked the room; the row was never written).

Teams can't put agents behind a CI gate because:

1. **Runs aren't reproducible** — temperature, tool nondeterminism, and provider
   drift make every run a fresh roll of the dice.
2. **Graders check the transcript, not the world** — "it said `booked`" passes;
   "the `bookings` row exists" is what actually matters.

trace-vault attacks both, and keeps them **separate on purpose**.

### The two axes (and why they're separate)

> **Determinism ≠ Faithfulness.** An agent can be perfectly reproducible and
> perfectly wrong. It can also be right by luck on a run it can't repeat.
> Collapsing the two into one "score" hides the failure that bites you in prod.

| Axis | Question | How trace-vault measures it |
|------|----------|------------------------------|
| **Determinism** | Does the agent take the *same trajectory* every replay? | Replay N times, compare trajectory signatures, report `pass^k` / `pass@k` with a bootstrap CI and a min-runs power hint. |
| **Faithfulness** | Did the run actually change the *world* as claimed? | Outcome graders assert real **SQLite rows** and **temp-filesystem** state — never transcript strings — plus a deterministic evidence-overlap rubric. |

trace-vault surfaces both side by side and **gates them independently**. A drop in
either fails CI.

---

## The offline-green invariant

> **Every test in this repo runs with the network blocked and no API key.**

That isn't a testing trick bolted on afterwards — it *is* the architecture.
Replay is offline by definition: the cassette **is** the fixture, and a
deterministic `FakeProvider` **is** the test double. The default code path never
imports a real provider SDK. CI runs the entire agent → cassette → eval → gate →
ledger pipeline in seconds, on a runner with no secrets.

```text
record once (optionally against a real LLM)  ──►  cassettes/*.yaml
                                                        │
        ┌───────────────────────────────────────────────┘
        ▼
replay forever, offline ──► agent loop ──► dual-axis eval ──► vault gate ──► exit 0 / 1
```

---

## When you'd reach for it

- **Gate an agent PR in CI** — block a merge that makes the agent less
  reproducible *or* less correct, with one `vault gate` call and a non-zero exit.
- **Catch "looks-fine" regressions** — a refactor that quietly stops writing the
  row still passes every transcript check; faithfulness (which reads the DB)
  catches it.
- **Quantify flakiness honestly** — `pass^k` and a confidence interval instead of
  "seems to work on my machine."
- **Prove a guardrail works** — record an attack (e.g. prompt injection) once and
  keep the gate red until the defense lands.

## Quickstart

```bash
# 1. install (uv recommended)
uv venv && uv pip install -e .

# 2. run the dual-axis gate against the committed baseline
vault gate --baseline examples/baseline.json

# 3. see the headline: the good suite is green, then two regressions get caught
vault demo
```

`vault gate` runs the committed good suite and exits **0** — this is what CI runs:

```text
trace-vault gate · 4 scenarios

scenario                     determ.  faithful.    traj.  verdict
-----------------------------------------------------------------
booking.write_room             1.00       1.00     1.00   PASS
research.cite_source           1.00       1.00     1.00   PASS
refund.transfer_once           1.00       1.00     1.00   PASS
refund.idempotent_retry        1.00       1.00     1.00   PASS

GATE: PASS  (4/4 scenarios within thresholds)   exit 0
```

`vault gate --full` adds the red-path scenarios and the gate **bites** (exit 1):

```text
scenario                     determ.  faithful.    traj.  verdict
-----------------------------------------------------------------
...
report.flaky_plan              0.60*      1.00     1.00   FAIL   <- reproducibly broken
booking.unfaithful_write       1.00       0.00*    1.00   FAIL   <- reliably WRONG
payment.injection              1.00       0.00*    1.00   FAIL   <- evidence-poisoned

GATE: FAIL  (3/7 scenario(s) below threshold)   exit 1
```

That `report.flaky_plan` / `booking.unfaithful_write` split is the whole point:
**two failures, two different root causes, two different fixes** — and a single
collapsed score would have hidden one of them. (`*` marks the breached axis.)

---

## Use it on your own agent

trace-vault doesn't care how your agent is built — it only needs a provider that
returns the next step. Point it at your agent in four steps. The full runnable
version is [`examples/use_on_your_agent.py`](./examples/use_on_your_agent.py)
(`python examples/use_on_your_agent.py` → prints the report, exits 0/1).

**1 — Describe the task as data.** The world your tools act on, the goal, the plan
you expect, and outcome checks that assert *real state* (a row's value), not the
transcript:

```python
from trace_vault.schemas import Scenario, WorldSpec, ExpectedToolCall, OutcomeCheck

scenario = Scenario(
    name="discount.apply",
    goal="Apply 20% off order 1001 (rack total 200) and persist the new total.",
    world=WorldSpec(sql_setup=("CREATE TABLE order_totals (id INTEGER, total REAL);",)),
    expected_tools=(ExpectedToolCall(name="calculator"), ExpectedToolCall(name="db_insert")),
    outcome_checks=(OutcomeCheck(
        kind="db_value_equals",
        params={"table": "order_totals", "column": "total",
                "where": {"id": 1001}, "expected": 160.0}),),
    evidence=("160",),
)
```

**2 — Record your agent once.** Wrap your real provider; the recorder writes a
normalized cassette you commit and replay forever:

```python
from trace_vault.cassette.recorder import record_run
from trace_vault.cassette.store import save_cassette

_, cassette = record_run(agent, scenario.goal, YourProvider(), world, name=scenario.name)
save_cassette(cassette, "cassettes/discount.apply.yaml")
```

Your provider is anything with `complete(messages, tools) -> Completion`: a
~25-line adapter (see [`providers/real.py`](./src/trace_vault/providers/real.py)
for an OpenAI-compatible one that also covers Ollama / vLLM / Groq), or a scripted
`FakeProvider([...])` for tests.

**3 — Replay N times and score both axes:**

```python
from trace_vault.eval.runner import Case, run_case
from trace_vault.providers import CassetteProvider

case = Case(scenario=scenario, make_provider=lambda i: CassetteProvider(cassette))
report = run_case(case, agent, root="/tmp/runs", runs=20, k=5)
print(report.determinism.rate, report.faithfulness.rate)   # 1.0 1.0
```

**4 — Gate it, and wire into CI:**

```python
from trace_vault.gate import Baseline, evaluate_gate, render_gate

gate = evaluate_gate([report], Baseline())   # thresholds default to 1.0
print(render_gate(gate))
raise SystemExit(0 if gate.passed else 1)
```

Need an irreversible tool (a charge, an email) to fire exactly once across
retries? Pass `ledger_factory=EffectLedger` to the `Case` — see
[`refund.idempotent_retry`](./src/trace_vault/suite/scenarios.py).

## CLI reference

| command | what it does |
|---------|--------------|
| `vault gate -b baseline.json` | run the good suite, gate vs baseline, **exit 0/1** — this is what CI runs |
| `vault gate -b baseline.json --full` | also include the red-path scenarios (they fail by design) |
| `vault eval [--full]` | run a suite and print the dual-axis report, no gating |
| `vault demo` | the headline: green suite, then two regressions caught on two axes |
| `vault version` | print the version |

Common flags: `--runs N` (replays per scenario, default 20), `--k K`
(for `pass^k`/`pass@k`), `--seed S`. Output is colorized on a terminal and plain
when piped or under `NO_COLOR`.

---

## Architecture

trace-vault is built as **many small, immutable-data modules** (no module mutates
shared state; every update returns a new object). Six layers:

```
┌──────────────────────────────────────────────────────────────────────┐
│  cli  ·  vault gate | eval | demo | version                            │
├──────────────────────────────────────────────────────────────────────┤
│  gate     baseline diff + verdict           ledger   replay-or-fork    │
│           (exit 0/1 on regression)                   (no double-charge)│
├──────────────────────────────────────────────────────────────────────┤
│  eval     determinism (pass^k, bootstrap CI) · faithfulness (world) ·  │
│           trajectory (order-tolerant grading)                          │
├──────────────────────────────────────────────────────────────────────┤
│  cassette  normalize (scrub volatile ids/timestamps) · match modes ·   │
│            record / replay · typed DivergenceError                      │
├──────────────────────────────────────────────────────────────────────┤
│  agent    thin ReAct loop · tool registry · the assertable World       │
│           (in-process SQLite + temp filesystem)                        │
├──────────────────────────────────────────────────────────────────────┤
│  providers   LLMProvider Protocol                                      │
│              FakeProvider (CI default) · CassetteProvider (rec/replay) │
│              · Real adapters (secret-gated, never on the default path) │
└──────────────────────────────────────────────────────────────────────┘
```

| Layer | What it does |
|-------|--------------|
| **providers** | The model-agnostic seam. `FakeProvider` is scripted and prompt-hash-keyed; `CassetteProvider` records real exchanges and replays them with the network blocked; real OpenAI/Anthropic/Ollama adapters live behind optional extras so the offline path never touches them. |
| **agent** | A deliberately *thin* ReAct loop (`plan → act → observe → answer`) over a small toolset (calculator, search, files, SQLite, and one side-effecting `transfer`). The harness is the star; the agent stays minimal and replaceable. |
| **cassette** | Records each request→completion pair, normalizing a fixed allowlist of volatile fields (tool-call ids, timestamps, UUIDs). Replays with three order-tolerant **match modes** (`strict` / `unordered` / `subset`) and raises a typed `DivergenceError` (`prompt-hash` / `tool-name` / `call-order` / `arg-mismatch`) the instant a trajectory drifts. |
| **eval** | The two axes. **Determinism**: `pass^k` + `pass@k` over N replays with a seeded bootstrap CI and a min-runs power hint. **Faithfulness**: outcome graders against the real SQLite + temp-fs world, plus an evidence-overlap rubric. |
| **ledger** | An irreversible-effect ledger enforcing *replay-or-fork*: on a rollback / re-run, a side-effecting `transfer` is **never re-fired** (the "don't double-charge the customer" assertion). |
| **gate** | `vault gate --baseline baseline.json` diffs both axes + trajectory metrics against a frozen baseline and exits non-zero on regression. |

See [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md) for the full design and the
data-flow walkthrough.

---

## What's deliberately *in* and *out* of scope

**In:** the reliability harness — record/replay, divergence detection, dual-axis
scoring with honest statistics, an effect ledger, and a CI gate.

**Out:** being a general agent framework. The agent loop is intentionally ~150
lines so the harness is the contribution, not the agent.

---

## Results

The reference suite covers all four determinism × faithfulness quadrants plus a
security scenario. Every number below is produced offline and reproduced by
`vault eval --full` on each CI run — full table and interpretation in
[`docs/RESULTS.md`](./docs/RESULTS.md).

The headline, from one flaky scenario over 20 replays:

| scenario | determinism | pass^5 | pass@5 | faithfulness |
|----------|:-----------:|:------:|:------:|:------------:|
| `report.flaky_plan`        | **0.60** | **0.051** | 0.996 | 1.00 |
| `booking.unfaithful_write` | 1.00 | 1.000 | 1.000 | **0.00** |

* `report.flaky_plan` — **reproducibly broken**: `pass@5` (0.996) looks healthy
  while `pass^5` (0.051) exposes the flake. Caught by *determinism*.
* `booking.unfaithful_write` — **reliably wrong**: every replay is identical and
  every replay leaves the real table empty. Caught by *faithfulness*.

Determinism and faithfulness are uncorrelated here by construction — which is
exactly why they are gated separately.

---

## 中文说明

**trace-vault** 是一个面向「工具调用型 Agent」的**录制/回放可靠性闸门**。

核心理念：**可复现 ≠ 可信**（Determinism ≠ Faithfulness）。一个 Agent 可以每次都走
完全相同的轨迹，却每次都做错事；也可能靠运气做对了一次、却无法复现。把这两件事
压成一个分数，恰好会掩盖真正会在生产环境咬你的那种失败。

trace-vault 把一次真实运行录制成**归一化的 cassette**（剥离 tool-call id、时间戳、
UUID 等易变字段），随后整套测试都通过一个**确定性的 FakeProvider 离线回放** ——
不需要任何 API key、网络在回放期被禁用。它在 CI 上**独立地**度量并卡两条轴：

- **确定性（Determinism）**：N 次回放轨迹是否一致 —— 用 `pass^k` / `pass@k` +
  自助法置信区间 + 最小运行次数提示，抵御温度噪声。
- **可信度（Faithfulness）**：运行是否**真的**改变了世界 —— 断言真实的 SQLite 行与
  临时文件系统状态（而非转录文本），并配合确定性的证据重合度评分。

外加四个有界增量：轨迹评分、不可逆副作用账本（回滚不重复扣款）、一个 OWASP 风格的
「工具输出投毒」场景，以及可选的 OpenTelemetry 内存 span 断言。

一句话总结：**「我让不确定的 Agent 变得可复现、可进 CI 闸门，并证明了——光有确定性
并不等于正确。」**

---

## Repository layout

```
src/trace_vault/
  schemas/        immutable Pydantic models (messages, cassette, transcript, …)
  providers/      LLMProvider seam: fake, cassette (record/replay), real
  agent/          thin ReAct loop, toolset, the assertable World
  cassette/       normalize, match modes, store, divergence
  eval/           determinism, faithfulness, trajectory, stats
  ledger/         irreversible-effect ledger (replay-or-fork)
  gate/           baseline diff + verdict + report rendering
  observability/  in-memory tracer (+ optional OTel adapter)
  suite/          the reference scenarios
  cli.py          the `vault` command
tests/            unit / integration / e2e  (all offline)
docs/             ARCHITECTURE.md, RESULTS.md
examples/         baseline.json, a sample recorded cassette
```

## License

MIT © 2026 Beamus Wayne

