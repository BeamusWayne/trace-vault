"""Observability: a dependency-free in-memory tracer (+ optional OTel adapter)."""

from __future__ import annotations

from .tracer import InMemoryTracer, Span

__all__ = ["InMemoryTracer", "Span"]
