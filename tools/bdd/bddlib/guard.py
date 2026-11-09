"""`bdd guard`: the PreToolUse hook that keeps the process honest.

Claude Code runs it before file-editing tools, Bash, and the tools that can schedule or send
prompts. It reads the hook payload (JSON) on stdin and either allows (exit 0, no output) or
blocks (exit 2, reason on stderr, which the model sees).

What it blocks inside a greenlight project:

* edits to files locked by a feature (approved specs, bound steps and drivers) or by the project (the shared
  test plumbing);
* edits to the CLI-managed data files (``state.json``, ``lock.json``, ``.bdd/config.toml``,
  enforcement markers);
* edits to what enforces all of this: the plugin's own files, Claude Code's hook scripts and session transcripts, and
  the parts of Claude Code's settings that could switch greenlight off (``claudepaths.settings_view``); a file tool's
  settings change is judged by the file it would leave, a shell's is refused;
* writes outside what the calling agent is allowed to touch (see ``AGENT_WRITES``); a script in the system temp folder,
  outside every project, is scratch and anyone's;
* shell commands that write to any of the above (best effort: a shell can always do things
  a hook cannot foresee, which is why ``bdd lock --check`` remains the guarantee). Only what a command writes to counts
  (``shellwrites``): its redirections, the arguments of the commands that change files and the code of an interpreter
  that writes, not a quoted argument, a regular expression or the bdd command line's own path;
* scheduling, sending or running anything that contains an approval command, in a tool call or in
  a shell command (for example a nested ``claude -p``), because such a prompt would reach the
  approval hook looking exactly like something the user typed.

This is a best-effort text check, not a sandbox: a shell has more spellings than any pattern list covers, and the pattern
sets are deliberately not grown to chase them. What holds is elsewhere: the lock check and the tripwire (they report the
effect of a change, whatever command made it, including the installed test tooling), the deny rules that ``bdd doctor``
shows and only the person can add, and the same checks in CI.

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
import tempfile
from dataclasses import dataclass
from pathlib import Path

from . import claudepaths, codexsession
from . import config as cfg
from . import enforcement, lockfile, reviewlog, roles, sharedvocab, shellwrites, store
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
    "ui-engineer": {"data", "production"},
    "code-reviewer": {"data"},              # the reviewers write their report under .bdd/ and nothing else
    "security-reviewer": {"data"},
    "ui-reviewer": {"data"},
    "spec-auditor": set(),
}
# A subagent that is not one of greenlight's (a built-in one, a user's own, another plugin's) gets what the implementer
# gets: it may never write the feature files or the steps, whichever tests are locked yet.
FOREIGN_AGENT = "another agent"
FOREIGN_WRITES = {"data", "production"}
MANAGED_NAMES = {"state.json", "lock.json", "docs-consulted.json", sharedvocab.LOCK_NAME, lockfile.PLUMBING_FILE}
MANAGED_SUFFIXES = (".lock", ".tmp")
MANAGED_DIRS = (".enforcement", ".integrity", ".runs")   # session markers, integrity data, recorded test runs
ENVIRONMENT_DIRS = (".venv", "venv")           # the project's interpreter and packages: installed by the person
INSTALLED_PACKAGES = "node_modules"             # installed packages of a node project, wherever the folder is
MANAGED_CONFIG = "config.toml"          # only .bdd/config.toml: other projects have config.toml files too
PERSON_FILES = (MANAGED_CONFIG, "standards.md")   # in .bdd/, edited by the person only
SETTINGS_NAMES = claudepaths.SETTINGS_NAMES
PLUGIN_ROOT_ENV = "CLAUDE_PLUGIN_ROOT"
PROJECT_OWNER = "the project"           # who holds the plumbing lock

_APPROVAL_TEXT = re.compile(r"greenlight:(?:approve|reject)\b|\$greenlight-(?:approve|reject)\b", re.IGNORECASE)
# Codex: its hook entry points are not for an agent to run (a made-up payload could fake an approval), and its home,
# its `.codex` folders and its session (rollout) files are not for an agent to write, whichever tool is calling.
_CODEX_HOOK_ENTRY = codexsession.HOOK_ENTRY
_CODEX_STATE = re.compile(r"(?<![\w.-])\.codex(?![\w-])|\bCODEX_HOME\b|(?<![\w-])rollout-[\w.-]*\.jsonl", re.IGNORECASE)
CODEX_HOOK_MESSAGE = ("greenlight: the hook entry points (`codex-hook`, `install-hooks`, `--from-hook`) are run by the "
                      "tools' hooks for the person; calling one with a made-up payload could fake an approval.")
CODEX_STATE_MESSAGE = ("greenlight: Codex's home folder, its `.codex` folders, its hook and settings files and its session "
                       "files are what Codex-side enforcement and approvals rest on; only Codex and the person write them.")
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
    r"(?:^|[\s;&|(\"'`{=])(?:sed\s+(?:-\w*i|--in-place)|perl\s+-\w*i|tee|cp|mv|rm|truncate|dd|install|ln|chmod|touch|"
    r"git\s+(?:checkout|restore|reset|stash|apply|rm|mv|clean)|Set-Content|Add-Content|Out-File|"
    r"Remove-Item|Move-Item|Copy-Item|New-Item|del|erase|move|copy)\b|>>?|write_text|write_bytes|"
    r"open\([^)]*[\"'][wa+]|\.write\(|\.writelines\(|os\.(?:remove|rename|replace|unlink)|shutil\.",
    re.IGNORECASE)


def path_key(path: Path | str) -> str:
    """A comparison key that is the same for every spelling of the same file."""
    resolved = os.path.realpath(path)
    key = resolved.replace("\\", "/")
    if sys.platform == "win32":                    # Windows drops trailing dots and spaces: `a.feature.` is `a.feature`
        key = "/".join(part.rstrip(". ") or part for part in key.split("/"))
    return key.casefold() if CASE_INSENSITIVE_FS else key


def file_name(token: str) -> str:
    """The file name a written path ends in, compared the way the file system compares it."""
    name = token.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
    if sys.platform == "win32":
        name = name.rstrip(". ") or name
    return name.casefold()


SCRATCH = "scratch"


def is_scratch(key: str, root: Path) -> bool:
    """Is the file (by its ``path_key``) under the system temp folder and outside every greenlight project, this one
    included? Then it is a scratch file: no project's tests run on it and no project's rules cover it."""
    temp = path_key(tempfile.gettempdir())
    if not key.startswith(temp + "/") or key.startswith(path_key(root) + "/"):
        return False
    return cfg.find_root(Path(key).parent) is None


@dataclass(frozen=True)
class Locked:
    feature: str
    scope: str
    path: Path


class Project:
    """What the guard needs to know about the project: locked files, data files, directories."""

    def __init__(self, root: Path, follow_workspace: bool = True):
        self.root = root.resolve()
        self.config = cfg.load(self.root)
        self.locked: dict[str, Locked] = {}
        self.shared = {path_key(f): f for f in sharedvocab.protected_files(self.config.vocabulary_file)}   # included vocabularies
        self.load_locks()
        # The other repositories of a workspace are protected with their own locks and data, wherever the tool call
        # reaches them from. Which directories a session includes is not in the hook input, so a member that no tool
        # call touches is simply not seen here. Every configured member is protected, whether or not its directory or its
        # .bdd exists yet: a missing folder is not a way round the rules.
        self.members = [Project(m.path, follow_workspace=False) for m in self.config.workspace if follow_workspace]
        for member in self.members:
            self.locked.update(member.locked)

    def owner_of(self, path: Path) -> Project:
        """The project (this one or a member) whose files include ``path``."""
        key = path_key(path)
        for member in self.members:
            if key == path_key(member.root) or key.startswith(path_key(member.root) + "/"):
                return member
        return self

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
        plumbing = lockfile.read_plumbing(self.root)                # StoreError propagates: fail closed
        if not plumbing.get("unlocked"):
            for rel in plumbing.get("files", {}):
                self.locked[path_key(self.root / rel)] = Locked(PROJECT_OWNER, lockfile.PLUMBING, self.root / rel)

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
                or inside in PERSON_FILES)

    def category(self, path: Path) -> str:
        key = path_key(path)
        if is_scratch(key, self.root):
            return SCRATCH
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
    if lock.scope == lockfile.PLUMBING:
        return (f"greenlight: {project.relative(path)} is shared test plumbing, locked by the project. Every feature's "
                "tests run on it, so a change to it is its own change: the person or the orchestrator releases it with "
                "`bdd unlock --plumbing --reason \"...\"` and locks it again with `bdd lock --plumbing --reason \"...\"`, "
                "after which every bound feature reruns its scenarios once.")
    return (f"greenlight: {project.relative(path)} is locked by {lock.feature} ({lock.scope}). Approved specs and "
            "bound steps are read-only while a feature is in progress. If the spec or a step is really wrong, "
            "stop and raise a change request with the user; unlocking needs a recorded reason "
            f"(bdd unlock {lock.feature} --scope {lock.scope} --reason \"...\").")


def managed_message(project: Project, path: Path) -> str:
    return (f"greenlight: {project.relative(path)} is managed by the bdd command line (state, locks, approvals, "
            "project configuration, engineering standards, shared vocabularies). Use the bdd commands instead of editing it; the person can edit it "
            "themselves outside the agent.")


def enforcement_message(path: Path, what: str) -> str:
    return (f"greenlight: {path.as_posix()} {what}. Changing it could switch off the checks that keep the AI "
            "from approving or weakening its own work, so it is not allowed from inside the agent. The person "
            "can change it themselves outside the agent.")


def check_enforcement_files(path: Path, change: dict | None = None) -> str | None:
    """Protect what enforces greenlight: the plugin's own files, Claude Code's hook scripts, its session transcripts
    (not the memory notes next to them) and the parts of its settings that could switch greenlight off.

    A settings change made with a file tool (``change`` is the tool call) is judged by the file it would leave
    (``settings_refusal``); one made any other way, such as a shell, is refused."""
    plugin_root = os.environ.get(PLUGIN_ROOT_ENV)
    key = path_key(path)
    if plugin_root and key.startswith(path_key(plugin_root) + "/"):
        return enforcement_message(path, "is part of the greenlight plugin")
    if "/.claude/hooks/" in key:
        return enforcement_message(path, "is a Claude Code hook")
    if any(key.startswith(path_key(root) + "/") and not is_memory(key, path_key(root)) for root in claudepaths.transcript_roots()):
        return enforcement_message(path, "is a Claude Code session transcript, which approvals are verified against")
    if claudepaths.is_settings_file(path):
        if change is None:
            return enforcement_message(path, "is a Claude Code settings file")
        return settings_refusal(path, change)
    return None


def is_memory(key: str, root: str) -> bool:
    """Is the file (by its ``path_key``) a memory note, ``<projects>/<project>/memory/...``? Claude Code keeps its
    auto-memory there; transcripts are looked up only one folder down (``approvals.find_transcript``)."""
    parts = key[len(root) + 1:].split("/")
    return len(parts) >= 3 and parts[1] == "memory"


def settings_refusal(path: Path, change: dict) -> str | None:
    """Refuse a file tool's change to a Claude Code settings file when the file it would leave differs from the file now
    in a part that could switch greenlight off (``claudepaths.settings_view``), or when either cannot be read as
    JSON. The new file is computed the way the tool writes it: Write's content, Edit's exact replacement."""
    what = "is a Claude Code settings file"
    target = Path(os.path.realpath(path))
    try:
        old = target.read_text(encoding="utf-8") if target.exists() else None
    except (OSError, UnicodeDecodeError) as exc:
        return enforcement_message(path, f"{what} that cannot be read ({exc})")
    try:
        new = changed_text(old, change)
    except ValueError as exc:
        return enforcement_message(path, f"{what}, and this change cannot be judged: {exc}")
    try:
        before = claudepaths.parse_settings(old) if old is not None else {}
    except ValueError as exc:
        return enforcement_message(path, f"{what} that is not valid JSON now ({exc}), so a change cannot be judged")
    try:
        after = claudepaths.parse_settings(new)
    except ValueError as exc:
        return enforcement_message(path, f"{what}, and the change would leave it invalid JSON ({exc})")
    differs = claudepaths.view_differences(before, after)
    if not differs:
        return None
    deny = (" greenlight's own deny rules are added by the person with `bdd doctor --add-deny-rules`."
            if "permissions.deny" in differs else "")
    return enforcement_message(path, f"{what}, and this change touches {', '.join(differs)}, which can switch off "
                               "greenlight's checks") + deny


def changed_text(old: str | None, change: dict) -> str:
    """The file a Write, Edit or MultiEdit would leave. Edit replaces ``old_string`` exactly as Claude Code does: it must
    be found, and only once unless ``replace_all``; otherwise the tool fails, and the change is not judged."""
    tool, tool_input = change.get("tool_name"), change.get("tool_input") or {}
    if tool == "Write":
        if not isinstance(tool_input.get("content"), str):
            raise ValueError("Write has no content")
        return tool_input["content"]
    edits = [tool_input] if tool == "Edit" else tool_input.get("edits") if tool == "MultiEdit" else None
    if not isinstance(edits, list):
        raise ValueError(f"{tool} is not a Write, Edit or MultiEdit")
    text = old
    for edit in edits:
        if not isinstance(edit, dict) or not isinstance(edit.get("old_string"), str) or not isinstance(edit.get("new_string"), str):
            raise ValueError("an edit has no old_string or new_string")
        before, after = edit["old_string"], edit["new_string"]
        if text is None:
            if before:
                raise ValueError("the file does not exist")
            text = after
            continue
        count = text.count(before) if before else 0
        if count == 0 or (count > 1 and not edit.get("replace_all")):
            raise ValueError("old_string is not found exactly once")
        text = text.replace(before, after) if edit.get("replace_all") else text.replace(before, after, 1)
    if text is None:
        raise ValueError("no edit")
    return text


_INSTALL = re.compile(r"\b(?:pip3?|pipx|poetry|pipenv|conda)\s+(?:install|add|sync|i)\b|-m\s+pip3?\s+install\b"
                      r"|\buv\s+(?:pip\s+install|add|sync)\b", re.IGNORECASE)
_ENVIRONMENT_PATH = re.compile(r"(?<![\w.-])(?:\.venv|venv|node_modules)(?![\w.-])", re.IGNORECASE)   # a whole path segment
# Node package tools fail closed. For an agent a command that runs npm, pnpm, yarn or bun is allowed only when the
# subcommand comes first (after at most a few flags that take no value) and is a script or read-only one; anything else
# is refused, and so are the programs that fetch a package and run it. No tool's flag parsing is modelled: a flag that
# might take a value in front of the subcommand makes its place unclear, and an unclear place is a refusal.
NODE_PROGRAMS = {"npm": "npm", "pnpm": "pnpm", "yarn": "yarn", "yarnpkg": "yarn", "bun": "bun",
                 "npx": "fetch", "pnpx": "fetch", "bunx": "fetch", "corepack": "fetch"}
SCRIPT_SUFFIXES = {"cmd", "exe", "ps1", "js", "cjs", "mjs"}
SAFE_SUBCOMMANDS = {"run", "run-script", "test", "t", "ls", "list", "why", "view", "info", "outdated"}
VERSION_FLAGS = {"--version", "-v", "-V", "--help", "-h"}
QUIET_FLAGS = {"--silent", "-s", "--no-color", "--no-progress"}
AUDIT_FLAGS = ("--json", "--production", "--omit=", "--audit-level=", "--dir=", "--prefix=")   # all `audit` may be given
AUDIT_FOLDER_FLAGS = {"--dir", "--prefix", "-c"}                          # and these, each with the folder after it
NO_INSTALL_FLAGS = {"--no-install", "--no"}
CHANGING_WORDS = {"install", "i", "add", "ci", "clean-install", "link", "ln", "unlink", "uninstall", "un", "remove", "rm", "r",
                  "update", "up", "upgrade", "rebuild", "prune", "dedupe", "ddp", "it", "cit", "install-test", "install-ci-test",
                  "exec", "dlx", "x", "init", "create", "publish", "global"}
DATA_COMMANDS = {"ls", "cat", "head", "tail", "wc", "stat", "file", "grep", "rg", "du", "tree", "dir", "which", "where",
                 "realpath", "readlink", "cd", "pushd"}      # a path they are given is data, not a program
INTERPRETERS = {"sh", "bash", "zsh", "dash", "ksh", "fish", "cmd", "powershell", "pwsh", "xargs", "eval", "source", ".", "node",
                "nodejs", "bun", "deno", "python", "python3", "py", "perl", "ruby", "php"}   # they can run what they are given
_CONTINUATION = re.compile(r"\\\r?\n")
_SIMPLE_COMMANDS = re.compile(r"[;&|\n`()]+")
INSTALL_MESSAGE = ("greenlight: an agent may not install packages or change the project's environment (.venv, venv, node_modules): "
                   "that is the person's decision and it would change what the tests run on. Report the missing "
                   "requirement instead.")
NODE_MESSAGE = ("greenlight: an agent may not install packages or run package-manager commands other than scripts and "
                "read-only ones (run, test, ls, list, why, view, info, outdated, audit, --version), and may not use npx, pnpx, "
                "bunx or corepack except `npx --no-install <tool>` for a tool that is installed already. Put the subcommand "
                "first and the flags after it (`npm run typecheck --prefix tests`). Installing is the person's decision; "
                "report the missing requirement instead.")


_PIN_COMMAND = re.compile(r"\bvocabulary\s+pin\b|--shared-vocabulary\b", re.IGNORECASE)
PIN_MESSAGE = ("greenlight: pinning a shared vocabulary says that a person has read the included files, so it is the person's "
               "act and no tool call may do it. Ask the person to read the files and run `bdd vocabulary pin` themselves "
               "(in Claude Code, type `! ` followed by the command).")
_HELPERS_INSTALL = re.compile(r"\bbdd\b[^;&|\n]*\bhelpers\b[^;&|\n]*\binstall\b", re.IGNORECASE)
HELPERS_MESSAGE = ("greenlight: installing the helper plugins changes the person's Claude Code settings (which the tripwire "
                   "watches), so it is the person's act and no tool call may do it. Show them `bdd helpers`, which prints the "
                   "line to type: in Claude Code they type `! ` followed by the command.")
_DENY_RULES = re.compile(r"\bdoctor\b[^;&|\n]*--add-deny-rules\b", re.IGNORECASE)
DENY_RULES_MESSAGE = ("greenlight: adding the deny rules changes the person's Claude Code settings, so it is the person's act "
                      "and no tool call may do it. Show them `bdd doctor`, which prints the line to type: in Claude Code "
                      "they type `! ` followed by the command.")
_COST_AMEND = re.compile(r"\bcost\b[^;&|\n]*--amend\b", re.IGNORECASE)
COST_AMEND_MESSAGE = ("greenlight: cost corrections are made by the person or the orchestrator, from what Claude Code "
                      "counted, not by the agent whose cost it is. Say what is wrong in your report instead.")
_PLUMBING = re.compile(r"\b(?:un)?lock\b[^;&|\n]*--plumbing\b", re.IGNORECASE)
PLUMBING_MESSAGE = ("greenlight: the shared test plumbing is every feature's, so the person or the orchestrator releases it "
                    "(`bdd unlock --plumbing`) and locks it again (`bdd lock --plumbing`), not an agent. Say in your report "
                    "which file has to change and why.")
_PR_WRITE = re.compile(r"\bbdd\b[^;&|\n]*\bpr\b[^;&|\n]*--write\b", re.IGNORECASE)
PR_FILE = "PULL_REQUEST.md"


def _last_segment(word: str) -> str:
    return word.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1].casefold()


def node_program(word: str, run_by_interpreter: bool = False) -> str | None:
    """What kind of package tool a command word starts, if any, whatever folder it is in: ``npm``, ``./tools/yarn``,
    ``npm.cmd``, a script (``npm-cli.js``, ``pnpm.cjs``, ``yarn-1.22.19.cjs``) or the same without its suffix. Run through
    node or bun, anything under ``node_modules/<tool>/`` is that tool. A name with another dot (``yarn-error.log``) is not."""
    name = _last_segment(word)
    stem, _, suffix = name.rpartition(".")
    if suffix in SCRIPT_SUFFIXES:
        name = stem
    elif "." in name:
        return None
    program = NODE_PROGRAMS.get(name.split("-", 1)[0])
    if program or not run_by_interpreter:
        return program
    parts = word.replace("\\", "/").casefold().split("/")
    return next((NODE_PROGRAMS[after] for before, after in zip(parts, parts[1:]) if before == "node_modules" and after in NODE_PROGRAMS), None)


def node_arguments_are_safe(args: list[str]) -> bool:
    """Is the subcommand the first argument (after value-less flags), a script or read-only one, with nothing later that
    changes packages? ``audit`` is read-only only with the flags that report."""
    first = 0
    while first < len(args) and args[first] in QUIET_FLAGS:
        first += 1
    words = [word.casefold() for word in args[first:]]
    if not words or CHANGING_WORDS & set(words):
        return False
    if words[0] in VERSION_FLAGS:
        return True
    if words[0] == "audit":
        rest = words[1:]
        while rest:
            if rest[0] in AUDIT_FOLDER_FLAGS and len(rest) > 1 and not rest[1].startswith("-"):
                rest = rest[2:]                              # `--dir <folder>`: which project to report on
            elif rest[0].startswith(AUDIT_FLAGS):
                rest = rest[1:]
            else:
                return False
        return True
    return words[0] in SAFE_SUBCOMMANDS


def runs_installed(word: str, args: list[str]) -> bool:
    """``npx --no-install <tool>`` (or ``--no``) runs a tool that is already installed and never fetches one; the tool
    it runs is then judged as a command of its own. Any other flag before the tool (``--yes``, ``-p``) may fetch."""
    if _last_segment(word).split(".", 1)[0] != "npx" or not args or args[0] not in NO_INSTALL_FLAGS:
        return False
    flags = [arg for arg in args[:next((at for at, arg in enumerate(args) if not arg.startswith("-")), len(args))]]
    return all(flag in NO_INSTALL_FLAGS for flag in flags)


def _command_refuses(simple: str, interpreting: bool) -> bool:
    words = simple.split()
    if not words:
        return False
    # A path given to a plain read command is data. Not when the command redirects, or when something in the same command
    # can run what it is given (a shell, xargs, node ...): then every path counts.
    data = not interpreting and _last_segment(words[0]) in DATA_COMMANDS and not re.search("[<>]", simple)
    for at, word in enumerate(words):
        if data and at > 0 and ("/" in word or "\\" in word):
            continue
        run_by_interpreter = any(_last_segment(earlier) in INTERPRETERS for earlier in words[:at])   # flags may sit in between
        program = node_program(word, run_by_interpreter)
        if program == "fetch" and runs_installed(word, words[at + 1:]):
            continue
        if program == "fetch" or (program and not node_arguments_are_safe(words[at + 1:])):
            return True
    return False


def refuses_node_packages(command: str) -> bool:
    """Does any reading of the command run a package tool in a way an agent may not? A long here-document a shell does
    not run is read once as it is, quotes dropped, and not in every spelling (that would take seconds)."""
    whole = _CONTINUATION.sub("", command)
    for reading in [whole.replace('"', "").replace("'", ""), *shell_readings(shellwrites.without_data(whole))]:
        commands = _SIMPLE_COMMANDS.split(reading)
        interpreting = any(_last_segment(word) in INTERPRETERS for simple in commands for word in simple.split())
        if any(_command_refuses(simple, interpreting) for simple in commands):
            return True
    return False


def agent_name(payload: dict) -> str | None:
    """greenlight's name for the agent making the call: its own agents by their name, any other subagent as
    ``FOREIGN_AGENT``, and None for the main session (the orchestrator)."""
    agent_type = payload.get("agent_type") or ""
    if not agent_type:
        return None
    name = agent_type[len(AGENT_PREFIX):] if agent_type.startswith(AGENT_PREFIX) else ""
    return name if name in AGENT_WRITES else FOREIGN_AGENT


REVIEW_FILE = re.compile(r"t-\d+\.\d+-(?P<reviewer>[a-z-]+)\.md")


def _parts(project: Project, path: Path) -> tuple[str, ...]:
    """The path's segments below the project, folded the way the file system folds them (``.BDD/Features`` is
    ``.bdd/features`` on Windows and macOS)."""
    parts = Path(project.relative(path)).parts
    return tuple(p.casefold() for p in parts) if CASE_INSENSITIVE_FS else parts


def review_owner(project: Project, path: Path) -> str | None:
    """For a file in a feature's ``reviews/`` folder, the reviewer that alone may write it (an empty string when the name
    is not a review report, which nobody may write); None for any other file."""
    parts = _parts(project, path)
    if len(parts) < 5 or parts[0] != cfg.BDD_DIR or parts[1] != "features" or parts[3] != roles.REVIEWS_DIR:
        return None
    match = REVIEW_FILE.fullmatch(parts[-1].casefold()) if len(parts) == 5 else None
    return match.group("reviewer") if match and match.group("reviewer") in roles.REVIEWERS else ""


def in_reviews(project: Project, cwd: Path | None) -> bool:
    """Is the working directory of the call a feature's reviews/ folder (or below it)?"""
    if cwd is None:
        return False
    key, base = path_key(cwd), path_key(project.root / cfg.BDD_DIR / "features")
    return key.startswith(base + "/") and f"/{roles.REVIEWS_DIR}" in key[len(base):]


