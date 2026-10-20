"""The UserPromptSubmit hook that records approvals the person types.

    /greenlight:approve FEAT-007 rules
    /greenlight:approve FEAT-007 examples reject the boundary case is missing

Only a prompt that is *exactly* one of these forms counts; a sentence that merely contains one does
not. The hook also fires for prompts the system injects (platform notes), so it cannot tell who wrote
the text: it records the approval as ``pending`` with the prompt id and transcript path, and the gates
verify it against the transcript later. It always exits 0 so the prompt still reaches the model, and
prints one line the ``approve`` skill relays.

Outside a greenlight project it does nothing, and it reads nothing but its input for any other prompt.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from . import approvalcommand

PREFIX = "greenlight approval:"


def record(payload: dict, parse=approvalcommand.parse, tool: str = "Claude Code", grade: str = "hook") -> str | None:
    """Record the approval the prompt asks for. Returns the line to show, or None if it is not one.

    ``parse`` reads the command in the spelling of the tool the prompt came from, ``tool`` names it in the line."""
    parsed = parse(payload.get("prompt"))
    if parsed is None:
        return None
    from . import approvals, config, enforcement, state, store
    from .config import ConfigError
    from .errors import StoreError, UsageError

    feature, gate, reason = parsed
    root = config.find_root(Path(payload.get("cwd") or "."))
    if root is None:
        return None
    try:
        enforcement.touch(root, payload.get("session_id"))
        feature_dir = store.find_feature_dir(root, feature)
        approvals.record(root, feature_dir, gate, "approve" if reason is None else "reject", grade,
                         session=enforcement.safe_session(payload.get("session_id")),
                         prompt_id=payload.get("prompt_id"), transcript_path=payload.get("transcript_path"),
                         reason=reason or "", source=payload.get("source_evidence"))
        phase = state.load(feature_dir)["phase"]
    except (UsageError, StoreError, ConfigError) as exc:
        return f"{PREFIX} NOT recorded. {exc}"
    verb = "approved" if reason is None else "rejected"
    return (f"{PREFIX} {feature} {gate} {verb}; phase is now {phase}. "
            + ("The approval stays pending until Claude Code's transcript confirms the person typed it." if grade == "hook" else
               f"It is recorded as typed in {tool} and is not provenance-verified: review the committed record in CI "
               "(`bdd approve --check`)."))


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        return 0
    line = record(payload) if isinstance(payload, dict) else None
    if line:
        print(line)
    return 0
