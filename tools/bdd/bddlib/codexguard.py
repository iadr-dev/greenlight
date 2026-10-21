"""The guard for a Codex tool call: the Claude Code guard's checks plus what only Codex needs.

Added to ``guard.evaluate_in_project`` (locks, managed data, per-path limits, the shell command text checks):

* a tool nobody has looked at is refused inside a project (see ``codexpayload.is_known``), and a call runs in the
  working directory it asks for, so ``workdir`` cannot be used to look like another folder;
* the person approves with ``$greenlight-approve`` in Codex, so that spelling in a tool call is refused like the
  Claude Code one;
* a nested Codex session is the way to produce a prompt that looks typed, so starting one is refused, apart from
  read-only commands;
* greenlight's own hook entry points (``bdd codex-hook``, ``--from-hook``, ``guard``, ``tripwire``, ``install-hooks``)
  are not for an agent to run: a made-up payload given to one of them could record an approval or change what the
  guard believes;
* everything Codex keeps for itself is off limits for writes: its home folder (hook and settings files, and the
  ``sessions`` folder whose rollout files are what an approval is checked against), any ``.codex`` folder, and any
  rollout file, whichever way the path is spelled (case, relative path, link); and so is changing where Codex's home
  is (``CODEX_HOME``).

Every text check runs on the command as written and on each way a shell could read it (quotes dropped, variables
expanded). Like the Claude Code guard this reads text, so it is friction and not the safeguard: the tripwire watches the
hook and settings files, an approval is checked against an append-only fingerprint of the rollout file, and a feature
with a Codex approval is never graded hard (see ``codexorigin``).
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from . import claudepaths, codexpayload, codexsession, enforcement, guard
from . import config as cfg
from .errors import StoreError

APPROVAL_TEXT = re.compile(r"\$greenlight-(?:approve|reject)\b", re.IGNORECASE)
_SETS_HOME = re.compile(r"\bCODEX_HOME\b\s*=|\b(?:set|setx|export)\s+CODEX_HOME\b", re.IGNORECASE)
_HOME_NAME = re.compile(r"\bCODEX_HOME\b", re.IGNORECASE)
_HOOK_ENTRY = codexsession.HOOK_ENTRY
CODEX_DIR = ".codex"
_CODEX_FOLDER = re.compile(r"(?<![\w.-])" + re.escape(CODEX_DIR) + r"(?![\w-])", re.IGNORECASE)
_ROLLOUT = re.compile(r"(?<![\w-])rollout-[\w.-]*\.jsonl", re.IGNORECASE)

NESTED_MESSAGE = codexsession.NESTED_MESSAGE
APPROVAL_MESSAGE = ("greenlight: approvals can only be given by the person typing $greenlight-approve themselves. "
                    "Running or sending that command from a tool would let the AI approve its own work. Ask the user to "
                    "type it.")
CONFIG_MESSAGE = ("greenlight: Codex's home folder, its hook and settings files and its session files keep greenlight's "
                  "hooks running and are what approvals are checked against; only Codex and the person write them, and "
                  "where Codex's home is (CODEX_HOME) is not for a command to change.")
HOOK_MESSAGE = ("greenlight: the hook entry points (`bdd codex-hook`, `--from-hook`, `guard`, `tripwire`, `install-hooks`) "
                "are run by Codex for the person; an agent calling one with a made-up payload could fake an approval.")
TOOL_MESSAGE = ("greenlight: the tool `{tool}` is not one greenlight knows to be harmless, and a tool it has not looked at "
                "could change locked files without the guard seeing it. If you have checked it, list it in "
                "`[approvals] codex_allowed_tools` in .bdd/config.toml.")
WORKDIR_MESSAGE = "greenlight: this tool call names a working directory that cannot be resolved, so it cannot be checked."


starts_codex_session = codexsession.starts_codex_session


def _key(path: Path | str) -> str:
    return Path(str(path).replace("\\", "/")).as_posix().casefold().rstrip("/")


def protected_roots(root: Path | None) -> list[str]:
    """Codex's home folder (the default, the one named by CODEX_HOME and the configured one) and the project's ``.codex``
    folder, resolved and case-folded, so that a path can be compared whatever its spelling."""
    homes = [claudepaths.codex_home(), Path.home() / CODEX_DIR]
    try:
        configured = cfg.load(root).codex_home if root else None
    except cfg.ConfigError:
        configured = None
    if configured:
        homes.append(Path(configured).expanduser())
    folders = [*homes, *([root / CODEX_DIR] if root else [])]
    return sorted({_key(folder.absolute()) for folder in folders} | {_key(os.path.realpath(folder)) for folder in folders})


def touches_codex_state(path_text: str, cwd: Path, root: Path | None) -> bool:
    """Is this path (as written, and with links followed) Codex's own: under its home, a ``.codex`` folder, or a rollout?"""
    written = Path(path_text.replace("\\", "/")).expanduser()
    candidate = written if written.is_absolute() else cwd / written
    roots = protected_roots(root)
    for spelling in (candidate, Path(os.path.realpath(candidate))):
        key = _key(spelling)
        if any(key == base or key.startswith(base + "/") for base in roots):
            return True
        if CODEX_DIR in key.split("/") or _ROLLOUT.fullmatch(key.rsplit("/", 1)[-1]):
            return True
    return False


