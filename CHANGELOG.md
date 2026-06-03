# Changelog

The format follows [Keep a Changelog](https://keepachangelog.com/) and the
project adheres to [Semantic Versioning](https://semver.org/).

## [0.1.0] — 2026-06-04

Initial release.

### Added
- Model-agnostic provider seam (`LLMProvider` Protocol) with offline `Fake`,
  `Keyed`, and `Stochastic` doubles, record/replay cassette providers, and an
  optional secret-gated OpenAI-compatible adapter.
- Thin ReAct agent loop over an assertable World (in-process SQLite + temp fs)
  and a small toolset (calculator, search, files, parameterized DB, transfer).
- Cassette engine: volatile-field normalization, three order-tolerant match
  modes (`strict` / `unordered` / `subset`), typed `DivergenceError`, ruamel
  YAML store.
- Dual-axis evaluation: determinism (`pass^k` / `pass@k`, seeded bootstrap CI,
  min-runs hint) and faithfulness (world-state graders + evidence overlap), plus
  order-tolerant trajectory grading.
- `vault` CLI (`gate`, `eval`, `demo`, `version`) and a baseline-diff gate that
  exits non-zero on regression.
- Irreversible-effect ledger (replay-or-fork, exactly-once, content-stable).
- Reference suite spanning all four determinism × faithfulness quadrants plus an
  indirect prompt-injection scenario.
- Optional in-memory and OpenTelemetry tracing.
- Offline-by-design test suite (unit / integration / e2e) with a network
  sentinel and an 80% coverage gate; GitHub Actions on Python 3.11–3.13.
