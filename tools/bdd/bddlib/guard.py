"""`bdd guard`: the PreToolUse hook that keeps the process honest.

Claude Code runs it before file-editing tools, Bash, and the tools that can schedule or send
prompts. It reads the hook payload (JSON) on stdin and either allows (exit 0, no output) or
blocks (exit 2, reason on stderr, which the model sees).

What it blocks inside a greenlight project:

* edits to files locked by a feature (approved specs, bound steps and drivers);
* edits to the CLI-managed data files (``state.json``, ``lock.json``, ``.bdd/config.toml``,
  enforcement markers);
* edits to what enforces all of this: the plugin's own files, and Claude Code settings or hooks
  (``.claude/settings*.json``) when the change involves hooks or plugins;
* writes outside what the calling agent is allowed to touch (see ``AGENT_WRITES``);
* shell commands that write to any of the above (best effort: a shell can always do things
  a hook cannot foresee, which is why ``bdd lock --check`` remains the guarantee);
* scheduling, sending or running anything that contains an approval command, in a tool call or in
  a shell command (for example a nested ``claude -p``), because such a prompt would reach the
  approval hook looking exactly like something the user typed.

Outside a project (no ``.bdd`` directory) it does nothing. Inside one it fails closed: if the guard
cannot work out whether a call is safe (unreadable lock data, broken configuration, an internal
error) the call is blocked and the reason says how to fix it.
"""
from __future__ import annotations

import fnmatch
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from . import claudepaths
from . import config as cfg
from . import enforcement, lockfile, store
from .config import ConfigError
from .errors import StoreError

WRITE_TOOLS = {"Edit": "file_path", "Write": "file_path", "MultiEdit": "file_path", "NotebookEdit": "notebook_path"}
INJECTION_TOOLS = {"CronCreate", "ScheduleWakeup", "SendMessage", "Skill", "RemoteTrigger"}
AGENT_PREFIX = "greenlight:"
CASE_INSENSITIVE_FS = sys.platform in ("win32", "darwin")

# Which kinds of file each greenlight agent may write. The orchestrator (no agent_type) may write
# anything that is not locked or managed. Categories: data (.bdd/), features, steps, production.
AGENT_WRITES = {
    "product-analyst": {"data"},
    "qa-designer": {"data", "features"},
    "system-analyst": {"data"},
    "step-engineer": {"data", "steps"},
    "implementer": {"data", "production"},
    "spec-auditor": set(),
}
MANAGED_NAMES = {"state.json", "lock.json"}
MANAGED_SUFFIXES = (".lock", ".tmp")
MANAGED_DIRS = (".enforcement", ".integrity", ".runs")   # session markers, integrity data, recorded test runs
ENVIRONMENT_DIRS = (".venv", "venv")           # the project's interpreter and packages: installed by the person
INSTALLED_PACKAGES = "node_modules"             # installed packages of a node project, wherever the folder is
MANAGED_CONFIG = "config.toml"          # only .bdd/config.toml: other projects have config.toml files too
SETTINGS_NAMES = {"settings.json", "settings.local.json"}
PLUGIN_ROOT_ENV = "CLAUDE_PLUGIN_ROOT"

_APPROVAL_TEXT = re.compile(r"greenlight:(?:approve|reject)\b", re.IGNORECASE)
# The only `claude ...` forms a greenlight project's agent may run: they neither start a session nor
# change anything. Everything else is refused, including `claude plugin disable|uninstall|install`,
# `mcp add|remove`, `config set` and `update`, because those can switch greenlight's own checks off.
_CLAUDE_READ_ONLY = {("--version",), ("-v",), ("--help",), ("-h",), ("doctor",),
                     ("plugin", "list"), ("plugins", "list"), ("plugin", "details"), ("plugin", "validate"),
                     ("mcp", "list"), ("mcp", "get"), ("config", "list"), ("config", "get")}
# `claude ...` as a command: at the start of a command or pipeline segment, after optional env/sudo-style
# prefixes and VAR=value assignments, possibly with a path in front. The next two words are captured in
# a lookahead, so a match does not swallow the text after it (a second `claude` inside `$(...)` is
# still found), and a word never contains a shell separator.
_ARG = r"[^\s;&|()`$]+"
_CLAUDE_CALL = re.compile(
    r"(?:^|[;&|(`\n]|\$\()\s*(?:(?:env|sudo|command|exec|nohup|time|nice)\s+|[A-Za-z_]\w*=\S*\s+)*"
    r"(?:\S*[\\/])?claude(?:\.exe|\.cmd)?(?=(?:\s+(" + _ARG + r"))?(?:\s+(" + _ARG + r"))?)", re.IGNORECASE)
