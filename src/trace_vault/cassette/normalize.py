"""Request normalization for stable record/replay.

Two recordings of "the same" agent step differ in volatile noise: randomly
generated tool-call ids, wall-clock timestamps, UUIDs. To match a replayed
request against a recording we first scrub that noise on a fixed allowlist and
canonicalize tool-call ids to appearance order, then hash the result.

All functions here are pure functions of their inputs.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence
from typing import Any

from ..schemas.messages import Message, ToolSpec

# --- the volatile-field allowlist (and nothing else) -----------------------

_UUID = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
_TIMESTAMP = re.compile(
    r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?"
)

UUID_PLACEHOLDER = "<UUID>"
TIMESTAMP_PLACEHOLDER = "<TS>"


def scrub_text(text: str) -> str:
    """Replace volatile UUIDs and timestamps with stable placeholders.

    Order matters: UUIDs first (a UUID never contains a timestamp), then
    timestamps.
    """
    text = _UUID.sub(UUID_PLACEHOLDER, text)
    return _TIMESTAMP.sub(TIMESTAMP_PLACEHOLDER, text)


def _scrub_value(value: Any) -> Any:
    """Recursively scrub volatile substrings inside tool arguments."""
    if isinstance(value, str):
        return scrub_text(value)
    if isinstance(value, dict):
        return {k: _scrub_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_scrub_value(v) for v in value]
    return value


def _canonical_id_map(messages: Sequence[Message]) -> dict[str, str]:
    """Map each distinct tool-call id to ``call_<n>`` in first-appearance order."""
    mapping: dict[str, str] = {}

    def add(identifier: str | None) -> None:
        if identifier is not None and identifier not in mapping:
            mapping[identifier] = f"call_{len(mapping)}"

    for message in messages:
        for call in message.tool_calls:
            add(call.id)
        add(message.tool_call_id)
    return mapping


def normalize_messages(messages: Sequence[Message]) -> list[dict[str, Any]]:
    """Return a canonical, JSON-able view of the conversation with volatile
    fields scrubbed and tool-call ids re-indexed to appearance order."""
    id_map = _canonical_id_map(messages)
    out: list[dict[str, Any]] = []
    for message in messages:
        out.append(
            {
                "role": message.role,
                "content": scrub_text(message.content),
                "tool_calls": [
                    {
                        "id": id_map.get(call.id, call.id),
                        "name": call.name,
                        "arguments": _scrub_value(call.arguments),
                    }
                    for call in message.tool_calls
                ],
                "tool_call_id": (
                    id_map.get(message.tool_call_id) if message.tool_call_id else None
                ),
                "name": message.name,
            }
        )
    return out


def normalize_request(
    messages: Sequence[Message], tools: Sequence[ToolSpec] = ()
) -> dict[str, Any]:
    """The full normalized request digest used for strict / unordered matching."""
    return {
        "messages": normalize_messages(messages),
        "tools": sorted(tool.name for tool in tools),
    }


def _hash(blob: dict[str, Any]) -> str:
    text = json.dumps(blob, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def request_key(messages: Sequence[Message], tools: Sequence[ToolSpec] = ()) -> str:
    """A short, stable hash of the full normalized request."""
    return _hash(normalize_request(messages, tools))


def tail_key(messages: Sequence[Message], tools: Sequence[ToolSpec] = ()) -> str:
    """A relaxed key over only the *latest* turn, used by ``subset`` matching,
    which tolerates differences in earlier conversation history."""
    norm = normalize_messages(messages)
    last = norm[-1] if norm else {}
    return _hash({"last": last, "tools": sorted(t.name for t in tools)})


def tail_key_of_digest(digest: dict[str, Any]) -> str:
    """The ``subset`` tail key computed from a stored request digest (so a
    recorded interaction can be matched without re-deriving it from messages)."""
    messages = digest.get("messages", [])
    last = messages[-1] if messages else {}
    return _hash({"last": last, "tools": digest.get("tools", [])})
