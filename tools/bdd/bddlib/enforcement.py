"""Evidence that hooks were active: one marker file per Claude Code session.

The guard hook touches ``.bdd/.enforcement/<session id>`` every time it runs. A command run
from the agent's shell inherits the same session id (``CLAUDE_CODE_SESSION_ID``), so it can ask
"are hooks active in *this* session?". That is how ``bdd approve --self-reported`` knows to
refuse in a hard-enforcement session, and how a feature is classified hard or soft afterwards.

Markers are CLI-managed data: the guard stops the agent from creating, editing or deleting them.
"""
from __future__ import annotations

import os
import re
import time
from datetime import datetime
from pathlib import Path

from .config import BDD_DIR

MARKER_DIR = ".enforcement"
SESSION_ENV = "CLAUDE_CODE_SESSION_ID"
KEEP_SECONDS = 14 * 24 * 3600
_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}")     # no leading "_": that is for reserved names
SEEN_MARKER = "_seen"                                           # hooks have run in this project, ever; never pruned
CODEX_MARKER = "_codex"                                         # a Codex hook has run in this project (a hint, never evidence); never pruned


def safe_session(value: str | None) -> str | None:
    """The session id if it is safe to use as a file name, else None."""
    return value if value and _SAFE_ID.fullmatch(value) and value not in (".", "..") else None


def current_session() -> str | None:
    return safe_session(os.environ.get(SESSION_ENV))


def marker_dir(root: Path) -> Path:
    return root / BDD_DIR / MARKER_DIR


def touch(root: Path, session: str | None) -> bool:
    """Record that hooks ran in ``session``. Returns False if there is nothing to record."""
    session = safe_session(session)
    if session is None:
        return False
    directory = marker_dir(root)
    marker = directory / session
    seen = directory / SEEN_MARKER
    try:
        directory.mkdir(parents=True, exist_ok=True)
        if not seen.exists():                    # on every call, so a deleted marker repairs itself
            seen.write_text("hooks have run in this project\n", encoding="utf-8")
        if not marker.exists():
            marker.write_text("hooks active\n", encoding="utf-8")
            prune(directory)
    except OSError:
        return False
    return True


def hooks_seen(root: Path) -> bool:
    """Have hooks ever run in this project? Unlike a session id, this cannot be changed by the caller.

    True if the permanent marker exists or any session marker does (so removing one file is not
    enough). The fact is also copied into each feature's state by ``state.observe_hooks``."""
    directory = marker_dir(root)
    return (directory / SEEN_MARKER).is_file() or (
        directory.is_dir() and any(p.is_file() and p.name not in (SEEN_MARKER, CODEX_MARKER) for p in directory.iterdir()))


def touch_codex(root: Path, session: str | None) -> bool:
    """Note that a Codex hook ran in this project, and when it last did.

    That is all this is: a hint for ``bdd doctor``. Codex gives a command no session id, and the hook is an ordinary command
    that anything able to run commands could call with a made-up payload, so nothing here is evidence for a grade. Work done
    in Codex is never classified hard (see ``classify``)."""
    if not touch(root, session):
        return False
    try:
        (marker_dir(root) / CODEX_MARKER).write_text(f"{int(time.time())}\n", encoding="utf-8", newline="\n")
    except OSError:
        return False
    return True


def codex_seen(root: Path) -> bool:
    return (marker_dir(root) / CODEX_MARKER).is_file()


def prune(directory: Path) -> None:
    """Forget markers older than KEEP_SECONDS so the folder does not grow without bound."""
    cutoff = time.time() - KEEP_SECONDS
    for old in directory.iterdir():
        try:
            if old.name not in (SEEN_MARKER, CODEX_MARKER) and old.is_file() and old.stat().st_mtime < cutoff:
                old.unlink()
        except OSError:
            pass


def active(root: Path, session: str | None) -> bool:
    session = safe_session(session)
    return bool(session) and (marker_dir(root) / session).is_file()


def approval_reasons(approval: dict) -> list[str]:
    """Why this approval alone keeps a feature from being hard (empty: it does not)."""
    gate = approval["gate"]
    reasons = []
    if approval["grade"] == "self-reported":
        reasons.append(f"the {gate} approval was self-reported, not typed by the person")
    if approval["grade"] == "codex":
        reasons.append(f"the {gate} approval was typed in Codex and is not provenance-verified: nothing there proves who typed "
                       "it. Review the committed approval record in CI (`bdd approve --check`) and protect the branch")
    return reasons


def classify(root: Path, data: dict) -> tuple[str, list[str]]:
    """Was this feature built under hard enforcement? Returns ("hard" | "soft", reasons it is soft).

    Hard means hooks demonstrably ran in every session that recorded something, and no approval
    was merely self-reported. Soft is not a failure, it is a statement of what was prevented
    (nothing, only detected afterwards) and the report must say so."""
    reasons: list[str] = []
    sessions: set[str] = set()
    for approval in data.get("approvals", []):
        reasons += approval_reasons(approval)
        if approval["grade"] in ("hook", "self-reported") and approval.get("session"):
            sessions.add(approval["session"])
    for name, gate in data.get("gates", {}).items():
        if gate.get("session"):
            sessions.add(gate["session"])
        else:
            reasons.append(f"the {name} gate was recorded outside a Claude Code session")
    if codex_seen(root):
        reasons.append("Codex hooks were used here: they are best effort (the hook is an ordinary command that anything able to "
                       "run commands could call, and the agent and the person are the same user), so work done in Codex is "
                       "never graded hard; the guarantee is the committed record reviewed in CI and branch protection")
    if not sessions:
        reasons.append("no session left evidence that hooks were active")
    reasons += [f"hooks left no trace in session {s}" for s in sorted(sessions) if not active(root, s)]
    return ("soft" if reasons else "hard"), reasons

