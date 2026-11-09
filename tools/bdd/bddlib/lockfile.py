"""Hash locks: the guarantee that approved specs, bound steps and the shared test plumbing are not changed afterwards.

``lock.json`` (one per feature) records a SHA-256 for every file the feature locked, in two scopes:

    spec   the approved ``.feature`` files
    bind   the feature's own step definitions and drivers, proven red, and (``plumbing``) the digest of the
           plumbing lock they were bound against

``.bdd/plumbing.lock.json`` (one per project) records the shared test plumbing: the adapters' support files (runner
settings, package manifests) and the step and driver files the adapters ship. Every feature's tests run on it, so it
is locked once for the project, and a change to it is its own change (``bdd lock --plumbing``), after which every
feature reruns its scenarios once and none is reopened.

Every locked file in the step and driver folders has one owner: the plumbing, or the feature whose bind lock took it
first. A file no lock covers is a violation of every bound feature, except a step or driver file while another
feature is locked but not bound (between its approved examples and its bind lock, or reopened before it): that file
is presumed to be the binding feature's, and its bind lock takes it.

A bind scope without a ``plumbing`` entry was written before the plumbing lock existed: it is checked as it was
locked, and ``bdd migrate`` converts it.

The hook that blocks edits is a first line of defence; ``check`` is the guarantee, because a shell command can always
change a file behind a hook's back.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from . import config as cfg
from . import store
from .errors import UsageError

SCOPES = ("spec", "bind")
LOCK_FILE = "lock.json"
PLUMBING = "plumbing"                   # the owner, and the scope of a violation, of the shared test plumbing
PLUMBING_FILE = "plumbing.lock.json"
_SKIP_DIRS = {"__pycache__", "node_modules", ".git"}

_ADDED = {"spec": "is tagged for this feature but was never locked",
          "bind": "is in a step or driver folder, and neither a feature's bind lock nor the plumbing lock covers it",
          PLUMBING: "is shared test plumbing that the plumbing lock does not cover; lock it with "
                    "`bdd lock --plumbing --reason \"...\"`"}


@dataclass(frozen=True)
class Violation:
    scope: str
    path: str
    kind: str  # changed | missing | added

    def __str__(self) -> str:
        if self.kind == "added":
            return f"[{self.scope}] {self.path} {_ADDED[self.scope]}"
        if self.scope == PLUMBING:
            what = {"changed": "changed since the project locked it", "missing": "was locked by the project but no longer exists"}
            return (f"[{self.scope}] {self.path} is shared test plumbing and {what[self.kind]}; a change to it is "
                    "its own change: `bdd lock --plumbing --reason \"...\"`")
        what = {"changed": "changed since it was locked", "missing": "was locked but no longer exists"}
        return f"[{self.scope}] {self.path} {what[self.kind]}"


def file_digest(path: Path) -> str:
    """SHA-256 of the file. Text files are hashed with LF endings so that a checkout that
    converted CRLF (Windows autocrlf) is not mistaken for tampering."""
    data = path.read_bytes()
    if b"\x00" not in data:
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def files_digest(files: dict[str, str]) -> str:
    """One digest of a set of locked files (path -> digest)."""
    digest = hashlib.sha256()
    for rel in sorted(files):
        digest.update(f"{rel}\n{files[rel]}\n".encode("utf-8"))
    return digest.hexdigest()


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


def _write_scope(feature_dir: Path, feature_id: str, scope: str, files: dict[str, str], **extra: str) -> None:
    data = read_lock(feature_dir, feature_id)
    if scope in data["scopes"]:
        raise UsageError(f"{feature_id} {scope} is already locked; use `bdd unlock` with a reason to change it")
    now = store.utc_now()
    data["scopes"][scope] = {"locked_at": now, "files": files, **extra}
    data["history"].append({"event": "lock", "scope": scope, "at": now, "files": sorted(files)})
    store.write_json(feature_dir / LOCK_FILE, data)


def lock(root: Path, feature_dir: Path, feature_id: str, scope: str, paths: list[Path]) -> dict[str, str]:
    """Lock ``paths`` under ``scope``. A locked scope must be unlocked (with a reason) first. A bind lock takes only
    the files no other lock covers, with the support files as the shared plumbing (see ``lock_bind``)."""
    if scope not in SCOPES:
        raise UsageError(f"scope must be one of {', '.join(SCOPES)}")
    if scope == "bind":
        return lock_bind(root, feature_dir, feature_id, paths, support_files(root))[0]
    files = {relative(root, f): file_digest(f) for f in expand(root, paths)}
    _write_scope(feature_dir, feature_id, scope, files)
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


def bound_files(root: Path) -> list[str]:
    """Every file in the adapters' step and driver folders, and their support files, as they are now."""
    config = cfg.load(root)
    present = [p for p in (*config.step_dirs, *config.support_files) if p.exists()]
    return [relative(root, f) for f in expand(root, present)] if present else []


