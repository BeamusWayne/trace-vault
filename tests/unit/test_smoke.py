"""M0 smoke tests: the package imports and the schema invariants hold."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

import trace_vault as tv
from trace_vault.schemas import Completion, Message, ToolCall


@pytest.mark.unit
def test_version_is_exposed() -> None:
    assert tv.__version__ == "0.2.0"


@pytest.mark.unit
def test_schemas_are_frozen() -> None:
    m = Message(role="user", content="hi")
    with pytest.raises(ValidationError):
        m.content = "mutated"  # type: ignore[misc]


@pytest.mark.unit
def test_completion_is_final_distinguishes_tool_calls() -> None:
    assert Completion().is_final is True
    has_call = Completion(tool_calls=(ToolCall(id="c0", name="calc"),))
    assert has_call.is_final is False
