"""The UserPromptSubmit hook that records approvals the person types.

    /greenlight:approve FEAT-007 rules
    /greenlight:approve FEAT-007 examples reject the boundary case is missing
    /greenlight:approve integrity tools reinstalled

Only a prompt that is *exactly* one of these forms counts; a message that holds one together with other text, or a
second one, records nothing and is answered with "NOT recorded: send one approval per message", shown to the
person as the hook's ``systemMessage`` and given to the model as context. (A rejection whose reason, on the same line,
mentions another command is still one rejection.) The hook also fires for prompts the system injects (platform notes), so it cannot tell who wrote
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
ONE_PER_MESSAGE = "send one approval per message"


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


def acknowledge(payload: dict) -> str | None:
    """Record ``/greenlight:approve integrity <reason>``. Returns the line to show, or None if the prompt is not one.

    Like an approval it is pending until the transcript shows the person typed it; then the violations close."""
    reason = approvalcommand.parse_integrity(payload.get("prompt"))
    if reason is None:
        return None
    from . import config, enforcement, integrityack, tripwire
    from .config import ConfigError
    from .errors import StoreError, UsageError

    root = config.find_root(Path(payload.get("cwd") or "."))
    if root is None:
        return None
    try:
        enforcement.touch(root, payload.get("session_id"))
        entry, left = integrityack.acknowledge(root, tripwire.plugin_root(), reason,
                                               session=enforcement.safe_session(payload.get("session_id")),
                                               prompt_id=payload.get("prompt_id"), transcript_path=payload.get("transcript_path"))
    except (UsageError, StoreError, ConfigError, OSError, KeyError, TypeError, ValueError) as exc:
        return f"{PREFIX} NOT recorded. {exc}"
    return (f"{PREFIX} integrity acknowledgement recorded ({entry['reason']}) for exactly: " + "; ".join(entry["shown"])
            + ". These close, with the files as listed, once Claude Code's transcript confirms the person typed this, at "
            "the next tool call or `bdd status`." + (" Not covered: " + "; ".join(left) + "." if left else ""))


def near_miss(payload: dict, pattern=approvalcommand.HOLDS_COMMAND) -> str | None:
    """The line to show when a prompt holds an approval command but is not only that command (other text, or a second
    command). Nothing is recorded for such a prompt: which part the person meant cannot be told."""
    found = approvalcommand.holds_command(payload.get("prompt"), pattern)
    if found is None:
        return None
    from . import config

    if config.find_root(Path(payload.get("cwd") or ".")) is None:
        return None
    example = found.group(0)
    if approvalcommand.REJECT_AFTER.match(payload["prompt"], found.end()):
        example += " reject <the reason, on one line>"
    return (f"{PREFIX} NOT recorded: {ONE_PER_MESSAGE}. This message holds an approval command together with other text or "
            f"another command, so nothing was recorded. Send the command alone, for example: {example}")


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        return 0
    if not isinstance(payload, dict):
        return 0
    line = acknowledge(payload) or record(payload)
    if line:
        print(line)
        return 0
    notice = near_miss(payload)
    if notice:
        print(json.dumps({"systemMessage": notice,
                          "hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": notice}}))
    return 0
