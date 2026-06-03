"""An irreversible-effect ledger enforcing *replay-or-fork*.

A side-effecting tool (a wire transfer, an email, a fulfilment) must fire exactly
once even if the agent run is retried, replayed, or rolled back. The ledger keys
each effect by its idempotency key (or, failing that, a hash of its arguments).
The first time it sees an effect it runs it and records the result; every time
after, it returns the recorded result *without re-executing*.

That is the "don't double-charge the customer on a retry" invariant, made into a
small, testable object.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass

from ..agent.tools.base import ToolResult
from ..schemas.messages import ToolCall


@dataclass(frozen=True)
class LedgerEntry:
    key: str
    tool: str
    result: ToolResult


class EffectLedger:
    """Make repeated identical effects idempotent across replays and retries."""

    def __init__(self) -> None:
        self._entries: dict[str, LedgerEntry] = {}
        self._executions = 0

    def effect_key(self, call: ToolCall) -> str:
        idem = call.arguments.get("idempotency_key")
        if idem:
            return f"{call.name}:{idem}"
        blob = json.dumps(
            {"name": call.name, "args": call.arguments}, sort_keys=True, ensure_ascii=False
        )
        return f"{call.name}:{hashlib.sha256(blob.encode()).hexdigest()[:12]}"

    def run_effect(self, call: ToolCall, run: Callable[[], ToolResult]) -> ToolResult:
        key = self.effect_key(call)
        prior = self._entries.get(key)
        if prior is not None:
            # replay-or-fork: do NOT re-execute the irreversible effect. We return
            # the recorded result with its *content unchanged* (the annotation goes
            # in `data`) so a cassette recorded without a ledger still replays
            # byte-for-byte — the de-duplication is invisible to the trajectory.
            annotated = {**prior.result.data, "ledger_replayed": True}
            return prior.result.model_copy(update={"data": annotated})
        result = run()
        self._executions += 1
        self._entries = {**self._entries, key: LedgerEntry(key=key, tool=call.name, result=result)}
        return result

    @property
    def executions(self) -> int:
        """How many times a real side effect actually ran."""
        return self._executions

    def committed_keys(self) -> tuple[str, ...]:
        return tuple(self._entries)
