"""Stubbed external dependencies.

Route the application's outbound calls through ``world.stubs.call(dependency, operation, request)`` (an
HTTP client wrapper, a gateway interface) or point a library such as ``respx`` at ``respond``. A call
the scenario did not stub fails the scenario.
"""
from __future__ import annotations

from typing import Any

from .compare import assert_subset
from .errors import UnstubbedCall


class Stubs:
    def __init__(self) -> None:
        self._responses: dict[tuple[str, str], Any] = {}
        self.calls: list[tuple[str, str, Any]] = []

    def respond(self, dependency: str, operation: str, response: Any) -> None:
        self._responses[(dependency, operation)] = response

    def call(self, dependency: str, operation: str, request: Any = None) -> Any:
        self.calls.append((dependency, operation, request))
        if (dependency, operation) not in self._responses:
            raise UnstubbedCall(f"{dependency} was asked to {operation} but the scenario did not stub it")
        return self._responses[(dependency, operation)]

    def assert_received(self, dependency: str, operation: str, expected: Any) -> None:
        requests = [r for d, o, r in self.calls if (d, o) == (dependency, operation)]
        assert requests, f"{dependency} never received {operation}; it received {[(d, o) for d, o, _ in self.calls]}"
        if expected in (None, [], {}):
            return
        problems = []
        for request in requests:
            try:
                assert_subset(request, expected, f"{dependency} {operation}")
                return
            except AssertionError as exc:
                problems.append(str(exc))
        raise AssertionError("; ".join(problems))
