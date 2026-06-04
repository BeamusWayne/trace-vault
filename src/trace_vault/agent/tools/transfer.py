"""The side-effecting tool: an irreversible money transfer.

This is the one tool with a real-world consequence. It is marked ``effectful``
so the irreversible-effect ledger can guarantee it fires *exactly once* across
replays and rollbacks, the "don't double-charge the customer" invariant.
"""

from __future__ import annotations

from typing import Any

from ..world import World
from .base import Tool, ToolResult


class TransferTool(Tool):
    name = "transfer"
    description = (
        "Transfer money between accounts. IRREVERSIBLE. "
        "Provide an idempotency_key to make retries safe."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "from_account": {"type": "string"},
            "to_account": {"type": "string"},
            "amount": {"type": "number"},
            "idempotency_key": {"type": "string"},
        },
        "required": ["from_account", "to_account", "amount"],
    }
    effectful = True

    def run(self, args: dict[str, Any], world: World) -> ToolResult:
        self._require(args, "from_account", "to_account", "amount")
        src = str(args["from_account"])
        dst = str(args["to_account"])
        amount = float(args["amount"])
        idem = str(args.get("idempotency_key", ""))

        if amount <= 0:
            return ToolResult.fail("amount must be positive")
        balance = world.scalar("SELECT balance FROM accounts WHERE account = ?", [src])
        if balance is None:
            return ToolResult.fail(f"no such account: {src}")
        if world.scalar("SELECT balance FROM accounts WHERE account = ?", [dst]) is None:
            return ToolResult.fail(f"no such account: {dst}")
        if float(balance) < amount:
            return ToolResult.fail("insufficient funds")

        world.execute(
            "UPDATE accounts SET balance = balance - ? WHERE account = ?", [amount, src]
        )
        world.execute(
            "UPDATE accounts SET balance = balance + ? WHERE account = ?", [amount, dst]
        )
        world.execute(
            "INSERT INTO transfers (from_account, to_account, amount, idem) "
            "VALUES (?, ?, ?, ?)",
            [src, dst, amount, idem],
        )
        return ToolResult(
            content=f"transferred {amount:g} from {src} to {dst}",
            data={"from": src, "to": dst, "amount": amount, "idem": idem},
        )
