"""Optional real LLM adapter. Not on the offline default path.

This module is imported lazily and only when you opt in with an API key; the
default Fake/Cassette path never touches it, so the offline test suite stays
offline. It is excluded from coverage for the same reason.

One OpenAI-compatible adapter covers OpenAI, Ollama, vLLM, Groq, Together, and
any other Chat Completions endpoint via ``base_url``. (An Anthropic adapter
follows the same shape.)
"""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
from typing import Any

from ..errors import TraceVaultError
from ..schemas.messages import Completion, Message, ToolCall, ToolSpec


def _messages_to_openai(messages: Sequence[Message]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for message in messages:
        if message.role == "assistant" and message.tool_calls:
            out.append(
                {
                    "role": "assistant",
                    "content": message.content or None,
                    "tool_calls": [
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {
                                "name": call.name,
                                "arguments": json.dumps(call.arguments),
                            },
                        }
                        for call in message.tool_calls
                    ],
                }
            )
        elif message.role == "tool":
            out.append(
                {
                    "role": "tool",
                    "tool_call_id": message.tool_call_id,
                    "content": message.content,
                }
            )
        else:
            out.append({"role": message.role, "content": message.content})
    return out


def _tools_to_openai(tools: Sequence[ToolSpec]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters or {"type": "object", "properties": {}},
            },
        }
        for tool in tools
    ]


class OpenAICompatibleProvider:
    """Chat Completions adapter for OpenAI / Ollama / vLLM / Groq / Together / ..."""

    name = "openai-compatible"

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        *,
        api_key_env: str = "OPENAI_API_KEY",
        base_url: str | None = None,
    ) -> None:
        self.model = model
        self._api_key_env = api_key_env
        self._base_url = base_url

    def complete(
        self, messages: Sequence[Message], tools: Sequence[ToolSpec] = ()
    ) -> Completion:
        try:
            from openai import OpenAI  # lazy: optional dependency
        except ImportError as exc:  # pragma: no cover
            raise TraceVaultError(
                "OpenAICompatibleProvider needs the 'openai' extra: pip install "
                "'trace-vault[openai]'"
            ) from exc

        client = OpenAI(api_key=os.environ.get(self._api_key_env, "x"), base_url=self._base_url)
        response = client.chat.completions.create(
            model=self.model,
            messages=_messages_to_openai(messages),
            tools=_tools_to_openai(tools) or None,
        )
        choice = response.choices[0].message
        calls = tuple(
            ToolCall(
                id=tc.id,
                name=tc.function.name,
                arguments=json.loads(tc.function.arguments or "{}"),
            )
            for tc in (choice.tool_calls or [])
        )
        return Completion(content=choice.content or "", tool_calls=calls)
