"""Entry point for the `bdd` CLI.

Runs under `python -I` (isolated mode), which does not put this file's directory on
sys.path, so it is added explicitly before importing the package.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bddlib.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
