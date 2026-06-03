"""The built-in toolset and the default registry."""

from __future__ import annotations

from .base import Tool, ToolRegistry, ToolResult
from .calculator import CalculatorTool, safe_eval
from .database import DBInsertTool, DBQueryTool
from .files import ReadFileTool, WriteFileTool
from .search import SearchTool
from .transfer import TransferTool


def default_registry() -> ToolRegistry:
    """The standard toolset every reference scenario draws from."""
    return ToolRegistry(
        [
            CalculatorTool(),
            SearchTool(),
            ReadFileTool(),
            WriteFileTool(),
            DBQueryTool(),
            DBInsertTool(),
            TransferTool(),
        ]
    )


__all__ = [
    "CalculatorTool",
    "DBInsertTool",
    "DBQueryTool",
    "ReadFileTool",
    "SearchTool",
    "Tool",
    "ToolRegistry",
    "ToolResult",
    "TransferTool",
    "WriteFileTool",
    "default_registry",
    "safe_eval",
]