def is_tasks_file(project: Project, path: Path) -> bool:
    parts = _parts(project, path)
    return len(parts) == 4 and parts[0] == cfg.BDD_DIR and parts[1] == "features" and parts[3] == "tasks.md"


def feature_phase(project: Project, path: Path) -> str | None:
    """The phase of the feature a file under ``.bdd/features/<feature>/`` belongs to (None when it cannot be read)."""
    folder = Path(project.relative(path)).parts[2:3]
    try:
        return store.read_json(project.root / cfg.BDD_DIR / "features" / folder[0] / "state.json", "state").get("phase") if folder else None
    except Exception:                                            # the guard never fails a call over a record it cannot read
        return None


def record_review(project: Project, payload: dict, target: Path, agent: str | None) -> str | None:
    """When a reviewer writes its own report, remember what it wrote (``reviewlog``); the gate later accepts the report
    only with exactly that content. A report can only be written whole, with the Write tool, so the content is known."""
    owner = review_owner(project, target)
    if not owner or agent != owner:
        return None
    tool_input = payload.get("tool_input") or {}
    if payload.get("tool_name") != "Write" or not isinstance(tool_input.get("content"), str):
        return f"greenlight: write the whole review report with the Write tool ({project.relative(target)})."
    reviewlog.record(project.root, target, owner, tool_input["content"], payload.get("agent_id"), feature_phase(project, target))
    return None