# The `.claude` directory itself as an argument (not a file inside it): moving, deleting or replacing
# it with a symlink would take its settings with it.
_CLAUDE_DIR_ARG = re.compile(r"(?<![\w.-])\.claude/?(?=[\s;&|)]|$)", re.IGNORECASE)
_CLAUDE_RUNNER = re.compile(r"\b(?:npx|bunx|pnpm\s+dlx|yarn\s+dlx|npm\s+exec)\b[^;&|\n]*"
                            r"(?:\bclaude\b|@anthropic-ai/claude-code)", re.IGNORECASE)
_CLAUDE_FROM_CODE = re.compile(r"(?:subprocess|Popen|os\.system|os\.exec\w*|spawn\w*|execFile?|execa)\W[^\n]*"
                               r"\bclaude\b", re.IGNORECASE)
_GLOB = re.compile(r"[*?\[]")
# One list of what is protected inside a `.claude` folder, used by the text check and the glob check:
# the settings files, the hook scripts, and the session transcripts that approvals are verified against.
CLAUDE_PROTECTED_DIRS = ("hooks", "projects")
_SETTINGS_TEXT = re.compile(r"settings(?:\.local)?\.json|(?<![\w-])\.claude/(?:" + "|".join(CLAUDE_PROTECTED_DIRS) + r")\b",
                            re.IGNORECASE)
_BRACES = re.compile(r"\{([^{}]*,[^{}]*)\}")
_ANSI_C = re.compile(r"\$'((?:[^'\\]|\\.)*)'", re.DOTALL)
_VARIABLE = re.compile(r"\$\{(\w+)\}|\$(\w+)|%(\w+)%")
_HOME = re.compile(r"(?<![\w$])~(?=/|\\|\s|$)")
MAX_READINGS = 256
_NOISE = re.compile(r"\d?>\s*/dev/null|\d>&\d|&>\s*/dev/null|2>\s*nul\b", re.IGNORECASE)
_SHELL_WRITES = re.compile(
    r"(?:^|[\s;&|(])(?:sed\s+(?:-\w*i|--in-place)|perl\s+-\w*i|tee|cp|mv|rm|truncate|dd|install|ln|chmod|touch|"
    r"git\s+(?:checkout|restore|reset|stash|apply|rm|mv|clean)|Set-Content|Add-Content|Out-File|"
    r"Remove-Item|Move-Item|Copy-Item|New-Item|del|erase|move|copy)\b|>>?|write_text|write_bytes|"
    r"open\([^)]*[\"'][wa+]|\.write\(|\.writelines\(|os\.(?:remove|rename|replace|unlink)|shutil\.",
    re.IGNORECASE)


def path_key(path: Path | str) -> str:
    """A comparison key that is the same for every spelling of the same file."""
    resolved = os.path.realpath(path)
    key = resolved.replace("\\", "/")
    return key.casefold() if CASE_INSENSITIVE_FS else key


@dataclass(frozen=True)
class Locked:
    feature: str
    scope: str
    path: Path


