#!/usr/bin/env python3
"""Run greenlight's own specs the way a user's project runs theirs.

It scaffolds the `python-pytest-bdd` adapter into a temporary folder, drops in the one project-specific file
(`specs/operations.py`, which maps the names used in the features to `tools/bdd/bdd`) and the features, and runs
pytest there. Nothing of the adapter is copied into the repository, so nothing can drift from it.

    python specs/run_specs.py

Needs `pytest` and `pytest-bdd` (requirements-dev.txt) and `sh`.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
ADAPTER = REPO / "adapters" / "python-pytest-bdd" / "templates" / "tests"


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="greenlight-specs-") as tmp:
        scaffold = Path(tmp) / "tests"
        shutil.copytree(ADAPTER, scaffold, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        (scaffold / "features" / "sample.feature").unlink()                  # the adapter's sample is not ours
        (scaffold / "sample_domain.py").unlink()
        shutil.copyfile(HERE / "operations.py", scaffold / "drivers" / "operations.py")
        shutil.copytree(HERE / "features", scaffold / "features", dirs_exist_ok=True)
        env = {**os.environ, "GREENLIGHT_REPO": str(REPO)}
        command = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-W", "ignore"]
        return subprocess.run(command, cwd=tmp, env=env).returncode


if __name__ == "__main__":
    sys.exit(main())