def check_file_write(project: Project, path: Path, agent: str | None, change: dict | None = None) -> str | None:
    """Why ``agent`` may not write ``path``, or None. ``change`` is the file tool's call, when it is one: a settings
    change is judged by its effect only then."""
    lock = project.locked.get(path_key(path))
    if lock:
        return locked_message(project, path, lock)
    if project.is_data(path) or path_key(path) in project.shared:
        return managed_message(project, path)
    owner = review_owner(project, path)
    if owner is not None and agent != owner:
        return (f"greenlight: {project.relative(path)} is a review report; only "
                + (f"the {owner} agent writes it, as its own review" if owner else "a reviewer writes one, named <task>-<reviewer>.md")
                + ". A writer, the orchestrator or another agent may not write or change it.")
    if agent is not None and is_tasks_file(project, path):
        return (f"greenlight: {project.relative(path)} is written by the orchestrator; an agent may not change the tasks, "
                "because the reviews are routed from them.")
    protected = check_enforcement_files(path, change)
    if not protected and any(_CODEX_STATE.search(spelling.replace("\\", "/"))       # as written, and with links followed
                             for spelling in (path.as_posix(), os.path.realpath(path))):
        protected = CODEX_STATE_MESSAGE
    if protected:
        return protected
    allowed = (FOREIGN_WRITES if agent == FOREIGN_AGENT else AGENT_WRITES.get(agent)) if agent else None
    category = project.category(path)
    if allowed is not None and category not in allowed and category != SCRATCH:
        what = ", ".join(sorted(allowed)) or "nothing (it is read-only)"
        who = ("an agent that is not one of greenlight's" if agent == FOREIGN_AGENT else f"the {agent} agent")
        return (f"greenlight: {who} may not write {category} files ({project.relative(path)}); "
                f"it may write: {what}.")
    return None


