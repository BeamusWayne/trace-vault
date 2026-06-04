# Architecture

English · [中文](./ARCHITECTURE.zh.md)

trace-vault is a small, layered library. Every layer is pure data + pure
functions where it can be, and the one stateful object (the `World`) is explicit
about it. The design goal: make "is this agent reliable?" a question you can
answer in CI, offline, deterministically.

## The layers

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

Dependencies point downward only. `schemas/` (immutable Pydantic models) and
`errors.py` underpin everything and depend on nothing.

## Data flow: one scenario, end to end

1. **Record (once).** An agent run is driven by some provider, in the reference
   suite a scripted `FakeProvider`, in production a real LLM. A `RecordingProvider`
   wraps it and writes each `request → completion` into a **cassette**, after
   normalizing volatile fields (tool-call ids → `call_0…`, timestamps → `<TS>`,
   UUIDs → `<UUID>`).

2. **Replay (forever, offline).** `run_case` runs the agent **N times**. Each run
   gets a *fresh* `World` and a `CassetteProvider`. The provider serves recorded
   completions by matching the normalized request; the **tools really execute**
   against the fresh World. Only the LLM is replayed.

3. **Score two axes, independently.**
   - **Determinism** compares the N trajectory *signatures*. Identical ⇒ 1.0.
     Reports `pass^k` / `pass@k`, a seeded bootstrap CI, and a min-runs hint.
   - **Faithfulness** runs outcome graders against each run's real World (SQLite
     rows, files) plus an evidence-overlap check on the final answer.

4. **Gate.** `evaluate_gate` compares each axis to the baseline's absolute
   thresholds *and* its last-known-good value, and emits a per-scenario verdict.
   Non-zero exit on any regression.

## Five decisions worth defending

**1. The offline-green invariant is structural, not a flag.**
Replay is offline *by definition*: the cassette is the fixture and `FakeProvider`
is the test double. The default code path never imports a network SDK. A pytest
`conftest` sentinel fails any test that opens a non-local socket, we enforce the
promise instead of trusting it.

**2. Determinism and faithfulness are separate scores on purpose.**
The field keeps collapsing reliability into one number. The two failing reference
scenarios (`report.flaky_plan`, `booking.unfaithful_write`) are uncorrelated by
construction, a single score hides one of them. So the gate checks each axis
independently and the report shows them side by side.

**3. Faithfulness grades the world, not the transcript.**
"It said it booked the room" is a string; "the `bookings` row exists" is a fact.
Tools mutate an in-process SQLite DB and a temp filesystem, and graders assert on
*that*. This is what makes the unfaithful and injection scenarios catchable.

**4. Normalization + match modes make replay robust, not brittle.**
A naive request-hash diverges on benign noise (a new random tool-call id). We
scrub a *fixed allowlist* of volatile fields and canonicalize ids to appearance
order, then offer three match modes (`strict`, `unordered`, `subset`) so
order-independent steps don't read as divergence. When a request genuinely
diverges, the error is *classified* (`tool-name` / `call-order` / `arg-mismatch`
/ `prompt-hash`), because a useful gate tells you what changed.

**5. The ledger is content-stable.**
The irreversible-effect ledger makes a side-effecting tool fire exactly once
across retries. Critically, on a de-duplicated call it returns the recorded
result with *unchanged content* (the annotation goes in `data`). That means a
cassette recorded **without** a ledger still replays byte-for-byte **with** one, so
idempotency is invisible to the trajectory and never manufactures a divergence.

## Testing strategy

Three layers, all offline (`pytest -m unit | integration | e2e`):

- **unit**: pure functions with exact assertions: normalization, divergence
  classification, the `pass^k` / `pass@k` / bootstrap math against hand-computed
  closed forms, graders, ledger keys, tool error paths.
- **integration**: record→replay round-trip (byte-stable), graders against the
  real World, tracer spans, the with/without-ledger double-charge contrast.
- **e2e**: the full agent → cassette → eval → gate pipeline: green on the
  baseline; catches a flaky *and* an unfaithful scenario on two different axes;
  the determinism ≠ faithfulness thesis asserted directly; CLI exit codes.

Coverage runs with `--cov-fail-under=80`; the suite sits well above that.
