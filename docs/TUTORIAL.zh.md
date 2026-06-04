# 教程：你的第一个可靠性检查

[English](./TUTORIAL.md) · 中文

约十分钟，全程离线，无需 API key。读完你将写出一个任务、在两条轴上给一个 Agent 打分，并看着
闸门在每条轴上各抓到一个真实的 bug。这里每一段代码都能直接复制运行。

我们用的任务：*给一张 40 块的账单加 15% 小费，并存下新总额。* 正确总额是 `46`。

---

## 1. 安装

```bash
git clone https://github.com/BeamusWayne/trace-vault
cd trace-vault
uv venv && uv pip install -e .
# 不用 uv：python -m venv .venv && .venv/bin/pip install -e .
```

下面的命令请在项目的虚拟环境里运行（`uv run python ...`，或激活 `.venv`）。

## 2. 先看终点

```bash
vault demo
```

这会跑一个小的参考套件：四个场景通过，再有三个故意做坏的在两个分数（确定性和可信度）上被抓住。
接下来你要从零搭出它最小的版本。

## 3. 先跑一次，看它到底做了什么

新建 `tip_check.py`：

```python
"""tip_check.py：先跑一次，看它做了什么。"""
import tempfile
from pathlib import Path

from trace_vault.agent import Agent, World, default_registry
from trace_vault.providers import FakeProvider
from trace_vault.schemas import Completion, ToolCall, WorldSpec

# world：一张空的 bills 表，工具可以往里写。
world_spec = WorldSpec(sql_setup=("CREATE TABLE bills (id INTEGER, total REAL);",))

# 模型的行为，用脚本写死。生产里这是真实 LLM；这里用三步固定脚本顶上，于是全程离线。
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

运行：

```bash
python tip_check.py
```

```text
tools used:  ('calculator', 'db_insert')
final answer: Saved bill 1 with total 46 (40 + 15% tip).
bills row:    [{'id': 1, 'total': 46.0}]
```

发生了什么：`World` 是一个真实的内存 SQLite 数据库。`FakeProvider` 按顺序播放了模型的三步。
agent 循环真实地跑了 `calculator` 和 `db_insert` 工具，所以 `bills` 里那行是真的，`total = 46.0`。
这一行就是稍后可信度分数要读的东西。全程没有碰网络。

## 4. 把它变成一个 scenario 并打分

一次运行不足以谈可靠性。把 `tip_check.py` 换成下面这版：把任务描述成一个 `Scenario`，并回放 20 次。

```python
"""tip_check.py：在两条轴上打分，再卡闸门。"""
import tempfile

from trace_vault.agent import Agent, default_registry
from trace_vault.eval.runner import Case, run_case
from trace_vault.gate import Baseline, evaluate_gate, render_gate
from trace_vault.providers import FakeProvider
from trace_vault.schemas import (Completion, ToolCall, WorldSpec, Scenario,
                                 ExpectedToolCall, OutcomeCheck)

# 把任务写成数据：初始 world、目标、期望的计划，以及一个读取真实存下来的总额
# （而不是转录）的检查。
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
# 一个 Case 把任务和「每次运行如何产出模型行为」配在一起。
case = Case(scenario=scenario, make_provider=lambda i: FakeProvider(script()))

with tempfile.TemporaryDirectory() as tmp:
    report = run_case(case, agent, root=tmp, runs=20, k=5)

print("determinism: ", report.determinism.rate)
print("faithfulness:", report.faithfulness.rate)
print(render_gate(evaluate_gate([report], Baseline())))
```

运行：

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

`run_case` 把 agent 跑了 20 次，每次都对一个全新的 world。确定性是 1.0，因为每次都走相同路径。
可信度是 1.0，因为每次都让 `bills.total = 46`，正是 outcome 检查要的。`evaluate_gate` 配默认的
`Baseline()` 要求每个分数都是 1.0，所以闸门通过、退出 0。真实项目里你会提交一份 baseline JSON，
并在 CI 里跑 `vault gate`。

现在你有了一个绿的可靠性检查。接下来两步会故意把它弄坏。

## 5. 抓住一个答错（可信度）

这是一个转录检查会漏掉的 bug。在 `script()` 里，把存下的总额从 `46` 改成 `40`（Agent 忘了加小费，
却照样报告成功）：

```python
        Completion(tool_calls=(ToolCall(id="2", name="db_insert",
            arguments={"table": "bills", "values": {"id": 1, "total": 40}}),)),  # bug：存成了未加小费的金额
```

再跑一次：

```text
determinism:  1.0
faithfulness: 0.0
tip.save                       1.00       0.00*    1.00   FAIL