_TOKEN_BREAKS = re.compile(r"[\s;&|()`<>=\"']+")          # a path starts after whitespace, a redirection, an assignment, a quote
_WILDCARDS_ONLY = re.compile(r"[*?\[\]]*")


def shell_pattern(segment: str) -> str:
    """A shell glob as ``fnmatch`` reads it: case-folded, and `[^x]` (a negated class to a shell) written `[!x]`."""
    return segment.casefold().replace("[^", "[!")


def glob_matches(name: str, segment: str) -> bool:
    """Would the shell glob ``segment`` match the file name ``name`` (which starts with a dot)? A glob that starts with a
    dot matches it as it is; one that does not matches it only when the shell's dotglob option is on, so it is tried
    against the name without its dot, but only if it has a literal character (`b*`, `ru?s`): a bare `*` is everywhere.
    `[^x]` means `[!x]` to a shell."""
    pattern = shell_pattern(segment)
    if pattern.startswith("."):
        return fnmatch.fnmatchcase(name, pattern)
    return not _WILDCARDS_ONLY.fullmatch(pattern) and fnmatch.fnmatchcase(name.lstrip("."), pattern)


def segment_glob_reaches(text: str, name: str) -> bool:
    """Could a glob in the command expand to the folder or file ``name`` (a name that starts with a dot)?

    Decided by matching the glob against the real name: `.b*`, `.?dd`, `.[^a]dd` and `.*` reach `.bdd`; `.gitignore*` and
    `src/*` do not."""
    for token in _TOKEN_BREAKS.split(text):
        if any(_GLOB.search(segment) and glob_matches(name, segment) for segment in token.split("/")):
            return True
    return False