class Project:
    """What the guard needs to know about the project: locked files, data files, directories."""

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.config = cfg.load(self.root)
        self.locked: dict[str, Locked] = {}
        self.load_locks()

    def load_locks(self) -> None:
        for feature_dir in sorted(store.features_dir(self.root).glob("FEAT-*")):
            lock_path = feature_dir / lockfile.LOCK_FILE
            if not lock_path.is_file():
                continue
            data = store.read_json(lock_path, "lock file")        # StoreError propagates: fail closed
            for scope, entry in data.get("scopes", {}).items():
                for rel in entry.get("files", {}):
                    self.locked[path_key(self.root / rel)] = Locked(data.get("feature", feature_dir.name), scope,
                                                                    self.root / rel)

    def relative(self, path: Path) -> str:
        try:
            return Path(os.path.realpath(path)).relative_to(self.root).as_posix()
        except ValueError:
            return path.as_posix()

    def is_data(self, path: Path) -> bool:
        key, data_root = path_key(path), path_key(self.root / cfg.BDD_DIR)
        if not key.startswith(data_root + "/"):
            return False
        inside = key[len(data_root) + 1:]
        name = inside.rsplit("/", 1)[-1]
        return (inside.startswith(tuple(d + "/" for d in MANAGED_DIRS)) or name in MANAGED_NAMES or name.endswith(MANAGED_SUFFIXES)
                or inside == MANAGED_CONFIG)

    def category(self, path: Path) -> str:
        key = path_key(path)
        if key.startswith(path_key(self.root / cfg.BDD_DIR) + "/"):
            return "data"
        if any(key.startswith(path_key(self.root / name) + "/") for name in ENVIRONMENT_DIRS) or INSTALLED_PACKAGES in key.split("/"):
            return "environment"
        if key in {path_key(f) for f in self.config.support_files}:
            return "steps"
        if any(cfg.pattern_matches(pattern, self.relative(path)) for pattern in self.config.support_patterns):
            return "steps"
        for category, dirs in (("features", self.config.feature_dirs), ("steps", self.config.step_dirs)):
            if any(key.startswith(path_key(d) + "/") for d in dirs):
                return category
        return "production"


def locked_message(project: Project, path: Path, lock: Locked) -> str:
    return (f"greenlight: {project.relative(path)} is locked by {lock.feature} ({lock.scope}). Approved specs and "
            "bound steps are read-only while a feature is in progress. If the spec or a step is really wrong, "
            "stop and raise a change request with the user; unlocking needs a recorded reason "
            f"(bdd unlock {lock.feature} --scope {lock.scope} --reason \"...\").")


def managed_message(project: Project, path: Path) -> str:
    return (f"greenlight: {project.relative(path)} is managed by the bdd command line (state, locks, approvals, "
            "project configuration). Use the bdd commands instead of editing it; the person can edit it "
            "themselves outside the agent.")


def enforcement_message(path: Path, what: str) -> str:
    return (f"greenlight: {path.as_posix()} {what}. Changing it could switch off the checks that keep the AI "
            "from approving or weakening its own work, so it is not allowed from inside the agent. The person "
            "can change it themselves outside the agent.")


def check_enforcement_files(path: Path) -> str | None:
    """Protect what enforces greenlight: the plugin's own files and Claude Code's settings.

    Settings files are refused whatever the change says. Inspecting the new content for hook
    settings can be dodged (JSON escapes such as ``"hoo\\u006bs"`` mean the same key), and the
    person can still edit them, or use Claude Code's own /permissions and /hooks screens."""
    plugin_root = os.environ.get(PLUGIN_ROOT_ENV)
    key = path_key(path)
    if plugin_root and key.startswith(path_key(plugin_root) + "/"):
        return enforcement_message(path, "is part of the greenlight plugin")
    if "/.claude/hooks/" in key:
        return enforcement_message(path, "is a Claude Code hook")
    if any(key.startswith(path_key(root) + "/") for root in claudepaths.transcript_roots()):
        return enforcement_message(path, "is a Claude Code session transcript, which approvals are verified against")
    # Both spellings: the path as written (a `.claude` that is itself a symlink to somewhere else
    # resolves to a path without `.claude` in it) and the resolved path (a symlink *to* `.claude`).
    for parts in (path.parts, Path(os.path.realpath(path)).parts):
        names = [part.casefold() for part in parts]
        if ".claude" in names[:-1] and names[-1] in SETTINGS_NAMES:
            return enforcement_message(path, "is a Claude Code settings file")
    return None


_INSTALL = re.compile(r"\b(?:pip3?|pipx|poetry|pipenv|conda)\s+(?:install|add|sync|i)\b|-m\s+pip3?\s+install\b"
                      r"|\buv\s+(?:pip\s+install|add|sync)\b", re.IGNORECASE)
_ENVIRONMENT_PATH = re.compile(r"(?<![\w.-])(?:\.venv|venv|node_modules)(?![\w.-])", re.IGNORECASE)   # a whole path segment
# Node package managers: whatever follows the program name and its flags decides. `npm run build` is fine, `npm --prefix
# tests ci` is not, and neither is anything that fetches a package and runs it (npx, npm exec, pnpm dlx).
PACKAGE_MANAGERS = {"npm", "pnpm", "yarn", "bun"}
FETCH_AND_RUN = {"npx", "pnpx", "bunx"}
PACKAGE_COMMANDS = {"install", "i", "add", "ci", "link", "ln", "unlink", "uninstall", "un", "remove", "rm", "r", "update", "up",
                    "upgrade", "rebuild", "prune", "dedupe", "ddp", "it", "cit", "install-test", "install-ci-test", "exec", "dlx", "x"}
