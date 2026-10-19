"""Command-line dispatch."""
from __future__ import annotations

import sys

from . import __version__


def main(argv: list[str]) -> int:
    if argv in (["--version"], ["version"]):
        print(f"bdd {__version__}")
        return 0
    if argv and argv[0] == "doctor":
        from . import doctor
        return doctor.main(argv[1:])
    print("usage: bdd <command> [options]   (commands: doctor, --version)", file=sys.stderr)
    return 2
