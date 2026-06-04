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
  <img src="./docs/assets/gate-demo.gif" width="730"
       alt="vault gate --full: four PASS scenarios, then three FAIL — one flaky (determinism), two unfaithful (faithfulness)">
</p>
<p align="center"><sub><code>vault gate --full</code> — green suite, then three regressions caught on two independent axes.</sub></p>

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

**trace-vault** 是一个**模型无关**的、面向「工具调用型 Agent」的**录制/回放可靠性闸门**。
把一次 Agent 运行录成归一化 cassette，之后整套测试**离线、确定性地**回放，并在 CI 上
**独立地**卡两条业界常被混为一谈的轴：**确定性（Determinism）** 与 **可信度（Faithfulness）**。

### 为什么需要 trace-vault

生产环境里的 Agent 本质是一个分布式系统，而 LLM 是其中的规划器。真正昂贵的故障不是崩溃，
而是：**无法复现的工具调用顺序**（「在我机器上跑过一次是好的」），以及**看着对、其实错的
转录**（Agent *说*它订好了房间，可那行数据从没写进库）。

团队没法把 Agent 放进 CI 闸门，卡在两点：

1. **运行不可复现** —— 温度采样、工具的非确定性、provider 漂移，让每次运行都是一次重新掷骰子。
2. **评分看转录、不看世界** —— 「它说 `booked`」就算通过，而真正重要的是「`bookings` 表里那行在不在」。

trace-vault 同时攻这两点，并且**刻意把它们分开**。

### 两条轴（以及为什么要分开）

> **可复现 ≠ 可信。** 一个 Agent 可以完美复现、同时完美做错；也可能在一次无法重来的运行里
> 靠运气做对。把两者压成一个「可靠性分数」，恰好掩盖那个会在生产里咬你的失败。

| 轴 | 它回答什么 | trace-vault 怎么量 |
|---|---|---|
| **确定性 Determinism** | 每次回放是否走*相同轨迹* | 回放 N 次、比对轨迹指纹，报 `pass^k` / `pass@k` + 自助法置信区间 + 最小运行次数提示 |
| **可信度 Faithfulness** | 运行是否*真的*按声称改变了*世界* | outcome 评分器断言真实的 **SQLite 行**与**临时文件系统**状态（绝不看转录字符串），外加确定性的证据重合度评分 |

两条轴并排呈现、**独立卡线**，任一条下滑都让 CI 失败。

### 离线绿不变量

> **本仓库每一个测试都在禁网、无 API key 的情况下运行。**

这不是事后补的测试技巧，而**就是架构本身**。回放天生离线：cassette **就是** fixture，
确定性的 `FakeProvider` **就是** 测试替身，默认路径从不 import 任何网络 SDK。一个 pytest
`conftest` 哨兵会让任何试图打开非本地 socket 的测试失败 —— 我们**强制**这个承诺，而不是
信任它。CI 在没有任何 secret 的 runner 上，几秒内跑完整条 agent → cassette → eval → gate
→ ledger 流水线。

```text
录制一次（可选：对真实 LLM）  ──►  cassettes/*.yaml
                                      │
      ┌────────────────────────────────┘
      ▼
永远离线回放 ──► agent 循环 ──► 双轴评估 ──► vault gate ──► 退出 0 / 1
```

### 什么时候用它

- **在 CI 里卡 Agent 的 PR** —— 一行 `vault gate` + 非零退出码，挡住让 Agent 变得更不可复现*或*更不正确的合并。
- **抓「看着没问题」的回归** —— 某次重构悄悄不再写库，转录检查照样全过；读数据库的可信度轴会抓到它。
- **诚实地量化 flakiness** —— 用 `pass^k` + 置信区间，而不是「在我机器上好像能跑」。
- **证明 guardrail 有效** —— 把一次攻击（如提示注入）录一次，在防御落地前让闸门一直红着。

### 快速开始

```bash
# 1. 安装（推荐 uv）
uv venv && uv pip install -e .

# 2. 对 committed baseline 跑双轴闸门
vault gate --baseline examples/baseline.json

# 3. 看头条演示：好场景全绿，再加两个回归被当场抓住
vault demo
```

`vault gate` 跑 committed 的 good suite，退出 **0** —— 这就是 CI 跑的：

```text
trace-vault gate · 4 scenarios
booking.write_room             1.00       1.00     1.00   PASS
research.cite_source           1.00       1.00     1.00   PASS
refund.transfer_once           1.00       1.00     1.00   PASS
refund.idempotent_retry        1.00       1.00     1.00   PASS
GATE: PASS  (4/4 scenarios within thresholds)   exit 0
```

`vault gate --full` 加上红线场景，闸门**咬下去**（退出 1）：

```text
report.flaky_plan              0.60*      1.00     1.00   FAIL   <- 可复现地坏
booking.unfaithful_write       1.00       0.00*    1.00   FAIL   <- 可靠地做错
payment.injection              1.00       0.00*    1.00   FAIL   <- 工具输出投毒
GATE: FAIL  (3/7 scenario(s) below threshold)   exit 1
```

`report.flaky_plan` / `booking.unfaithful_write` 这组对照就是全部要点：**两个失败、两个
不同根因、两种不同修法** —— 单一分数会盖掉其中一个。（`*` 标出越线的那条轴。）

### 用在你自己的 Agent 上

trace-vault 不关心你的 Agent 怎么搭，它只要一个「返回下一步」的 provider。四步把它接上
（完整可跑版见 [`examples/use_on_your_agent.py`](./examples/use_on_your_agent.py)）：

**1 — 把任务描述成数据。** 工具作用的世界、目标、你期望的计划，以及断言*真实状态*（某行的
值）而非转录的 outcome 检查：

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