VALUE_FLAGS = {"--prefix", "-C", "--cwd", "--dir", "--workspace", "-w", "--filter", "-F", "--registry", "--cache",
               "--userconfig", "--loglevel", "--tag"}           # flags whose value is the next word
_SIMPLE_COMMANDS = re.compile(r"[;&|\n`()]+")
INSTALL_MESSAGE = ("greenlight: an agent may not install packages or change the project's environment (.venv, venv, node_modules): "
                   "that is the person's decision and it would change what the tests run on. Report the missing "
                   "requirement instead.")


def _program(word: str) -> str:
    name = word.strip("\"'").replace("\\", "/").rsplit("/", 1)[-1].casefold()
    return re.sub(r"\.(?:cmd|exe|ps1)$", "", name)


def _subcommand(words: list[str]) -> str | None:
    """The first word that is not a flag or a flag's value, or None if there is none."""
    skip = False
    for word in (w.strip("\"'") for w in words):
        if skip:
            skip = False
        elif word.startswith("-"):
            skip = word in VALUE_FLAGS
        else:
            return word.casefold()
    return None


def changes_packages(command: str) -> bool:
    """Does a simple command in ``command`` install, remove or update packages, or fetch one and run it?"""
    for simple in _SIMPLE_COMMANDS.split(command):
        words = simple.split()
        for at, word in enumerate(words):
            program = _program(word)
            if program in FETCH_AND_RUN:
                return True
            if program in PACKAGE_MANAGERS:
                subcommand = _subcommand(words[at + 1:])
                if subcommand in PACKAGE_COMMANDS or (subcommand is None and program == "yarn"):   # bare `yarn` installs
                    return True
    return False


def agent_name(payload: dict) -> str | None:
    agent_type = payload.get("agent_type") or ""
    return agent_type[len(AGENT_PREFIX):] if agent_type.startswith(AGENT_PREFIX) else None


def check_file_write(project: Project, path: Path, agent: str | None) -> str | None:
    lock = project.locked.get(path_key(path))
    if lock:
        return locked_message(project, path, lock)
    if project.is_data(path):
        return managed_message(project, path)
    protected = check_enforcement_files(path)
    if protected:
        return protected
    allowed = AGENT_WRITES.get(agent) if agent else None
    category = project.category(path)
    if allowed is not None and category not in allowed:
        what = ", ".join(sorted(allowed)) or "nothing (it is read-only)"
        return (f"greenlight: the {agent} agent may not write {category} files ({project.relative(path)}); "
                f"it may write: {what}.")
    return None


def mentioned_protected(project: Project, command: str) -> tuple[Path, Locked | None] | None:
    """A locked or managed file that the command names, if there is one.

    Matches on the file name anywhere in the command text, whatever the quoting or slash style
    (``features/a.feature``, ``'a.feature'`` inside a Python one-liner, a backslash path), so a
    command that ``cd``s first or builds the path in a script is still recognised. A false alarm
    only produces a clear refusal; a miss would defeat the point."""
    by_name = {lock.path.name.casefold(): lock for lock in project.locked.values()}
    names = sorted(set(by_name) | MANAGED_NAMES, key=len, reverse=True)
    pattern = re.compile(r"(?<![\w.-])(?:" + "|".join(re.escape(n) for n in names) + r")(?![\w-])")
    for reading in shell_readings(command):
        text = reading.casefold()
        match = pattern.search(text)
        if match:
            name = match.group(0)
            lock = by_name.get(name)
            return (lock.path if lock else project.root / cfg.BDD_DIR / name), lock
        if ".bdd/config.toml" in text:
            return project.root / cfg.BDD_DIR / MANAGED_CONFIG, None
        for managed in MANAGED_DIRS:
            if f"/{managed}/" in text:
                return project.root / cfg.BDD_DIR / managed, None
    return None