def support_files(root: Path) -> set[str]:
    """The adapters' support files (runner settings, package manifests) that exist now: plumbing by definition."""
    return {relative(root, f) for f in cfg.load(root).support_files if f.is_file()}


# -- the plumbing lock ---------------------------------------------------------------------------------------------

def plumbing_path(root: Path) -> Path:
    return root / cfg.BDD_DIR / PLUMBING_FILE


def read_plumbing(root: Path) -> dict:
    """The plumbing lock. ``files`` is there once it has been locked; ``unlocked`` holds when and why it was released."""
    path = plumbing_path(root)
    if path.exists():
        return store.read_json(path, "plumbing lock file")
    return {"schema": store.SCHEMA, "unlocked": None, "history": []}


def plumbing_digest(root: Path) -> str | None:
    """The digest of the plumbing as locked now; None while it is not locked."""
    data = read_plumbing(root)
    return files_digest(data["files"]) if "files" in data and not data.get("unlocked") else None


def feature_locks(root: Path) -> dict[str, tuple[Path, dict]]:
    """Every feature's lock data: feature id -> (its folder, its lock.json)."""
    features = store.features_dir(root)
    found: dict[str, tuple[Path, dict]] = {}
    for feature_dir in sorted(features.glob("FEAT-*")) if features.is_dir() else []:
        if (feature_dir / LOCK_FILE).is_file():
            data = store.read_json(feature_dir / LOCK_FILE, "lock file")
            found[data.get("feature", feature_dir.name)] = (feature_dir, data)
    return found


def legacy_features(root: Path) -> list[str]:
    """Features whose bind lock was written before the plumbing lock existed (``bdd migrate`` converts them)."""
    return sorted(fid for fid, (_, data) in feature_locks(root).items()
                  if "bind" in data["scopes"] and PLUMBING not in data["scopes"]["bind"])


def owners(root: Path) -> dict[str, str]:
    """Who owns each locked step, driver and plumbing file: ``plumbing``, or the feature whose bind lock took it first."""
    owned = dict.fromkeys(read_plumbing(root).get("files", {}), PLUMBING)
    binds = sorted((data["scopes"]["bind"]["locked_at"], fid, data["scopes"]["bind"]["files"])
                   for fid, (_, data) in feature_locks(root).items() if "bind" in data["scopes"])
    for _, fid, files in binds:
        for rel in files:
            owned.setdefault(rel, fid)
    return owned


def binding(root: Path) -> list[str]:
    """Features locked once but not bound now: between their approved examples and their bind lock, or reopened (with
    ``bdd change``) before it. Their step engineer may be adding or keeping files no lock covers."""
    return sorted(fid for fid, (_, data) in feature_locks(root).items() if "bind" not in data["scopes"])


def unclaimed(root: Path, current: list[str]) -> list[Violation]:
    """The files of ``current`` that no lock covers. A new step or driver file is presumed to be a binding feature's;
    a support file never is: it is plumbing."""
    owned, support = owners(root), support_files(root)
    presumed = bool(binding(root))
    return [Violation(PLUMBING if rel in support else "bind", rel, "added") for rel in sorted(current)
            if rel not in owned and (rel in support or not presumed)]


def plumbing_violations(root: Path) -> list[Violation]:
    """The locked plumbing files that differ from the disk; a missing plumbing lock is itself a violation. Nothing
    while the plumbing is unlocked: it is being changed, and ``plumbing_problem`` says so."""
    data = read_plumbing(root)
    if "files" not in data:
        return [Violation(PLUMBING, f"{cfg.BDD_DIR}/{PLUMBING_FILE}", "missing")]
    return [] if data.get("unlocked") else _compare(root, PLUMBING, data["files"])


def plumbing_problem(root: Path) -> str | None:
    """Why the plumbing does not back a gate right now, other than a changed file (None when it is locked)."""
    released = read_plumbing(root).get("unlocked")
    if released:
        return (f"the shared test plumbing was unlocked at {released['at']} ({released['reason']}); lock it again with "
                "`bdd lock --plumbing --reason \"...\"`, then rerun every bound feature once")
    return None