CODEX_FOLDER_NAME = ".codex"
_ROLLOUT_PREFIX = "rollout-"
_ROLLOUT_SAMPLE = "rollout-2026-01-01t00-00-00-00000000-0000-0000-0000-000000000000.jsonl"   # the shape of a session file


def glob_reaches_rollout(text: str) -> bool:
    """Could a glob in the command expand to one of Codex's session files (`rollout-<time>-<id>.jsonl`)? Only a glob that
    spells the start of that name counts (`r*.jsonl`, `rollout-?*`, `ro[l]lout*`): `*.jsonl` alone is anybody's file."""
    for token in _TOKEN_BREAKS.split(text):
        for segment in token.split("/"):
            match = _GLOB.search(segment)
            if not match:
                continue
            literal = segment[:match.start()].casefold()
            spells_it = bool(literal) and (_ROLLOUT_PREFIX.startswith(literal) or literal.startswith(_ROLLOUT_PREFIX))
            if spells_it and fnmatch.fnmatchcase(_ROLLOUT_SAMPLE, shell_pattern(segment)):
                return True
    return False


def names_codex_state(text: str) -> bool:
    """Does the text name a `.codex` folder, Codex's home variable or a session file, spelled out or reached by a glob?"""
    text = text.replace("\\", "/")
    return bool(_CODEX_STATE.search(text)) or segment_glob_reaches(text, CODEX_FOLDER_NAME) or glob_reaches_rollout(text)


