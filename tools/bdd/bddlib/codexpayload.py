"""What Codex sends to a hook, read as the guard and the tripwire already understand it.

Codex runs a hook command with a JSON object on stdin: ``hook_event_name``, ``session_id``, ``cwd``,
``transcript_path`` and, per event, ``tool_name`` and ``tool_input`` (tool events), ``prompt`` (a submitted
prompt) and ``turn_id`` (turn-scoped events). Its tools differ from Claude Code's:

* a shell tool whose command may arrive as a string or as a list of words;
* ``apply_patch``, whose argument is a patch text that names the files it adds, updates, deletes or moves to.

Nothing here decides anything; it only turns a Codex tool call into the Claude-shaped calls that
``guard.evaluate`` checks. What cannot be read is reported, so that the guard can refuse it: a guard that lets
through whatever it does not understand is not a guard.
"""
from __future__ import annotations

import os
import re

SHELL_TOOLS = {"bash", "shell", "local_shell", "shell_command", "exec_command", "unified_exec"}
PATCH_TOOLS = {"apply_patch"}
STDIN_TOOLS = {"write_stdin"}
# Tools known to change nothing. Every other tool is refused inside a project unless the person listed it in
# [approvals] codex_allowed_tools: a tool nobody has looked at is a way past the guard.
HARMLESS_TOOLS = {"update_plan", "view_image", "read_file", "list_dir", "grep_files", "web_search", "tool_search",
                  "request_user_input"}
WORKDIR_KEYS = ("workdir", "cwd", "working_directory", "dir")
_HEADER = re.compile(r"[ \t]*\*\*\*[ \t]+(?:Add File|Update File|Delete File|Move to)[ \t]*:[ \t]*(\S[^\n]*)")
_ODD_PATH_CHAR = re.compile(r"[\"'`\x00-\x1f\x7f]")      # a path is checked exactly as written, so one that a shell or terminal could read differently is refused
_MENTIONS_HEADER = re.compile(r"\*\*\*[ \t]*(?:(?:Add|Update|Delete)[ \t]*File|Move[ \t]*to)", re.IGNORECASE)
COMMAND_KEYS = ("command", "cmd", "script", "argv")
UNREADABLE = ("greenlight: this tool call has no shell command or no patched file the guard can read, so it cannot be "
              "checked against the locks and is refused. A patch needs `*** Update File: <path>` style lines.")


