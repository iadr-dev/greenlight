"""The map from the logical names in greenlight's own specs to the real command-line tool.

greenlight specifies its own behaviour the way it asks its users to: the features contain no paths, flags or exit
codes; they say `alice runs lint` and `the command fails with violations found`, and this file knows what those
mean. The command under test is `tools/bdd/bdd`, run in a fresh workspace per scenario.

This is the one project-specific file: `run_specs.py` copies it over the adapter's `tests/drivers/operations.py` in a
scaffold of the `python-pytest-bdd` adapter, which is exactly what a user's project does.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

REPO = Path(os.environ["GREENLIGHT_REPO"])        # set by run_specs.py
BDD = ["sh", str(REPO / "tools" / "bdd" / "bdd")]


@dataclass(frozen=True)
class Api:
    method: str
    path: str


@dataclass(frozen=True)
class ErrorRule:
    """What a logical error looks like. Any field that is set must match."""
    statuses: tuple[int, ...] = ()
    exception: str = ""
    exit_code: int | None = None
    text: str = ""


API: dict[str, Api] = {}

COMMANDS: dict[str, list[str]] = {
    "lint": [*BDD, "lint"],
    "lock": [*BDD, "lock"],
    "unlock": [*BDD, "unlock"],
    "trace": [*BDD, "trace"],
    "status": [*BDD, "status"],
    "migrate": [*BDD, "migrate"],
    "gate": [*BDD, "gate"],
    "create feature": [*BDD, "state", "init"],
    "detect adapters": [*BDD, "init", "--detect"],
}

LIB: dict[str, str] = {}

# Files a scenario can create or look at, by logical name. Each is relative to the scenario's workspace.
FILES: dict[str, str] = {
    "project config": ".bdd/config.toml",
    "newer project config": ".bdd/config.toml",
    "rules": ".bdd/features/FEAT-007-discounts/rules.md",
    "test design": ".bdd/features/FEAT-007-discounts/test-design.md",
    "feature file": "features/discounts.feature",
    "step file": "steps/steps.py",
    "lock record": ".bdd/features/FEAT-007-discounts/lock.json",
    "package manifest": "package.json",
}

ERRORS: dict[str, ErrorRule] = {
    "usage error": ErrorRule(exit_code=2),
    "violations found": ErrorRule(exit_code=1),
}
