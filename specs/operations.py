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
    "report": [*BDD, "report"],
    "add the .NET adapter": [*BDD, "adapter", "apply", "dotnet-reqnroll"],
    "add the Node adapter": [*BDD, "adapter", "apply", "ts-cucumber-js"],
    "route": [*BDD, "route"],
    "classify": [*BDD, "classify"],
    "helpers": [*BDD, "helpers"],
    "docs": [*BDD, "docs"],
    "cost": [*BDD, "cost"],
    "subagent stop": [*BDD, "subagent-stop"],
    "doctor": [*BDD, "doctor"],
    "guard": [*BDD, "guard"],
    "init": [*BDD, "init"],
    "add the standards": [*BDD, "init", "--standards"],
    "approve": [*BDD, "approve"],
    "the prompt check": [*BDD, "tripwire", "--accept"],
    "the tool-call check": [*BDD, "tripwire"],
    "the approval hook": [*BDD, "approve", "--from-hook"],
}

LIB: dict[str, str] = {}

# Files a scenario can create or look at, by logical name. Each is relative to the scenario's workspace.
FILES: dict[str, str] = {
    "project config": ".bdd/config.toml",
    "newer project config": ".bdd/config.toml",
    "rules": ".bdd/features/FEAT-007-discounts/rules.md",
    "test design": ".bdd/features/FEAT-007-discounts/test-design.md",
    "tasks": ".bdd/features/FEAT-007-discounts/tasks.md",
    "helpers record": ".bdd/helpers.json",
    "docs record": ".bdd/features/FEAT-007-discounts/docs-consulted.json",
    "feature file": "features/discounts.feature",
    "discounts state": ".bdd/features/FEAT-007-discounts/state.json",
    "step file": "steps/steps.py",
    "lock record": ".bdd/features/FEAT-007-discounts/lock.json",
    "second feature file": "features/refunds.feature",
    "second rules": ".bdd/features/FEAT-008-refunds/rules.md",
    "second step file": "steps/refunds.py",
    "second lock record": ".bdd/features/FEAT-008-refunds/lock.json",
    "support file": "steps/conftest.py",
    "plumbing lock record": ".bdd/plumbing.lock.json",
    "package manifest": "package.json",
    "pubspec manifest": "pubspec.yaml",
    ".NET lock file": "tests/packages.lock.json",
    "Node lock file": "tests/pnpm-lock.yaml",
    "first feature state": ".bdd/features/FEAT-001-sign-in/state.json",
    "second feature state": ".bdd/features/FEAT-002-sign-up/state.json",
    "discounts state": ".bdd/features/FEAT-007-discounts/state.json",
    "recorded run": ".bdd/.runs/FEAT-007/latest.json",
    "agent notes": ".bdd/.runs/agents.jsonl",
    "agent transcript": "transcripts/project/s/subagents/agent-x.jsonl",
    "session transcript": "transcripts/project/s.jsonl",
    "plugin manifest": "plugin/.claude-plugin/plugin.json",
    "plugin guard": "plugin/tools/bdd/bddlib/guard.py",
    "updated plugin manifest": "claude-home/plugins/cache/gl/greenlight/1.2.2/.claude-plugin/plugin.json",
    "copied plugin manifest": "plugin-copy/.claude-plugin/plugin.json",
    "copied plugin guard": "plugin-copy/tools/bdd/bddlib/guard.py",
    "acknowledging session transcript": "claude-home/projects/project/s.jsonl",
    "integrity record": ".bdd/.integrity/violations.json",
    "Claude Code plugin record": "claude-home/plugins/installed_plugins.json",
    "call record": ".bdd/.integrity/calls.json",
}

ERRORS: dict[str, ErrorRule] = {
    "usage error": ErrorRule(exit_code=2),
    "violations found": ErrorRule(exit_code=1),
    "refused": ErrorRule(exit_code=2),
    "integrity violation": ErrorRule(exit_code=2, text="integrity check failed"),
}
