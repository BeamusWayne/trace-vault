"""Structured database tools.

The model never supplies raw SQL. It names a table and supplies a column->value
mapping; identifiers are validated against an allowlist regex *and* the live
schema, and all values are bound as parameters. This is parameterized-query
discipline applied to a tool surface.
"""

from __future__ import annotations

import json
from typing import Any, ClassVar

from ...errors import ToolError
from ...sql_safe import safe_identifier
from ..world import World
from .base import Tool, ToolResult


def _ident(name: object) -> str:
    try:
        return safe_identifier(name)
    except ValueError as exc:
        raise ToolError(str(exc)) from exc


def _validate_columns(world: World, table: str, cols: list[str]) -> None:
    known = set(world.columns(table))
    unknown = [c for c in cols if c not in known]
    if unknown:
        raise ToolError(f"unknown column(s) for {table}: {', '.join(unknown)}")


class DBQueryTool(Tool):
    name = "db_query"
    description = "Read rows from a table, optionally filtered by exact column matches."
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "table": {"type": "string"},
            "where": {"type": "object"},
        },
        "required": ["table"],
    }

    def run(self, args: dict[str, Any], world: World) -> ToolResult:
        self._require(args, "table")
        table = _ident(args["table"])
        if not world.has_table(table):
            return ToolResult.fail(f"no such table: {table}")
        filters = dict(args.get("where") or {})
        cols = [_ident(c) for c in filters]
        _validate_columns(world, table, cols)
        clause = ""
        params: list[Any] = []
        if cols:
            clause = " WHERE " + " AND ".join(f"{c} = ?" for c in cols)
            params = list(filters.values())
        rows = world.query(f"SELECT * FROM {table}{clause}", params)
        return ToolResult(
            content=json.dumps(rows, ensure_ascii=False, default=str),
            data={"rows": rows},
        )


class DBInsertTool(Tool):
    name = "db_insert"
    description = "Insert a row into a table from a column->value mapping."
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "table": {"type": "string"},
            "values": {"type": "object"},
        },
        "required": ["table", "values"],
    }

    def run(self, args: dict[str, Any], world: World) -> ToolResult:
        self._require(args, "table", "values")
        table = _ident(args["table"])
        if not world.has_table(table):
            return ToolResult.fail(f"no such table: {table}")
        values = dict(args["values"])
        cols = [_ident(c) for c in values]
        _validate_columns(world, table, cols)
        placeholders = ", ".join("?" for _ in cols)
        world.execute(
            f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders})",
            list(values.values()),
        )
        return ToolResult(
            content=f"inserted 1 row into {table}",
            data={"table": table, "values": values},
        )
