<div align="center">

# trace-vault

A testing harness for tool-using AI agents. Record one run, replay it offline,
and fail CI when the agent stops behaving the same way or stops actually doing
what it says.

[![CI](https://github.com/BeamusWayne/trace-vault/actions/workflows/ci.yml/badge.svg)](https://github.com/BeamusWayne/trace-vault/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](./LICENSE)

[English](#what-it-does) · [中文说明](#中文说明)

</div>

<p align="center">
  <img src="./docs/assets/gate-demo.gif" width="730"
       alt="vault gate --full: four scenarios pass, three fail on two different scores">
</p>
<p align="center"><sub><code>vault gate --full</code>: four scenarios pass, three fail on two different scores.</sub></p>

---

## What it does

A tool-using agent is an LLM that decides which tools to call and in what order
to reach a goal. trace-vault records one such run, then replays the recording so
the same run can be checked repeatedly without calling a live model. On every
replay it answers two questions and fails CI if either gets worse:

1. **Determinism**: does the agent take the same path every time?
2. **Faithfulness**: did it actually change the data it claims to have changed?

The whole check runs offline, with no API key, in a few seconds.

## Why agents are hard to test

Two things get in the way of putting an agent behind a normal CI check.

**Runs aren't reproducible.** The same prompt can produce different tool calls
from one run to the next (temperature, provider updates, a tool that reads the
clock). A test that passed yesterday can fail today with no change to your code,
so teams stop trusting the test.

**The usual checks read what the agent said, not what it did.** An agent told to
book a room can reply "Booked!" without ever writing the booking to the database.
A test that searches the transcript for "Booked" passes, and the row is still
missing. This is the failure that reaches production.

trace-vault measures these as two separate scores, because they are genuinely
different problems with different fixes, and a single combined number hides one
of them.

## The two scores

| Score | Plain-language question | How it's measured |
|-------|-------------------------|-------------------|
| **Determinism** | Does the agent do the same thing every time? | Replay the recording N times and compare the sequence of tool calls. Reported as a pass rate, plus `pass^k` (the chance that *k* runs in a row all agree) and a confidence interval, so normal sampling noise isn't mistaken for a real change. |
| **Faithfulness** | Did the run really change the world, not just say so? | The tools run for real against an in-memory database and a temp folder. The check then reads that state directly: the row exists, the file holds the value. It never inspects the transcript. |

The two are independent. An agent can be perfectly reproducible and still wrong
(it reliably writes to the wrong table), or correct once on a run it can't repeat.
Gating them separately is the point of the tool.

## How it works

A run has three parts, and keeping them separate is what makes offline replay
possible.

- **Provider**: whatever produces the model's next step. In production it's a
  real LLM. In tests it's a `FakeProvider` (a fixed script) or a
  `CassetteProvider` (a recording). The agent code calls the same interface
  either way, so nothing above this layer knows which is in use.
- **Cassette**: the recording itself: the model's outputs for one run, saved as
  a YAML file with the volatile parts (randomly generated ids, timestamps, UUIDs)
  stripped out so it still matches on replay.
- **World**: an in-memory SQLite database and a temporary folder that the tools
  actually read from and write to. This is the ground truth that faithfulness
  checks against.

You record a real run once and commit the cassette. From then on the suite
replays it offline: the model is faked, but the tools run for real, so "did the
booking get written" has a real answer. If a replay ever takes a different path
than the recording, trace-vault stops with a typed error that says what changed
(a different tool, a different order, different arguments).

## Quickstart

```bash
# 1. install (uv recommended)
uv venv && uv pip install -e .

# 2. run the two-score gate against the committed baseline
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

`vault gate --full` adds three deliberately broken scenarios and exits 1:

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
takes different paths across runs, so it fails on determinism. `booking.unfaithful_write`
takes the same path every time but never writes the row, so it fails on
faithfulness. A single combined score would have hidden one of them. The `*`
marks the score that fell below its threshold.

## Using it on your own agent

trace-vault only needs a provider that returns the next step, so it works with
any agent. The four steps below are the whole workflow; the complete runnable
version is [`examples/use_on_your_agent.py`](./examples/use_on_your_agent.py).

**1. Describe the task as data.** State the starting world, the goal, the tool
calls you expect, and outcome checks that read real state (a row's value) rather
than the transcript.

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

**2. Record your agent once.** Wrap your real provider; the recorder writes a
cassette you commit and replay later.

```python
from trace_vault.cassette.recorder import record_run
from trace_vault.cassette.store import save_cassette

_, cassette = record_run(agent, scenario.goal, YourProvider(), world, name=scenario.name)
save_cassette(cassette, "cassettes/discount.apply.yaml")
```

A provider is anything with `complete(messages, tools) -> Completion`. That is
about 25 lines for an OpenAI-style API (see
[`providers/real.py`](./src/trace_vault/providers/real.py), which also covers
Ollama, vLLM, and Groq), or a scripted `FakeProvider([...])` for tests.

**3. Replay N times and score both axes.**

```python
from trace_vault.eval.runner import Case, run_case
from trace_vault.providers import CassetteProvider

case = Case(scenario=scenario, make_provider=lambda i: CassetteProvider(cassette))
report = run_case(case, agent, root="/tmp/runs", runs=20, k=5)
print(report.determinism.rate, report.faithfulness.rate)   # 1.0 1.0
```

**4. Gate it, and wire it into CI.**

```python
from trace_vault.gate import Baseline, evaluate_gate, render_gate

gate = evaluate_gate([report], Baseline())   # thresholds default to 1.0
print(render_gate(gate))
raise SystemExit(0 if gate.passed else 1)
```

If a tool has an irreversible side effect (a charge, an email) that must fire only
once even when the agent retries, pass `ledger_factory=EffectLedger` to the
`Case`. See [`refund.idempotent_retry`](./src/trace_vault/suite/scenarios.py).

## CLI

| command | what it does |
|---------|--------------|
| `vault gate -b baseline.json` | run the good suite, compare to the baseline, exit 0 or 1; this is what CI runs |
| `vault gate -b baseline.json --full` | also include the deliberately broken scenarios, which are expected to fail |
| `vault eval [--full]` | run a suite and print the report without gating |
| `vault demo` | run the good suite, then the full suite, to show both scores side by side |
| `vault version` | print the version |

Common flags: `--runs N` (replays per scenario, default 20), `--k K` (for
`pass^k` / `pass@k`), `--seed S`. Output is colored on a terminal and plain when
piped or under `NO_COLOR`.

## Architecture

Each layer is immutable data plus pure functions where it can be. The one
stateful object, the `World`, is marked as such. Six layers, top to bottom:

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
| providers | The interface every model plugs into. `FakeProvider` is a fixed script; `CassetteProvider` records real exchanges and replays them with no network; the real OpenAI/Anthropic/Ollama adapters sit behind optional extras and stay off the default path. |
| agent | A small ReAct loop (plan, act, observe, answer) over a short toolset. The loop stays minimal so the harness is the focus and the agent is easy to replace. |
| cassette | Records each request/response pair, normalizing a fixed list of volatile fields (tool-call ids, timestamps, UUIDs). Replays with three match modes (`strict`, `unordered`, `subset`) and raises a typed `DivergenceError` (`prompt-hash`, `tool-name`, `call-order`, `arg-mismatch`) when a run drifts. |
| eval | Determinism: `pass^k` / `pass@k` over N replays with a seeded bootstrap confidence interval and a hint for how many runs you actually need. Faithfulness: outcome checks against the real SQLite and temp-file state, plus an evidence-overlap check on the answer. |
| ledger | An irreversible-effect ledger. On a retry or rollback it replays the recorded result instead of running the side effect again, so a transfer fires once. |
| gate | `vault gate --baseline baseline.json` compares both scores and the trajectory metrics to a frozen baseline and exits non-zero on a regression. |

Full design and data flow: [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md).

## Scope

In scope: the reliability harness, meaning record/replay, drift detection,
two-score grading with honest statistics, an effect ledger, and a CI gate.

Out of scope: a general agent framework. The loop is about 150 lines on purpose,
so the harness is the contribution and the agent is a stand-in you can swap for
your own.

## Results

The reference suite covers all four determinism-by-faithfulness combinations plus
one security scenario. The numbers are produced offline and reproduced by
`vault eval --full` on every CI run; the full table is in
[`docs/RESULTS.md`](./docs/RESULTS.md). Here is one flaky scenario over 20 replays:

| scenario | determinism | pass^5 | pass@5 | faithfulness |
|----------|:-----------:|:------:|:------:|:------------:|
| `report.flaky_plan`        | 0.60 | 0.051 | 0.996 | 1.00 |
| `booking.unfaithful_write` | 1.00 | 1.000 | 1.000 | 0.00 |

`pass@5` is the chance that at least one of five runs matches; `pass^5` is the
chance that all five match. A flaky agent can score a healthy-looking `pass@5`
(0.996: something usually works) and a near-zero `pass^5` (0.051: it rarely works
the same way twice), and the second number is closer to what you feel in
production. `report.flaky_plan` shows exactly that gap, and the determinism score
catches it. `booking.unfaithful_write` is the opposite: every replay is identical
and every replay leaves the real table empty, which only the faithfulness score
catches. The two scores are uncorrelated here, which is why they are gated apart.

---

## 中文说明

### 这是什么

工具调用型 Agent，就是一个会自己决定调用哪些工具、按什么顺序去完成目标的 LLM。trace-vault
把这样一次运行录下来，之后回放这份录制，于是同一次运行可以反复检查，而不必再调用真实模型。
每次回放它都回答两个问题，任何一个变差就让 CI 失败：

1. **确定性（Determinism）**：Agent 每次是不是走相同的路径？
2. **可信度（Faithfulness）**：它有没有真的改动它声称改动了的数据？

整个检查离线运行，不需要 API key，几秒钟跑完。

### 为什么 Agent 难测

有两件事挡在「把 Agent 接进普通 CI」前面。

**运行不可复现。** 同一个 prompt，这次和下次可能给出不同的工具调用（温度采样、provider 更新、
某个读时钟的工具）。昨天通过的测试今天可能在代码没改的情况下失败，于是大家就不再信任这个测试。

**常规检查看的是 Agent「说了什么」，不是它「做了什么」。** 一个被要求订房的 Agent，可以回一句
「已订！」却从没把这条记录写进数据库。一个在转录里搜「已订」的测试会通过，而那行数据仍然是空的。
这正是会跑到生产环境去的那种故障。

trace-vault 把这两件事拆成两个独立的分数，因为它们是不同的问题、有不同的修法，而一个合并的
数字会盖掉其中一个。

### 两个分数

| 分数 | 大白话问题 | 怎么量 |
|------|-----------|--------|
| **确定性 Determinism** | Agent 每次是不是做同样的事 | 回放录制 N 次，比对工具调用的序列。报一个通过率，再加 `pass^k`（连续 *k* 次运行全都一致的概率）和置信区间，这样正常的采样抖动不会被当成真实变化。 |
| **可信度 Faithfulness** | 这次运行有没有真的改变世界，而不只是嘴上说 | 工具对一个内存数据库和一个临时文件夹真实执行，检查再直接读这个状态：那行在不在、文件里有没有那个值。它从不看转录。 |

两者相互独立。一个 Agent 可以完全可复现、却仍然做错（它每次都稳定地写错表），也可能在一次
无法重来的运行里靠运气做对。把它们分开卡，正是这个工具的意义。

### 工作原理

一次运行由三部分组成，把它们分开正是离线回放得以成立的原因。

- **Provider**: 产出模型「下一步」的东西。生产环境里它是真实 LLM；测试里它是 `FakeProvider`
  （一段固定脚本）或 `CassetteProvider`（一份录制）。Agent 代码调用的是同一个接口，所以这一层
  之上谁都不知道用的是哪种。
- **Cassette**: 录制本身：一次运行里模型的输出，存成 YAML 文件，并把易变部分（随机生成的 id、
  时间戳、UUID）剥掉，这样回放时仍能匹配上。
- **World（世界）**: 一个内存 SQLite 数据库加一个临时文件夹，工具真实地对它读写。这就是
  可信度检查所对照的「事实」。

你把一次真实运行录一次、提交那份 cassette，之后整套测试就离线回放它：模型是假的，但工具是真跑的，
所以「那条订房记录到底写没写」有一个真实的答案。如果某次回放走了和录制不同的路径，trace-vault 会
停下并抛出一个带类型的错误，告诉你变的是什么（换了工具、换了顺序、还是参数不同）。

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

`vault gate --full` 加上三个故意做坏的场景，退出 1：

```text
report.flaky_plan              0.60*      1.00     1.00   FAIL
booking.unfaithful_write       1.00       0.00*    1.00   FAIL
payment.injection              1.00       0.00*    1.00   FAIL
GATE: FAIL  (3/7 scenario(s) below threshold)   exit 1
```

前两个失败原因不同：`report.flaky_plan` 能复现，但每次走不同路径，所以栽在确定性上；
`booking.unfaithful_write` 每次走相同路径、却从不写那行，所以栽在可信度上。一个合并的分数会
盖掉其中一个。`*` 标出跌破阈值的那个分数。

### 用在你自己的 Agent 上

trace-vault 只需要一个「返回下一步」的 provider，所以它适用于任何 Agent。下面四步就是全部流程；
完整可跑版见 [`examples/use_on_your_agent.py`](./examples/use_on_your_agent.py)。

**1. 把任务描述成数据。** 写清初始世界、目标、你期望的工具调用，以及读取真实状态（某行的值）、
而非读转录的 outcome 检查。

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

**2. 把你的 Agent 录一次。** 包住你真实的 provider，recorder 写出一份 cassette，提交后回放。

```python
from trace_vault.cassette.recorder import record_run
from trace_vault.cassette.store import save_cassette

_, cassette = record_run(agent, scenario.goal, YourProvider(), world, name=scenario.name)
save_cassette(cassette, "cassettes/discount.apply.yaml")
```

provider 就是任何带 `complete(messages, tools) -> Completion` 的东西。对一个 OpenAI 风格的 API，
这大约是 25 行（见 [`providers/real.py`](./src/trace_vault/providers/real.py)，它同样覆盖 Ollama、
vLLM、Groq），或者测试用的脚本化 `FakeProvider([...])`。

**3. 回放 N 次，给两个分数打分。**

```python
from trace_vault.eval.runner import Case, run_case
from trace_vault.providers import CassetteProvider

case = Case(scenario=scenario, make_provider=lambda i: CassetteProvider(cassette))
report = run_case(case, agent, root="/tmp/runs", runs=20, k=5)
print(report.determinism.rate, report.faithfulness.rate)   # 1.0 1.0
```

**4. 卡闸门，接进 CI。**

```python
from trace_vault.gate import Baseline, evaluate_gate, render_gate

gate = evaluate_gate([report], Baseline())   # 阈值默认全 1.0
print(render_gate(gate))
raise SystemExit(0 if gate.passed else 1)
```

如果某个工具有不可逆的副作用（扣款、发邮件），即使 Agent 重试也必须只触发一次，给 `Case` 传
`ledger_factory=EffectLedger`，见 [`refund.idempotent_retry`](./src/trace_vault/suite/scenarios.py)。

### 命令行

| 命令 | 作用 |
|------|------|
| `vault gate -b baseline.json` | 跑 good suite、对 baseline 比对，退出 0 或 1，CI 跑的就是这条 |
| `vault gate -b baseline.json --full` | 再加上故意做坏的场景（按设计会失败） |
| `vault eval [--full]` | 跑一个 suite 并打印报告，不卡线 |
| `vault demo` | 先跑 good suite，再跑 full suite，把两个分数并排展示 |
| `vault version` | 打印版本 |

常用 flag：`--runs N`（每场景回放次数，默认 20）、`--k K`（用于 `pass^k`/`pass@k`）、`--seed S`。
输出在终端上带色，管道或 `NO_COLOR` 下为纯文本。

### 架构

每一层尽量是不可变数据加纯函数，唯一的有状态对象 `World` 也明确标出。共六层，分层图见上方
[Architecture](#architecture)。

| 层 | 做什么 |
|----|--------|
| providers | 每个模型接入的接口。`FakeProvider` 是固定脚本；`CassetteProvider` 录制真实交互并在无网络下回放；真实的 OpenAI/Anthropic/Ollama 适配器在可选 extras 后，留在默认路径之外。 |
| agent | 一个小的 ReAct 循环（计划、行动、观察、作答），工具集很短。循环保持精简，让 harness 是重点、agent 易替换。 |
| cassette | 录每个 请求/响应 对，归一化一份固定的易变字段清单（tool-call id、时间戳、UUID）。回放用三种匹配模式（`strict`、`unordered`、`subset`），运行漂移时抛带类型的 `DivergenceError`（`prompt-hash`、`tool-name`、`call-order`、`arg-mismatch`）。 |
| eval | 确定性：N 次回放的 `pass^k`/`pass@k`，附种子化的自助置信区间，以及一个「你到底需要跑多少次」的提示。可信度：对真实 SQLite 和临时文件状态的 outcome 检查，加对答案的证据重合度检查。 |
| ledger | 不可逆副作用账本。重试或回滚时，它回放已记录的结果、而不是再跑一遍副作用，于是一笔 transfer 只触发一次。 |
| gate | `vault gate --baseline baseline.json` 把两个分数和轨迹指标与冻结的 baseline 比对，回归即非零退出。 |

完整设计与数据流见 [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md)。

### 范围

做：可靠性 harness，即录制/回放、漂移检测、带诚实统计的双分数打分、副作用账本、CI 闸门。

不做：通用 agent 框架。循环刻意只有约 150 行，所以贡献点是 harness，agent 只是一个你可以替换成
自己实现的占位。

### 结果

参考套件覆盖确定性与可信度的全部四种组合，外加一个安全场景。数字离线产出，每次 CI 由
`vault eval --full` 复现，完整表见 [`docs/RESULTS.md`](./docs/RESULTS.md)。一个 flaky 场景在
20 次回放下：

| 场景 | 确定性 | pass^5 | pass@5 | 可信度 |
|------|:------:|:------:|:------:|:------:|
| `report.flaky_plan`        | 0.60 | 0.051 | 0.996 | 1.00 |
| `booking.unfaithful_write` | 1.00 | 1.000 | 1.000 | 0.00 |

`pass@5` 是「五次里至少一次一致」的概率；`pass^5` 是「五次全都一致」的概率。一个 flaky 的 Agent
可以有好看的 `pass@5`（0.996：总有一次能成）和接近零的 `pass^5`（0.051：很少有两次走得一样），
而后一个数字更接近你在生产里的真实体感。`report.flaky_plan` 正是这种落差，确定性分数抓住了它。
`booking.unfaithful_write` 相反：每次回放都一样、且每次都让真表保持空，只有可信度分数能抓。两个
分数在这里互不相关，所以要分开卡。

---

## Repository layout

```
src/trace_vault/
  schemas/        immutable Pydantic models (messages, cassette, transcript, …)
  providers/      LLMProvider interface: fake, cassette (record/replay), real
  agent/          ReAct loop, toolset, the assertable World
  cassette/       normalize, match modes, store, divergence
  eval/           determinism, faithfulness, trajectory, stats
  ledger/         irreversible-effect ledger (replay-or-fork)
  gate/           baseline diff + verdict + report rendering
  observability/  in-memory tracer (+ optional OpenTelemetry adapter)
  suite/          the reference scenarios
  cli.py          the `vault` command
tests/            unit / integration / e2e  (all offline)
docs/             ARCHITECTURE.md, RESULTS.md
examples/         baseline.json, a sample recorded cassette
```

## License

MIT © 2026 Beamus Wayne
