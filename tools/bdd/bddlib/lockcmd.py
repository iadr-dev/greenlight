"""`bdd lock` and `bdd unlock`.

    bdd lock FEAT-007 --scope spec [PATH...]   hash the approved .feature files
    bdd lock FEAT-007 --scope bind PATH...     hash the step definitions and drivers proven red
    bdd lock FEAT-007 --check [--scope S]      verify the hashes (exit 1 on any mismatch)
    bdd unlock FEAT-007 --scope S --reason "." release a scope; the reason is kept in the history
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import config as cfg
from . import featurefiles, lockfile, store
from .errors import StoreError, UsageError


def project_root() -> Path:
    root = cfg.find_root()
    if root is None:
        raise UsageError("not inside a greenlight project (no .bdd directory found); run /greenlight:init first")
    return root


def spec_files(root: Path, feature_id: str) -> list[Path]:
    """The .feature files in the configured feature directories that carry @<feature_id>."""
    dirs = list(cfg.load(root).feature_dirs)
    if not dirs:
        raise UsageError("no feature directories are configured in .bdd/config.toml; pass the files explicitly")
    return featurefiles.tagged_files(featurefiles.collect_files(dirs), "@" + feature_id)


def lock_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="bdd lock", description="Hash-lock approved specs and bound steps.")
    ap.add_argument("feature", help="feature id, e.g. FEAT-007")
    ap.add_argument("paths", nargs="*", type=Path, help="files or directories to lock")
    ap.add_argument("--scope", choices=lockfile.SCOPES, help="spec = .feature files, bind = steps and drivers")
    ap.add_argument("--check", action="store_true", help="verify existing locks instead of creating one")
    ap.add_argument("--require", action="store_true", help="with --check: fail if a scope is not locked at all")
    ap.add_argument("--json", action="store_true", help="machine-readable output (with --check)")
    return ap


def do_lock(args: argparse.Namespace, root: Path) -> int:
    if not args.scope:
        raise UsageError("--scope spec|bind is required to create a lock")
    feature_dir = store.find_feature_dir(root, args.feature)
    paths = args.paths
    if not paths and args.scope == "spec":
        paths = spec_files(root, args.feature)
        if not paths:
            raise UsageError(f"no .feature file is tagged @{args.feature}")
    if not paths:
        raise UsageError("name the files to lock: bdd lock FEAT --scope bind PATH...")
    files = lockfile.lock(root, feature_dir, args.feature, args.scope, paths)
    print(f"locked {args.feature} {args.scope}: {len(files)} file(s)")
    for rel in files:
        print(f"  {rel}")
    return 0


def do_check(args: argparse.Namespace, root: Path) -> int:
    feature_dir = store.find_feature_dir(root, args.feature)
    scopes = (args.scope,) if args.scope else lockfile.SCOPES
    data = lockfile.read_lock(feature_dir, args.feature)
    current = None
    if "spec" in scopes and "spec" in data["scopes"]:
        current = [lockfile.relative(root, f) for f in spec_files(root, args.feature)]
    violations = lockfile.check(root, feature_dir, args.feature, scopes, current)
    unlocked = [s for s in scopes if s not in data["scopes"]] if args.require else []
    ok = not violations and not unlocked
    if args.json:
        print(json.dumps({"feature": args.feature, "ok": ok, "not_locked": unlocked,
                          "locked": {s: len(v["files"]) for s, v in data["scopes"].items()},
                          "violations": [{"scope": v.scope, "path": v.path, "kind": v.kind} for v in violations]},
                         indent=2))
    else:
        report_check(args.feature, data, violations, unlocked)
    return 0 if ok else 1


def report_check(feature_id: str, data: dict, violations: list[lockfile.Violation], unlocked: list[str]) -> None:
    for v in violations:
        print(f"{feature_id}: {v}")
    for scope in unlocked:
        print(f"{feature_id}: [{scope}] is not locked")
    if not violations and not unlocked:
        held = ", ".join(f"{s}: {len(v['files'])} file(s)" for s, v in sorted(data["scopes"].items()))
        print(f"{feature_id}: locks intact ({held or 'nothing locked'})")


def run_lock(argv: list[str]) -> int:
    # Intermixed: Python 3.11's argparse otherwise rejects `bdd lock FEAT --scope bind PATH`.
    args = lock_parser().parse_intermixed_args(argv)
    try:
        root = project_root()
        return do_check(args, root) if args.check else do_lock(args, root)
    except (UsageError, StoreError, FileNotFoundError) as exc:
        print(f"bdd lock: {exc}", file=sys.stderr)
        return 2


def unlock_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="bdd unlock", description="Release a lock, recording why.")
    ap.add_argument("feature")
    ap.add_argument("--scope", choices=lockfile.SCOPES, required=True)
    ap.add_argument("--reason", required=True, help="why the lock is being released (kept in lock.json)")
    return ap


def run_unlock(argv: list[str]) -> int:
    args = unlock_parser().parse_args(argv)
    try:
        feature_dir = store.find_feature_dir(project_root(), args.feature)
        lockfile.unlock(feature_dir, args.feature, args.scope, args.reason)
    except (UsageError, StoreError, FileNotFoundError) as exc:
        print(f"bdd unlock: {exc}", file=sys.stderr)
        return 2
    print(f"unlocked {args.feature} {args.scope}")
    return 0
