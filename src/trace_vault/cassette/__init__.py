"""Cassette engine: normalize, match, record, replay."""

from __future__ import annotations

from .matcher import CassetteCursor, classify_divergence
from .normalize import (
    normalize_messages,
    normalize_request,
    request_key,
    scrub_text,
    tail_key,
)
from .store import load_cassette, save_cassette

__all__ = [
    "CassetteCursor",
    "classify_divergence",
    "load_cassette",
    "normalize_messages",
    "normalize_request",
    "request_key",
    "save_cassette",
    "scrub_text",
    "tail_key",
]