def mentions_codex_state(text: str, root: Path | None) -> bool:
    """Does shell text name Codex's folders, its home variable or a rollout file (a write is then refused)?"""
    flattened = text.replace("\\", "/").casefold()
    return bool(_CODEX_FOLDER.search(text) or _HOME_NAME.search(text) or _ROLLOUT.search(text)
                or any(base in flattened for base in protected_roots(root)))


def check_reading(text: str, root: Path | None, derived: bool = False) -> str | None:
    """The Codex-specific reason to refuse one reading of a shell command, or None."""
    if APPROVAL_TEXT.search(text):
        return APPROVAL_MESSAGE
    if _HOOK_ENTRY.search(text):
        return HOOK_MESSAGE
    if starts_codex_session(text, derived):
        return NESTED_MESSAGE
    if _SETS_HOME.search(text):
        return CONFIG_MESSAGE
    scrubbed = guard._NOISE.sub(" ", text)
    if guard._SHELL_WRITES.search(scrubbed) and mentions_codex_state(scrubbed, root):
        return CONFIG_MESSAGE
    return None


def check_text(command: str, root: Path | None = None) -> str | None:
    """The reason a shell command is refused for Codex-specific reasons, or None. The command is checked as written and
    in each way a shell could read it, so a quote, a variable or a brace in the middle of a name does not hide it."""
    for derived, reading in [(False, command), *((True, other) for other in guard.shell_readings(command))]:
        reason = check_reading(reading, root, derived)
        if reason:
            return reason
    return None


def check_path(path: str, cwd: Path, root: Path | None) -> str | None:
    """The reason writing this file is refused for Codex-specific reasons, or None."""
    return CONFIG_MESSAGE if touches_codex_state(path, cwd, root) else None


def check_where(command: str, cwd: Path, root: Path) -> str | None:
    """A command that writes, run from inside Codex's own folders, writes there whatever file name it uses."""
    if guard._SHELL_WRITES.search(guard._NOISE.sub(" ", command)) and touches_codex_state(".", cwd, root):
        return CONFIG_MESSAGE
    return None


def codex_reason(call: dict, cwd: Path, root: Path) -> str | None:
    """What only Codex adds to the checks of one guard call."""
    tool_input = call["tool_input"]
    if call["tool_name"] == "Bash":
        return check_text(tool_input["command"], root) or check_where(tool_input["command"], cwd, root)
    if call["tool_name"] == "Write":
        return check_path(tool_input["file_path"], cwd, root)
    return None


def project_reason(root: Path, call: dict) -> str | None:
    """The Claude Code guard's verdict on a call, for this project whatever folder the call runs in. As there, anything
    that stops it from reaching a verdict blocks the call."""
    try:
        return guard.evaluate_in_project(root, call, Path(call["cwd"]))
    except (StoreError, cfg.ConfigError) as exc:
        return f"greenlight: cannot enforce the locks because {exc}. Restore the file (for example with git) and retry."
    except Exception as exc:    # deliberate: any failure inside a project blocks the call
        return f"greenlight: the guard hit an internal error ({type(exc).__name__}: {exc}) and blocks this call to stay safe."


