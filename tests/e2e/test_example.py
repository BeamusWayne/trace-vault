"""M6 end-to-end: the 'use it on your own agent' example actually runs and passes."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_EXAMPLE = Path(__file__).resolve().parents[2] / "examples" / "use_on_your_agent.py"


@pytest.mark.e2e
def test_use_on_your_agent_example_runs_and_passes() -> None:
    result = subprocess.run(
        [sys.executable, str(_EXAMPLE)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    assert "GATE: PASS" in result.stdout
    assert "discount.apply" in result.stdout
