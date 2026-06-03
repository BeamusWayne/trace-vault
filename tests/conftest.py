"""Shared pytest fixtures and the offline-invariant guard.

This conftest installs a network sentinel that fails ANY test which attempts a
real socket connection. trace-vault's promise is that the default path never
touches the network; we enforce that promise rather than trusting it.
"""

from __future__ import annotations

import socket

import pytest

_ALLOWED_HOSTS = {"127.0.0.1", "::1", "localhost"}


class NetworkUseInTestError(RuntimeError):
    """Raised when a test attempts a non-local network connection."""


@pytest.fixture(autouse=True)
def _block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Block outbound non-local sockets for every test (autouse)."""
    real_connect = socket.socket.connect

    def guarded_connect(self, address, *args, **kwargs):  # type: ignore[no-untyped-def]
        host = address[0] if isinstance(address, tuple) else str(address)
        if host not in _ALLOWED_HOSTS:
            raise NetworkUseInTestError(
                f"Network blocked in tests: attempted connection to {host!r}. "
                "trace-vault's default path must stay offline."
            )
        return real_connect(self, address, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