def names_segment(text: str, name: str, globs: str | None = None) -> bool:
    """Does ``name`` appear in the command as a whole path segment, spelled out in ``text`` or reached by a glob in
    ``globs`` (the same text unless only some of it is expanded by the shell)?"""
    return (re.search(rf"(?<![\w.-]){re.escape(name)}(?![\w.-])", text) is not None
            or segment_glob_reaches(text if globs is None else globs, name))


STANDARDS_NAME = "standards.md"


def clearly_elsewhere(before: str) -> bool:
    """Is the file name that follows ``before`` written with a folder in front of it that is not .bdd and cannot lead to it
    (`docs/standards.md`, `src/*/standards.md`)? A bare name, `./name` or `../name` could be anywhere, `.bdd` included."""
    folder = re.search(r"[^\s;&|()`<>=\"']*/$", before)
    if folder is None:
        return False
    segments = [part for part in folder.group(0).split("/") if part not in ("", ".", "..")]
    return bool(segments) and not names_segment(folder.group(0), cfg.BDD_DIR)


def cwd_inside(project: Project, cwd: Path | None, folder: str = "") -> bool:
    """Is the working directory of the call at or below ``.bdd`` (or ``.bdd/<folder>``)? A command that starts there
    can name a file in it by its bare name."""
    if cwd is None:
        return False
    base = path_key(project.root / cfg.BDD_DIR / folder) if folder else path_key(project.root / cfg.BDD_DIR)
    key = path_key(cwd)
    return key == base or key.startswith(base + "/")


@dataclass(frozen=True)
class Spelled:
    """What a shell command writes to, in every way a shell could read it: ``texts`` for names, ``patterns`` for globs
    (where only the shell's own globs are left), and the targets they came from (None: the whole command counts)."""
    texts: list[str]
    patterns: list[str]
    found: shellwrites.Writes | None


def spellings(target: shellwrites.Target) -> list[str]:
    """The ways a written target can be read: as the shell reads it and with backslashes as folder separators, and for a
    shell word its brace expansions (a script's braces are code)."""
    if target.code:
        return list(dict.fromkeys((target.text, target.raw)))
    return list(dict.fromkeys(expand_braces(target.text) + expand_braces(target.raw)))


def spelled(command: str, found: shellwrites.Writes) -> Spelled:
    if found.whole:
        readings = shell_readings(_NOISE.sub(" ", command))
        return Spelled(readings, readings, None)
    texts, patterns = [], []
    for folder in found.context:
        texts += expand_braces(folder)
        patterns += expand_braces(folder)
    for target in found.targets:
        texts += [*spellings(target), target.source]           # as written too: `$CODEX_HOME/x` names what it is
        patterns += [] if target.code else expand_braces(target.pattern)
    return Spelled([" ".join(texts)], [" ".join(patterns)], found)


_PATH_TOKENS = re.compile(r"[\s;&|(){}`<>=,\"']+")


def target_places(token: str, target: shellwrites.Target, bare: bool = False,
                  made: frozenset[Path] = frozenset()) -> list[Path] | None:
    """Where a written path lands: one place for each folder the command may be in at that point. None when that cannot
    be told: a pattern (a find name, a glob), a variable, a folder option, an unknown folder; a path whose folder does
    not exist and is not one the command makes (it could be the end of a longer path in a script, or go through a link
    the command makes first); and, unless ``bare``, a name with no folder of its own
    (``name``, ``./name``, ``../name``), which could be anywhere: the shell may be in another folder than the call says,
    and a script may join it to any; except after a `cd` to an absolute folder. ``bare`` is for a check that only refuses
    more when it places more."""
    word = token.replace("\\", "/")
    if target.names_only or _GLOB.search(word) or "$" in word or not word.strip("/."):
        return None
    segments = [part for part in word.split("/")[:-1] if part not in ("", ".", "..")]
    placeable = not target.code and (bare or target.certain)       # a name after `cd /abs/path &&` lands there
    if not segments and not word.startswith("/") and not re.match(r"[A-Za-z]:/", word) and not placeable:
        return None
    if word.startswith("~/"):
        word = Path.home().as_posix() + word[1:]
    path = Path(shellwrites.windows_path(word))
    if path.is_absolute() or path.anchor:
        places = [path]
    elif any(folder is None for folder in target.dirs):
        return None
    else:
        places = [folder / path for folder in target.dirs]
    if not bare and not all(place.parent.is_dir() or (not target.code and place.parent in made) for place in places):
        return None
    return places


