"""A review is only as new as the code it read.

When a reviewer finishes, ``reviewlog.seal`` records which production files its task covered and their hashes
(``judge``). The implement gate measures the same files again from what the seal records (``changed``), never from
``tasks.md``, which anyone may have edited since, and refuses a report whose code has changed: the reviewer has to read
the new code (Fieldly's CR-001.8, found by the auditor after a whole round).

The production files of a task are the production files changed since the red was proven, narrowed to the paths its
``Areas:`` line in ``tasks.md`` names (a folder, a file or a glob; other words in the line are ignored). When no path of
the line matches a changed file, or the task has no ``Areas:``, a feature with one task (or none: the quick path) uses
every changed production file, and a feature with several tasks is not judged, because nothing says which file belongs
to which task (``Unjudged``; the seal says so and the gate leaves the report as it is). Pictures, videos, logs, archives
and traces a reviewer's tools leave in the project do not count.
"""
from __future__ import annotations

import fnmatch
import re
from pathlib import Path

from . import config as cfg
from . import lockfile, redrecord, state, trace

HASH_CHARS = 16
HOOK_TIMEOUT = 30
NOT_CODE = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".mp4", ".webm", ".mov", ".log", ".tmp", ".har", ".zip", ".gz",
            ".trace", ".heapsnapshot", ".cpuprofile")
REPORT = re.compile(r"(?P<task>T-\d+\.\d+)-[a-z-]+\.md", re.IGNORECASE)
_PATH = re.compile(r"[\w.*?\[\]@-]+(?:/[\w.*?\[\]@+-]+)*/?")


class Unjudged(Exception):
    """The files of this task cannot be told, whatever the code does: the report is judged as it always was."""


def task_of(report: Path) -> str | None:
    match = REPORT.fullmatch(report.name)
    return match.group("task") if match else None


def area_paths(text: str) -> list[str]:
    """The paths a task's ``Areas:`` line names: words with a slash, or a file name with an extension."""
    words = (w.strip("`'\"()[]<>,;") for w in text.replace(",", " ").replace(";", " ").split())
    return [w.removeprefix("./") for w in words if _PATH.fullmatch(w) and ("/" in w or re.search(r"\.\w{1,6}$", w))]


def _inside(name: str, area: str) -> bool:
    folder = area.rstrip("/")
    return name == folder or name.startswith(folder + "/") or fnmatch.fnmatchcase(name, area)


def _changed_since_red(root: Path, red: str) -> list[str]:
    files = redrecord.changed_production_files(root, cfg.load(root).test_dirs, red, timeout=HOOK_TIMEOUT)
    return [f for f in files if not f.lower().endswith(NOT_CODE)]


def _hashes(root: Path, names: list[str]) -> dict[str, str]:
    return {name: lockfile.file_digest(root / name)[:HASH_CHARS] for name in names}


def judge(root: Path, feature_dir: Path, task_id: str) -> dict:
    """What a seal records for the task's report: the red commit, the areas that narrowed the files (None: every changed
    production file) and the hash of each file. Raises ``Unjudged`` when nothing says which files are the task's."""
    red = state.load(feature_dir).get("red")
    if not red or not redrecord.is_commit(red.get("commit")):
        raise Unjudged("no red was recorded for this feature")
    changed = _changed_since_red(root, red["commit"])
    tasks = trace.read_tasks(feature_dir / "tasks.md") or {}
    areas = area_paths((tasks.get(task_id) or {}).get("areas", ""))
    named = [f for f in changed if any(_inside(f, a) for a in areas)]
    if named:
        return {"red": red["commit"], "areas": areas, "files": _hashes(root, named)}
    if len(tasks) == 0 or (len(tasks) == 1 and task_id in tasks):
        return {"red": red["commit"], "areas": None, "files": _hashes(root, changed)}
    raise Unjudged("the feature has several tasks and the Areas of this one name no changed file")


def changed(root: Path, code: dict) -> dict[str, str | None]:
    """The files that differ from what a seal recorded (added, removed or edited), measured the way the seal says, each
    with the start of its hash now (None: it is gone)."""
    red, areas, then = code.get("red"), code.get("areas"), code.get("files")
    if not redrecord.is_commit(red) or not isinstance(then, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in then.items()) or not (
            areas is None or (isinstance(areas, list) and all(isinstance(a, str) for a in areas))):
        raise ValueError("the record of the code is malformed")
    names = _changed_since_red(root, red)
    if areas is not None:
        names = [f for f in names if any(_inside(f, a) for a in areas)]
    now = _hashes(root, names)
    return {name: now.get(name) for name in sorted(then.keys() | now.keys()) if then.get(name) != now.get(name)}
