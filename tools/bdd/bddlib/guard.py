"""`bdd guard`: the PreToolUse hook that keeps the process honest.

Claude Code runs it before file-editing tools, Bash, and the tools that can schedule or send
prompts. It reads the hook payload (JSON) on stdin and either allows (exit 0, no output) or
blocks (exit 2, reason on stderr, which the model sees).

What it blocks inside a greenlight project:

* edits to files locked by a feature (approved specs, bound steps and drivers);
* edits to the CLI-managed data files (``state.json``, ``lock.json``, enforcement markers);
* writes outside what the calling agent is allowed to touch (see ``AGENT_WRITES``);
* shell commands that write to either of the above (best effort: a shell can always do things
  a hook cannot foresee, which is why ``bdd lock --check`` remains the guarantee);
* scheduling or sending prompts that contain an approval command, because such prompts reach the
  approval hook looking exactly like something the user typed.

Outside a project (no ``.bdd`` directory) it does nothing.
"""
from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from . import config as cfg
from . import lockfile, store
from .errors import StoreError

WRITE_TOOLS = {"Edit": "file_path", "Write": "file_path", "MultiEdit": "file_path", "NotebookEdit": "notebook_path"}
INJECTION_TOOLS = {"CronCreate", "ScheduleWakeup", "SendMessage", "Skill", "RemoteTrigger"}
AGENT_PREFIX = "greenlight:"
CASE_INSENSITIVE_FS = sys.platform in ("win32", "darwin")

# Which kinds of file each greenlight agent may write. The orchestrator (no agent_type) may write
# anything that is not locked or managed. Categories: data (.bdd/), features, steps, production.
AGENT_WRITES = {
    "product-analyst": {"data"},
    "qa-designer": {"data", "features"},
    "system-analyst": {"data"},
    "step-engineer": {"data", "steps"},
    "implementer": {"data", "production"},
    "spec-auditor": set(),
}
MANAGED_NAMES = {"state.json", "lock.json"}
MANAGED_SUFFIXES = (".lock", ".tmp")

_APPROVAL_TEXT = re.compile(r"greenlight:(?:approve|reject)\b", re.IGNORECASE)
_NOISE = re.compile(r"\d?>\s*/dev/null|\d>&\d|&>\s*/dev/null|2>\s*nul\b", re.IGNORECASE)
_SHELL_WRITES = re.compile(
    r"(?:^|[\s;&|(])(?:sed\s+(?:-\w*i|--in-place)|perl\s+-\w*i|tee|cp|mv|rm|truncate|dd|install|ln|chmod|touch|"
    r"git\s+(?:checkout|restore|reset|stash|apply|rm|mv|clean)|Set-Content|Add-Content|Out-File|"
    r"Remove-Item|Move-Item|Copy-Item|New-Item|del|erase|move|copy)\b|>>?|write_text|write_bytes|"
    r"open\([^)]*[\"'][wa+]|\.write\(|\.writelines\(|os\.(?:remove|rename|replace|unlink)|shutil\.",
    re.IGNORECASE)


def path_key(path: Path | str) -> str:
    """A comparison key that is the same for every spelling of the same file."""
    resolved = os.path.realpath(path)
    key = resolved.replace("\\", "/")
    return key.casefold() if CASE_INSENSITIVE_FS else key


@dataclass(frozen=True)
class Locked:
    feature: str
    scope: str
    path: Path


class Project:
    """What the guard needs to know about the project: locked files, data files, directories."""

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.config = cfg.load(self.root)
        self.locked: dict[str, Locked] = {}
        self.load_locks()

    def load_locks(self) -> None:
        for feature_dir in sorted(store.features_dir(self.root).glob("FEAT-*")):
            lock_path = feature_dir / lockfile.LOCK_FILE
            if not lock_path.is_file():
                continue
            data = store.read_json(lock_path, "lock file")        # StoreError propagates: fail closed
            for scope, entry in data.get("scopes", {}).items():
                for rel in entry.get("files", {}):
                    self.locked[path_key(self.root / rel)] = Locked(data.get("feature", feature_dir.name), scope,
                                                                    self.root / rel)

    def relative(self, path: Path) -> str:
        try:
            return Path(os.path.realpath(path)).relative_to(self.root).as_posix()
        except ValueError:
            return path.as_posix()

    def is_data(self, path: Path) -> bool:
        key, data_root = path_key(path), path_key(self.root / cfg.BDD_DIR)
        if not key.startswith(data_root + "/"):
            return False
        inside = key[len(data_root) + 1:]
        name = inside.rsplit("/", 1)[-1]
        return inside.startswith(".enforcement/") or name in MANAGED_NAMES or name.endswith(MANAGED_SUFFIXES)

    def category(self, path: Path) -> str:
        key = path_key(path)
        if key.startswith(path_key(self.root / cfg.BDD_DIR) + "/"):
            return "data"
        for category, dirs in (("features", self.config.feature_dirs), ("steps", self.config.step_dirs)):
            if any(key.startswith(path_key(d) + "/") for d in dirs):
                return category
        return "production"


