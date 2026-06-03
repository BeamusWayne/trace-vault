"""The agent layer: a thin loop, a toolset, and the assertable World."""

from __future__ import annotations

from .loop import SYSTEM_PROMPT, Agent
from .tools import ToolRegistry, default_registry
from .world import World

__all__ = [
    "SYSTEM_PROMPT",
    "Agent",
    "ToolRegistry",
    "World",
    "default_registry",
]
