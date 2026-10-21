"""Does a shell command start a Codex session? One answer, used by the Codex guard and by the Claude Code guard.

A nested session is the way for an agent to produce a prompt that looks typed, so starting one is refused inside a greenlight
project, whichever tool the agent is running in. A word whose program name is ``codex`` counts anywhere outside quotes, and inside quotes where a program would start, in
whatever argument it sits (``bash -lc "..."``, ``xargs``, ``timeout``, a script passed to an interpreter), unless it is a
read-only form such as ``codex --version``. A directory or a file merely called codex is caught too; that is the price of not
guessing how it is run. Like every text check in the guards this is friction, not the safeguard.
"""
from __future__ import annotations

import re

READ_ONLY = {("--version",), ("-v",), ("--help",), ("-h",), ("login", "status"), ("features", "list"), ("doctor",),
             ("plugin", "list"), ("mcp", "list"), ("mcp", "get")}
_BOUNDARIES = {";", "&", "|", "(", "`", "\n", "{"}                  # a new command starts after these
_QUOTES = {'"', "'"}
_OTHER_PUNCTUATION = {")", "<", ">", "}", "[", "]"}
_TOKEN = re.compile(r"[;&|()`\n{}<>\[\]\"']|[^\s;&|()`\"'<>{}\[\]]+")
# a word behind which the next word is a program, and the options that introduce a script or a command
LAUNCHERS = {"env", "sudo", "doas", "timeout", "nice", "nohup", "xargs", "command", "exec", "time", "start", "start-process", "call",
             "cmd", "powershell", "pwsh", "bash", "sh", "zsh", "dash", "ksh", "fish", "script", "runas", "wsl", "then", "do", "else",
             "eval", "builtin", "stdbuf", "setsid", "ionice", "watch", "parallel", "invoke-expression", "iex", "invoke-command", "icm"}
LAUNCH_OPTIONS = {"-c", "-lc", "-ic", "-command", "-c:", "/c", "/k", "-exec", "-execdir", "-e"}
_RUNNERS = re.compile(r"\b(?:npx|bunx|pnpm\s+dlx|yarn\s+dlx|npm\s+exec)\b[^;&|\n]*(?:\bcodex\b|@openai/codex)", re.IGNORECASE)
_FROM_CODE = re.compile(r"(?:subprocess|Popen|os\.system|os\.exec\w*|spawn\w*|execFile?|execa)\W[^\n]*\bcodex\b", re.IGNORECASE)

# greenlight's hook entry points, however the CLI is reached, and the modules that record an approval (an interpreter that
# imports them could record one with a made-up payload just as the hook command could)
HOOK_ENTRY = re.compile(
    r"(?<![\w-])(?:codex-hook|install-hooks)(?![\w-])|--from-hook\b|\b(?:codexhook|approvehook)\b|"
    r"(?:\bbdd|main\.py|\bbddlib(?:\.cli)?)[\"']?\s+(?:guard|tripwire)\b|\bbddlib\b[\s.\w,]*\bapprovals\b", re.IGNORECASE)

NESTED_MESSAGE = ("greenlight: starting another Codex session from inside this one is not allowed in a greenlight "
                  "project: a prompt typed into a nested session could be used to approve work on the person's behalf. "
                  "Read-only commands such as `codex --version`, `codex login status` and `codex features list` are fine.")


def program(word: str) -> str:
    name = word.strip("\"'").replace("\\", "/").rsplit("/", 1)[-1].casefold()
    for suffix in (".exe", ".cmd", ".ps1"):
        name = name.removesuffix(suffix)
    return name


def _tokens(command: str) -> list[str]:
    """Words, with each separator, quote and brace kept as a token of its own."""
    return _TOKEN.findall(command)


def _is_program_position(tokens: list[str], index: int) -> bool:
    """Is the word at ``index`` the program being started: first in its command, or behind a launcher (``sudo``, ``timeout 5``,
    ``bash -lc "..."``, ``xargs``, ``cmd /c``)? Text inside the argument of another program (``-Value '# by codex'``) is not."""
    for position in range(index - 1, -1, -1):
        token = tokens[position]
        folded = token.casefold()
        if token in _QUOTES:
            continue
        if token in _BOUNDARIES:
            return True
        if folded in LAUNCH_OPTIONS:
            return True
        if token.startswith("-") or token.isdigit() or "=" in token:
            continue                                    # an option, a count or an assignment between launcher and program
        return program(token) in LAUNCHERS
    return True


def _quoted_flags(tokens: list[str]) -> list[bool]:
    """For each token: is it inside a quoted string?"""
    flags, opened = [], ""
    for token in tokens:
        if token in _QUOTES:
            if not opened:
                opened = token
            elif token == opened:
                opened = ""
            flags.append(False)
        else:
            flags.append(bool(opened))
    return flags


def starts_codex_session(command: str, derived: bool = False) -> bool:
    """Does the command start a (nested) Codex session, other than to read something? A ``codex`` word outside quotes counts
    wherever it sits; inside quotes it counts only where a program would start (a quoted script, ``-Value '# by codex'`` is text).
    ``derived`` is for a reading of the command with its quotes already removed (``co""dex``): there every word counts only
    where a program would start, since a quote that is gone can no longer say what was text."""
    tokens = _tokens(command)
    quoted = _quoted_flags(tokens)
    words = [(i, t) for i, t in enumerate(tokens) if t not in _QUOTES and t not in _BOUNDARIES and t not in _OTHER_PUNCTUATION]
    for place, (index, word) in enumerate(words):
        if program(word) == "codex" and (not quoted[index] and not derived or _is_program_position(tokens, index)):
            rest = tuple(next_word.casefold() for _, next_word in words[place + 1:place + 3])
            if not any(rest[:size] in READ_ONLY for size in (1, 2)):
                return True
    return bool(_RUNNERS.search(command) or _FROM_CODE.search(command))