def _write_plumbing(root: Path, files: dict[str, str], reason: str, changed: list[str]) -> None:
    data = read_plumbing(root)
    now = store.utc_now()
    data.update({"locked_at": now, "files": files, "unlocked": None})
    data["history"].append({"event": "lock", "at": now, "reason": reason, "digest": files_digest(files),
                            "changed": changed})
    store.write_json(plumbing_path(root), data)


def _refuse_legacy(root: Path) -> None:
    legacy = legacy_features(root)
    if legacy:
        raise UsageError(f"the bind lock of {', '.join(legacy)} was written before the shared plumbing lock existed; "
                         "run `bdd migrate` first (it moves the shared files into the plumbing lock)")


def lock_bind(root: Path, feature_dir: Path, feature_id: str, paths: list[Path] | None,
              candidates: set[str]) -> tuple[dict[str, str], dict[str, str]]:
    """Lock a feature's own step and driver files: those of ``paths`` (with None, of the step and driver folders) that
    no other lock covers. ``candidates`` are the shared plumbing files (support files and the files the adapters ship);
    the first bind of a project locks them as the plumbing. Returns (the files locked, the files left out -> who
    covers them, or that they are plumbing the plumbing lock does not cover yet)."""
    _refuse_legacy(root)
    problem = plumbing_problem(root)
    if problem:
        raise UsageError(problem)
    if "files" not in read_plumbing(root):
        present = sorted(rel for rel in candidates if (root / rel).is_file())
        _write_plumbing(root, {rel: file_digest(root / rel) for rel in present}, f"first bind: {feature_id}", present)
    owned = owners(root)
    shared = candidates | support_files(root)
    named = bound_files(root) if paths is None else [relative(root, f) for f in expand(root, paths)]
    left_out = {rel: "the shared plumbing" if owned[rel] == PLUMBING else owned[rel] for rel in named if rel in owned}
    left_out |= {rel: "shared plumbing not locked yet" for rel in named if rel in shared and rel not in owned}
    files = {rel: file_digest(root / rel) for rel in named if rel not in left_out}
    _write_scope(feature_dir, feature_id, "bind", files, plumbing=files_digest(read_plumbing(root)["files"]))
    return files, left_out


def lock_plumbing(root: Path, reason: str, paths: list[Path], candidates: set[str]) -> dict:
    """Lock the shared plumbing again as it is now: the files it covers that still exist, the plumbing files no lock
    covers yet, and ``paths`` (a file a feature locked moves here, provided it is unchanged). Returns
    {"files", "changed", "moved", "rerun"}; ``rerun`` lists every bound feature, each of which reruns its scenarios
    once. Locking an unchanged plumbing again changes nothing."""
    if not reason.strip():
        raise UsageError("a plumbing change needs a --reason: it is kept in the plumbing lock's history")
    _refuse_legacy(root)
    data, owned, locks = read_plumbing(root), owners(root), feature_locks(root)
    names = set(data.get("files", {})) | {rel for rel in candidates | support_files(root) if rel not in owned}
    moved: dict[str, list[str]] = {}
    for rel in [relative(root, f) for f in expand(root, paths)] if paths else []:
        names.add(rel)
        for fid, (_, lock_data) in locks.items():
            digest = lock_data["scopes"].get("bind", {}).get("files", {}).get(rel)
            if digest is None:
                continue
            if digest != file_digest(root / rel):
                raise UsageError(f"{rel} changed since {fid} locked it; it can be shared only as {fid} locked it")
            moved.setdefault(fid, []).append(rel)
    files = {rel: file_digest(root / rel) for rel in sorted(names) if (root / rel).is_file()}
    old = data.get("files", {})
    changed = sorted(rel for rel in set(old) | set(files) if old.get(rel) != files.get(rel))
    bound = sorted(fid for fid, (_, lock_data) in locks.items() if "bind" in lock_data["scopes"])
    if "files" in data and not changed and not moved and not data.get("unlocked"):
        return {"files": files, "changed": [], "moved": {}, "rerun": []}
    _write_plumbing(root, files, reason.strip(), changed)
    for fid, rels in moved.items():
        feature_dir, lock_data = locks[fid]
        for rel in rels:
            del lock_data["scopes"]["bind"]["files"][rel]
        lock_data["history"].append({"event": "share", "scope": "bind", "at": store.utc_now(), "reason": reason.strip(),
                                     "files": sorted(rels)})
        store.write_json(feature_dir / LOCK_FILE, lock_data)
    return {"files": files, "changed": changed, "moved": moved, "rerun": bound}


