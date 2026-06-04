"""A deterministic search tool over the world's ``documents`` table.

Real search is the classic source of untrusted, model-steering tool output, so
this tool deliberately returns document *bodies* verbatim, which is exactly how
an indirect prompt-injection scenario gets its foothold.
"""

from __future__ import annotations

import re
from typing import Any

from ..world import World
from .base import Tool, ToolResult

_WORD = re.compile(r"\w+")
_MAX_RESULTS = 3


class SearchTool(Tool):
    name = "search"
    description = "Search the knowledge base; returns matching document snippets."
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    }

    def run(self, args: dict[str, Any], world: World) -> ToolResult:
        self._require(args, "query")
        if not world.has_table("documents"):
            return ToolResult(content="no documents available", data={"results": []})

        terms = [t for t in _WORD.findall(str(args["query"]).lower()) if t]
        rows = world.query("SELECT id, title, body FROM documents ORDER BY id")

        scored: list[tuple[int, int, dict[str, Any]]] = []
        for row in rows:
            haystack = f"{row['title']} {row['body']}".lower()
            score = sum(haystack.count(term) for term in terms)
            if score > 0:
                scored.append((-score, int(row["id"]), row))
        scored.sort()
        top = [row for _, _, row in scored[:_MAX_RESULTS]]

        if not top:
            return ToolResult(content="no results", data={"results": []})
        snippets = "\n".join(f"[{r['id']}] {r['title']}: {r['body']}" for r in top)
        return ToolResult(content=snippets, data={"results": top})
