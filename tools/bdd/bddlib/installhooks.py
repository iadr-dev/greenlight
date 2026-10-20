"""`bdd install-hooks codex`: wire greenlight's hooks into Codex.

    bdd install-hooks codex                  show the hook file entries and where they would go (changes nothing)
    bdd install-hooks codex --apply          write them (merged into the file, never replacing anything else)
    bdd install-hooks codex --uninstall      take out exactly the entries greenlight added
    --project                                 use <project>/.codex/hooks.json instead of ~/.codex/hooks.json

Codex reads its hooks only from the person's own configuration, so this is the person's command: it shows what it
will write, writes only on ``--apply``, and an agent is not allowed to run it (the guard refuses, and the tripwire
reports a change to the file whatever made it). Codex asks the person to review and trust new hooks the first time
it loads them; nothing here can do that for them.

The entries call the bdd wrapper of this installation: ``sh "<plugin>/tools/bdd/bdd" codex-hook``. A POSIX ``sh``
is therefore needed, as for the Claude Code hooks.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

from . import claudepaths
from . import config as cfg
from .errors import UsageError

OWN_WORD = "codex-hook"
HOOK_FILE = "hooks.json"
EVENTS = {"PreToolUse": "*", "PostToolUse": "*", "UserPromptSubmit": None}
TIMEOUT_SECONDS = 30
STATUS = "greenlight"


def wrapper_path() -> Path:
    return Path(__file__).resolve().parents[1] / "bdd"


def command() -> str:
    return f'sh "{wrapper_path().as_posix()}" {OWN_WORD}'


def group(event: str) -> dict:
    entry = {"type": "command", "command": command(), "timeout": TIMEOUT_SECONDS, "statusMessage": STATUS}
    matcher = EVENTS[event]
    return {"hooks": [entry]} if matcher is None else {"matcher": matcher, "hooks": [entry]}


def snippet() -> dict:
    return {"hooks": {event: [group(event)] for event in EVENTS}}


def is_ours(item: object) -> bool:
    """Is this hook group one greenlight added: a command that runs ``bdd codex-hook``?"""
    inner = item.get("hooks") if isinstance(item, dict) else None
    return isinstance(inner, list) and any(
        isinstance(h, dict) and isinstance(h.get("command"), str) and h["command"].rstrip().endswith(f"bdd\" {OWN_WORD}")
        for h in inner)


def target(project: Path | None) -> Path:
    return (project / ".codex" if project else claudepaths.codex_home()) / HOOK_FILE


def load(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except ValueError as exc:
        raise UsageError(f"{path} is not valid JSON ({exc}); fix it first, nothing was changed") from exc
    if not isinstance(data, dict) or not isinstance(data.get("hooks", {}), dict):
        raise UsageError(f"{path} does not have the shape {{\"hooks\": {{...}}}}; nothing was changed")
    return data


def merged(data: dict) -> dict:
    """``data`` with greenlight's groups in place of any it had before, and everything else untouched."""
    result = json.loads(json.dumps(data))
    hooks = result.setdefault("hooks", {})
    for event in EVENTS:
        groups = hooks.get(event, [])
        if not isinstance(groups, list):
            raise UsageError(f"hooks.{event} in the file is not a list; nothing was changed")
        hooks[event] = [g for g in groups if not is_ours(g)] + [group(event)]
    return result


def without_ours(data: dict) -> dict:
    result = json.loads(json.dumps(data))
    kept: dict = {}
    for event, groups in result.get("hooks", {}).items():
        remaining = [g for g in groups if not is_ours(g)] if isinstance(groups, list) else groups
        if remaining or not isinstance(groups, list):
            kept[event] = remaining
    if "hooks" in result:
        result["hooks"] = kept
    return result


def write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=".hooks-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(data, handle, indent=2)
            handle.write("\n")
        os.replace(name, path)
    except OSError:
        Path(name).unlink(missing_ok=True)
        raise


def installed(path: Path) -> bool:
    """Does the hook file at ``path`` hold all of greenlight's groups?"""
    try:
        hooks = load(path).get("hooks", {})
    except UsageError:
        return False
    return all(isinstance(hooks.get(event), list) and any(is_ours(g) for g in hooks[event]) for event in EVENTS)


def run(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="bdd install-hooks", description="Wire greenlight's hooks into Codex.")
    ap.add_argument("tool", choices=["codex"])
    ap.add_argument("--apply", action="store_true", help="write the entries (default: only show them)")
    ap.add_argument("--uninstall", action="store_true", help="remove the entries greenlight added")
    ap.add_argument("--project", action="store_true", help="use <project>/.codex/hooks.json instead of the home folder")
    args = ap.parse_args(argv)
    if args.apply and args.uninstall:
        print("bdd install-hooks: choose --apply or --uninstall, not both", file=sys.stderr)
        return 2
    project = cfg.find_root() if args.project else None
    if args.project and project is None:
        print("bdd install-hooks: --project needs a greenlight project (no .bdd/ found here or above)", file=sys.stderr)
        return 2
    path = target(project)
    try:
        current = load(path)
        if args.uninstall:
            return uninstall(path, current)
        return apply(path, current, args.apply)
    except (UsageError, OSError) as exc:
        print(f"bdd install-hooks: {exc}", file=sys.stderr)
        return 2


def uninstall(path: Path, current: dict) -> int:
    remaining = without_ours(current)
    changed = remaining != current
    if changed and remaining.get("hooks") == {} and set(remaining) <= {"hooks"}:
        path.unlink()
    elif changed:
        write(path, remaining)
    print(f"{path}: " + ("greenlight's hook entries removed" if changed else "nothing of greenlight's to remove"))
    return 0


def apply(path: Path, current: dict, write_it: bool) -> int:
    proposal = merged(current)
    if not write_it:
        print(f"Would write to {path}:\n{json.dumps(snippet(), indent=2)}\n\nThis shows the greenlight entries; "
              "entries of yours in the file are kept. Run again with --apply to write them. Codex will ask you to "
              "review and trust the hooks the first time it loads them.")
    elif proposal == current:
        print(f"{path}: greenlight's hook entries are already in place")
    else:
        write(path, proposal)
        print(f"{path}: greenlight's hook entries written. Start Codex and review and trust the hooks when it asks. "
              "`bdd doctor` reports when they have run.")
    return 0
