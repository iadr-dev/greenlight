"""`bdd codex-hook`: the one command Codex runs for greenlight's hooks (installed by ``bdd install-hooks codex``).

Codex sends the event as JSON on stdin (``hook_event_name`` says which). This turns each into what greenlight already does:

    PreToolUse        the guard (``codexguard``): locks, managed data, nested sessions, Codex's own hook files;
                      a reason is printed on stderr and the exit status is 2, which blocks the call
    PostToolUse       the tripwire: a difference from the baseline or the locks is reported the same way
    UserPromptSubmit  refresh the tripwire baseline, and record ``$greenlight-approve FEAT-n rules|examples`` as an
                      approval that stays pending until Codex's own record of the session shows the person typed it

Every event first notes that a Codex hook ran (``enforcement.touch_codex``): a project is only called hard after the
hooks demonstrably ran around its gates. Outside a greenlight project it does nothing. Unreadable input is not a
reason to block a prompt; inside a project an unexpected failure blocks a tool call, because a guard that a bad
payload can switch off is not a guard.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys
from pathlib import Path

from . import approvehook, approvalcommand, codexguard, codexorigin, enforcement, tripwire
from . import config as cfg
from .errors import StoreError

PLUGIN_ROOT = Path(__file__).resolve().parents[3]
CONTEXT_ERRORS = (StoreError, OSError, cfg.ConfigError, KeyError, TypeError, ValueError)


@contextlib.contextmanager
def plugin_root_set():
    """The tripwire finds the plugin's own files through CLAUDE_PLUGIN_ROOT, which Claude Code sets and Codex does not:
    name this installation for the duration of the hook so both tools watch the same files."""
    saved = os.environ.get("CLAUDE_PLUGIN_ROOT")
    os.environ["CLAUDE_PLUGIN_ROOT"] = str(PLUGIN_ROOT)
    try:
        yield
    finally:
        if saved is None:
            os.environ.pop("CLAUDE_PLUGIN_ROOT", None)
        else:
            os.environ["CLAUDE_PLUGIN_ROOT"] = saved


def pre_tool_use(payload: dict) -> int:
    reason = codexguard.evaluate(payload)
    if reason:
        print(reason, file=sys.stderr)
        return 2
    return 0


def post_tool_use(root: Path, payload: dict) -> int:
    try:
        new = tripwire.check(root, PLUGIN_ROOT, payload.get("tool_name"))
    except CONTEXT_ERRORS as exc:
        print(f"greenlight: the integrity check could not run ({exc}). The implement and verify gates will refuse until "
              "the integrity data under .bdd/.integrity is readable again; tell the person.", file=sys.stderr)
        return 2
    if new:
        print("greenlight: integrity check failed after this tool call:\n  " + "\n  ".join(tripwire.describe(i) for i in new)
              + "\nThe implement and verify gates will refuse to pass until this is undone. Restore the file (for example "
              "with git) and tell the person what happened.", file=sys.stderr)
        return 2
    return 0


def user_prompt_submit(root: Path, payload: dict) -> int:
    """Never blocks the prompt; what happened goes to the model as context."""
    lines: list[str] = []
    with contextlib.redirect_stdout(io.StringIO()) as shown:
        tripwire.run_accept(root)
    lines += [line for line in shown.getvalue().splitlines() if line]
    turn = payload.get("turn_id")
    typed = {"prompt": payload.get("prompt"), "cwd": payload.get("cwd"), "session_id": payload.get("session_id"),
             "prompt_id": f"codex:{turn}" if turn else None, "transcript_path": payload.get("transcript_path"),
             "source_evidence": codexorigin.fingerprint(root, payload.get("transcript_path"))}
    line = approvehook.record(typed, parse=approvalcommand.parse_codex, tool="Codex", grade="codex")
    if line:
        lines.append(line)
    if lines:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": "\n".join(lines)}}))
    return 0


def note_call(root: Path, event: object, payload: dict) -> None:
    """Note that a Codex hook ran in this project. That is all it says: the hook is a command anything could call, so
    nothing is graded from it (see ``enforcement.classify``)."""
    enforcement.touch_codex(root, payload.get("session_id"))


def guard_from_outside(payload: dict) -> int:
    """A tool call from a folder that is in no greenlight project can still write into one (``workdir``, an absolute path,
    ``..``): guard it, and let it through when it reaches none. If the guard itself fails, the call is blocked whenever it
    names a path inside a project (or the paths cannot be read), and let through otherwise."""
    try:
        return pre_tool_use(payload)
    except Exception as exc:          # deliberate: decide below whether a failing guard may let this call go
        try:
            projects, unresolved = codexguard.raw_reach(payload)
        except Exception:
            projects, unresolved = [], True
        if not projects and not unresolved:
            return 0
        print(f"greenlight: the Codex hook hit an internal error ({type(exc).__name__}: {exc}) on a call that names a path "
              "inside a greenlight project, and blocks it to stay safe.", file=sys.stderr)
        return 2


def main(_argv: list[str]) -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        return 0
    if not isinstance(payload, dict):
        return 0
    root = cfg.find_root(Path(payload.get("cwd") or "."))
    event = payload.get("hook_event_name")
    if root is None:
        return guard_from_outside(payload) if event == "PreToolUse" else 0
    try:
        note_call(root, event, payload)
        with plugin_root_set():
            if event == "PreToolUse":
                return pre_tool_use(payload)
            if event == "PostToolUse":
                return post_tool_use(root, payload)
            if event == "UserPromptSubmit":
                return user_prompt_submit(root, payload)
    except Exception as exc:          # deliberate: inside a project a failure must not become "allowed"
        if event in ("PreToolUse", "PostToolUse"):
            print(f"greenlight: the Codex hook hit an internal error ({type(exc).__name__}: {exc}) and blocks this call "
                  "to stay safe. Please report it.", file=sys.stderr)
            return 2
    return 0
