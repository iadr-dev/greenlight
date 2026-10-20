"""The map from the logical names used in features to this system. Features never contain paths, binaries or
module names. The step-engineer fills this in from the system map (system.md); the sample entries below
belong to the sample feature and can be deleted with it.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Api:
    method: str
    path: str          # may contain {field}, filled from the request data


@dataclass(frozen=True)
class ErrorRule:
    """What a logical error looks like. Any field that is set must match."""
    statuses: tuple[int, ...] = ()      # HTTP status codes
    exception: str = ""                 # exception class name
    exit_code: int | None = None        # process exit code
    text: str = ""                      # text in the response body, stderr or exception message


API: dict[str, Api] = {
    # "place order": Api("POST", "/orders"),
}

COMMANDS: dict[str, list[str]] = {
    # "export report": ["python", "-m", "myapp", "export"],
}

LIB: dict[str, str] = {
    "add": "tests.sample_domain:add",        # sample; "module:function"
}

FILES: dict[str, str] = {
    # "report": "out/report.txt",            # relative to the scenario workspace
}

ERRORS: dict[str, ErrorRule] = {
    "negative input": ErrorRule(exception="ValueError"),      # sample
    # "validation error": ErrorRule(statuses=(400, 422)),
}
