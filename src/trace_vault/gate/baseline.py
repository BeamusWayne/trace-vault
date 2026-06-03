"""The frozen baseline a gate run is compared against.

A baseline pins both an absolute bar (``thresholds``) and the last-known-good
per-scenario numbers (``scenarios``), so the gate fails on *either* an absolute
miss or a regression below the recorded value (minus ``tolerance``).
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from ..errors import TraceVaultError
from ..schemas.report import GateThresholds


class ScenarioBaseline(BaseModel):
    model_config = ConfigDict(frozen=True)

    determinism: float = 0.0
    faithfulness: float = 0.0
    trajectory: float = 0.0


class Baseline(BaseModel):
    model_config = ConfigDict(frozen=True)

    thresholds: GateThresholds = GateThresholds()
    tolerance: float = 0.0
    scenarios: dict[str, ScenarioBaseline] = Field(default_factory=dict)


def load_baseline(path: str | Path) -> Baseline:
    path = Path(path)
    if not path.exists():
        raise TraceVaultError(f"baseline not found: {path}")
    return Baseline.model_validate(json.loads(path.read_text(encoding="utf-8")))


def save_baseline(baseline: Baseline, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(baseline.model_dump(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path