GATE: FAIL  (1/1 scenario(s) below threshold)   exit 1
  x tip.save: faithfulness 0.00 < 1.00
```

Agent 是*稳定地*这么干（确定性仍是 1.0），而且它的最终答案还说了「Saved」，所以一个在转录里搜
「Saved」的测试会通过。trace-vault 改为读 `bills` 那行，看到 `40`、而它要的是 `46`，于是在可信度上
失败。这正是会跑到生产环境去的那种 bug。

进入下一步前，把 `40` 改回 `46`。

## 6. 抓住一个 flake（确定性）

现在反过来：答案总是对的，但 Agent 每次用两种不同的方式去得到它。把 provider 换成
`StochasticFakeProvider`，它会按本次运行的种子在每一步的若干选项里挑一个。把 `script` 函数
和那行 `case` 换成：

```python
from trace_vault.providers import StochasticFakeProvider

# 第 0 步用两种方式都算到 46；第 1、2 步固定。
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

再把两个 pass 率统计打印出来：

```python
d = report.determinism
print(f"determinism: {d.rate}  pass^5: {d.pass_caret_k:.3f}  pass@5: {d.pass_at_k:.3f}")
print("faithfulness:", report.faithfulness.rate)
print(render_gate(evaluate_gate([report], Baseline())))
```

运行：

```text
determinism: 0.6  pass^5: 0.051  pass@5: 0.996
faithfulness: 1.0
tip.save                       0.60*      1.00     1.00   FAIL

GATE: FAIL  (1/1 scenario(s) below threshold)   exit 1
  x tip.save: determinism 0.60 < 1.00
```

可信度仍是 1.0（两条路径都存 46），但路径不可复现。`pass@5` 是 0.996，意思是「五次里至少一次
一致」，看着很健康。`pass^5` 是 0.051，意思是「五次全都一致」，把这个 flake 暴露了出来。后一个
数字更接近你在生产里的真实体感，而闸门在确定性上失败。

这就是 `vault demo` 展示的同样两个失败，现在你亲手搭出来了。

## 7. 用录制的 cassette 代替写脚本

到目前为止，模型一直是一段固定脚本。真实的工作流是：把你 Agent 的一次运行录下来，然后回放这份
录制。这份录制就是一个 *cassette*，一个你会提交的 YAML 文件。把好的 `script()` 放回去，然后：

```python
from pathlib import Path
from trace_vault.agent import World
from trace_vault.cassette.recorder import record_run
from trace_vault.cassette.store import save_cassette, load_cassette
from trace_vault.providers import CassetteProvider

with tempfile.TemporaryDirectory() as tmp:
    # 录一次。这里包了个 FakeProvider；生产里你传自己真实的 provider
    # （OpenAI 风格的见 src/trace_vault/providers/real.py）。
    rec_world = World(Path(tmp) / "rec", scenario.world)
    _, cassette = record_run(agent, scenario.goal, FakeProvider(script()), rec_world, name="tip.save")
    rec_world.close()
    save_cassette(cassette, "cassettes/tip.save.yaml")

    # 从此离线回放这份 cassette。没有模型、没有 key。
    loaded = load_cassette("cassettes/tip.save.yaml")
    case = Case(scenario=scenario, make_provider=lambda i: CassetteProvider(loaded))
    report = run_case(case, agent, root=Path(tmp) / "runs", runs=20, k=5)
    print("from cassette -> determinism:", report.determinism.rate,
          "faithfulness:", report.faithfulness.rate)
```

```text
from cassette -> determinism: 1.0 faithfulness: 1.0
```

打开 `cassettes/tip.save.yaml` 看看录了什么：每一步的请求，以及模型的响应，易变字段（id、时间戳）
被剥掉，这样回放时仍能匹配。把这个文件提交，整套测试就会永远离线地回放它。

## 8. 接下来去哪

你已经从零搭出了一个可靠性检查，并看着闸门抓到了一个答错（可信度）和一个 flake（确定性），
而这两个失败被一个合并的分数会糊在一起。

- **自带工具。** 内置工具集很小。继承 `Tool` 再注册；见 [自带工具](../README.md#自带工具)。
- **让副作用只触发一次。** 对一个扣卡、发邮件的工具，副作用账本能让重试不会做两次。见
  `src/trace_vault/suite/scenarios.py` 里的 `refund.idempotent_retry` 场景。
- **读设计。** [`docs/ARCHITECTURE.md`](./ARCHITECTURE.md) 讲了分层和背后的决定；
  [`docs/RESULTS.md`](./RESULTS.md) 解释参考数字。
- **翻参考场景**：`src/trace_vault/suite/scenarios.py` 里有每个象限的范例，外加一个提示注入场景。
