"""The design review of a feature: the code, security and UI reviewers read ``design.md`` before the tasks are written.

Each reviewer writes ``reviews/design-<reviewer>.md`` in the feature folder, with a ``Design:`` line naming the digest of
the ``design.md`` it read (``bdd design FEAT-n`` prints it) and a ``Verdict:`` line. The tasks gate waits until every
reviewer the feature needs has passed this very design: the ui-reviewer only when the design shows a screen. A
``FINDINGS`` verdict goes back to the system-analyst, who changes ``design.md``; the changed design has a new digest, so
the reviewers read it again.

Where the hooks run, a report counts only as its own reviewer wrote it (``reviewlog.written_by``): the guard lets only
that reviewer write the file and records what it wrote, and Claude Code must have reported the agent as finished.
"""
from __future__ import annotations

import re
from pathlib import Path

from . import designsections, lockfile, reviewlog, roles

REVIEWERS = ("code-reviewer", "security-reviewer", "ui-reviewer")
# The phases a design review may be written in: from the system map, which writes the design, to the tasks gate.
PHASES = ("system-map", "refine", "bind", "tasks")
DIGEST = re.compile(r"^\s*Design:\s*([0-9a-f]{64})\s*$", re.MULTILINE)
VERDICT = re.compile(r"^\s*Verdict:\s*(PASS|FINDINGS)\b", re.IGNORECASE | re.MULTILINE)


def review_path(feature_dir: Path, reviewer: str) -> Path:
    return feature_dir / roles.REVIEWS_DIR / f"design-{reviewer}.md"


def digest(feature_dir: Path) -> str | None:
    path = feature_dir / designsections.DESIGN_FILE
    return lockfile.file_digest(path) if path.is_file() else None


def needed(root: Path, feature_dir: Path, feature_id: str) -> list[str]:
    screens = designsections.has_screens(feature_dir, designsections.screens_of(root, feature_id))
    return [r for r in REVIEWERS if r != "ui-reviewer" or screens]


def problems(root: Path, feature_dir: Path, feature_id: str, hooks_seen: bool) -> list[str]:
    """Why the tasks gate may not pass yet: a design review that is missing, of another version of the design, with
    must-fix items, or (where the hooks run) not written by its own reviewer."""
    current = digest(feature_dir)
    if current is None:
        return []                                        # the design checks already say there is no design.md
    from . import route
    log = reviewlog.recorded(root) if hooks_seen else {}
    finished = route.finished_agents(root) if hooks_seen else {}
    out = []
    for reviewer in needed(root, feature_dir, feature_id):
        path = review_path(feature_dir, reviewer)
        rel = path.relative_to(feature_dir).as_posix()
        if not path.is_file():
            out.append(f"{feature_id} has no design review by the {reviewer} ({rel}): run the code-reviewer, the "
                       "security-reviewer and, when the design has screens, the ui-reviewer on design.md, at most three at once")
            continue
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        verdict, named = VERDICT.search(text), DIGEST.search(text)
        if len(VERDICT.findall(text)) > 1 or len(DIGEST.findall(text)) > 1:
            out.append(f"{rel} has more than one Verdict: or Design: line; a report says each once")
        elif verdict is None:
            out.append(f"{rel} has no 'Verdict: PASS' or 'Verdict: FINDINGS' line")
        elif named is None or named.group(1) != current:
            out.append(f"{rel} reviewed another version of design.md (its Design: line is not {current[:12]}..., which "
                       f"`bdd design {feature_id}` prints); the {reviewer} reviews it again")
        elif hooks_seen and not reviewlog.written_by(root, path, reviewer, log, finished, phases=PHASES, need_agent=True):
            out.append(f"{rel} is not what the {reviewer} agent wrote: a review counts only as its own reviewer wrote it, "
                       "unchanged; run the reviewer again")
        elif verdict.group(1).upper() == "FINDINGS":
            out.append(f"{rel} has must-fix items: the system-analyst changes design.md for them, then the {reviewer} "
                       "reviews the changed design")
    return out


def verdicts(feature_dir: Path) -> dict[str, str]:
    """{reviewer: PASS, FINDINGS, stale or missing} for the report."""
    current = digest(feature_dir)
    found = {}
    for reviewer in REVIEWERS:
        path = review_path(feature_dir, reviewer)
        if not path.is_file():
            found[reviewer] = "missing"
            continue
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        verdict, named = VERDICT.search(text), DIGEST.search(text)
        found[reviewer] = ("stale" if named is None or named.group(1) != current else
                           verdict.group(1).upper() if verdict else "no verdict")
    return found
