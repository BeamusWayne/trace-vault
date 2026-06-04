<div align="center">

# trace-vault

Record a tool-using agent's run once, replay it offline, and gate CI on two
separate scores: whether the agent repeats the same trajectory (determinism) and
whether it actually changed the world it claimed to (faithfulness).

[![CI](https://github.com/BeamusWayne/trace-vault/actions/workflows/ci.yml/badge.svg)](https://github.com/BeamusWayne/trace-vault/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](./LICENSE)

[English](#why) · [中文说明](#中文说明)

</div>

<p align="center">
  <img src="./docs/assets/gate-demo.gif" width="730"
       alt="vault gate --full: four scenarios pass, three fail on two different scores">
</p>
<p align="center"><sub><code>vault gate --full</code>: four scenarios pass, three fail on two different scores.</sub></p>

---

## Why

Putting an agent behind a CI gate is hard for two reasons:

1. Runs aren't reproducible. Temperature, tool nondeterminism, and provider
   changes make each run different.
2. Graders usually check the transcript ("it said `booked`") instead of the
   world ("the `bookings` row exists").

trace-vault handles both, and keeps the two concerns as separate scores.

### The two scores

An agent can be perfectly reproducible and still wrong. It can also be right once
on a run it can't repeat. A single combined "reliability" number hides one of
those cases, so the two are measured and gated independently.

| Score | Question | How it's measured |
|-------|----------|-------------------|
| Determinism | Same trajectory on every replay? | Replay N times, compare trajectory fingerprints. Report `pass^k` / `pass@k` with a bootstrap CI and a min-runs hint. |
| Faithfulness | Did the run change the world as claimed? | Outcome checks against real SQLite rows and temp files, not transcript text, plus an evidence-overlap check on the answer. |

## No network, no keys

Every test runs with the network blocked and no API key. Replay is offline by
construction: the cassette is the fixture, `FakeProvider` is the test double, and
the default code path never imports a network client. A `conftest` fixture fails
any test that opens a non-local socket, so the rule is enforced rather than
assumed. CI runs the whole pipeline (agent, cassette, eval, gate, ledger) in a
few seconds with no secrets.

```text
record once (optionally against a real LLM)  ->  cassettes/*.yaml
                                                      |
        +----------------------------------------------+
        v
replay offline -> agent loop -> dual-score eval -> vault gate -> exit 0 / 1
```

## Use cases

- Gate an agent PR in CI: fail a merge that makes the agent less reproducible or
  less correct, with one `vault gate` call and a non-zero exit code.
- Catch regressions that still pass transcript checks: a refactor that quietly
  stops writing a row still "looks done"; the faithfulness score reads the
  database and catches it.
- Quantify flakiness: `pass^k` and a confidence interval instead of "works on my
  machine".
- Check a guardrail: record an attack such as prompt injection once, and keep the
  gate red until the defense lands.

## Quickstart

```bash
# 1. install (uv recommended)
uv venv && uv pip install -e .

# 2. run the dual-score gate against the committed baseline
vault gate --baseline examples/baseline.json

# 3. run the demo: the good suite passes, then two regressions get caught
vault demo
```

`vault gate` runs the committed good suite and exits 0. This is what CI runs:

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

`vault gate --full` adds the red-path scenarios and exits 1:

```text
scenario                     determ.  faithful.    traj.  verdict
-----------------------------------------------------------------
...
report.flaky_plan              0.60*      1.00     1.00   FAIL
booking.unfaithful_write       1.00       0.00*    1.00   FAIL
payment.injection              1.00       0.00*    1.00   FAIL

GATE: FAIL  (3/7 scenario(s) below threshold)   exit 1
```

The first two fail for different reasons. `report.flaky_plan` is reproducible but
takes different paths across runs; `booking.unfaithful_write` repeats the same
path every time but never writes the row. They fail on different scores, so a
single number would have hidden one of them. (`*` marks the score that fell below
threshold.)

## Using it on your own agent

trace-vault only needs a provider that returns the next step, so it doesn't care
how your agent is built. The four steps below are the whole workflow; the full
runnable version is [`examples/use_on_your_agent.py`](./examples/use_on_your_agent.py).

1. Describe the task as data: the world your tools act on, the goal, the plan you
   expect, and outcome checks that read real state (a row's value) instead of the
   transcript.

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

2. Record your agent once. Wrap your real provider; the recorder writes a
   normalized cassette you commit and replay later.

```python
from trace_vault.cassette.recorder import record_run
from trace_vault.cassette.store import save_cassette

_, cassette = record_run(agent, scenario.goal, YourProvider(), world, name=scenario.name)
save_cassette(cassette, "cassettes/discount.apply.yaml")
```

A provider is anything with `complete(messages, tools) -> Completion`: a ~25-line
adapter (see [`providers/real.py`](./src/trace_vault/providers/real.py) for an
OpenAI-compatible one that also covers Ollama, vLLM, and Groq), or a scripted
`FakeProvider([...])` for tests.

3. Replay N times and score both axes.

```python
from trace_vault.eval.runner import Case, run_case
from trace_vault.providers import CassetteProvider

case = Case(scenario=scenario, make_provider=lambda i: CassetteProvider(cassette))
report = run_case(case, agent, root="/tmp/runs", runs=20, k=5)
print(report.determinism.rate, report.faithfulness.rate)   # 1.0 1.0
```

4. Gate it, and wire it into CI.

```python
from trace_vault.gate import Baseline, evaluate_gate, render_gate

gate = evaluate_gate([report], Baseline())   # thresholds default to 1.0
print(render_gate(gate))
raise SystemExit(0 if gate.passed else 1)
```

If a tool has an irreversible side effect (a charge, an email) that should fire
once even on a retry, pass `ledger_factory=EffectLedger` to the `Case`. See
[`refund.idempotent_retry`](./src/trace_vault/suite/scenarios.py).

## CLI

| command | what it does |
|---------|--------------|
| `vault gate -b baseline.json` | run the good suite, compare to the baseline, exit 0/1; this is what CI runs |
| `vault gate -b baseline.json --full` | also include the red-path scenarios, which are expected to fail |
| `vault eval [--full]` | run a suite and print the report, without gating |
| `vault demo` | run the good suite, then the full suite, to show both scores |
| `vault version` | print the version |

Common flags: `--runs N` (replays per scenario, default 20), `--k K` (for
`pass^k` / `pass@k`), `--seed S`. Output is colorized on a terminal and plain when
piped or under `NO_COLOR`.

## Architecture

Each layer is immutable data plus pure functions where it can be, and the one
stateful object (the `World`) is explicit about it. Six layers:

```
+----------------------------------------------------------------------+
|  cli  ·  vault gate | eval | demo | version                          |
+----------------------------------------------------------------------+
|  gate     baseline diff + verdict           ledger   replay-or-fork   |
|           (exit 0/1 on regression)                   (fire once)      |
+----------------------------------------------------------------------+
|  eval     determinism (pass^k, bootstrap CI) · faithfulness (world)  |
|           · trajectory (order-tolerant grading)                      |
+----------------------------------------------------------------------+
|  cassette  normalize · match modes · record / replay · DivergenceError|
+----------------------------------------------------------------------+
|  agent    ReAct loop · tool registry · the assertable World          |
|           (in-process SQLite + temp filesystem)                      |
+----------------------------------------------------------------------+
|  providers   LLMProvider Protocol                                    |
|              FakeProvider · CassetteProvider · real (secret-gated)   |
+----------------------------------------------------------------------+
```

| Layer | What it does |
|-------|--------------|
| providers | The model-agnostic seam. `FakeProvider` is scripted and keyed by a normalized prompt hash; `CassetteProvider` records real exchanges and replays them with no network; real OpenAI/Anthropic/Ollama adapters live behind optional extras and stay off the default path. |
| agent | A small ReAct loop (plan, act, observe, answer) over a short toolset. The loop stays minimal so the harness is the focus and the agent is easy to swap. |
| cassette | Records each request/completion pair, normalizing a fixed allowlist of volatile fields (tool-call ids, timestamps, UUIDs). Replays with three match modes (`strict`, `unordered`, `subset`) and raises a typed `DivergenceError` (`prompt-hash`, `tool-name`, `call-order`, `arg-mismatch`) when a trajectory drifts. |
| eval | Determinism: `pass^k` / `pass@k` over N replays with a seeded bootstrap CI and a min-runs hint. Faithfulness: outcome checks against the real SQLite and temp-fs world, plus evidence overlap. |
| ledger | An irreversible-effect ledger that replays or forks, so a `transfer` is not re-run on a rollback or retry. |
| gate | `vault gate --baseline baseline.json` compares both scores and the trajectory metrics to a frozen baseline and exits non-zero on a regression. |

Full design and data flow: [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md).

## Scope

In scope: the reliability harness, namely record/replay, divergence detection,
two-score grading with honest statistics, an effect ledger, and a CI gate.

Out of scope: a general agent framework. The loop is about 150 lines so the
harness stays the contribution, not the agent.

## Results

The reference suite covers all four determinism-by-faithfulness combinations plus
one security scenario. Numbers are produced offline and reproduced by
`vault eval --full` on each CI run; the full table is in
[`docs/RESULTS.md`](./docs/RESULTS.md). One flaky scenario over 20 replays:

| scenario | determinism | pass^5 | pass@5 | faithfulness |
|----------|:-----------:|:------:|:------:|:------------:|
| `report.flaky_plan`        | 0.60 | 0.051 | 0.996 | 1.00 |
| `booking.unfaithful_write` | 1.00 | 1.000 | 1.000 | 0.00 |

`report.flaky_plan` is reproducible-broken: `pass@5` (0.996) looks healthy while
`pass^5` (0.051) shows the trajectory is a coin flip. The determinism score
catches it. `booking.unfaithful_write` is the opposite: every replay is identical
and every replay leaves the real table empty, which only the faithfulness score
catches. The two are uncorrelated here, which is why they are gated separately.

---

## 中文说明

**trace-vault** 是一个模型无关的、面向工具调用型 Agent 的录制/回放可靠性闸门。把一次
Agent 运行录成归一化 cassette，之后整套测试离线、确定性地回放，并在 CI 上分别卡两个分数：
确定性（每次回放是否走相同轨迹）和可信度（运行是否真的按声称改变了世界）。

### 为什么

把 Agent 放进 CI 闸门有两个难点：

1. 运行不可复现。温度采样、工具的非确定性、provider 变更，让每次运行都不一样。
2. 评分通常看转录（「它说 `booked`」），而不看世界（「`bookings` 表里那行在不在」）。

trace-vault 同时处理这两点，并把它们拆成两个独立的分数。

### 两个分数

一个 Agent 可以每次都完全复现，却每次都做错；也可能在一次无法重来的运行里靠运气做对。
把两者合成一个「可靠性」分数会盖掉其中一种情况，所以它们被分开度量、分开卡线。

| 分数 | 它回答什么 | 怎么量 |
|------|-----------|--------|
| 确定性 Determinism | 每次回放是否走相同轨迹 | 回放 N 次、比对轨迹指纹，报 `pass^k` / `pass@k`，附自助法置信区间和最小运行次数提示 |
| 可信度 Faithfulness | 运行是否真的按声称改变了世界 | 对真实的 SQLite 行和临时文件做 outcome 检查（不看转录文本），再加一个对答案的证据重合度检查 |

### 禁网、无 key

每个测试都在禁网、无 API key 下运行。回放天生离线：cassette 就是 fixture，`FakeProvider`
就是测试替身，默认路径不 import 任何网络客户端。一个 `conftest` fixture 会让任何打开非本地
socket 的测试失败，所以这条规则是被强制的，而不是靠信任。CI 在没有任何 secret 的情况下，
几秒内跑完整条流水线（agent、cassette、eval、gate、ledger）。

```text
录制一次（可选：对真实 LLM）  ->  cassettes/*.yaml
                                      |
      +--------------------------------+
      v
离线回放 -> agent 循环 -> 双分数评估 -> vault gate -> 退出 0 / 1
```

### 使用场景

- 在 CI 里卡 Agent 的 PR：让一次使 Agent 更不可复现、或更不正确的合并失败，一行 `vault gate`
  加非零退出码即可。
- 抓住那些仍能通过转录检查的回归：某次重构悄悄不再写库，看着还是「做完了」，可信度分数读
  数据库就能抓到。
- 量化 flakiness：用 `pass^k` 加置信区间，而不是「在我机器上能跑」。
- 检查 guardrail：把一次攻击（比如提示注入）录一次，在防御落地前让闸门一直红着。

### 快速开始

```bash
# 1. 安装（推荐 uv）
uv venv && uv pip install -e .

# 2. 对 committed baseline 跑双分数闸门
vault gate --baseline examples/baseline.json

# 3. 跑演示：好场景通过，再加两个回归被抓住
vault demo
```

`vault gate` 跑 committed 的 good suite，退出 0，这就是 CI 跑的：

```text
trace-vault gate · 4 scenarios
booking.write_room             1.00       1.00     1.00   PASS
research.cite_source           1.00       1.00     1.00   PASS
refund.transfer_once           1.00       1.00     1.00   PASS
refund.idempotent_retry        1.00       1.00     1.00   PASS
GATE: PASS  (4/4 scenarios within thresholds)   exit 0
```

`vault gate --full` 加上红线场景，退出 1：

```text
report.flaky_plan              0.60*      1.00     1.00   FAIL
booking.unfaithful_write       1.00       0.00*    1.00   FAIL
payment.injection              1.00       0.00*    1.00   FAIL
GATE: FAIL  (3/7 scenario(s) below threshold)   exit 1
```

前两个失败的原因不同：`report.flaky_plan` 能复现，但每次走不同路径；`booking.unfaithful_write`
每次走相同路径，却从不写那行。它们栽在不同的分数上，单一数字会盖掉其中一个。（`*` 标出越线
的那个分数。）

### 用在你自己的 Agent 上

trace-vault 只要一个「返回下一步」的 provider，不关心你的 Agent 怎么搭。下面四步就是全部流程；
完整可跑版见 [`examples/use_on_your_agent.py`](./examples/use_on_your_agent.py)。

1. 把任务描述成数据：工具作用的世界、目标、你期望的计划，以及读取真实状态（某行的值）、
   而不是读转录的 outcome 检查。

```python
from trace_vault.schemas import Scenario, WorldSpec, ExpectedToolCall, OutcomeCheck

scenario = Scenario(
    name="discount.apply",
    goal="给订单 1001（原价 200）打 8 折并写回新总额。",
    world=WorldSpec(sql_setup=("CREATE TABLE order_totals (id INTEGER, total REAL);",)),
    expected_tools=(ExpectedToolCall(name="calculator"), ExpectedToolCall(name="db_insert")),
    outcome_checks=(OutcomeCheck(
        kind="db_value_equals",
        params={"table": "order_totals", "column": "total",
                "where": {"id": 1001}, "expected": 160.0}),),
    evidence=("160",),
)
```

2. 把你的 Agent 录一次。包住你真实的 provider，recorder 写出一个归一化 cassette，提交后回放。

```python
from trace_vault.cassette.recorder import record_run
from trace_vault.cassette.store import save_cassette

_, cassette = record_run(agent, scenario.goal, YourProvider(), world, name=scenario.name)
save_cassette(cassette, "cassettes/discount.apply.yaml")
```

provider 就是任何带 `complete(messages, tools) -> Completion` 的东西：一个约 25 行的适配器
（OpenAI 兼容版见 [`providers/real.py`](./src/trace_vault/providers/real.py)，同样覆盖 Ollama、
vLLM、Groq），或测试用的脚本化 `FakeProvider([...])`。

3. 回放 N 次，给两个分数打分。

```python
from trace_vault.eval.runner import Case, run_case
from trace_vault.providers import CassetteProvider

case = Case(scenario=scenario, make_provider=lambda i: CassetteProvider(cassette))
report = run_case(case, agent, root="/tmp/runs", runs=20, k=5)
print(report.determinism.rate, report.faithfulness.rate)   # 1.0 1.0
```

4. 卡闸门，接进 CI。

```python
from trace_vault.gate import Baseline, evaluate_gate, render_gate

gate = evaluate_gate([report], Baseline())   # 阈值默认全 1.0
print(render_gate(gate))
raise SystemExit(0 if gate.passed else 1)
```

如果某个工具有不可逆的副作用（扣款、发邮件），希望它在重试时也只触发一次，给 `Case` 传
`ledger_factory=EffectLedger`，见 [`refund.idempotent_retry`](./src/trace_vault/suite/scenarios.py)。

### 命令行

| 命令 | 作用 |
|------|------|
| `vault gate -b baseline.json` | 跑 good suite、对 baseline 比对，退出 0/1，CI 跑的就是这条 |
| `vault gate -b baseline.json --full` | 再加上红线场景（按设计会失败） |
| `vault eval [--full]` | 跑一个 suite 并打印报告，不卡线 |
| `vault demo` | 先跑 good suite，再跑 full suite，展示两个分数 |
| `vault version` | 打印版本 |

常用 flag：`--runs N`（每场景回放次数，默认 20）、`--k K`（用于 `pass^k`/`pass@k`）、`--seed S`。
输出在终端上带色，管道或 `NO_COLOR` 下为纯文本。

### 架构

每一层尽量是不可变数据加纯函数，唯一的有状态对象（`World`）也明确标出。共六层，分层图见上方
[Architecture](#architecture)。

| 层 | 做什么 |
|----|--------|
| providers | 模型无关接缝。`FakeProvider` 脚本化、按归一化 prompt 哈希定址；`CassetteProvider` 录制真实交互并在无网络下回放；真实 OpenAI/Anthropic/Ollama 适配器在可选 extras 后，留在默认路径之外。 |
| agent | 一个小的 ReAct 循环（计划、行动、观察、作答），工具集很短。循环保持精简，让 harness 是重点、agent 易替换。 |
| cassette | 录每个 请求/completion 对，归一化固定白名单里的易变字段（tool-call id、时间戳、UUID）。回放用三种匹配模式（`strict`、`unordered`、`subset`），轨迹漂移时抛分类化的 `DivergenceError`（`prompt-hash`、`tool-name`、`call-order`、`arg-mismatch`）。 |
| eval | 确定性：N 次回放的 `pass^k`/`pass@k`，附种子化自助 CI 和最小运行次数提示。可信度：对真实 SQLite 和临时 fs 世界的 outcome 检查，加证据重合度。 |
| ledger | 不可逆副作用账本，回放或分叉，使 `transfer` 在回滚或重试时不被重跑。 |
| gate | `vault gate --baseline baseline.json` 把两个分数和轨迹指标与冻结的 baseline 比对，回归即非零退出。 |

完整设计与数据流见 [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md)。

### 范围

做：可靠性 harness，即录制/回放、漂移检测、带诚实统计的双分数打分、副作用账本、CI 闸门。

不做：通用 agent 框架。循环约 150 行，让 harness 是贡献本身，而不是 agent。

### 结果

参考套件覆盖确定性与可信度的全部四种组合，外加一个安全场景。数字离线产出，每次 CI 由
`vault eval --full` 复现，完整表见 [`docs/RESULTS.md`](./docs/RESULTS.md)。一个 flaky 场景在
20 次回放下：

| 场景 | 确定性 | pass^5 | pass@5 | 可信度 |
|------|:------:|:------:|:------:|:------:|
| `report.flaky_plan`        | 0.60 | 0.051 | 0.996 | 1.00 |
| `booking.unfaithful_write` | 1.00 | 1.000 | 1.000 | 0.00 |

`report.flaky_plan` 能复现但坏：`pass@5`（0.996）看着健康，而 `pass^5`（0.051）显示轨迹是
抛硬币，由确定性分数抓住。`booking.unfaithful_write` 相反：每次回放都一样、且每次都让真表
保持空，只有可信度分数能抓。两者在这里互不相关，所以分开卡。

---

## Repository layout

```
src/trace_vault/
  schemas/        immutable Pydantic models (messages, cassette, transcript, …)
  providers/      LLMProvider seam: fake, cassette (record/replay), real
  agent/          ReAct loop, toolset, the assertable World
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
