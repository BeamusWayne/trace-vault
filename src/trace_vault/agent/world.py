"""The assertable World: an in-process SQLite database + a temp filesystem.

Faithfulness grades against this. Tools really mutate it and only the LLM is
faked, so "did the row get written, did the file get created" has a real answer
instead of a transcript string match.

The World is the one deliberately *mutable* object in trace-vault (it is an
environment, like a test database). Domain data everywhere else is immutable.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from ..schemas.scenario import WorldSpec


class World:
    """A disposable environment an agent run acts upon and graders inspect."""

    def __init__(self, root: Path, spec: WorldSpec | None = None) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        if spec is not None:
            self.apply(spec)

    # -- setup ---------------------------------------------------------------

    def apply(self, spec: WorldSpec) -> None:
        """Initialize DB schema/seed and seed files from a spec."""
        for statement in spec.sql_setup:
            self.db.executescript(statement)
        self.db.commit()
        for relpath, content in spec.files.items():
            self.write_file(relpath, content)

    # -- database access (used by tools and graders) -------------------------

    def execute(self, sql: str, params: Sequence[Any] = ()) -> None:
        self.db.execute(sql, tuple(params))
        self.db.commit()

    def query(self, sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
        cur = self.db.execute(sql, tuple(params))
        return [dict(row) for row in cur.fetchall()]

    def scalar(self, sql: str, params: Sequence[Any] = ()) -> Any:
        cur = self.db.execute(sql, tuple(params))
        row = cur.fetchone()
        if row is None:
            return None
        return row[0]

    def row_count(self, table: str, where: str = "", params: Sequence[Any] = ()) -> int:
        # `table` and `where` come from trusted scenario/tool definitions, never
        # from raw model output; values are always bound as parameters.
        clause = f" WHERE {where}" if where else ""
        return int(self.scalar(f"SELECT COUNT(*) FROM {table}{clause}", params) or 0)

    def has_table(self, table: str) -> bool:
        return (
            self.scalar(
                "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
                [table],
            )
            is not None
        )

    def columns(self, table: str) -> tuple[str, ...]:
        rows = self.query(f"PRAGMA table_info({table})")
        return tuple(str(r["name"]) for r in rows)

    # -- filesystem access ---------------------------------------------------

    def _safe_path(self, relpath: str) -> Path:
        """Resolve a path inside the world root, refusing escapes."""
        target = (self.root / relpath).resolve()
        root = self.root.resolve()
        if root != target and root not in target.parents:
            raise ValueError(f"path escapes world root: {relpath!r}")
        return target

    def write_file(self, relpath: str, content: str) -> Path:
        path = self._safe_path(relpath)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def read_file(self, relpath: str) -> str | None:
        path = self._safe_path(relpath)
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")

    def file_exists(self, relpath: str) -> bool:
        return self._safe_path(relpath).exists()

    # -- lifecycle -----------------------------------------------------------

    def close(self) -> None:
        self.db.close()

    def __enter__(self) -> World:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
