"""Command-line dispatch."""
from __future__ import annotations

import sys

from . import __version__


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
    if argv and argv[0] == "doctor":
        from . import doctor
        return doctor.main(argv[1:])
    if argv and argv[0] == "lint":
        from . import lint
        return lint.run(argv[1:])
    print("usage: bdd <command> [options]   (commands: doctor, lint, --version)", file=sys.stderr)
    return 2