def command_touches_enforcement(command: str) -> bool:
    """Does a (write-like) shell command target Claude Code's hook settings or the plugin itself?"""
    plugin_root = os.environ.get(PLUGIN_ROOT_ENV)
    named_places = [path_key(root) for root in claudepaths.transcript_roots()]
    if plugin_root:
        named_places.append(path_key(plugin_root))
    for text in shell_readings(command):
        if _SETTINGS_TEXT.search(text) or _CLAUDE_DIR_ARG.search(text) or glob_reaches_claude(text):
            return True
        if any(place in text.casefold() for place in named_places):
            return True
    return False


def decode_ansi_c(text: str) -> str:
    """Decode bash ``$'...'`` strings (``$'.cl\\x61ude'`` is ``.claude``)."""
    def decode(match: re.Match) -> str:
        try:
            return match.group(1).encode("utf-8").decode("unicode_escape")
        except UnicodeDecodeError:
            return match.group(1)
    return _ANSI_C.sub(decode, text)


def expand_variables(text: str) -> str:
    """Substitute ``$VAR``, ``${VAR}``, ``%VAR%`` and a leading ``~`` from this process's environment
    (the hook runs with the same environment as the agent's shell), leaving unknown names alone."""
    def substitute(match: re.Match) -> str:
        name = next(group for group in match.groups() if group)
        return os.environ.get(name, match.group(0))
    home = str(Path.home()).replace("\\", "/")
    return _HOME.sub(lambda _match: home, _VARIABLE.sub(substitute, text))


def expand_braces(text: str, limit: int = 64) -> list[str]:
    """Bash brace expansion for ``{a,b}`` lists (``.{claude,x}`` is ``.claude`` and ``.x``), bounded."""
    results = [text]
    for _ in range(6):                                       # nesting depth
        expanded, changed = [], False
        for item in results:
            match = _BRACES.search(item)
            if match is None:
                expanded.append(item)
                continue
            changed = True
            expanded += [item[:match.start()] + option + item[match.end():] for option in match.group(1).split(",")]
        results = expanded[:limit]
        if not changed:
            break
    return results


def shell_readings(command: str) -> list[str]:
    """The ways a shell could read this command's file names, so each can be checked.

    ANSI-C strings are decoded, variables and ``~`` substituted, braces expanded, and quotes dropped
    (``.cla"ude/set"tings.json`` spells a path). A backslash is either a Windows separator or, in a
    POSIX shell, an escape for the next character (``.cla\\ude``): one reading each. Bounded."""
    decoded = decode_ansi_c(command)
    readings: list[str] = []
    for variant in (decoded, expand_variables(decoded)):
        for expanded in expand_braces(variant):
            unquoted = expanded.replace('"', "").replace("'", "")
            readings += [unquoted.replace("\\", "/"), re.sub(r"\\(.)", r"\1", unquoted)]
    return readings[:MAX_READINGS]


def glob_reaches_claude(text: str) -> bool:
    """Could a glob in the command expand to the `.claude` folder, or to a settings file inside it?

    Decided by matching the glob against the real names, not by guessing: `.cl*`, `.c?aude` and
    `.*` reach `.claude`; `.gitignore*` and `build/*` do not. Shells do not let `*` match a leading dot,
    so a segment has to start with a dot to count."""
    for token in re.split(r"[\s;&|()`]+", text):
        segments = token.split("/")
        for position, segment in enumerate(segments):
            if segment.startswith(".") and _GLOB.search(segment) and fnmatch.fnmatchcase(".claude", segment.casefold()):
                return True
            following = segments[position + 1] if position + 1 < len(segments) else ""
            if segment.casefold() == ".claude" and _GLOB.search(following) and any(
                    fnmatch.fnmatchcase(name, following.casefold()) for name in (*SETTINGS_NAMES, *CLAUDE_PROTECTED_DIRS)):
                return True
    return False


def starts_claude_session(command: str) -> bool:
    """Does the command start a (nested) Claude Code session?

    A nested session is the one way for the agent to produce a prompt that *looks* typed. Matching
    the approval text alone cannot be complete (it can be built from pieces), so the session itself
    is refused, and so is every management command that changes something (``plugin disable``
    would switch greenlight off). Only the read-only forms in ``_CLAUDE_READ_ONLY`` pass. This is
    friction, not the safeguard: the approval is still checked against the transcript, and a
    prompt from a headless session is not accepted by default."""
    for call in _CLAUDE_CALL.finditer(command):
        words = tuple(word.strip("\"'").casefold() for word in call.groups() if word)
        if any("claude" in word for word in words) or not any(words[:size] in _CLAUDE_READ_ONLY for size in (1, 2)):
            return True
    return bool(_CLAUDE_RUNNER.search(command) or _CLAUDE_FROM_CODE.search(command))


