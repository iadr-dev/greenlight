"""Does a shell command start a Codex session? One answer, used by the Codex guard and by the Claude Code guard.

A nested session is the way for an agent to produce a prompt that looks typed, so starting one is refused inside a greenlight
project, whichever tool the agent is running in. Any word anywhere in the text whose program name is ``codex`` counts, in
whatever argument it sits (``bash -lc "..."``, ``xargs``, ``timeout``, a script passed to an interpreter), unless it is a
read-only form such as ``codex --version``. A directory or a file merely called codex is caught too; that is the price of not
guessing how it is run. Like every text check in the guards this is friction, not the safeguard.
"""
from __future__ import annotations

import re

READ_ONLY = {("--version",), ("-v",), ("--help",), ("-h",), ("login", "status"), ("features", "list"), ("doctor",),
             ("plugin", "list"), ("mcp", "list"), ("mcp", "get")}
_WORDS = re.compile(r"[\s;&|()`\"'<>=,\[\]{}]+")
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


def starts_codex_session(command: str) -> bool:
    """Does the command start a (nested) Codex session, other than to read something?"""
    words = [word for word in _WORDS.split(command) if word]
    for index, word in enumerate(words):
        if program(word) == "codex":
            rest = tuple(next_word.casefold() for next_word in words[index + 1:index + 3])
            if not any(rest[:size] in READ_ONLY for size in (1, 2)):
                return True
    return bool(_RUNNERS.search(command) or _FROM_CODE.search(command))
