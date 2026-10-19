"""Command-line dispatch."""
from __future__ import annotations

import sys

from . import __version__


def main(argv: list[str]) -> int:
    if argv in (["--version"], ["version"]):
        print(f"bdd {__version__}")
        return 0
    print("usage: bdd <command> [options]   (commands arrive in later milestones)", file=sys.stderr)
    return 2
