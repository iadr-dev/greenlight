"""`bdd lock` and `bdd unlock`.

    bdd lock FEAT-007 --scope spec [PATH...]   hash the approved .feature files
    bdd lock FEAT-007 --scope bind --bound     hash the feature's own step definitions and drivers proven red
    bdd lock FEAT-007 --check [--scope S]      verify the hashes, the shared plumbing's included (exit 1 on any mismatch)
    bdd unlock FEAT-007 --scope S --reason "." release a scope; the reason is kept in the history
    bdd lock --plumbing --reason "." [PATH...] lock the shared test plumbing again as it is now; every bound feature
                                               reruns its scenarios once
    bdd unlock --plumbing --reason "."         release the shared plumbing so it can be changed
"""
from __future__ import annotations

import argparse
import json
import sys
import tomllib
from pathlib import Path

from . import config as cfg
from . import featurefiles, lockfile, store
from .errors import StoreError, UsageError


def project_root() -> Path:
    root = cfg.find_root()
    if root is None:
        raise UsageError("not inside a greenlight project (no .bdd directory found); run /greenlight:init first")
    return root


def plumbing_candidates(root: Path) -> set[str]:
    """The shared test plumbing: the adapters' support files, and the step and driver files the adapters ship."""
    from . import adapter                                   # here, not at the top: it costs `bdd lock --check` ~70 ms
    config = cfg.load(root)
    found = lockfile.support_files(root)
    folders = [lockfile.relative(root, d) + "/" for d in config.step_dirs]
    path = root / cfg.BDD_DIR / "config.toml"
    for entry in tomllib.loads(path.read_text(encoding="utf-8")).get("adapters", []) if path.is_file() else []:
        try:
            shipped = adapter.shipped(adapter.find(entry.get("name", "")))
        except UsageError:                                  # an adapter of the project's own: only its support files
            continue
        base = cfg.adapter_base(entry, path)
        for name in shipped:
            rel = f"{base}/{name}" if base else name
            if rel.startswith(tuple(folders)) and (root / rel).is_file():
                found.add(rel)
    return found


def lock_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="bdd lock", description="Hash-lock approved specs, bound steps and the shared plumbing.")
    ap.add_argument("feature", nargs="?", help="feature id, e.g. FEAT-007")
    ap.add_argument("paths", nargs="*", type=Path, help="files or directories to lock")
    ap.add_argument("--scope", choices=lockfile.SCOPES, help="spec = .feature files, bind = steps and drivers")
    ap.add_argument("--bound", action="store_true",
                    help="with --scope bind: lock the files of the adapter's step and driver folders that no other lock covers")
    ap.add_argument("--plumbing", action="store_true",
                    help="lock the shared test plumbing again as it is now (with --reason); every bound feature reruns once")
    ap.add_argument("--reason", help="with --plumbing: why the plumbing changed (kept in its history)")
    ap.add_argument("--check", action="store_true", help="verify existing locks instead of creating one")
    ap.add_argument("--require", action="store_true", help="with --check: fail if a scope is not locked at all")
    ap.add_argument("--json", action="store_true", help="machine-readable output (with --check)")
    return ap


def do_lock(args: argparse.Namespace, root: Path) -> int:
    if not args.feature:
        raise UsageError("name the feature: bdd lock FEAT-n --scope spec|bind (or bdd lock --plumbing --reason \"...\")")
    if not args.scope:
        raise UsageError("--scope spec|bind is required to create a lock")
    feature_dir = store.find_feature_dir(root, args.feature)
    paths = args.paths
    if args.bound and (args.scope != "bind" or paths):
        raise UsageError("--bound goes with --scope bind and no paths")
    if not paths and args.scope == "spec":
        paths = featurefiles.spec_files(root, args.feature)
        if not paths:
            raise UsageError(f"no .feature file is tagged @{args.feature}")
    if not paths and not args.bound:
        raise UsageError("name the files to lock: bdd lock FEAT --scope bind PATH...")
    left_out: dict[str, str] = {}
    if args.scope == "bind":
        files, left_out = lockfile.lock_bind(root, feature_dir, args.feature, None if args.bound else paths,
                                             plumbing_candidates(root))
    else:
        files = lockfile.lock(root, feature_dir, args.feature, args.scope, paths)
    print(f"locked {args.feature} {args.scope}: {len(files)} file(s)")
    for rel in files:
        print(f"  {rel}")
    if args.scope == "bind":
        print(f"bound against the shared plumbing: {len(lockfile.read_plumbing(root)['files'])} file(s)")
    for rel, owner in sorted(left_out.items()):
        if owner != "the shared plumbing":                  # already counted in the line above
            print(f"  left to {owner}: {rel}")
    if any(owner == "shared plumbing not locked yet" for owner in left_out.values()):
        print("lock the new plumbing with `bdd lock --plumbing --reason \"...\"`; until then every feature's check fails")
    return 0