_PATH_WORDS = re.compile(r"[\s;&|()`\"'<>=,]+")
UNRESOLVED_MESSAGE = ("greenlight: this command names a path that cannot be resolved, and it writes, so it cannot be checked "
                      "against the locks of the projects it might touch.")


def path_like(word: str) -> bool:
    return "/" in word or "\\" in word or word.startswith((".", "~")) or bool(re.match(r"[A-Za-z]:", word))


def resolve_word(word: str, cwd: Path) -> Path | None:
    """The place a path-like word names when the command runs in ``cwd``: ``~`` expanded, relative paths put after the
    working directory, ``..`` and links followed. None if it cannot be resolved."""
    if "\0" in word:
        return None
    try:
        path = Path(os.path.expanduser(word.replace("\\", "/")))
        return Path(os.path.realpath(path if path.is_absolute() else cwd / path))
    except (OSError, ValueError, RuntimeError):
        return None


def named_places(call: dict) -> list[str]:
    """The path-like words a call names: its file, the words of its command in every reading of it (variables expanded), or,
    for any other tool, every path-like string anywhere in its input."""
    tool_input = call["tool_input"]
    if call["tool_name"] == "Write":
        return [str(tool_input["file_path"])]
    if call["tool_name"] == "Bash":
        command = tool_input["command"]
        return [word for text in [command, *guard.shell_readings(command)] for word in _PATH_WORDS.split(text) if word and path_like(word)]
    return [text for text in codexpayload.strings(tool_input) if path_like(text)]


def writes(call: dict) -> bool:
    return call["tool_name"] == "Write" or (
        call["tool_name"] == "Bash" and bool(guard._SHELL_WRITES.search(guard._NOISE.sub(" ", call["tool_input"]["command"]))))


def projects_of(call: dict, root: Path | None) -> tuple[list[Path], bool]:
    """The greenlight projects whose rules apply to this call, and whether a path it names could not be resolved.

    The session's project (if it is in one); the one the call runs in; and any project that a path-like word of the call
    lands in once relative paths, ``~``, ``..`` and links are resolved. A call cannot get out from under a project's locks by
    running from, or naming a file in, another one, and a session that starts outside every project can still reach into
    one."""
    cwd = Path(call["cwd"])
    places, unresolved = [cwd], False
    for word in named_places(call):
        place = resolve_word(word, cwd)
        unresolved = unresolved or place is None
        places += [place] if place is not None else []
    found = {root} if root is not None else set()
    for place in places:
        project = cfg.find_root(place if place.is_dir() else place.parent)
        if project is not None:
            found.add(project)
    return sorted(found), unresolved


STDIN_REFUSAL = ("greenlight: text sent to a running interactive command cannot be checked, so inside a greenlight project only "
                 "polling (empty input) and a very small set of answers are allowed there: y, n, yes, no, q, a number of one to "
                 "three digits, or a single Enter. Run the command as a normal tool call instead.")
_STDIN_ANSWER = re.compile(r"(?:y|n|yes|no|q|\d{1,3})(?:\r?\n)?", re.IGNORECASE | re.ASCII)


def stdin_reason(payload: dict) -> str | None:
    """The strict rule for text sent to a running command, whose directory and state the guard cannot know.

    An allowlist, not a list of what is forbidden (that would always have holes): empty or white-space input (polling, or a
    single Enter), and the answers ``y``, ``n``, ``yes``, ``no``, ``q`` or a number of one to three digits, in any case, each
    with at most one new line after it. Everything else is refused, and the person runs it as a normal tool call."""
    tool, tool_input = payload.get("tool_name"), payload.get("tool_input")
    if not (isinstance(tool, str) and tool.casefold() in codexpayload.STDIN_TOOLS):
        return None
    chars = tool_input.get("chars", "") if isinstance(tool_input, dict) else None
    if not isinstance(chars, str):
        return STDIN_REFUSAL
    if not chars.strip() and len(chars) <= 3 and chars.count("\n") <= 1:
        return None
    return None if _STDIN_ANSWER.fullmatch(chars) else STDIN_REFUSAL


