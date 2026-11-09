"""The record of review reports as their reviewers wrote them: which reviewer wrote which file, and a hash of what it wrote.

The guard adds a line when it lets a reviewer write its own report (``.bdd/.runs/reviews.jsonl``, a folder no agent may
write). Where the hooks run, the implement gate accepts a report only when its content now hashes to the *latest* line
recorded for that file and that reviewer, written while the feature was in the implement phase by an agent that Claude
Code then reported as finished, so a report written or changed any other way (another agent, the orchestrator, a shell
command, a later edit), or an old report put back, does not count, whatever command made the change. When the reviewer
finishes, the SubagentStop hook adds a seal line with the hashes of the production files of its task (``seal``), so a
report older than the code it covers is found too. Kept light: the guard imports it on every call.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

LOG = Path(".bdd") / ".runs" / "reviews.jsonl"
CASE_INSENSITIVE_FS = sys.platform in ("win32", "darwin")
REPORT_FIELDS = {"path", "reviewer", "sha256"}


def digest(text: str) -> str:
    """SHA-256 of a report's text, with LF endings (as the lock files hash text)."""
    return hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()


def key(root: Path, path: Path) -> str:
    """The report's path relative to the project, spelled the same way for every spelling of the same file."""
    rel = Path(path).resolve().relative_to(root.resolve()).as_posix()
    return rel.casefold() if CASE_INSENSITIVE_FS else rel


def _append(root: Path, line: dict) -> None:
    """One write of the whole line to a file opened for appending, so two writers at once (the guard for one reviewer, the
    hook for another) never cut each other's line in two."""
    log = root / LOG
    log.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(log, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        os.write(descriptor, (json.dumps(line) + "\n").encode("utf-8"))
    finally:
        os.close(descriptor)


def record(root: Path, path: Path, reviewer: str, content: str, agent_id: object = None, phase: str | None = None) -> None:
    _append(root, {"path": key(root, path), "reviewer": reviewer, "sha256": digest(content), "agent_id": agent_id, "phase": phase})


def _read(root: Path) -> list[dict]:
    log = root / LOG
    if not log.is_file():
        return []
    found = []
    for raw in log.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            line = json.loads(raw)
        except ValueError:
            continue
        if isinstance(line, dict):
            found.append(line)
    return found


def _held(root: Path) -> dict[tuple[str, str], list[dict | None]]:
    """{(report path, reviewer): [the latest line recorded for it, the seal of exactly that line or None]}, read in the
    order of the log. A seal counts only when it comes after the line it names, for the same hash and the same agent; a
    newer line for the report takes its place and has no seal until its own is made."""
    held: dict[tuple[str, str], list[dict | None]] = {}
    for line in _read(root):
        where = (str(line.get("path")), str(line.get("reviewer")))
        if REPORT_FIELDS <= set(line):
            held[where] = [line, None]
        elif "seal" in line and "code" in line and where in held:
            report = held[where][0]
            if line["seal"] == report["sha256"] and line.get("agent_id") == report.get("agent_id"):
                held[where][1] = line
    return held


def recorded(root: Path) -> dict[tuple[str, str], dict]:
    """{(report path, reviewer): the latest line that reviewer recorded for it}. An earlier line is replaced, so a report
    put back to what it once was does not match."""
    return {where: pair[0] for where, pair in _held(root).items()}


def seals(root: Path) -> dict[tuple[str, str], dict]:
    """{(report path, reviewer): the seal of its latest line}; a report whose latest line has none is missing."""
    return {where: pair[1] for where, pair in _held(root).items() if pair[1] is not None}


def seal(root: Path, agent_id: object) -> bool:
    """When a reviewer finishes, record next to each report it wrote which production files its task covered and their
    hashes (``reviewfresh``), so the gate finds a report older than the code it covers. The SubagentStop hook does it, not
    the guard when the report is written, because reading the code takes git calls the guard has no time for.

    A seal is its own line, naming the hash of the report line it seals and the agent that wrote it. It is made only for
    the latest line of a report and only for a named agent, so an agent that finishes late cannot seal a newer report, and
    it is not made when the code cannot be read: the gate then asks for the review again. Never raises."""
    if agent_id is None or str(agent_id) == "":
        return False
    try:
        from . import reviewfresh
        done = False
        for line, existing in _held(root).values():
            if str(line.get("agent_id")) != str(agent_id) or existing is not None:
                continue
            report = root / str(line["path"])
            task = reviewfresh.task_of(report)
            if task is None:
                continue
            try:
                code, why = reviewfresh.judge(root, report.parent.parent, task.upper()), None
            except reviewfresh.Unjudged as exc:
                code, why = None, str(exc)
            sealed = {"seal": line["sha256"], "path": line["path"], "reviewer": line["reviewer"],
                      "agent_id": line["agent_id"], "code": code, "why": why}
            _append(root, sealed)
            done = True
        return done
    except Exception:
        return False


def written_by(root: Path, path: Path, reviewer: str, log: dict[tuple[str, str], dict] | None = None,
               finished: dict[str, str] | None = None) -> bool:
    """Is the report's content now exactly what ``reviewer`` last wrote to it, during the implement phase? With
    ``finished`` ({agent id: agent type} of the agents Claude Code reported as finished), the agent that wrote it must
    also be one of them, and a ``greenlight:<reviewer>``."""
    line = (recorded(root) if log is None else log).get((key(root, path), reviewer))
    if line is None or line.get("sha256") != digest(Path(path).read_text(encoding="utf-8-sig")):
        return False
    if line.get("phase") != "implement":
        return False
    agent_id = line.get("agent_id")
    return finished is None or agent_id is None or finished.get(str(agent_id)) == f"greenlight:{reviewer}"