def do_plumbing(args: argparse.Namespace, root: Path) -> int:
    paths = ([Path(args.feature)] if args.feature else []) + list(args.paths)
    result = lockfile.lock_plumbing(root, args.reason or "", paths, plumbing_candidates(root))
    if not result["changed"] and not result["moved"] and not result["rerun"]:
        print(f"the shared plumbing is unchanged: {len(result['files'])} file(s) locked")
        return 0
    print(f"locked the shared plumbing: {len(result['files'])} file(s), {len(result['changed'])} changed")
    for rel in result["changed"]:
        print(f"  {rel}")
    for fid, rels in sorted(result["moved"].items()):
        print(f"  shared from {fid}: {', '.join(rels)}")
    if result["rerun"]:
        print("every bound feature reruns its scenarios once; none is reopened:")
        for fid in result["rerun"]:
            print(f"  {fid}" + (f"  (bdd run {fid})" if cfg.load(root).runs else ""))
    return 0


def do_check(args: argparse.Namespace, root: Path) -> int:
    if not args.feature:
        raise UsageError("name the feature to check: bdd lock FEAT-n --check")
    feature_dir = store.find_feature_dir(root, args.feature)
    scopes = (args.scope,) if args.scope else lockfile.SCOPES
    data = lockfile.read_lock(feature_dir, args.feature)
    current = None
    if "spec" in scopes and "spec" in data["scopes"]:
        current = [lockfile.relative(root, f) for f in featurefiles.spec_files(root, args.feature)]
    bound = lockfile.bound_files(root) if "bind" in scopes and "bind" in data["scopes"] else None
    violations = lockfile.check(root, feature_dir, args.feature, scopes, current, bound)
    unlocked = [s for s in scopes if s not in data["scopes"]] if args.require else []
    bind = data["scopes"].get("bind") if "bind" in scopes else None
    on_plumbing = bind is not None and lockfile.PLUMBING in bind
    released = lockfile.plumbing_problem(root) if on_plumbing else None
    ok = not violations and not unlocked and not (released and args.require)
    if args.json:
        plumbing = lockfile.read_plumbing(root)
        print(json.dumps({"feature": args.feature, "ok": ok, "not_locked": unlocked,
                          "locked": {s: len(v["files"]) for s, v in data["scopes"].items()},
                          "plumbing": ({"files": len(plumbing.get("files", {})), "unlocked": plumbing.get("unlocked")}
                                       if on_plumbing else None),
                          "violations": [{"scope": v.scope, "path": v.path, "kind": v.kind} for v in violations]},
                         indent=2))
    else:
        report_check(root, args.feature, data, violations, unlocked, on_plumbing, released)
    return 0 if ok else 1


def report_check(root: Path, feature_id: str, data: dict, violations: list[lockfile.Violation], unlocked: list[str],
                 on_plumbing: bool, released: str | None) -> None:
    for v in violations:
        print(f"{feature_id}: {v}")
    for scope in unlocked:
        print(f"{feature_id}: [{scope}] is not locked")
    if released:
        print(f"{feature_id}: [plumbing] {released}")
    if not violations and not unlocked and not released:
        held = ", ".join(f"{s}: {len(v['files'])} file(s)" for s, v in sorted(data["scopes"].items()))
        plumbing = f"; plumbing: {len(lockfile.read_plumbing(root)['files'])} file(s)" if on_plumbing else ""
        print(f"{feature_id}: locks intact ({held or 'nothing locked'}){plumbing}")
    if "bind" in data["scopes"] and not on_plumbing:
        print(f"{feature_id}: its bind lock was written before the shared plumbing lock existed; "
              "`bdd migrate` moves the shared files into it")


def run_lock(argv: list[str]) -> int:
    # Intermixed: Python 3.11's argparse otherwise rejects `bdd lock FEAT --scope bind PATH`.
    args = lock_parser().parse_intermixed_args(argv)
    try:
        root = project_root()
        if args.plumbing:
            if args.check or args.scope or args.bound:
                raise UsageError("--plumbing goes with --reason and, optionally, the paths to share")
            return do_plumbing(args, root)
        return do_check(args, root) if args.check else do_lock(args, root)
    except (UsageError, StoreError, FileNotFoundError) as exc:
        print(f"bdd lock: {exc}", file=sys.stderr)
        return 2


def unlock_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="bdd unlock", description="Release a lock, recording why.")
    ap.add_argument("feature", nargs="?")
    ap.add_argument("--scope", choices=lockfile.SCOPES)
    ap.add_argument("--plumbing", action="store_true", help="release the shared test plumbing so it can be changed")
    ap.add_argument("--reason", required=True, help="why the lock is being released (kept in its history)")
    return ap


def run_unlock(argv: list[str]) -> int:
    args = unlock_parser().parse_args(argv)
    try:
        if args.plumbing:
            if args.feature or args.scope:
                raise UsageError("--plumbing takes no feature and no --scope")
            lockfile.unlock_plumbing(project_root(), args.reason)
            print("unlocked the shared plumbing; lock it again with `bdd lock --plumbing --reason \"...\"`")
            return 0
        if not args.feature or not args.scope:
            raise UsageError("name the feature and the --scope to release (or --plumbing)")
        feature_dir = store.find_feature_dir(project_root(), args.feature)
        lockfile.unlock(feature_dir, args.feature, args.scope, args.reason)
    except (UsageError, StoreError, FileNotFoundError) as exc:
        print(f"bdd unlock: {exc}", file=sys.stderr)
        return 2
    print(f"unlocked {args.feature} {args.scope}")
    return 0
