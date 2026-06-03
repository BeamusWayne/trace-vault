"""trace-vault — a record/replay reliability gate for tool-using agents.

trace-vault records an agent's LLM + tool exchanges into normalized cassettes,
replays them deterministically offline, and gates CI on two *independent* axes:

* **Determinism** — does the agent take the same trajectory every replay?
* **Faithfulness** — did the run actually change the world as claimed?

The two are measured and gated separately, on purpose: an agent can be perfectly
reproducible and still wrong, and trace-vault is built to surface exactly that.
"""

from __future__ import annotations

from .errors import (
    CassetteError,
    DivergenceError,
    MaxStepsExceeded,
    NetworkBlockedError,
    ToolError,
    TraceVaultError,
)
from .schemas import (
    Cassette,
    Completion,
    Message,
    Scenario,
    ToolCall,
    ToolSpec,
    Transcript,
)

__version__ = "0.1.0"

__all__ = [
    "Cassette",
    "CassetteError",
    "Completion",
    "DivergenceError",
    "MaxStepsExceeded",
    "Message",
    "NetworkBlockedError",
    "Scenario",
    "ToolCall",
    "ToolError",
    "ToolSpec",
    "TraceVaultError",
    "Transcript",
    "__version__",
]
