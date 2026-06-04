"""Providers, the model-agnostic seam.

Only the offline doubles are imported here. Real SDK adapters live in
``providers.real`` and are imported lazily (and only via optional extras) so the
default path never pulls a network client into the process.
"""

from __future__ import annotations

from .base import LLMProvider
from .cassette import CassetteProvider, RecordingProvider
from .fake import FakeProvider, KeyedFakeProvider, StochasticFakeProvider

__all__ = [
    "CassetteProvider",
    "FakeProvider",
    "KeyedFakeProvider",
    "LLMProvider",
    "RecordingProvider",
    "StochasticFakeProvider",
]
