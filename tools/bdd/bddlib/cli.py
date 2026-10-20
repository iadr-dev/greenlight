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
    "migrate": ("migrate", "run"),
    "run": ("runcmd", "run_run"),
    "classify": ("runcmd", "run_classify"),
    "adapter": ("adapter", "run"),
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


def main(argv: list[str]) -> int:
    configure_streams()
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