NESTED_SESSION_MESSAGE = (
    "greenlight: starting another Claude Code session from inside this one is not allowed in a greenlight "
    "project: a prompt typed into a nested session could be used to approve work on the person's behalf, and "
    "commands such as `claude plugin disable` would switch greenlight off. Read-only commands such as "
    "`claude plugin list`, `claude mcp list` and `claude --version` are fine.")


def check_bash(project: Project, command: str, agent: str | None = None) -> str | None:
    """Best effort: block a command that runs an approval or a nested Claude session, or that both
    names a protected file and looks like it writes."""
    injection = check_injection({"command": command})
    if injection:
        return injection
    if starts_claude_session(command):
        return NESTED_SESSION_MESSAGE
    scrubbed = _NOISE.sub(" ", command)
    if agent and (_INSTALL.search(scrubbed) or changes_packages(scrubbed)):
        return INSTALL_MESSAGE
    if not _SHELL_WRITES.search(scrubbed):
        return None
    if agent and _ENVIRONMENT_PATH.search(scrubbed):
        return INSTALL_MESSAGE
    if command_touches_enforcement(scrubbed):
        return enforcement_message(Path("the targeted file"), "is part of what enforces greenlight "
                                   "(Claude Code hook settings or the plugin itself)")
    hit = mentioned_protected(project, scrubbed)
    if hit is None:
        return None
    target, lock = hit
    base = locked_message(project, target, lock) if lock else managed_message(project, target)
    return base + " (This shell command looks like it writes to it.)"


def check_injection(tool_input: dict) -> str | None:
    if _APPROVAL_TEXT.search(json.dumps(tool_input, ensure_ascii=False)):
        return ("greenlight: approvals can only be given by the person typing /greenlight:approve or "
                "/greenlight:reject themselves. Scheduling, sending, running (for example in a nested `claude` "
                "session) or invoking that command from a tool would let the AI approve its own work, so it is "
                "not allowed. Ask the user to type it.")
    return None


def evaluate_in_project(root: Path, payload: dict, cwd: Path) -> str | None:
    tool, tool_input = payload.get("tool_name"), payload.get("tool_input") or {}
    if tool in INJECTION_TOOLS:
        return check_injection(tool_input)
    project = Project(root)
    enforcement.touch(root, payload.get("session_id"))      # evidence that hooks ran in this session
    if tool in WRITE_TOOLS and tool_input.get(WRITE_TOOLS[tool]):
        raw = Path(tool_input[WRITE_TOOLS[tool]])
        return check_file_write(project, raw if raw.is_absolute() else cwd / raw, agent_name(payload))
    if tool == "Bash" and tool_input.get("command"):
        return check_bash(project, tool_input["command"], agent_name(payload))
    return None


def evaluate(payload: dict) -> str | None:
    """The reason to block this tool call, or None to allow it.

    Inside a project this fails closed: whatever stops the guard from reaching a verdict blocks
    the call, because a guard that can be switched off by corrupting a file is not a guard."""
    cwd = Path(payload.get("cwd") or os.getcwd())
    root = cfg.find_root(cwd)
    if root is None:
        return None
    try:
        return evaluate_in_project(root, payload, cwd)
    except (StoreError, ConfigError) as exc:
        return f"greenlight: cannot enforce the locks because {exc}. Restore the file (for example with git) and retry."
    except Exception as exc:    # deliberate: any failure inside a project blocks the call
        return (f"greenlight: the guard hit an internal error ({type(exc).__name__}: {exc}) and blocks this call "
                "to stay safe. Please report it; the person can disable the greenlight plugin to continue.")


def main(argv: list[str]) -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except ValueError as exc:                    # nothing to evaluate, and no way to tell if this is a project
        print(f"greenlight guard: unreadable hook input ({exc}); allowing the call", file=sys.stderr)
        return 0
    reason = evaluate(payload) if isinstance(payload, dict) else None
    if reason:
        print(reason, file=sys.stderr)
        return 2
    return 0
