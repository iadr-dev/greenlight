"""Command-line dispatch."""
from __future__ import annotations

import importlib
import sys

from . import __version__

# command -> (module, function). Modules are imported on demand to keep start-up fast: hooks
# run this on every tool call.
COMMANDS = {
    "doctor": ("doctor", "main"),
    "lint": ("lint", "run"),
    "lock": ("lockcmd", "run_lock"),
    "unlock": ("lockcmd", "run_unlock"),
    "state": ("statecmd", "run_state"),
    "gate": ("statecmd", "run_gate"),
    "assume": ("statecmd", "run_assume"),
    "cost": ("statecmd", "run_cost"),
    "mode": ("statecmd", "run_mode"),
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
        module, function = COMMANDS[argv[0]]
        return getattr(importlib.import_module(f"{__package__}.{module}"), function)(argv[1:])
    print(f"usage: bdd <command> [options]   (commands: {', '.join(sorted(COMMANDS))}, --version)", file=sys.stderr)
    return 2
