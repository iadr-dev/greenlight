"""The map from the logical names in greenlight's own specs to the real command-line tool.

greenlight specifies its own behaviour the way it asks its users to: the features contain no paths, flags or exit
codes; they say `alice runs lint` and `the command fails with violations found`, and this file knows what those
mean. The command under test is `tools/bdd/bdd`, run in a fresh workspace per scenario.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
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
}

ERRORS: dict[str, ErrorRule] = {
    "usage error": ErrorRule(exit_code=2),
    "violations found": ErrorRule(exit_code=1),
}
