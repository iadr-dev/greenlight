"""Command-line dispatch."""
from __future__ import annotations

import importlib
import sys

from . import __version__, config

# command -> (module, function). Modules are imported on demand to keep start-up fast: hooks
# run this on every tool call.
COMMANDS = {
    "doctor": ("doctor", "main"),
    "guard": ("guard", "main"),
    "lint": ("lint", "run"),
    "lock": ("lockcmd", "run_lock"),
    "unlock": ("lockcmd", "run_unlock"),
    "state": ("statecmd", "run_state"),
    "gate": ("statecmd", "run_gate"),
    "approve": ("approvecmd", "run"),
    "assume": ("statecmd", "run_assume"),
    "cost": ("statecmd", "run_cost"),
    "mode": ("statecmd", "run_mode"),
    "tripwire": ("tripwire", "main"),
    "status": ("reportcmd", "run_status"),
    "trace": ("reportcmd", "run_trace"),
    "scan": ("reportcmd", "run_scan"),
    "design": ("design", "run"),
    "pr": ("pr", "run"),
    "vocabulary": ("vocabcmd", "run"),
    "codex-hook": ("codexhook", "main"),
    "install-hooks": ("installhooks", "run"),
    "install-skills": ("installskills", "run"),
    "adopt": ("adopt", "run"),
    "check": ("quality", "run"),
    "mutate": ("mutation", "run"),
    "stability": ("stability", "run"),
    "migrate": ("migrate", "run"),
    "run": ("runcmd", "run_run"),
    "classify": ("runcmd", "run_classify"),
    "adapter": ("adapter", "run"),
    "init": ("initcmd", "run"),
    "change": ("changecmd", "run"),
    "cards": ("cards", "run"),
    "workspace": ("workspace", "run"),
}


def configure_streams(*streams) -> None:
    """Make stdout/stderr UTF-8 with LF endings whatever the terminal or code page.

    Hook output and reports are read by tools, not people at a console: PowerShell, cmd
    and Git Bash on Windows must all produce identical bytes (and not crash on a check mark).
    """
    for stream in streams or (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            # newline="\n": no translation, so Windows pipes get LF rather than CRLF
            stream.reconfigure(encoding="utf-8", errors="replace", newline="\n")


ACROSS_WORKSPACE = ("lock", "run", "classify", "status")      # commands that `--workspace` repeats in every repository


def across_workspace(argv: list[str]) -> int:
    """``bdd COMMAND ... --workspace``: COMMAND in this repository and then in every member of the workspace."""
    from . import workspace
    command = argv[0]
    _, rest = workspace.without_flag(argv[1:])
    root = config.find_root()
    if root is None:
        print(f"bdd {command}: not inside a greenlight project", file=sys.stderr)
        return 2
    if command == "lock" and "--check" not in rest:
        print("bdd lock: --workspace goes with --check", file=sys.stderr)
        return 2
    try:
        include_home = command in ("lock", "status") or bool(config.load(root).runs)
        return workspace.fan_out(root, lambda args: main([command, *args]), rest, include_home)
    except config.ConfigError as exc:
        print(f"bdd {command}: {exc}", file=sys.stderr)
        return 2


def in_member(argv: list[str]) -> int:
    """``bdd --in NAME COMMAND ...``: run COMMAND as if started in the member repository NAME of the workspace."""
    from . import workspace
    from .errors import UsageError
    try:
        name, rest = workspace.take_in_flag(argv)
        return workspace.run_in(name, rest, main)
    except (UsageError, config.ConfigError) as exc:
        print(f"bdd --in: {exc}", file=sys.stderr)
        return 2


def main(argv: list[str]) -> int:
    configure_streams()
    if argv[:1] == ["--in"]:
        return in_member(argv)
    if argv[:1] and argv[0] in ACROSS_WORKSPACE and "--workspace" in argv[1:]:
        return across_workspace(argv)
    if argv in (["--version"], ["version"]):
        print(f"bdd {__version__}")
        return 0
    if argv and argv[0] in COMMANDS:
        problem = config.version_problem(argv[0], argv[1:])
        if problem:
            print(f"bdd {argv[0]}: {problem}", file=sys.stderr)
            return 2
        module, function = COMMANDS[argv[0]]
        return getattr(importlib.import_module(f"{__package__}.{module}"), function)(argv[1:])
    print(f"usage: bdd <command> [options]   (commands: {', '.join(sorted(COMMANDS))}, --version)", file=sys.stderr)
    return 2
