"""What Codex's own record of a session can say about an approval typed in Codex: supporting evidence, never proof.

In Codex the agent and the person run as the same user in the same shell. Anything an agent could have written, a session
(rollout) file included, cannot prove who typed a prompt, and the hook command that records the approval is an ordinary
command that anything able to run commands could call with a made-up payload. So an approval typed in Codex has the grade
``codex``: it is accepted (unless the project requires hard enforcement), it is never graded hard, and the guarantee for it is
the review of the committed approval record in CI (``bdd approve --check``) together with branch protection.

This module keeps a fingerprint of the session file taken when the hook ran, and later describes what the file shows, so that
a reviewer has something to look at. It never turns an approval into a verified one:

* the recorded path must be a ``rollout-*.jsonl`` file that resolves, links followed, into Codex's sessions folder (the
  configured ``[approvals] codex_home`` or ``~/.codex``, never the environment) and the file must still begin with the
  bytes it had when the hook ran (Codex only appends);
* its ``session_meta`` must carry the session id recorded with the approval, and the turn must contain exactly the recorded
  approval as a user message, in a session whose ``source`` is one the person named in ``[approvals]
  codex_interactive_sources`` (only ``exec``, which is headless, has been observed).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

from . import approvalcommand
from . import config as cfg

PREFIX = "codex:"
ROLLOUT_NAME = re.compile(r"rollout-[A-Za-z0-9._-]+\.jsonl")
FINGERPRINT_LIMIT = 64 * 1024 * 1024        # a rollout file larger than this is not fingerprinted
LABEL = "supporting evidence only (it cannot show who typed the approval)"


def codex_sessions_dir(root: Path | None) -> Path:
    """Where Codex's session files are for this project: ``[approvals] codex_home`` in ``.bdd/config.toml`` or else the
    default ``~/.codex``. The environment is deliberately not consulted (a command can set CODEX_HOME for itself); a
    person whose Codex keeps its sessions elsewhere says so in the configuration."""
    configured = cfg.load(root).codex_home if root else None
    return (Path(configured).expanduser() if configured else Path.home() / ".codex") / "sessions"


def pinned_sessions(root: Path | None) -> str:
    return os.path.realpath(codex_sessions_dir(root))


def recorded_rollout(root: Path | None, transcript_path: str) -> Path | None:
    """The file the hook recorded, if it is a rollout file inside Codex's sessions folder (links followed)."""
    if not ROLLOUT_NAME.fullmatch(Path(transcript_path).name):
        return None
    try:
        base = os.path.realpath(codex_sessions_dir(root))
        resolved = os.path.realpath(transcript_path)
    except (OSError, ValueError):
        return None
    if not resolved.startswith(base + os.sep) or not os.path.isfile(resolved):
        return None
    return Path(resolved)


def fingerprint(root: Path | None, path_text: object) -> dict | None:
    """What the session file looks like now: its size and the hash of that many bytes.

    Only a rollout file inside Codex's sessions folder is ever read; anything else, or a file that cannot be read, gives
    None."""
    if not isinstance(path_text, str) or not path_text:
        return None
    path = recorded_rollout(root, path_text)
    try:
        if path is None or path.stat().st_size > FINGERPRINT_LIMIT:
            return None
        data = path.read_bytes()
    except OSError:
        return None
    return {"size": len(data), "sha256": hashlib.sha256(data).hexdigest(), "sessions": pinned_sessions(root)}


def _payload(row: dict) -> dict:
    payload = row.get("payload")
    return payload if isinstance(payload, dict) else {}


def parse_rollout(data: bytes) -> list[dict]:
    rows = []
    for line in data.decode("utf-8", errors="replace").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def session_meta(rows: list[dict]) -> dict:
    return next((_payload(row) for row in rows if row.get("type") == "session_meta"), {})


def messages_of_turn(rows: list[dict], turn: str) -> list[str] | None:
    """The user messages of one turn, or None if the turn never started in this file."""
    started, found = False, []
    for row in rows:
        payload = _payload(row)
        if row.get("type") != "event_msg":
            continue
        kind = payload.get("type")
        if kind == "task_started":
            if started:
                break                                    # the next turn begins
            started = payload.get("turn_id") == turn
        elif started and kind == "user_message":
            found.append(str(payload.get("message", "")))
    return found if started else None


def unchanged_since(data: bytes, recorded: object, sessions: str) -> str | None:
    """None if the file still starts with the bytes it had when the hook ran, else why not."""
    if not isinstance(recorded, dict) or not isinstance(recorded.get("size"), int) or not isinstance(recorded.get("sha256"), str):
        return "the hook did not record what the session file looked like"
    if recorded.get("sessions") != sessions:
        return (f"the hook saw Codex's sessions in {recorded.get('sessions')!r} but this project is configured for "
                f"{sessions!r}; set [approvals] codex_home in .bdd/config.toml to where Codex keeps its home")
    size = recorded["size"]
    if len(data) < size or hashlib.sha256(data[:size]).hexdigest() != recorded["sha256"]:
        return "the session file changed after the approval was recorded (Codex only ever appends to it)"
    return None


def source_note(root: Path | None, meta: dict) -> str:
    source, thread = meta.get("source"), meta.get("thread_source")
    note = f"source={source} thread_source={thread} originator={meta.get('originator')}"
    config = cfg.load(root) if root else None
    if thread != "user":
        return note + "; not a user session"
    if source == "exec":
        return note + "; a headless `codex exec` session"
    if config and source in config.codex_interactive_sources:
        return note + "; an interactive session as named in codex_interactive_sources"
    return note + f"; add {source!r} to [approvals] codex_interactive_sources if this is your interactive Codex"


def supporting_evidence(root: Path | None, approval: dict, feature: str) -> str:
    """What Codex's session file shows about this approval, in a sentence a reviewer can read. Never a verdict."""
    turn = str(approval.get("prompt_id", ""))[len(PREFIX):]
    if not approval.get("transcript_path"):
        return f"{LABEL}: the hook did not record where the session file is"
    path = recorded_rollout(root, approval["transcript_path"])
    if path is None:
        return f"{LABEL}: the recorded file is not a rollout file inside Codex's sessions folder"
    try:
        data = path.read_bytes()
    except OSError as exc:
        return f"{LABEL}: the session file cannot be read ({exc})"
    changed = unchanged_since(data, approval.get("source"), pinned_sessions(root))
    if changed:
        return f"{LABEL}: {changed}"
    rows = parse_rollout(data)
    meta = session_meta(rows)
    if not approval.get("session") or meta.get("id") != approval["session"]:
        return f"{LABEL}: the file belongs to session {meta.get('id')!r}, not {approval.get('session')!r}"
    messages = messages_of_turn(rows, turn)
    if not messages:
        return f"{LABEL}: the turn does not appear in the file (yet)"
    decision = approval["decision"]
    for message in messages:
        parsed = approvalcommand.parse_codex(message)
        if parsed is None or parsed[:2] != (feature, approval["gate"]) or (parsed[2] is not None) != (decision == "reject"):
            return f"{LABEL}: the turn's message is not the {approval['gate']} {decision} that was recorded"
    return f"{LABEL}: the session file shows exactly this approval typed in the turn ({source_note(root, meta)})"
