"""Typed errors for trace-vault.

A precise error taxonomy is part of the product: a replay that diverges should
tell you *why* (prompt changed? tool swapped? wrong order? bad args?), not just
fail.
"""

from __future__ import annotations

from typing import Any, Literal

DivergenceKind = Literal[
    "prompt-hash",  # the normalized request text changed
    "tool-name",  # a different tool was selected
    "call-order",  # right calls, wrong order (strict mode)
    "arg-mismatch",  # right tool, different arguments
    "exhausted",  # agent asked for more calls than the cassette recorded
]


class TraceVaultError(Exception):
    """Base class for all trace-vault errors."""


class DivergenceError(TraceVaultError):
    """Raised during replay when the agent's request does not match the recording.

    Carries a machine-readable ``kind`` so the gate can classify failures.
    """

    def __init__(
        self,
        kind: DivergenceKind,
        message: str,
        *,
        step: int | None = None,
        expected: Any = None,
        actual: Any = None,
    ) -> None:
        self.kind: DivergenceKind = kind
        self.step = step
        self.expected = expected
        self.actual = actual
        prefix = f"[{kind}]" + (f" step {step}" if step is not None else "")
        super().__init__(f"{prefix}: {message}")


class NetworkBlockedError(TraceVaultError):
    """Raised if replay ever attempts a real network call, the offline invariant
    is enforced, not assumed."""


class MaxStepsExceeded(TraceVaultError):
    """The agent exceeded the scenario's step budget without finishing."""


class CassetteError(TraceVaultError):
    """A cassette could not be read, written, or validated."""


class ToolError(TraceVaultError):
    """A tool received invalid arguments or failed to execute."""
