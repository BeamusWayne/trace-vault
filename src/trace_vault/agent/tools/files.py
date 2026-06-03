"""Filesystem tools scoped to the world root."""

from __future__ import annotations

from typing import Any

from ..world import World
from .base import Tool, ToolResult


class ReadFileTool(Tool):
    name = "read_file"
    description = "Read a UTF-8 text file from the workspace."
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    }

    def run(self, args: dict[str, Any], world: World) -> ToolResult:
        self._require(args, "path")
        content = world.read_file(str(args["path"]))
        if content is None:
            return ToolResult.fail(f"file not found: {args['path']}")
        return ToolResult(content=content, data={"path": args["path"]})


class WriteFileTool(Tool):
    name = "write_file"
    description = "Write a UTF-8 text file into the workspace."
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
        "required": ["path", "content"],
    }

    def run(self, args: dict[str, Any], world: World) -> ToolResult:
        self._require(args, "path", "content")
        world.write_file(str(args["path"]), str(args["content"]))
        return ToolResult(
            content=f"wrote {args['path']}", data={"path": args["path"]}
        )
