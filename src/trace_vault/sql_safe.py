"""Shared SQL-identifier validation.

Used by the database tools and the faithfulness graders, so the allowlist rule
lives in one place. Only identifiers (table and column names) pass through here;
values are always bound as query parameters.
"""

from __future__ import annotations

import re

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def safe_identifier(name: object) -> str:
    """Return ``name`` unchanged if it is a safe SQL identifier, else raise
    ``ValueError``."""
    text = str(name)
    if not _IDENTIFIER.match(text):
        raise ValueError(f"unsafe SQL identifier: {text!r}")
    return text
