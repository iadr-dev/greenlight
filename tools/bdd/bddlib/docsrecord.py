"""The documentation a task was written from: what the writer read, recorded per task by the orchestrator.

    bdd docs FEAT-n --task T-n.m --library NAME --version V --source URL_OR_FILE
    bdd docs FEAT-n --task T-n.m --none "why this task calls no library"
    bdd docs FEAT-n [--list]

A writer is told to read the current documentation of every library it calls instead of recalling it. It cannot run this
command (it reports, the orchestrator records); the report's "documentation consulted" lines become records here. A record
names the library and its version and a source anyone can open (an https address, or a file such as the installed package's
own documentation or type definitions), and the implement gate refuses while a task has neither a record nor a stated reason
for having none. This is a trail for the reviewer and the auditor to check the code against, not proof that the writer
followed it: whether the code matches the documentation is their judgement.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from . import config as cfg
from . import route, store
from .errors import StoreError, UsageError

RECORD = "docs-consulted.json"
TASK = re.compile(r"T-\d+\.\d+")
MIN_REASON = 8


def record_path(feature_dir: Path) -> Path:
    return feature_dir / RECORD


def entries(feature_dir: Path) -> list[dict]:
    path = record_path(feature_dir)
    if not path.is_file():
        return []
    return list(store.read_json(path, "the documentation record").get("entries", []))


def source_problem(root: Path, source: str) -> str | None:
    """Why ``source`` is not something a reader can open, or None when it is an https address or an existing file."""
    if re.fullmatch(r"https://[^\s/]+\.[^\s/]+\S*", source):
        return None
    target = Path(source)
    if not target.is_absolute():
        target = root / target
    if source and not re.match(r"[a-z]+://", source) and target.exists():
        return None
    return "the source must be an https address or a file that exists (the installed package's own documentation or types)"


def add(root: Path, feature_dir: Path, feature_id: str, task: str, library: str | None, version: str | None,
        source: str | None, none: str | None) -> dict:
    known = {r.task for r in route.routes(root, feature_dir, feature_id)}
    if not TASK.fullmatch(task) or task not in known:
        raise UsageError(f"{task} is not a task of {feature_id}; the tasks are {', '.join(sorted(known)) or '(none)'}")
    if none is not None:
        if library or version or source:
            raise UsageError("--none stands alone: a task either read some documentation or calls no library")
        if len(none.strip()) < MIN_REASON:
            raise UsageError(f"--none needs a reason of at least {MIN_REASON} characters")
        entry = {"task": task, "kind": "none", "reason": none.strip()}
    else:
        if not (library and version and source):
            raise UsageError("a record needs --library, --version and --source (or --none REASON)")
        problem = source_problem(root, source)
        if problem:
            raise UsageError(problem)
        entry = {"task": task, "kind": "doc", "library": library.strip(), "version": version.strip(), "source": source.strip()}
    entry["at"] = store.utc_now()
    path = record_path(feature_dir)
    store.write_json(path, {"schema": store.SCHEMA, "entries": [*entries(feature_dir), entry]})
    return entry


def problems(root: Path, feature_dir: Path, feature_id: str) -> list[str]:
    """Why the implement gate may not pass: a task with no record of the documentation read, and no reason for having none."""
    try:
        have = {e.get("task") for e in entries(feature_dir)}
    except StoreError as exc:
        return [str(exc)]
    return [f"{r.task} has no documentation record: `bdd docs {feature_id} --task {r.task} --library NAME --version V "
            "--source URL` for each library it calls, or `--none \"reason\"`" for r in route.routes(root, feature_dir, feature_id)
            if r.task not in have]


def describe(entry: dict) -> str:
    if entry.get("kind") == "none":
        return f"{entry['task']}  no library: {entry.get('reason', '')}"
    return f"{entry['task']}  {entry.get('library')} {entry.get('version')}  {entry.get('source')}"


def run(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="bdd docs", description="Record the documentation a task was written from.")
    ap.add_argument("feature", help="feature id, e.g. FEAT-007")
    ap.add_argument("--task", help="the task id, e.g. T-007.1")
    ap.add_argument("--library")
    ap.add_argument("--version")
    ap.add_argument("--source", help="an https address, or a file (the installed package's documentation or types)")
    ap.add_argument("--none", metavar="REASON", help="the task calls no library; say why")
    ap.add_argument("--list", action="store_true", help="print the records of the feature")
    args = ap.parse_args(argv)
    try:
        from .statecmd import project_root
        root = project_root()
        feature_dir = store.find_feature_dir(root, args.feature)
        if args.list or not args.task:
            found = entries(feature_dir)
            print("\n".join(describe(e) for e in found) or f"{args.feature}: no documentation recorded yet")
            return 0
        entry = add(root, feature_dir, args.feature, args.task, args.library, args.version, args.source, args.none)
    except (UsageError, StoreError, cfg.ConfigError) as exc:
        print(f"bdd docs: {exc}", file=sys.stderr)
        return 2
    print(f"recorded: {entry['task']} " + (f"{entry['library']} {entry['version']}" if entry["kind"] == "doc" else "no library"))
    return 0
