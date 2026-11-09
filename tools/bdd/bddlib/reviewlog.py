"""The record of review reports as their reviewers wrote them: which reviewer wrote which file, and a hash of what it wrote.

The guard adds a line when it lets a reviewer write its own report (``.bdd/.runs/reviews.jsonl``, a folder no agent may
write). Where the hooks run, the implement gate accepts a report only when its content now hashes to the *latest* line
recorded for that file and that reviewer, written while the feature was in the implement phase by an agent that Claude
Code then reported as finished, so a report written or changed any other way (another agent, the orchestrator, a shell
command, a later edit), or an old report put back, does not count, whatever command made the change. When the reviewer
finishes, its line also gets the hashes of the production files of its task (``seal``), so a report older than the code
it covers is found too. Kept light: the guard imports it on every call.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

LOG = Path(".bdd") / ".runs" / "reviews.jsonl"
CASE_INSENSITIVE_FS = sys.platform in ("win32", "darwin")


def digest(text: str) -> str:
    """SHA-256 of a report's text, with LF endings (as the lock files hash text)."""
    return hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()


def key(root: Path, path: Path) -> str:
    """The report's path relative to the project, spelled the same way for every spelling of the same file."""
    rel = Path(path).resolve().relative_to(root.resolve()).as_posix()
    return rel.casefold() if CASE_INSENSITIVE_FS else rel


def record(root: Path, path: Path, reviewer: str, content: str, agent_id: object = None, phase: str | None = None) -> None:
    log = root / LOG
    log.parent.mkdir(parents=True, exist_ok=True)
    line = {"path": key(root, path), "reviewer": reviewer, "sha256": digest(content), "agent_id": agent_id, "phase": phase}
    with log.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(line) + "\n")


def seal(root: Path, agent_id: object) -> bool:
    """When a reviewer finishes, add to the line of the report it wrote the hashes of the production files of that task as
    it leaves them (``reviewfresh``), so the gate finds a report older than the code it covers. The SubagentStop hook does
    it, not the guard when the report is written, because reading the code takes git calls the guard has no time for.
    Best effort: a report that cannot be sealed is judged as before, and a failure here never reaches the agent."""
    try:
        from . import reviewfresh
        mine = [line for line in _lines(root) if str(line.get("agent_id")) == str(agent_id)]
        if not mine or mine[-1].get("code") is not None:
            return False
        report = root / str(mine[-1]["path"])
        task = reviewfresh.task_of(report)
        code = None if task is None else reviewfresh.scope(root, report.parent.parent, task.upper())
        if code is None:
            return False
        with (root / LOG).open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps({**mine[-1], "code": code}) + "\n")
        return True
    except Exception:
        return False


def _lines(root: Path) -> list[dict]:
    log = root / LOG
    if not log.is_file():
        return []
    found = []
    for raw in log.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            line = json.loads(raw)
        except ValueError:
            continue
        if isinstance(line, dict) and {"path", "reviewer", "sha256"} <= set(line):
            found.append(line)
    return found


def recorded(root: Path) -> dict[tuple[str, str], dict]:
    """{(report path, reviewer): the latest line that reviewer recorded for it}. An earlier line is replaced, so a report
    put back to what it once was does not match."""
    return {(str(line["path"]), str(line["reviewer"])): line for line in _lines(root)}


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
