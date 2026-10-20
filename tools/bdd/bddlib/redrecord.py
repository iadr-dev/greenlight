"""The git position at which the tests were proven red.

When the bind gate passes, the production source must not have been touched yet. Recording
the commit and a digest of every non-test source file lets the independent verifier prove that
order later: the tests were red against exactly this source, before any implementation.
"""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

from . import lockfile, store
from .config import BDD_DIR
from .errors import UsageError


def git(root: Path, *args: str) -> str:
    try:
        done = subprocess.run(["git", "-C", str(root), "-c", "core.quotepath=off", *args],
                              capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    except FileNotFoundError:
        raise UsageError("git is not installed or not on PATH") from None
    if done.returncode != 0:
        raise UsageError(f"git {args[0]} failed: {(done.stderr or done.stdout).strip() or 'no output'}")
    return done.stdout


def is_production(name: str, excluded: list[str]) -> bool:
    """Folders (entries ending in a slash) match by prefix, files only by their exact name."""
    return not any(name.startswith(entry) if entry.endswith("/") else name == entry for entry in excluded)


def excluded_prefixes(root: Path, test_dirs: tuple[Path, ...]) -> list[str]:
    """Folders that are not production source: greenlight's own data and the test directories."""
    return [BDD_DIR + "/"] + [lockfile.relative(root, d) + ("/" if d.is_dir() or not d.suffix else "") for d in test_dirs]


def production_files(root: Path, test_dirs: tuple[Path, ...]) -> list[str]:
    """Tracked and untracked (not ignored) files that are neither greenlight data nor tests."""
    listing = git(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard")
    excluded = excluded_prefixes(root, test_dirs)
    names = sorted({n for n in listing.split("\0") if n})
    return [n for n in names if is_production(n, excluded) and (root / n).is_file()]


def uncommitted_production_changes(root: Path, test_dirs: tuple[Path, ...]) -> list[str]:
    """Production files that differ from HEAD (modified, added, deleted or untracked)."""
    parts = git(root, "status", "--porcelain", "-z", "--untracked-files=all").split("\0")
    excluded = excluded_prefixes(root, test_dirs)
    paths, i = [], 0
    while i < len(parts):
        entry = parts[i]
        i += 1
        if len(entry) < 4:
            continue
        if "R" in entry[:2] or "C" in entry[:2]:
            i += 1                                    # a rename/copy entry is followed by the original path
        paths.append(entry[3:])
    return [p for p in paths if is_production(p, excluded)]


def source_digest(root: Path, test_dirs: tuple[Path, ...]) -> str:
    h = hashlib.sha256()
    for name in production_files(root, test_dirs):
        h.update(name.encode("utf-8") + b"\0" + lockfile.file_digest(root / name).encode("ascii") + b"\n")
    return h.hexdigest()


def capture(root: Path, test_dirs: tuple[Path, ...]) -> dict:
    """The red record: the commit, whether production source differs from it (``dirty``), and a
    digest of the production source as it is right now."""
    commit = git(root, "rev-parse", "HEAD").strip()
    return {"commit": commit, "dirty": bool(uncommitted_production_changes(root, test_dirs)),
            "source_hash": source_digest(root, test_dirs), "at": store.utc_now()}