def locked_message(project: Project, path: Path, lock: Locked) -> str:
    return (f"greenlight: {project.relative(path)} is locked by {lock.feature} ({lock.scope}). Approved specs and "
            "bound steps are read-only while a feature is in progress. If the spec or a step is really wrong, "
            "stop and raise a change request with the user; unlocking needs a recorded reason "
            f"(bdd unlock {lock.feature} --scope {lock.scope} --reason \"...\").")


def managed_message(project: Project, path: Path) -> str:
    return (f"greenlight: {project.relative(path)} is managed by the bdd command line (state, locks, approvals). "
            "Use the bdd commands instead of editing it.")


def agent_name(payload: dict) -> str | None:
    agent_type = payload.get("agent_type") or ""
    return agent_type[len(AGENT_PREFIX):] if agent_type.startswith(AGENT_PREFIX) else None


def check_file_write(project: Project, path: Path, agent: str | None) -> str | None:
    lock = project.locked.get(path_key(path))
    if lock:
        return locked_message(project, path, lock)
    if project.is_data(path):
        return managed_message(project, path)
    allowed = AGENT_WRITES.get(agent) if agent else None
    category = project.category(path)
    if allowed is not None and category not in allowed:
        what = ", ".join(sorted(allowed)) or "nothing (it is read-only)"
        return (f"greenlight: the {agent} agent may not write {category} files ({project.relative(path)}); "
                f"it may write: {what}.")
    return None


def mentioned_protected(project: Project, command: str) -> tuple[Path, Locked | None] | None:
    """A locked or managed file that the command names, if there is one.

    Matches on the file name anywhere in the command text, whatever the quoting or slash style
    (``features/a.feature``, ``'a.feature'`` inside a Python one-liner, a backslash path), so a
    command that ``cd``s first or builds the path in a script is still recognised. A false alarm
    only produces a clear refusal; a miss would defeat the point."""
    text = command.replace("\\", "/").casefold()
    by_name = {lock.path.name.casefold(): lock for lock in project.locked.values()}
    names = sorted(set(by_name) | MANAGED_NAMES, key=len, reverse=True)
    match = re.search(r"(?<![\w.-])(?:" + "|".join(re.escape(n) for n in names) + r")(?![\w-])", text)
    if match:
        name = match.group(0)
        lock = by_name.get(name)
        return (lock.path if lock else project.root / cfg.BDD_DIR / name), lock
    if "/.enforcement/" in text:
        return project.root / cfg.BDD_DIR / ".enforcement", None
    return None


def check_bash(project: Project, command: str) -> str | None:
    """Best effort: block a command that both names a protected file and looks like it writes."""
    scrubbed = _NOISE.sub(" ", command)
    if not _SHELL_WRITES.search(scrubbed):
        return None
    hit = mentioned_protected(project, scrubbed)
    if hit is None:
        return None
    target, lock = hit
    base = locked_message(project, target, lock) if lock else managed_message(project, target)
    return base + " (This shell command looks like it writes to it.)"


def check_injection(tool_input: dict) -> str | None:
    if _APPROVAL_TEXT.search(json.dumps(tool_input, ensure_ascii=False)):
        return ("greenlight: approvals can only be given by the person typing /greenlight:approve or "
                "/greenlight:reject themselves. Scheduling, sending or invoking that command from a tool "
                "would let the AI approve its own work, so it is not allowed. Ask the user to type it.")
    return None


def evaluate(payload: dict) -> str | None:
    """The reason to block this tool call, or None to allow it."""
    tool, tool_input = payload.get("tool_name"), payload.get("tool_input") or {}
    cwd = Path(payload.get("cwd") or os.getcwd())
    root = cfg.find_root(cwd)
    if root is None:
        return None
    if tool in INJECTION_TOOLS:
        return check_injection(tool_input)
    try:
        project = Project(root)
    except StoreError as exc:
        return f"greenlight: cannot enforce locks because {exc}. Restore the file (for example with git) and retry."
    if tool in WRITE_TOOLS and tool_input.get(WRITE_TOOLS[tool]):
        raw = Path(tool_input[WRITE_TOOLS[tool]])
        return check_file_write(project, raw if raw.is_absolute() else cwd / raw, agent_name(payload))
    if tool == "Bash" and tool_input.get("command"):
        return check_bash(project, tool_input["command"])
    return None


def main(argv: list[str]) -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        reason = evaluate(payload)
    except (ValueError, OSError, KeyError, TypeError) as exc:    # a bug or a transient I/O problem: do not lock users out
        print(f"greenlight guard: could not evaluate this call ({type(exc).__name__}: {exc}); allowing it",
              file=sys.stderr)
        return 0
    if reason:
        print(reason, file=sys.stderr)
        return 2
    return 0
