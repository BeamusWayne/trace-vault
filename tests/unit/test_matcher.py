"""M2 unit: divergence classification and cursor match modes."""

from __future__ import annotations

from typing import Any

import pytest

from trace_vault.cassette.matcher import CassetteCursor, classify_divergence
from trace_vault.cassette.normalize import normalize_request, request_key
from trace_vault.errors import DivergenceError
from trace_vault.schemas.cassette import Cassette, Interaction
from trace_vault.schemas.messages import Completion, Message, ToolCall


def _digest_with_calls(calls: list[tuple[str, dict[str, Any]]]) -> dict[str, Any]:
    return {
        "messages": [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": f"call_{i}", "name": name, "arguments": args}
                    for i, (name, args) in enumerate(calls)
                ],
                "tool_call_id": None,
                "name": None,
            }
        ],
        "tools": [],
    }


@pytest.mark.unit
def test_classify_tool_name_divergence() -> None:
    cur = _digest_with_calls([("calculator", {})])
    rec = _digest_with_calls([("search", {})])
    kind, _ = classify_divergence(cur, rec)
    assert kind == "tool-name"


@pytest.mark.unit
def test_classify_call_order_divergence() -> None:
    cur = _digest_with_calls([("a", {}), ("b", {})])
    rec = _digest_with_calls([("b", {}), ("a", {})])
    kind, _ = classify_divergence(cur, rec)
    assert kind == "call-order"


@pytest.mark.unit
def test_classify_arg_mismatch() -> None:
    cur = _digest_with_calls([("a", {"x": 1})])
    rec = _digest_with_calls([("a", {"x": 2})])
    kind, _ = classify_divergence(cur, rec)
    assert kind == "arg-mismatch"


@pytest.mark.unit
def test_classify_prompt_hash_when_calls_identical() -> None:
    same = _digest_with_calls([("a", {"x": 1})])
    kind, _ = classify_divergence(same, dict(same))
    assert kind == "prompt-hash"


def _interaction(messages: list[Message], completion: Completion, index: int) -> Interaction:
    return Interaction(
        index=index,
        request_key=request_key(messages),
        request_digest=normalize_request(messages),
        completion=completion,
    )


@pytest.mark.unit
def test_strict_cursor_returns_then_diverges() -> None:
    m0 = [Message(role="user", content="hello")]
    comp = Completion(content="hi")
    cassette = Cassette(name="t", match_mode="strict", interactions=(_interaction(m0, comp, 0),))
    cursor = CassetteCursor(cassette)
    assert cursor.next_completion(m0).content == "hi"

    # A second, unrecorded request -> exhausted divergence.
    with pytest.raises(DivergenceError) as exc:
        cursor.next_completion([Message(role="user", content="another")])
    assert exc.value.kind == "exhausted"


@pytest.mark.unit
def test_unordered_cursor_matches_out_of_order() -> None:
    a = [Message(role="user", content="A")]
    b = [Message(role="user", content="B")]
    cassette = Cassette(
        name="t",
        match_mode="unordered",
        interactions=(
            _interaction(a, Completion(content="ra"), 0),
            _interaction(b, Completion(content="rb"), 1),
        ),
    )
    cursor = CassetteCursor(cassette)
    # Ask for B first, then A — both match despite recorded order.
    assert cursor.next_completion(b).content == "rb"
    assert cursor.next_completion(a).content == "ra"
