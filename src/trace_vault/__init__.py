"""trace-vault: a record/replay reliability gate for tool-using agents.

It records an agent's LLM and tool exchanges into normalized cassettes, replays
them deterministically offline, and gates CI on two independent scores:

* Determinism: does the agent take the same trajectory every replay?
* Faithfulness: did the run change the world it claimed to?

The two are measured and gated separately. An agent can be perfectly reproducible
and still wrong, and a single combined score would hide that.
"""

from __future__ import annotations

from .errors import (
    CassetteError,
    DivergenceError,
    MaxStepsExceeded,
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
    "Scenario",
    "ToolCall",
    "ToolError",
    "ToolSpec",
    "TraceVaultError",
    "Transcript",
    "__version__",
]
