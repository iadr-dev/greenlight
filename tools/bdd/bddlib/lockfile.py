"""Hash locks: the guarantee that approved specs and bound steps are not changed afterwards.

``lock.json`` (one per feature) records a SHA-256 for every locked file, in two scopes:

    spec   the approved ``.feature`` files
    bind   the step definitions and drivers that were proven red

The hook that blocks edits is a first line of defence; ``check`` is the guarantee, because a
shell command can always change a file behind a hook's back.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from . import store
from .errors import UsageError

SCOPES = ("spec", "bind")
LOCK_FILE = "lock.json"
_SKIP_DIRS = {"__pycache__", "node_modules", ".git"}


@dataclass(frozen=True)
class Violation:
    scope: str
    path: str
    kind: str  # changed | missing | added

    def __str__(self) -> str:
        what = {"changed": "changed since it was locked", "missing": "was locked but no longer exists",
                "added": "is tagged for this feature but was never locked"}[self.kind]
        return f"[{self.scope}] {self.path} {what}"


def file_digest(path: Path) -> str:
    """SHA-256 of the file. Text files are hashed with LF endings so that a checkout that
    converted CRLF (Windows autocrlf) is not mistaken for tampering."""
    data = path.read_bytes()
    if b"\x00" not in data:
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def relative(root: Path, path: Path) -> str:
    """POSIX path of ``path`` relative to ``root``; refuses anything outside the project."""
    resolved = path.resolve()
    try:
        return resolved.relative_to(root.resolve()).as_posix()
    except ValueError:
        raise UsageError(f"{path} is outside the project ({root}); only project files can be locked") from None


def expand(root: Path, paths: list[Path]) -> list[Path]:
    """Files named by ``paths``; directories are searched recursively (hidden and cache dirs skipped)."""
    files: list[Path] = []
    for p in paths:
        target = p if p.is_absolute() else Path.cwd() / p
        if target.is_dir():
            files += sorted(f for f in target.rglob("*") if f.is_file() and not any(
                part.startswith(".") or part in _SKIP_DIRS for part in f.relative_to(target).parts))
        elif target.is_file():
            files.append(target)
        else:
            raise UsageError(f"{p} does not exist")
    if not files:
        raise UsageError("nothing to lock: no files found")
    relative_paths = {relative(root, f): f for f in files}      # also validates they are inside the project
    return [relative_paths[k] for k in sorted(relative_paths)]


def read_lock(feature_dir: Path, feature_id: str) -> dict:
    path = feature_dir / LOCK_FILE
    if path.exists():
        return store.read_json(path, "lock file")
    return {"schema": store.SCHEMA, "feature": feature_id, "scopes": {}, "history": []}


def lock(root: Path, feature_dir: Path, feature_id: str, scope: str, paths: list[Path]) -> dict[str, str]:
    """Lock ``paths`` under ``scope``. A locked scope must be unlocked (with a reason) first."""
    if scope not in SCOPES:
        raise UsageError(f"scope must be one of {', '.join(SCOPES)}")
    data = read_lock(feature_dir, feature_id)
    if scope in data["scopes"]:
        raise UsageError(f"{feature_id} {scope} is already locked; use `bdd unlock` with a reason to change it")
    files = {relative(root, f): file_digest(f) for f in expand(root, paths)}
    now = store.utc_now()
    data["scopes"][scope] = {"locked_at": now, "files": files}
    data["history"].append({"event": "lock", "scope": scope, "at": now, "files": sorted(files)})
    store.write_json(feature_dir / LOCK_FILE, data)
    return files


def unlock(feature_dir: Path, feature_id: str, scope: str, reason: str) -> None:
    if not reason.strip():
        raise UsageError("unlock needs a --reason: it is recorded in the lock history")
    data = read_lock(feature_dir, feature_id)
    if scope not in data["scopes"]:
        raise UsageError(f"{feature_id} {scope} is not locked")
    released = sorted(data["scopes"].pop(scope)["files"])
    data["history"].append({"event": "unlock", "scope": scope, "at": store.utc_now(),
                            "reason": reason.strip(), "files": released})
    store.write_json(feature_dir / LOCK_FILE, data)


def check(root: Path, feature_dir: Path, feature_id: str, scopes: tuple[str, ...] = SCOPES,
          current_spec_files: list[str] | None = None) -> list[Violation]:
    """Compare locked files with the disk. ``current_spec_files`` (project-relative paths of the
    feature files tagged for this feature right now) also detects spec files added after locking."""
    data = read_lock(feature_dir, feature_id)
    violations: list[Violation] = []
    for scope in (s for s in scopes if s in data["scopes"]):
        locked = data["scopes"][scope]["files"]
        for rel, digest in sorted(locked.items()):
            target = root / rel
            if not target.is_file():
                violations.append(Violation(scope, rel, "missing"))
            elif file_digest(target) != digest:
                violations.append(Violation(scope, rel, "changed"))
        if scope == "spec" and current_spec_files is not None:
            violations += [Violation(scope, rel, "added") for rel in sorted(set(current_spec_files) - set(locked))]
    return violations
