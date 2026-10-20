"""`bdd migrate`: bring a project's ``.bdd/`` up to the schema this greenlight writes.

The schema version of ``.bdd/`` as a whole is ``version`` in ``.bdd/config.toml`` (absent means 1).
A project that is *newer* than this greenlight is refused by every command with a message to upgrade
greenlight; one that is *older* is refused by the commands that read or write its data until it is
migrated. A migration is a function ``(root) -> notes`` registered under the version it upgrades from;
it only has to turn version N data into version N+1 data. ``bdd migrate`` first copies ``.bdd/`` to
``.bdd-backup-v<N>`` next to it (and refuses to go on if that exists), runs the chain, and bumps
``version`` after each step, so a failed step leaves the project at the last good version.

The hooks never use this check: a hook that fails would only get in the way.
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path
from typing import Callable

from . import config as cfg
from .errors import UsageError
from .statecmd import guarded, project_root

Migration = Callable[[Path], list[str]]
MIGRATIONS: dict[int, Migration] = {}                  # from-version -> function; none yet: schema 1 is the first

_VERSION_LINE = re.compile(r"^version\s*=.*$", re.MULTILINE)
_FIRST_TABLE = re.compile(r"^\[", re.MULTILINE)


def set_version(root: Path, version: int) -> None:
    """Write ``version = N`` at the top level of config.toml, keeping everything else as it is."""
    path = root / cfg.BDD_DIR / "config.toml"
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    table = _FIRST_TABLE.search(text)
    top = text[:table.start()] if table else text
    line = f"version = {version}"
    if _VERSION_LINE.search(top):
        top = _VERSION_LINE.sub(line, top, count=1)
    else:
        top = f"{line}\n{top}"
    path.write_text(top + (text[table.start():] if table else ""), encoding="utf-8", newline="\n")


def backup(root: Path, version: int) -> Path:
    target = root / f"{cfg.BDD_DIR}-backup-v{version}"
    if target.exists():
        raise UsageError(f"{target.name} already exists; move it away before migrating again")
    shutil.copytree(root / cfg.BDD_DIR, target)
    return target


def plan(version: int) -> list[int]:
    """The versions to upgrade from, in order; refuses a chain with a missing step."""
    steps = list(range(version, cfg.SCHEMA_VERSION))
    missing = [v for v in steps if v not in MIGRATIONS]
    if missing:
        raise UsageError(f"no migration from schema {missing[0]}; the project cannot be upgraded automatically")
    return steps


def run(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="bdd migrate", description="Upgrade .bdd/ to the current schema.")
    ap.add_argument("--dry-run", action="store_true", help="say what would happen and change nothing")
    args = ap.parse_args(argv)
    try:
        return guarded("migrate", lambda: do_migrate(project_root(), args.dry_run))
    except cfg.ConfigError as exc:                      # a project newer than this greenlight, or a broken config
        print(f"bdd migrate: {exc}", file=sys.stderr)
        return 2


def do_migrate(root: Path, dry_run: bool) -> int:
    version = cfg.load(root).version                    # a newer project raises here, with the upgrade message
    if version == cfg.SCHEMA_VERSION:
        print(f"already at schema {version}; nothing to do")
        return 0
    steps = plan(version)
    if dry_run:
        print(f"would migrate schema {version} to {cfg.SCHEMA_VERSION} in {len(steps)} step(s): "
              + ", ".join(f"{v} -> {v + 1}" for v in steps))
        return 0
    saved = backup(root, version)
    print(f"backup: {saved.name}")
    for v in steps:
        for note in MIGRATIONS[v](root):
            print(f"  {v} -> {v + 1}: {note}")
        set_version(root, v + 1)
        print(f"schema {v + 1}")
    return 0


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))
