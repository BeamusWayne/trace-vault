"""A calculator tool backed by a *safe* arithmetic evaluator.

We never call :func:`eval` on model output. Expressions are parsed with ``ast``
and only a small whitelist of numeric operators is permitted.
"""

from __future__ import annotations

import ast
import operator
from collections.abc import Callable
from typing import Any, ClassVar

from ...errors import ToolError
from ..world import World
from .base import Tool, ToolResult

_BINOPS: dict[type[ast.operator], Callable[[float, float], float]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARYOPS: dict[type[ast.unaryop], Callable[[float], float]] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


def safe_eval(expression: str) -> float:
    """Evaluate a numeric expression with a whitelisted AST. Raises on anything
    that is not pure arithmetic over numbers."""
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ToolError(f"invalid expression: {expression!r}") from exc

    def _eval(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
            return _BINOPS[type(node.op)](_eval(node.left), _eval(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARYOPS:
            return _UNARYOPS[type(node.op)](_eval(node.operand))
        raise ToolError(f"unsupported expression element: {ast.dump(node)}")

    return _eval(tree)


class CalculatorTool(Tool):
    name = "calculator"
    description = "Evaluate a pure arithmetic expression (e.g. '120 * 0.85')."
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {"expression": {"type": "string"}},
        "required": ["expression"],
    }

    def run(self, args: dict[str, Any], world: World) -> ToolResult:
        self._require(args, "expression")
        value = safe_eval(str(args["expression"]))
        # Render integers without a trailing .0 for clean, citable evidence.
        rendered = str(int(value)) if value == int(value) else str(value)
        return ToolResult(content=rendered, data={"value": value})
