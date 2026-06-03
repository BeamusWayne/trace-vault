"""M2 unit: request normalization is stable under volatile noise."""

from __future__ import annotations

import pytest

from trace_vault.cassette.normalize import (
    normalize_messages,
    request_key,
    scrub_text,
)
from trace_vault.schemas.messages import Message, ToolCall, ToolSpec


@pytest.mark.unit
def test_scrub_text_replaces_uuid_and_timestamp() -> None:
    text = "id=550e8400-e29b-41d4-a716-446655440000 at 2026-06-04T11:30:00Z done"
    assert scrub_text(text) == "id=<UUID> at <TS> done"


@pytest.mark.unit
def test_tool_call_ids_are_canonicalized_to_appearance_order() -> None:
    messages = [
        Message(
            role="assistant",
            tool_calls=(ToolCall(id="xyz-987", name="calc", arguments={"e": "1+1"}),),
        ),
        Message(role="tool", content="2", tool_call_id="xyz-987", name="calc"),
    ]
    norm = normalize_messages(messages)
    assert norm[0]["tool_calls"][0]["id"] == "call_0"
    assert norm[1]["tool_call_id"] == "call_0"


@pytest.mark.unit
def test_request_key_is_invariant_to_volatile_ids() -> None:
    tools = (ToolSpec(name="calc"),)

    def convo(call_id: str) -> list[Message]:
        return [
            Message(role="user", content="add"),
            Message(
                role="assistant",
                tool_calls=(ToolCall(id=call_id, name="calc", arguments={"e": "1+1"}),),
            ),
            Message(role="tool", content="2", tool_call_id=call_id, name="calc"),
        ]

    # Two runs differing ONLY by random tool-call ids hash identically.
    assert request_key(convo("aaa"), tools) == request_key(convo("zzz"), tools)


@pytest.mark.unit
def test_request_key_changes_when_tool_name_changes() -> None:
    base = [Message(role="assistant", tool_calls=(ToolCall(id="c", name="calc"),))]
    other = [Message(role="assistant", tool_calls=(ToolCall(id="c", name="search"),))]
    assert request_key(base) != request_key(other)
