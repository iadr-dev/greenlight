"""Running a command by its logical name in the scenario workspace.

The table of a ``runs`` step has two columns, key and value. Keys: ``arg`` (repeat for several arguments),
``stdin``, and ``env.NAME``.
"""
from __future__ import annotations

import os
import subprocess

from .errors import NotMapped
from .operations import COMMANDS
from .world import Outcome, World

TIMEOUT_SECONDS = 60


def run(world: World, command: str, table: list[list[str]] | None) -> Outcome:
    if command not in COMMANDS:
        raise NotMapped("command", command, COMMANDS)
    words, stdin, env = list(COMMANDS[command]), None, dict(os.environ)
    for key, value in (table or [])[1:]:
        if key == "arg":
            words.append(value)
        elif key == "stdin":
            stdin = value
        elif key.startswith("env."):
            env[key[4:]] = value
        else:
            raise AssertionError(f"unknown key {key!r} in the command table (use arg, stdin or env.NAME)")
    done = subprocess.run(words, cwd=world.workspace.root, input=stdin, env=env, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=TIMEOUT_SECONDS)
    world.outcome = Outcome("cli", exit_code=done.returncode, stdout=done.stdout, stderr=done.stderr)
    return world.outcome


def assert_succeeds(world: World) -> None:
    outcome = world.last("cli")
    assert outcome.exit_code == 0, f"the command should succeed but exited {outcome.exit_code}: {outcome.stderr.strip()!r}"


def assert_fails(world: World, error: str) -> None:
    outcome = world.last("cli")
    assert outcome.exit_code != 0, "the command should fail but it succeeded"
    assert outcome.matches_error(error), f"the command failed, but not with {error!r}: exit {outcome.exit_code}, {outcome.stderr.strip()!r}"