def strings(value: object) -> list[str]:
    """Every string inside a JSON value, in order."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [text for item in value.values() for text in strings(item)]
    if isinstance(value, list):
        return [text for item in value for text in strings(item)]
    return []


def command_of(tool_input: object) -> str | None:
    """The shell command of a tool call as one string, whether Codex sent a string or a list of words.

    A call that carries more than one command-like key (``command``, ``cmd``, ``script``, ``argv``) is unreadable: the guard
    cannot tell which one the tool runs, and checking one while the tool runs the other would be a way past it."""
    if not isinstance(tool_input, dict):
        return None
    present = [key for key in COMMAND_KEYS if tool_input.get(key) is not None]
    if len(present) != 1:
        return None
    value = tool_input[present[0]]
    if isinstance(value, str):
        return value if value.strip() else None
    if isinstance(value, list) and value and all(isinstance(word, str) for word in value):
        return " ".join(value)
    return None


def patch_paths(tool_input: object) -> list[str] | None:
    """The files a patch adds, updates, deletes or moves to, wherever the patch text sits in the tool input.

    Line endings are normalised (``\\r\\n`` and a lone ``\\r`` are line ends) and indentation and trailing white space
    are ignored. A line that looks like a file header but is not one this can read, however it is spelled, or whose path holds a
    quote, a backtick or a control character (the path is checked exactly as written, never with quotes taken off), makes the
    whole patch unreadable (None), so the call is refused instead of naming a locked file unseen. Lines of a hunk (starting
    with ``+`` or ``-``) are content, not headers."""
    paths: list[str] = []
    for text in strings(tool_input):
        for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
            if not _MENTIONS_HEADER.search(line) or line.lstrip().startswith(("+", "-")):
                continue
            header = _HEADER.fullmatch(line)
            path = header.group(1).strip() if header else ""
            if not path or _ODD_PATH_CHAR.search(path):
                return None
            paths.append(path)
    return paths


def is_shell(tool_name: object) -> bool:
    return isinstance(tool_name, str) and tool_name.casefold() in SHELL_TOOLS


def is_known(tool_name: object, allowed: tuple[str, ...] = ()) -> bool:
    """May the guard let a call of this tool through once its text has been checked?"""
    if not isinstance(tool_name, str):
        return False
    name = tool_name.casefold()
    return name in SHELL_TOOLS | PATCH_TOOLS | STDIN_TOOLS | HARMLESS_TOOLS or name in {a.casefold() for a in allowed}


def working_directory(payload: dict) -> str | None:
    """Where the tool call runs: the hook's ``cwd``, or the one ``workdir`` (or similar) the call asks for, resolved against
    it. None, which refuses the call, if it names more than one (we cannot tell which one the tool honours) or one that
    cannot be resolved."""
    base = str(payload.get("cwd") or ".")
    tool_input = payload.get("tool_input")
    named = [tool_input[key] for key in WORKDIR_KEYS if isinstance(tool_input, dict) and tool_input.get(key) is not None]
    if len(named) > 1:
        return None
    if named:
        value = named[0]
        if not isinstance(value, str) or not value.strip() or "\0" in value:
            return None
        base = os.path.join(base, value.strip())
    return os.path.abspath(base)


def is_patch(tool_name: object) -> bool:
    return isinstance(tool_name, str) and tool_name.casefold() in PATCH_TOOLS


def _write_call(base: dict, path: str) -> dict:
    return {**base, "tool_name": "Write", "tool_input": {"file_path": path}}


def _stdin_calls(base: dict, tool_input: object) -> list[dict] | None:
    chars = tool_input.get("chars", "") if isinstance(tool_input, dict) else None
    return [{**base, "tool_name": "Bash", "tool_input": {"command": chars or " "}}] if isinstance(chars, str) else None


def _shell_calls(base: dict, tool_input: object) -> list[dict] | None:
    command, paths = command_of(tool_input), patch_paths(tool_input)
    if command is None or paths is None:
        return None
    return [{**base, "tool_name": "Bash", "tool_input": {"command": command}}, *(_write_call(base, path) for path in paths)]


def _patch_calls(base: dict, tool_input: object) -> list[dict] | None:
    paths = patch_paths(tool_input)
    return [_write_call(base, path) for path in paths] if paths else None


def guard_calls(payload: dict) -> list[dict] | None:
    """The calls ``guard.evaluate`` has to look at for this Codex tool call, or None if it cannot be read.

    A shell command is one ``Bash`` call, and so is the text sent to a running command (``write_stdin``); each file named
    in a patch (also one inside a shell command, such as ``apply_patch`` given a here-document) is one ``Write`` call.
    Every other tool gets a call without effect, which is how the guard still learns that hooks are running; whether a
    tool may be called at all is decided before this (``is_known``). The calls run in the working directory the tool call
    asks for."""
    cwd = working_directory(payload)
    if cwd is None:
        return None
    base = {"cwd": cwd, "session_id": payload.get("session_id")}
    tool, tool_input = payload.get("tool_name"), payload.get("tool_input") or {}
    name = tool.casefold() if isinstance(tool, str) else ""
    if name in STDIN_TOOLS:
        return _stdin_calls(base, tool_input)
    if name in SHELL_TOOLS:
        return _shell_calls(base, tool_input)
    if name in PATCH_TOOLS:
        return _patch_calls(base, tool_input)
    return [{**base, "tool_name": "Other", "tool_input": tool_input if isinstance(tool_input, dict) else {}}]
