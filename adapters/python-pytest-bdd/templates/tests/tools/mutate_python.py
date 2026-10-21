"""Run mutmut on the production files `bdd mutate` hands over, and write the report `bdd mutate` reads.

    python -I tests/tools/mutate_python.py --report REPORT -- FILE [FILE ...]

Started by `bdd mutate` from the project root with the project's own Python. It copies the project to a scratch folder,
tells mutmut to mutate only FILE... there (so the project never gains a `mutants/` folder or a mutmut setting), runs
the project's tests against every mutant with the same settings `bdd run` uses (`tests/pytest.ini`), and writes

    {"killed": N, "survived": N, "timeout": N, "suspicious": N, "skipped": N}

to REPORT. The exit status is 0 whenever mutmut ran to the end, survivors or not: they are in the counts. It is not 0
when the arguments are refused (2) or when mutmut itself could not run or finish (3).

Mutants that no test reaches ("no tests") count as survived: nothing noticed them. Mutants that crash the interpreter
(segfault) count as suspicious, and neither kind of doubt is counted as a kill.

mutmut is a development tool of the project, not of greenlight: install it in the project's environment
(`uv pip install mutmut`). It needs Linux or macOS (on Windows use WSL); this file stops with a clear message otherwise.
Standard library only.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

EXIT_REFUSED = 2
EXIT_TOOL_FAILED = 3
WINDOWS_MESSAGE = """mutate_python: mutmut does not run natively on Windows. Run the check from WSL, in the same checkout:
  wsl
  cd /mnt/c/<path to the project>
  uv venv venv          # a Linux environment beside the Windows .venv; each side finds its own
  uv pip install --python venv/bin/python -r <the project's requirements> pytest pytest-bdd "mutmut==3.8.0"
  sh /mnt/c/<path to greenlight>/tools/bdd/bdd mutate FEAT-n
WSL needs Python 3.11 or newer for bdd; a `python =` line in .bdd/config.toml that names a Windows path does not work there."""
SKIPPED_FOLDERS = (".git", ".bdd", ".venv", "venv", "node_modules", "__pycache__", "mutants", ".mypy_cache",
                   ".pytest_cache", ".ruff_cache")
PYTEST_ARGUMENTS = ("-c", "tests/pytest.ini", "--rootdir", ".", "--confcutdir", "tests", "-p", "no:cacheprovider",
                    "-W", "ignore::pytest.PytestUnknownMarkWarning")
STATS_FILE = Path("mutants") / "mutmut-cicd-stats.json"


class Refused(ValueError):
    """The arguments are not acceptable; the message says why."""


def check_files(root: Path, names: list[str]) -> list[str]:
    """The files as project-relative POSIX paths, each an existing Python file inside the project."""
    if not names:
        raise Refused("no file to mutate was given")
    resolved_root = root.resolve()
    checked: list[str] = []
    for name in names:
        candidate = Path(name)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise Refused(f"{name}: give the file relative to the project, without ..")
        target = (resolved_root / candidate).resolve()
        if resolved_root not in target.parents:
            raise Refused(f"{name}: not inside the project")
        if target.suffix != ".py" or not target.is_file():
            raise Refused(f"{name}: not an existing Python file")
        checked.append(target.relative_to(resolved_root).as_posix())
    return sorted(set(checked))


def check_report(root: Path, name: str) -> Path:
    """The report path: absolute, in an existing folder, and not inside the project."""
    path = Path(name)
    if not path.is_absolute() or not path.parent.is_dir():
        raise Refused("the report must be an absolute path in an existing folder")
    if root.resolve() in path.resolve().parents:
        raise Refused("the report must not be inside the project")
    return path


def toml_string(value: str) -> str:
    return json.dumps(value)


def mutmut_settings(files: list[str]) -> str:
    """The `pyproject.toml` the scratch copy gets: mutate these files, run the tests the way `bdd run` does."""
    sources = sorted({Path(f).parts[0] if len(Path(f).parts) > 1 else f for f in files})

    def array(values) -> str:
        return "[" + ", ".join(toml_string(v) for v in values) + "]"

    return "\n".join(["[tool.mutmut]", f"source_paths = {array(sources)}", f"only_mutate = {array(files)}",
                      f"pytest_add_cli_args = {array(PYTEST_ARGUMENTS)}",
                      f"pytest_add_cli_args_test_selection = {array(['tests'])}", ""])


def counts_from_stats(stats: dict) -> dict[str, int]:
    """The report counts from mutmut's CI/CD statistics. A mutant no test reached survived; a segfault is doubtful."""
    def number(key: str) -> int:
        value = stats.get(key, 0)
        return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0

    return {"killed": number("killed"), "survived": number("survived") + number("no_tests"),
            "timeout": number("timeout"), "suspicious": number("suspicious") + number("segfault"),
            "skipped": number("skipped")}


def copy_project(root: Path, scratch: Path) -> None:
    shutil.copytree(root, scratch, symlinks=True, dirs_exist_ok=True, ignore=shutil.ignore_patterns(*SKIPPED_FOLDERS))


def run_mutmut(scratch: Path, arguments: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "mutmut", *arguments], cwd=scratch, capture_output=True, text=True,
                          check=False)


def measure(root: Path, files: list[str]) -> dict[str, int]:
    with tempfile.TemporaryDirectory(prefix="greenlight-mutmut-") as folder:
        scratch = Path(folder) / "project"
        copy_project(root, scratch)
        (scratch / "pyproject.toml").write_text(mutmut_settings(files), encoding="utf-8", newline="\n")
        for arguments in (["run"], ["export-cicd-stats"]):
            done = run_mutmut(scratch, arguments)
            if done.returncode != 0:
                raise RuntimeError(f"mutmut {arguments[0]} exited with status {done.returncode}:\n"
                                   + (done.stdout + done.stderr)[-3000:])
        stats_path = scratch / STATS_FILE
        if not stats_path.is_file():
            raise RuntimeError("mutmut wrote no statistics")
        return counts_from_stats(json.loads(stats_path.read_text(encoding="utf-8")))


def parse(argv: list[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="mutate_python.py", description="Run mutmut for `bdd mutate`.")
    ap.add_argument("--report", required=True, help="where to write the JSON counts (absolute, outside the project)")
    ap.add_argument("files", nargs="+", help="production files to mutate, relative to the project")
    return ap.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse(argv)
    root = Path.cwd()
    try:
        files = check_files(root, args.files)
        report = check_report(root, args.report)
    except Refused as exc:
        print(f"mutate_python: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    if os.name == "nt":
        print(WINDOWS_MESSAGE, file=sys.stderr)
        return EXIT_TOOL_FAILED
    try:
        counts = measure(root, files)
    except (RuntimeError, OSError, ValueError) as exc:
        print(f"mutate_python: {exc}", file=sys.stderr)
        return EXIT_TOOL_FAILED
    report.write_text(json.dumps(counts), encoding="utf-8", newline="\n")
    print(f"mutate_python: {counts['killed']} killed, {counts['survived']} survived "
          f"({', '.join(files)})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