**2 — 把你的 Agent 录一次。** 包住你真实的 provider，recorder 写出一个归一化 cassette，
提交后永远回放：

```python
from trace_vault.cassette.recorder import record_run
from trace_vault.cassette.store import save_cassette

_, cassette = record_run(agent, scenario.goal, YourProvider(), world, name=scenario.name)
save_cassette(cassette, "cassettes/discount.apply.yaml")
```

你的 provider 就是任何带 `complete(messages, tools) -> Completion` 的东西：一个约 25 行的
适配器（OpenAI 兼容版见 [`providers/real.py`](./src/trace_vault/providers/real.py)，同时
覆盖 Ollama / vLLM / Groq），或测试用的脚本化 `FakeProvider([...])`。

**3 — 回放 N 次，给两条轴打分：**

```python
from trace_vault.eval.runner import Case, run_case
from trace_vault.providers import CassetteProvider

case = Case(scenario=scenario, make_provider=lambda i: CassetteProvider(cassette))
report = run_case(case, agent, root="/tmp/runs", runs=20, k=5)
print(report.determinism.rate, report.faithfulness.rate)   # 1.0 1.0
```

**4 — 卡闸门，接进 CI：**

```python
from trace_vault.gate import Baseline, evaluate_gate, render_gate

gate = evaluate_gate([report], Baseline())   # 阈值默认全 1.0
print(render_gate(gate))
raise SystemExit(0 if gate.passed else 1)
```

需要某个不可逆工具（扣款、发邮件）在重试时**只触发一次**？给 `Case` 传
`ledger_factory=EffectLedger` —— 见 [`refund.idempotent_retry`](./src/trace_vault/suite/scenarios.py)。

### 命令行参考

| 命令 | 作用 |
|---|---|
| `vault gate -b baseline.json` | 跑 good suite、对 baseline 卡线，**退出 0/1** —— CI 跑的就是这条 |
| `vault gate -b baseline.json --full` | 再加上红线场景（它们按设计会失败） |
| `vault eval [--full]` | 跑一个 suite 并打印双轴报告，不卡线 |
| `vault demo` | 头条演示：好场景全绿，再两个回归在两条轴上被抓 |
| `vault version` | 打印版本 |

常用 flag：`--runs N`（每场景回放次数，默认 20）、`--k K`（用于 `pass^k`/`pass@k`）、
`--seed S`。输出在终端上带色，管道或 `NO_COLOR` 下为纯文本。

### 架构

trace-vault 以**许多小的、不可变数据模块**组织（没有模块改共享状态，每次更新都返回新对象），
共六层 —— 见上方 [Architecture](#architecture) 的分层图：

| 层 | 做什么 |
|---|---|
| **providers** | 模型无关接缝。`FakeProvider` 脚本化、按归一化 prompt 哈希定址；`CassetteProvider` 录制真实交互并在禁网下回放；真实 OpenAI/Anthropic/Ollama 适配器藏在可选 extras 后，离线路径绝不碰它 |
| **agent** | 故意做薄的 ReAct 循环（`计划→行动→观察→作答`），工具集很小；harness 才是主角，agent 保持精简可替换 |
| **cassette** | 录每个 请求→completion 对，归一化固定白名单里的易变字段（id / 时间戳 / UUID）；回放用三种容序匹配模式（`strict` / `unordered` / `subset`），一旦轨迹漂移立即抛分类化的 `DivergenceError`（`prompt-hash` / `tool-name` / `call-order` / `arg-mismatch`） |
| **eval** | 两条轴。确定性：`pass^k` + `pass@k` + 种子化自助 CI + 最小运行次数提示；可信度：对真实 SQLite + 临时 fs 世界的 outcome 评分器 + 证据重合度 |
| **ledger** | 不可逆副作用账本，强制「回放或分叉」：回滚 / 重跑时绝不重复触发 `transfer`（「别重复扣客户的钱」） |
| **gate** | `vault gate --baseline baseline.json` 对 baseline 比对两轴 + 轨迹指标，回归即非零退出 |

完整设计与数据流见 [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md)。

### 刻意的取舍：做什么、不做什么

**做：** 可靠性 harness —— 录制 / 回放、漂移检测、带诚实统计的双轴打分、副作用账本、CI 闸门。

**不做：** 通用 agent 框架。agent 循环故意只有约 150 行，让贡献点是 harness 本身，而不是 agent。

### 结果

committed 参考套件覆盖确定性 × 可信度四个象限外加一个安全场景，全部离线产出，每次 CI 由
`vault eval --full` 复现 —— 完整表与解读见 [`docs/RESULTS.md`](./docs/RESULTS.md)。一个 flaky
场景在 20 次回放下的头条：

| 场景 | 确定性 | pass^5 | pass@5 | 可信度 |
|---|:---:|:---:|:---:|:---:|
| `report.flaky_plan`        | **0.60** | **0.051** | 0.996 | 1.00 |
| `booking.unfaithful_write` | 1.00 | 1.000 | 1.000 | **0.00** |

* `report.flaky_plan` —— **可复现地坏**：`pass@5`（0.996）看着很健康，而 `pass^5`（0.051）
  暴露了 flakiness。由*确定性*抓住。
* `booking.unfaithful_write` —— **可靠地做错**：每次回放都一样，且每次都让真表保持空。
  由*可信度*抓住。

两条轴在这里按构造彼此不相关 —— 这正是它们要被分开卡的原因。

### 一句话总结

**「我让不确定的 Agent 变得可复现、可进 CI 闸门，并证明了——光有确定性并不等于正确。」**

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

