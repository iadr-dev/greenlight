"""Calling a public function by its logical name; the return value or the raised error is kept."""
from __future__ import annotations

import importlib
from typing import Any

from .compare import assert_equal, assert_subset
from .errors import NotMapped
from .operations import LIB
from .world import Outcome, World


def resolve(operation: str):
    if operation not in LIB:
        raise NotMapped("library operation", operation, LIB)
    module, _, attribute = LIB[operation].partition(":")
    return getattr(importlib.import_module(module), attribute)


def call(world: World, operation: str, data: Any) -> Outcome:
    function = resolve(operation)                    # an unmapped or missing function is a failure, not a result
    try:
        if isinstance(data, dict):
            value = function(**data)
        elif isinstance(data, list):
            value = function(*data)
        else:
            value = function(data)
        world.outcome = Outcome("lib", body=value)
    except Exception as error:                      # the scenario decides whether this error was wanted
        world.outcome = Outcome("lib", exception=error)
    return world.outcome


def assert_result(world: World, expected: Any, exact: bool) -> None:
    outcome = world.last("lib")
    assert outcome.exception is None, f"the call raised {type(outcome.exception).__name__}: {outcome.exception}"
    (assert_equal if exact else assert_subset)(outcome.body, expected, "the result")


def assert_fails(world: World, error: str) -> None:
    outcome = world.last("lib")
    assert outcome.exception is not None, f"the call should fail but returned {outcome.body!r}"
    assert outcome.matches_error(error), f"the call failed, but not with {error!r}: {type(outcome.exception).__name__}: {outcome.exception}"
