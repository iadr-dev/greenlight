"""A review is only as new as the code it read.

When a reviewer writes its report, ``reviewlog`` keeps the hashes of the production files of that task as they were
(``scope``). The implement gate compares them with the files now (``changed_since``) and refuses a report whose code has
changed since: the reviewer has to read the new code (Fieldly's CR-001.8, found by the auditor after a whole round).

The production files of a task are the production files changed since the red was proven, narrowed to the paths its
``Areas:`` line in ``tasks.md`` names (a folder, a file or a glob; other words in the line are ignored). When no path of
the line matches a changed file, or the task has no ``Areas:``, a feature with one task (or none: the quick path) uses
every changed production file, and a feature with several tasks is not judged, because nothing says which file belongs
to which task. Pictures, videos and logs a reviewer's tools leave in the project do not count.
"""
from __future__ import annotations

import fnmatch
import re
from pathlib import Path

from . import config as cfg
from . import lockfile, redrecord, state, trace

HASH_CHARS = 16
NOT_CODE = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp4", ".webm", ".log", ".tmp")
REPORT = re.compile(r"(?P<task>T-\d+\.\d+)-[a-z-]+\.md", re.IGNORECASE)
_PATH = re.compile(r"[\w.*?\[\]@-]+(?:/[\w.*?\[\]@+-]+)*/?")


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


def files(root: Path, feature_dir: Path, task_id: str) -> list[str] | None:
    """The production files this task's review covers, or None when nothing says which they are."""
    red = state.load(feature_dir).get("red")
    if not red or not red.get("commit"):
        return None
    changed = [f for f in redrecord.changed_production_files(root, cfg.load(root).test_dirs, red["commit"])
               if not f.endswith(NOT_CODE)]
    tasks = trace.read_tasks(feature_dir / "tasks.md") or {}
    areas = area_paths((tasks.get(task_id) or {}).get("areas", ""))
    named = [f for f in changed if any(_inside(f, a) for a in areas)]
    if named:
        return named
    return changed if len(tasks) == 0 or (len(tasks) == 1 and task_id in tasks) else None


def scope(root: Path, feature_dir: Path, task_id: str) -> dict[str, str] | None:
    """{production file: the start of its hash} for the task, or None when it cannot be told."""
    covered = files(root, feature_dir, task_id)
    return None if covered is None else {name: lockfile.file_digest(root / name)[:HASH_CHARS] for name in covered}


def changed_since(then: dict[str, str], now: dict[str, str]) -> list[str]:
    """The files that differ between two scopes: added, removed or edited."""
    return sorted(name for name in then.keys() | now.keys() if then.get(name) != now.get(name))