def unlock_plumbing(root: Path, reason: str) -> None:
    """Release the plumbing so it can be changed; every bound feature's gates refuse until it is locked again."""
    if not reason.strip():
        raise UsageError("unlock needs a --reason: it is recorded in the plumbing lock's history")
    data = read_plumbing(root)
    if "files" not in data or data.get("unlocked"):
        raise UsageError("the shared plumbing is not locked")
    now = store.utc_now()
    data["unlocked"] = {"at": now, "reason": reason.strip()}
    data["history"].append({"event": "unlock", "at": now, "reason": reason.strip()})
    store.write_json(plumbing_path(root), data)


def migrate_legacy(root: Path, candidates: set[str]) -> list[str]:
    """Convert the bind locks written before the plumbing lock existed: the shared files they locked move to the
    plumbing lock, every other file stays with the feature that locked it first, and each lock records the plumbing
    digest. Refuses while one of those locks has a changed or missing file, so nothing unapproved is carried over."""
    legacy = legacy_features(root)
    locks = feature_locks(root)
    broken = [f"{fid}: {v}" for fid in legacy for v in check(root, locks[fid][0], fid, ("bind",)) if v.kind != "added"]
    if broken:
        raise UsageError("the old locks do not match the disk, so they cannot be converted: " + "; ".join(broken))
    plumbing = dict(read_plumbing(root).get("files", {}))
    order = sorted((locks[fid][1]["scopes"]["bind"]["locked_at"], fid) for fid in legacy)
    shared = candidates | support_files(root)
    first_owner: dict[str, str] = {}
    for _, fid in order:
        for rel, digest in locks[fid][1]["scopes"]["bind"]["files"].items():
            if rel in shared:
                plumbing[rel] = digest
            else:
                first_owner.setdefault(rel, fid)
    moved = sorted(set(plumbing) - set(read_plumbing(root).get("files", {})))
    _write_plumbing(root, plumbing, "migrate: the shared files of the old bind locks", moved)
    digest = files_digest(plumbing)
    notes = [f"plumbing lock: {len(plumbing)} file(s)"]
    for _, fid in order:
        feature_dir, data = locks[fid]
        entry = data["scopes"]["bind"]
        own = {rel: d for rel, d in entry["files"].items() if first_owner.get(rel) == fid}
        gone = sorted(set(entry["files"]) - set(own))
        entry.update({"files": own, PLUMBING: digest})
        data["history"].append({"event": "migrate", "scope": "bind", "at": store.utc_now(), "files": sorted(own),
                                "released": gone})
        store.write_json(feature_dir / LOCK_FILE, data)
        notes.append(f"{fid}: keeps {len(own)} file(s) of its own; {len(gone)} moved to the plumbing or an earlier feature")
    return notes


# -- checking ------------------------------------------------------------------------------------------------------

def _compare(root: Path, scope: str, locked: dict[str, str]) -> list[Violation]:
    violations: list[Violation] = []
    for rel, digest in sorted(locked.items()):
        target = root / rel
        if not target.is_file():
            violations.append(Violation(scope, rel, "missing"))
        elif file_digest(target) != digest:
            violations.append(Violation(scope, rel, "changed"))
    return violations


def check(root: Path, feature_dir: Path, feature_id: str, scopes: tuple[str, ...] = SCOPES,
          current_spec_files: list[str] | None = None, current_bound_files: list[str] | None = None) -> list[Violation]:
    """Compare locked files with the disk. A bind lock includes the plumbing it was bound against. ``current_spec_files``
    (project-relative paths of the feature files tagged for this feature right now) also detects spec files added after
    locking; ``current_bound_files`` detects step, driver and support files that no lock covers."""
    data = read_lock(feature_dir, feature_id)
    violations: list[Violation] = []
    for scope in (s for s in scopes if s in data["scopes"]):
        entry = data["scopes"][scope]
        violations += _compare(root, scope, entry["files"])
        if scope == "spec" and current_spec_files is not None:
            violations += [Violation(scope, rel, "added") for rel in sorted(set(current_spec_files) - set(entry["files"]))]
        if scope == "bind" and PLUMBING in entry:
            violations += plumbing_violations(root)
        if scope == "bind" and current_bound_files is not None:
            violations += unclaimed(root, current_bound_files)
    return violations
