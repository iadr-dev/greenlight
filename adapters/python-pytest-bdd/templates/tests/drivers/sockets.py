"""Block real outbound network connections during a scenario (loopback stays allowed)."""
from __future__ import annotations

import socket
from contextlib import contextmanager

from .errors import OutboundNetworkBlocked

LOOPBACK = {"127.0.0.1", "::1", "localhost", "testserver"}


@contextmanager
def block_network(allowed: set[str] = frozenset()):
    original = socket.socket.connect

    def guarded(self, address, *args, **kwargs):
        host = address[0] if isinstance(address, tuple) else str(address)
        if self.family == getattr(socket, "AF_UNIX", None) or host in LOOPBACK | set(allowed):
            return original(self, address, *args, **kwargs)
        raise OutboundNetworkBlocked(f"a real connection to {host} was attempted; stub the dependency (Given ... responds to ...)")

    socket.socket.connect = guarded
    try:
        yield
    finally:
        socket.socket.connect = original
