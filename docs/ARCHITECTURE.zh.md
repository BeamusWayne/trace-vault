# 架构

[English](./ARCHITECTURE.md) · 中文

trace-vault 是一个小而分层的库。每一层尽量是不可变数据加纯函数，唯一的有状态对象（`World`）也
明确标出。设计目标：把「这个 Agent 可靠吗」变成一个你能在 CI 上、离线、确定性地回答的问题。

## 分层

```
                          ┌─────────────────────────────┐
   vault CLI  ───────────▶│  gate / demo / eval / version│
                          └──────────────┬───────────────┘
                  ┌──────────────────────┴──────────────────────┐
                  ▼                                              ▼
        ┌──────────────────┐                          ┌────────────────────┐
        │   gate           │                          │   ledger           │
        │  baseline diff   │                          │  replay-or-fork     │
        │  per-axis verdict│                          │  (exactly-once)     │
        └────────┬─────────┘                          └─────────┬──────────┘
                 ▼                                               │
        ┌──────────────────────────────────────────────┐        │
        │   eval                                        │        │
        │  determinism (pass^k, bootstrap CI)           │        │
        │  faithfulness (world graders + evidence)      │        │
        │  trajectory (order-tolerant grading)          │        │
        └────────┬─────────────────────────────────────┘        │
                 ▼                                               │
        ┌──────────────────────────────────────────────┐        │
        │   cassette                                    │        │
        │  normalize · match modes · record / replay    │        │
        │  typed DivergenceError                        │        │
        └────────┬─────────────────────────────────────┘        │
                 ▼                                               ▼
        ┌──────────────────────────────────────────────────────────────┐
        │   agent  ·  thin ReAct loop · tool registry · World           │
        │           (in-process SQLite + temp filesystem)               │
        └────────┬─────────────────────────────────────────────────────┘
                 ▼
        ┌──────────────────────────────────────────────────────────────┐
        │   providers · LLMProvider Protocol                            │
        │     FakeProvider · CassetteProvider · (real, secret-gated)    │
        └──────────────────────────────────────────────────────────────┘
```

依赖只朝下指。`schemas/`（不可变的 Pydantic 模型）和 `errors.py` 撑起一切，自己不依赖任何东西。

## 数据流：一个 scenario，从头到尾

1. **录制（一次）。** 一次 Agent 运行由某个 provider 驱动：参考套件里是脚本化的 `FakeProvider`，
   生产里是真实 LLM。`RecordingProvider` 把它包住，并在归一化易变字段（tool-call id → `call_0…`、
   时间戳 → `<TS>`、UUID → `<UUID>`）之后，把每个 `请求 → completion` 写进一个 **cassette**。

2. **回放（永远，离线）。** `run_case` 把 Agent 跑 **N 次**。每次都拿到一个*全新*的 `World` 和一个
   `CassetteProvider`。provider 通过匹配归一化后的请求来供给录好的 completion；而**工具是真实
   执行**的，对着这个全新的 World。只有 LLM 是回放的。

3. **独立地给两条轴打分。**
   - **确定性** 比对 N 条轨迹*指纹*。完全相同 ⇒ 1.0。报 `pass^k` / `pass@k`、一个种子化的自助
     置信区间，以及一个最小运行次数提示。
   - **可信度** 对每次运行的真实 World（SQLite 行、文件）跑 outcome 评分器，再加一个对最终答案
     的证据重合度检查。

4. **闸门。** `evaluate_gate` 把每条轴和 baseline 的绝对阈值*以及*它上次已知良好的值比对，给出
   每个场景的判定。任何回归即非零退出。

## 五个值得辩护的决定

**1. 离线不变量是结构性的，不是一个开关。**
回放*天生*离线：cassette 是 fixture，`FakeProvider` 是测试替身。默认代码路径从不 import 任何
网络 SDK。一个 pytest `conftest` 哨兵会让任何打开非本地 socket 的测试失败，于是这个承诺是被
强制的，而不是靠信任。

**2. 确定性和可信度刻意是两个分开的分数。**
业界总爱把可靠性压成一个数字。两个会失败的参考场景（`report.flaky_plan`、
`booking.unfaithful_write`）按构造彼此不相关，一个分数会盖掉其中一个。所以闸门独立地检查每
条轴，报告也把它们并排放。

**3. 可信度评的是世界，不是转录。**
「它说它订了房」是一句话；「`bookings` 那行存在」是一个事实。工具改动一个进程内的 SQLite
数据库和一个临时文件系统，评分器断言的就是*那个*。这正是「不可信」和「注入」两个场景能被抓住
的原因。

**4. 归一化加匹配模式让回放稳健，而不脆弱。**
朴素的请求哈希会因无害的噪声（一个新的随机 tool-call id）就判为发散。我们把一份*固定白名单*里的
易变字段擦掉，并把 id 归一成出现顺序，再提供三种匹配模式（`strict`、`unordered`、`subset`），
于是顺序无关的步骤不会被读成发散。当一个请求真的发散时，错误是被*分类*的（`tool-name` /
`call-order` / `arg-mismatch` / `prompt-hash`），因为一个有用的闸门会告诉你变的是什么。

**5. 账本是内容稳定的。**
不可逆副作用账本让一个有副作用的工具在多次重试里只触发一次。关键在于：在一次去重的调用上，它
返回录好的结果、但*内容不变*（注记放进 `data`）。这意味着一份**没有**账本时录的 cassette，在
**有**账本时仍能逐字节回放，于是幂等对轨迹是不可见的，永远不会凭空造出一次发散。

## 测试策略

三层，全部离线（`pytest -m unit | integration | e2e`）：

- **unit**：带精确断言的纯函数：归一化、发散分类、`pass^k` / `pass@k` / 自助法的数学（对着手算的
  闭式值核对）、评分器、账本键、工具错误路径。
- **integration**：录制→回放往返（逐字节稳定）、对真实 World 的评分器、tracer span、有/无账本的
  重复扣款对照。
- **e2e**：完整的 agent → cassette → eval → gate 流水线：在 baseline 上绿；在两条不同的轴上分别
  抓住一个 flaky 和一个不可信的场景；直接断言 determinism ≠ faithfulness；CLI 退出码。

覆盖率以 `--cov-fail-under=80` 运行；实际远高于此。
