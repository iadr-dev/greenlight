"""The one command a person types to approve or reject, and how it looks in a session transcript.

    /greenlight:approve FEAT-007 rules
    /greenlight:approve FEAT-007 examples reject the boundary case is missing

The approval hook reads it from the prompt as typed; verification reads it again from the transcript,
where Claude Code stores a slash command in its expanded form:

    <command-message>greenlight:approve</command-message>
    <command-name>/greenlight:approve</command-name>
    <command-args>FEAT-007 rules</command-args>

Both must say the same thing, so an approval cannot borrow the prompt id of something else the person
typed. Only a whole prompt in exactly this form counts. The same command acknowledges the open integrity
violations:

    /greenlight:approve integrity tools reinstalled
"""
from __future__ import annotations

import re

COMMAND = "/greenlight:approve"
PROMPT = re.compile(r"/greenlight:approve[ \t]+(FEAT-\d+)[ \t]+(rules|examples)(?:[ \t]+(reject)(?:[ \t]+(\S.*))?)?")
INTEGRITY_PROMPT = re.compile(r"/greenlight:approve[ \t]+integrity(?:[ \t]+(\S.*))?")
CODEX_COMMAND = "$greenlight-approve"
CODEX_PROMPT = re.compile(r"\$greenlight-approve[ 	]+(FEAT-\d+)[ 	]+(rules|examples)(?:[ 	]+(reject)(?:[ 	]+(\S.*))?)?")
_COMMAND_BODY = r"[ \t]+(?:FEAT-\d+[ \t]+(?:rules|examples)|integrity)\b"
HOLDS_COMMAND = re.compile(r"/greenlight:approve" + _COMMAND_BODY)
CODEX_HOLDS_COMMAND = re.compile(r"\$greenlight-approve" + _COMMAND_BODY)
_EXPANDED = re.compile(r"<command-message>[^<\n]*</command-message>\s*<command-name>/greenlight:approve</command-name>"
                       r"\s*<command-args>([^<\n]*)</command-args>")


def parse(prompt: object, pattern: re.Pattern[str] = PROMPT) -> tuple[str, str, str | None] | None:
    """(feature, gate, reject reason or None) when the whole prompt is an approval command."""
    if not isinstance(prompt, str):
        return None
    match = pattern.fullmatch(prompt.strip())
    if match is None:
        return None
    feature, gate, reject, reason = match.groups()
    return feature, gate, (reason or "no reason given") if reject else None


def parse_integrity(prompt: object) -> str | None:
    """The reason when the whole prompt is an integrity acknowledgement ("" when it gives none), else None."""
    match = INTEGRITY_PROMPT.fullmatch(prompt.strip()) if isinstance(prompt, str) else None
    return None if match is None else (match.group(1) or "").strip()


def holds_command(prompt: object, pattern: re.Pattern[str] = HOLDS_COMMAND) -> re.Match[str] | None:
    """The first complete approval command inside a prompt, whether or not the prompt is only that command.

    A prompt that starts with ``<`` is a note the system injected (a finished agent's report quoting what to type), not
    something the person sent, and is skipped."""
    if not isinstance(prompt, str) or prompt.lstrip().startswith("<"):
        return None
    return pattern.search(prompt)


def parse_codex(prompt: object) -> tuple[str, str, str | None] | None:
    """The same, for the way the person types it in Codex: ``$greenlight-approve FEAT-007 rules``."""
    return parse(prompt, CODEX_PROMPT)


def typed_text(entry: dict) -> str | None:
    """The command text of a transcript entry, back in the form the person typed, or None."""
    content = (entry.get("message") or {}).get("content")
    if isinstance(content, list):
        texts = [b.get("text") for b in content if isinstance(b, dict) and b.get("type") == "text"]
        content = texts[0] if len(texts) == 1 and len(content) == 1 else None
    if not isinstance(content, str):
        return None
    expanded = _EXPANDED.fullmatch(content.strip())
    return f"{COMMAND} {expanded.group(1).strip()}" if expanded else content.strip()


def matches(entry: dict, feature: str, gate: str, decision: str) -> bool:
    """Does this transcript entry say exactly the approval that was recorded?"""
    parsed = parse(typed_text(entry))
    return parsed is not None and parsed[:2] == (feature, gate) and (parsed[2] is not None) == (decision == "reject")