def written_tokens(spelled_: Spelled):
    """Each path-like token of each written target, with its target."""
    for target in spelled_.found.targets if spelled_.found else ():
        for spelling in spellings(target):
            for token in _PATH_TOKENS.split(spelling):
                if token:
                    yield token, target


def locked_target(project: Project, spelled_: Spelled) -> tuple[Path, Locked] | None:
    """A locked file the command writes. A written path is compared by where it lands; a name that cannot be placed
    (a bare name in a script, a pattern, a variable) counts as the locked file of that name. When the targets are not
    known, any locked file's name anywhere in the command counts."""
    by_name: dict[str, Locked] = {}
    for lock in project.locked.values():
        by_name.setdefault(file_name(lock.path.name), lock)
    if not by_name:
        return None
    if spelled_.found is None:
        pattern = re.compile(r"(?<![\w.-])(?:" + "|".join(re.escape(n) for n in sorted(by_name, key=len, reverse=True)) + r")(?![\w-])")
        for text in spelled_.texts:
            match = pattern.search(text.casefold())
            if match:
                return by_name[match.group(0)].path, by_name[match.group(0)]
        return None
    for token, target in written_tokens(spelled_):
        named = by_name.get(file_name(token))
        if named is None:
            continue
        places = target_places(token, target, made=frozenset(spelled_.found.made))
        if places is None:
            return named.path, named
        for place in places:
            lock = project.locked.get(path_key(place))
            if lock:
                return lock.path, lock
    return None


def managed_target(project: Project, spelled_: Spelled) -> Path | None:
    """A managed data file the command writes (``state.json``, ``lock.json``, ``standards.md`` ...). Like a locked file:
    by where a written path lands, or by name when that cannot be told."""
    names = MANAGED_NAMES | {STANDARDS_NAME}
    if spelled_.found is None:
        pattern = re.compile(r"(?<![\w.-])(?:" + "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True)) + r")(?![\w-])")
        for reading in spelled_.texts:
            text = reading.casefold()
            for match in pattern.finditer(text):
                if not (match.group(0) == STANDARDS_NAME and clearly_elsewhere(text[:match.start()])):
                    return project.root / cfg.BDD_DIR / match.group(0)
        return None
    for token, target in written_tokens(spelled_):
        word = token.replace("\\", "/").rstrip("/").casefold()
        name = file_name(token)
        if name not in names:
            continue
        places = target_places(token, target, made=frozenset(spelled_.found.made))
        if places is None:
            if not (name == STANDARDS_NAME and clearly_elsewhere(word.rsplit("/", 1)[0] + "/" if "/" in word else "")):
                return project.root / cfg.BDD_DIR / name
        elif any(cfg.BDD_DIR in path_key(place).casefold().split("/") for place in places):
            return project.root / cfg.BDD_DIR / name                  # this project's or another's (a workspace member)
    return None


def mentioned_protected(project: Project, spelled_: Spelled, cwd: Path | None = None) -> tuple[Path, Locked | None] | None:
    """A locked or managed file that the command writes, if there is one.

    A locked file is found by where the written path lands (``locked_target``). A managed file is found by its name
    anywhere in what is written, whatever the quoting or slash style (``'state.json'`` inside a Python one-liner, a
    backslash path), with the folders the command moves into, so a command that ``cd``s first or builds the path in a
    script is still recognised. A false alarm only produces a clear refusal; a miss would defeat the point."""
    locked = locked_target(project, spelled_)
    if locked:
        return locked
    managed = managed_target(project, spelled_)
    if managed:
        return managed, None
    for reading, globs in zip(spelled_.texts, spelled_.patterns):
        text, globs = reading.casefold(), globs.casefold()
        # `cd .bdd && echo x > config.toml`, a call that already runs inside .bdd, and `.b*/config.toml` all name a person
        # file by its bare name or through a glob
        in_bdd = names_segment(text, cfg.BDD_DIR, globs) or cwd_inside(project, cwd)
        for person_file in PERSON_FILES:
            if f".bdd/{person_file}" in text or (in_bdd and re.search(rf"(?<![\w.-]){re.escape(person_file)}(?![\w-])", text)):
                return project.root / cfg.BDD_DIR / person_file, None
        for managed in MANAGED_DIRS:
            if names_segment(text, managed, globs) or cwd_inside(project, cwd, managed):
                return project.root / cfg.BDD_DIR / managed, None
        for shared in project.shared.values():                      # an included vocabulary, by its bare name or a glob
            if names_segment(text, shared.name.casefold(), globs):
                return shared, None
    return None


def touches_enforcement(spelled_: Spelled) -> str | None:
    """Does what the command writes include Claude Code's settings, hooks or transcripts, or the plugin itself? By name
    and glob in what is written, and by where each written path lands. The reason, or None."""
    plugin_root = os.environ.get(PLUGIN_ROOT_ENV)
    named_places = [path_key(root) for root in claudepaths.transcript_roots()]
    if plugin_root:
        named_places.append(path_key(plugin_root))
    shell_message = enforcement_message(Path("the targeted file"), "is part of what enforces greenlight "
                                        "(Claude Code hook settings or the plugin itself)")
    for text in spelled_.texts:
        if _SETTINGS_TEXT.search(text) or _CLAUDE_DIR_ARG.search(text):
            return shell_message
        if any(place in text.casefold().replace("\\", "/") for place in named_places):
            return shell_message
    if any(glob_reaches_claude(pattern) for pattern in spelled_.patterns):
        return shell_message
    plugin_key = path_key(plugin_root) if plugin_root else None
    transcripts = named_places[:-1] if plugin_root else named_places
    moved, seen = bool(spelled_.found and spelled_.found.context), set()
    for token, target in written_tokens(spelled_):
        if target.code or token.startswith("-") or (token, target.dirs) in seen or not (moved or "/" in token.replace("\\", "/")):
            continue                                       # a bare name lands in a protected folder only after a `cd`
        seen.add((token, target.dirs))
        for place in target_places(token, target, bare=True) or []:
            if enforcement_place(path_key(place), plugin_key, transcripts):
                return shell_message
    return None


