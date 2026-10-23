"""`bdd run FEAT-n --against-red`: prove the red again after the feature was reopened past its implementation.

When an approved example has to change after the code was written (an audit finding, a person's change), the change
flow reopens the feature and the rebound tests must again be shown to fail without the feature's code. Running them
in the project cannot show that any more: the code is there, so they pass. Taking the code away by hand (a stash, a
revert) would be the very thing the red gate exists to prevent.

So the tests run where the code is not: a temporary git worktree of the production source exactly as it was when the
red was first proven (the snapshot the bind gate recorded, or the red commit when the source matched it), with the
current bound files laid over it. Only test material is copied in: the adapter's feature, step and driver folders,
its plumbing files and greenlight's configuration. Production files always come from the red. The run is recorded
as the feature's latest run, marked ``against_red``; the bind gate accepts it as a red only for that same red, and
then keeps the original red record, so the order "red, then code" stays provable for the whole feature.
"""
from __future__ import annotations

import contextlib
import shutil
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path

from . import config as cfg
from . import folderlinks, lockfile, redrecord
from .errors import UsageError

# Folders a project installs into and git ignores, that the tests need to run and that hold no production code:
# they are linked into the worktree rather than copied (build output is never linked: it was made from today's code).
DEPENDENCY_DIRS = ("node_modules", ".venv", "venv")
SKIPPED = {"__pycache__", "node_modules", ".git", ".venv", "venv"}
LOCAL_DATA = {".runs", ".integrity", ".enforcement"}


def baseline(data: dict) -> dict | None:
    """The red the feature's tests were first proven against: the current record, or the last one a reopen kept."""
    if data.get("red"):
        return data["red"]
    history = data.get("red_history") or []
    return history[-1]["red"] if history else None


def source_commit(red: dict) -> str:
    """The commit whose tree is the production source of ``red``, or a UsageError saying why there is none."""
    snapshot = red.get("snapshot")
    if redrecord.is_commit(snapshot):
        return snapshot
    if red.get("dirty"):
        reason = red.get("snapshot_error") or "the red was recorded before greenlight kept a snapshot of it"
        raise UsageError("the red was proven with production changes that were not committed, and no snapshot of them "
                         f"was kept ({reason}), so that source cannot be checked out again; commit the production "
                         "source before recording a red next time")
    if not redrecord.is_commit(red.get("commit")):
        raise UsageError("the recorded red has no commit to check out")
    return red["commit"]


def problem(data: dict) -> str | None:
    """Why ``--against-red`` cannot be used for this feature, or None."""
    if data.get("kind") == "adopt":
        return ("an adoption has no red to reproduce: its scenarios describe what the code already does and pass from "
                "the start")
    if baseline(data) is None:
        return (f"{data['feature']} has no recorded red to run against: pass the bind gate with --record-red first; "
                "a plain `bdd run` proves the first red")
    return None


def _relative(root: Path, path: Path) -> str:
    return lockfile.relative(root, path)


def _copy(source: Path, target: Path) -> None:
    if source.is_dir():
        shutil.copytree(source, target, ignore=shutil.ignore_patterns(*SKIPPED), dirs_exist_ok=True, symlinks=False)
    elif source.is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def _remove(path: Path) -> None:
    if folderlinks.is_link(path):
        folderlinks.remove_link(path)
    elif path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def overlay(root: Path, place: Path, config: cfg.Config) -> list[str]:
    """Lay the project's current test material over the worktree (replacing what the red had there) and greenlight's
    configuration beside it. Returns the project-relative paths that were laid over."""
    laid: list[str] = []
    for path in sorted({p for p in config.test_dirs if p.exists()}, key=lambda p: len(p.parts)):
        rel = _relative(root, path)
        target = place / rel
        _remove(target)
        _copy(path, target)
        laid.append(rel)
    data = root / cfg.BDD_DIR
    for entry in sorted(data.iterdir()) if data.is_dir() else []:
        if entry.name not in LOCAL_DATA:
            _copy(entry, place / cfg.BDD_DIR / entry.name)
    return laid


def link_dependencies(root: Path, place: Path) -> Iterator[Path]:
    """Link the installed dependency folders the project has into the worktree, yielding each link as it is made so
    the caller can remove it even when a later one fails. A folder that cannot be linked raises UsageError naming it:
    tests that run without the project's installed dependencies prove nothing."""
    for name in DEPENDENCY_DIRS:
        source = root / name
        target = place / name
        if not source.is_dir() or target.exists() or folderlinks.is_link(target):
            continue
        folderlinks.link_directory(source.resolve(), target)
        yield target


def _production_digest(place: Path, root: Path, config: cfg.Config) -> str:
    test_dirs = tuple(place / _relative(root, p) for p in config.test_dirs)
    return redrecord.source_digest(place, test_dirs)


def _discard(root: Path, holder: Path, links: list[Path]) -> None:
    """Remove the worktree and its folder. The links go first, each one itself: a recursive delete would follow a
    junction into the project's real ``node_modules``. A link that cannot be removed stops the deletion, so the
    project's folder is never put at risk, and the leftover is named."""
    place = holder / "red"
    stuck = []
    for link in links:
        try:
            folderlinks.remove_link(link)
        except OSError:
            stuck.append(link)
    if stuck:
        print(f"the temporary worktree {holder} was left in place because these links to the project's folders could "
              f"not be removed: {', '.join(str(link) for link in stuck)}; remove each link itself (not its "
              "contents), then delete the worktree folder", file=sys.stderr)
        return
    with contextlib.suppress(UsageError):
        redrecord.git(root, "worktree", "remove", "--force", str(place))
    shutil.rmtree(holder, ignore_errors=True)
    with contextlib.suppress(UsageError):
        redrecord.git(root, "worktree", "prune")


@contextlib.contextmanager
def red_worktree(root: Path, red: dict, config: cfg.Config) -> Iterator[tuple[Path, list[str]]]:
    """A temporary worktree outside the project with the red's production source and today's test material.
    Yields (the worktree, the names of the dependency folders linked into it); removes it afterwards. Raises
    UsageError, before anything runs, when a dependency folder the project has cannot be linked."""
    commit = source_commit(red)
    holder = Path(tempfile.mkdtemp(prefix="greenlight-red-"))
    place = holder / "red"
    links: list[Path] = []
    try:
        redrecord.git(root, "worktree", "add", "--detach", str(place), commit)
        if _production_digest(place, root, config) != red.get("source_hash"):
            raise UsageError(f"the production source at {commit[:12]} is not the source the red was proven against "
                             "(its digest differs), so a run there would not reproduce that red")
        overlay(root, place, config)
        links.extend(link_dependencies(root, place))
        yield place, [link.name for link in links]
    finally:
        _discard(root, holder, links)


def describe(red: dict) -> dict:
    """What a run against the red records about it: enough for the bind gate to match it to the feature's red."""
    return {"commit": red.get("commit"), "snapshot": red.get("snapshot"), "source_hash": red.get("source_hash"),
            "red_at": red.get("at")}


def matches(record: dict, data: dict) -> bool:
    """Was this run made against the feature's own recorded red?"""
    red = baseline(data)
    marked = record.get("against_red")
    return bool(red and isinstance(marked, dict) and marked == describe(red))