def session_refusal(project: Path, payload: dict) -> str | None:
    """The refusals that depend on a project's own configuration: a tool nobody has looked at."""
    try:
        allowed = cfg.load(project).codex_allowed_tools
    except cfg.ConfigError as exc:
        return f"greenlight: cannot enforce the locks because {exc}. Restore the file (for example with git) and retry."
    if not codexpayload.is_known(payload.get("tool_name"), allowed):
        return TOOL_MESSAGE.format(tool=payload.get("tool_name"))
    return None


def reached_projects(payload: dict, calls: list[dict]) -> tuple[list[Path], bool]:
    """The greenlight projects a tool call reaches, found before anything else is decided: the one it was started in, the
    one its working directory is in, and any that a path-like word or string of it lands in. Whether a path could not be
    resolved comes with them."""
    found: set[Path] = set()
    unresolved = False
    session = cfg.find_root(Path(payload.get("cwd") or "."))
    if session is not None:
        found.add(session)
    for call in calls:
        projects, missed = projects_of(call, None)
        found.update(projects)
        unresolved = unresolved or missed
    return sorted(found), unresolved


def project_reason_for(project: Path, payload: dict) -> str | None:
    """What the rules of one project say about the call: its tool allowlist, the strict rule for text sent to a running
    command, and every check on every call the tool call comes to."""
    refusal = session_refusal(project, payload) or stdin_reason(payload)
    if refusal:
        return refusal
    calls = codexpayload.guard_calls(payload)
    if calls is None:
        return codexpayload.UNREADABLE
    for call in calls:
        reason = codex_reason(call, Path(call["cwd"]), project) or project_reason(project, call)
        if reason:
            return reason
    return None


def project_at(place: Path | None) -> Path | None:
    """The greenlight project a place is in, if any."""
    if place is None:
        return None
    return cfg.find_root(place if place.is_dir() else place.parent)


def raw_reach(payload: dict) -> tuple[list[Path], bool]:
    """For a payload that could not be parsed into calls: the projects that the folder it runs in (its working directory,
    ``workdir`` included) and any path-like string anywhere in its tool input land in, and whether one could not be resolved.
    Relative words are resolved against the folder the call runs in."""
    runs_in = codexpayload.working_directory(payload)
    if runs_in is None:
        return [], True
    base = Path(runs_in)
    places = [base] + [resolve_word(word, base) for text in codexpayload.strings(payload.get("tool_input"))
                       for word in _PATH_WORDS.split(text) if word and path_like(word)]
    found = {project for project in map(project_at, places) if project is not None}
    return sorted(found), any(place is None for place in places)


def unreadable_reason(payload: dict) -> str | None:
    """The verdict on a payload that could not be parsed into calls.

    Refused when its working directory cannot be resolved, when it names a working directory at all (it then runs somewhere
    the rest of the payload cannot be tied to), when its session is in a project, and when its folder or any path-like string
    of its input lands in a project or cannot be resolved; let through only when it reaches no project."""
    if codexpayload.working_directory(payload) is None:
        return WORKDIR_MESSAGE
    tool_input = payload.get("tool_input")
    if isinstance(tool_input, dict) and any(tool_input.get(key) is not None for key in codexpayload.WORKDIR_KEYS):
        return codexpayload.UNREADABLE
    projects, unresolved = raw_reach(payload)
    if cfg.find_root(Path(payload.get("cwd") or ".")) is None and not projects and not unresolved:
        return None
    return codexpayload.UNREADABLE


def evaluate(payload: dict) -> str | None:
    """The reason to block this Codex tool call, or None to allow it.

    The projects the call reaches are worked out first (see ``reached_projects``); with none, nothing is enforced. Each
    project reached then applies its own rules to the whole call. A session that starts outside every project is not let off:
    a call that reaches into one is held to its rules."""
    calls = codexpayload.guard_calls(payload)
    if calls is None:
        return unreadable_reason(payload)
    projects, unresolved = reached_projects(payload, calls)
    if not projects:
        return None
    if unresolved and any(writes(call) for call in calls):
        return UNRESOLVED_MESSAGE
    for project in projects:
        reason = project_reason_for(project, payload)
        if reason:
            return reason
    return None