def enforcement_place(key: str, plugin_key: str | None, transcripts: list[str]) -> bool:
    """``check_enforcement_files`` for a resolved ``path_key``, with the protected folders worked out once per call."""
    if plugin_key and key.startswith(plugin_key + "/"):
        return True
    if "/.claude/hooks/" in key or any(key.startswith(root + "/") and not is_memory(key, root) for root in transcripts):
        return True
    return key.rsplit("/", 1)[-1].casefold() in SETTINGS_NAMES and claudepaths.is_settings_file(Path(key))


def command_touches_enforcement(command: str, cwd: Path | None = None) -> bool:
    """Does a shell command write to Claude Code's hook settings, its transcripts or the plugin itself?"""
    found = shellwrites.writes(command, cwd)
    return found is not None and touches_enforcement(spelled(command, found)) is not None


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
            if segment.startswith(".") and _GLOB.search(segment) and fnmatch.fnmatchcase(".claude", shell_pattern(segment)):
                return True
            following = segments[position + 1] if position + 1 < len(segments) else ""
            if segment.casefold() == ".claude" and _GLOB.search(following) and any(
                    fnmatch.fnmatchcase(name, shell_pattern(following)) for name in (*SETTINGS_NAMES, *CLAUDE_PROTECTED_DIRS)):
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


def check_agent_command(project: Project, scrubbed: str, agent: str) -> str | None:
    """What only an agent is refused: writing the pull-request description outside its write matrix, correcting a cost,
    releasing the shared test plumbing, installing packages. An install the whole command shows is refused unless the
    command without its data shows none (``shellwrites.program_view``): a package tool named in a quoted pattern or a
    here-document runs nothing. A command that runs a shell, an interpreter or a runner keeps all of it."""
    if _PR_WRITE.search(scrubbed):                                 # `bdd pr --write` writes a file in the project root
        written = check_file_write(project, project.root / PR_FILE, agent)
        if written:
            return written
    if _COST_AMEND.search(scrubbed):
        return COST_AMEND_MESSAGE
    if _PLUMBING.search(scrubbed):
        return PLUMBING_MESSAGE
    programs = shellwrites.program_view(scrubbed)
    if _INSTALL.search(scrubbed) and _INSTALL.search(programs):
        return INSTALL_MESSAGE
    return NODE_MESSAGE if refuses_node_packages(scrubbed) and refuses_node_packages(programs) else None


def check_bash(project: Project, command: str, agent: str | None = None, cwd: Path | None = None) -> str | None:
    """Best effort: block a command that runs an approval or a nested Claude session, or that writes to a protected
    file (``shellwrites`` reads where it writes)."""
    injection = check_injection({"command": command})
    if injection:
        return injection
    readings = [command, *shell_readings(shellwrites.without_data(command))]
    if any(_CODEX_HOOK_ENTRY.search(reading) for reading in readings):
        return CODEX_HOOK_MESSAGE
    strict = project.config.accept_codex
    if (codexsession.starts_codex_session(command, strict=strict)
            or any(codexsession.starts_codex_session(reading, True, strict) for reading in readings[1:])):
        return codexsession.NESTED_MESSAGE
    if starts_claude_session(command):
        return NESTED_SESSION_MESSAGE
    scrubbed = _NOISE.sub(" ", command)
    if _PIN_COMMAND.search(scrubbed):
        return PIN_MESSAGE
    if _HELPERS_INSTALL.search(scrubbed):
        return HELPERS_MESSAGE
    if _DENY_RULES.search(scrubbed):
        return DENY_RULES_MESSAGE
    refused = check_agent_command(project, scrubbed, agent) if agent else None
    if refused:
        return refused
    found = shellwrites.writes(command, cwd)
    if found is None:
        return None
    return check_writes(project, spelled(command, found), agent, cwd)


def check_writes(project: Project, written: Spelled, agent: str | None, cwd: Path | None) -> str | None:
    """The protections a shell command's writes are held to, checked against what it writes to."""
    if (any(_CODEX_STATE.search(text.replace("\\", "/")) for text in written.texts)
            or any(segment_glob_reaches(p.replace("\\", "/"), CODEX_FOLDER_NAME) or glob_reaches_rollout(p.replace("\\", "/"))
                   for p in written.patterns)):
        return CODEX_STATE_MESSAGE
    if agent and any(_ENVIRONMENT_PATH.search(text) for text in written.texts):
        return INSTALL_MESSAGE
    enforced = touches_enforcement(written)
    if enforced:
        return enforced
    for reading, globs in zip(written.texts, written.patterns):
        text, globs = reading.casefold(), globs.casefold()
        names_report = re.search(r"(?<![\w.-])t-\d+\.\d+-(?:" + "|".join(roles.REVIEWERS) + r")\.md(?![\w-])", text)
        if (names_report or (names_segment(text, cfg.BDD_DIR, globs) and names_segment(text, roles.REVIEWS_DIR, globs))
                or in_reviews(project, cwd)):
            return ("greenlight: review reports are written only by each reviewer with its file tool, never from the "
                    "shell. (This shell command looks like it writes into a reviews/ folder.)")
        if agent and re.search(r"(?<![\w.-])tasks\.md(?![\w-])", text):
            return ("greenlight: tasks.md is written by the orchestrator; an agent may not change the tasks. "
                    "(This shell command looks like it writes to it.)")
    hit = mentioned_protected(project, written, cwd)
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
        target = raw if raw.is_absolute() else cwd / raw
        owner, agent = project.owner_of(target), agent_name(payload)
        return check_file_write(owner, target, agent, payload) or record_review(owner, payload, target, agent)
    if tool == "Bash" and tool_input.get("command"):
        return check_bash(project, tool_input["command"], agent_name(payload), cwd)
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
