"""Run the Reqnroll scenarios of one feature with `dotnet test` and write one JUnit report. Standard library only.

    python -I tests/run_dotnet.py --tag FEAT-007 --out report.xml [--seed N] [--scenario "name"]

`bdd run` starts it without a shell. It exists to build the test filter safely (a scenario name can contain the
characters the filter language treats as operators), to delete a stale report, to hand the shuffle seed to the test
host, and to keep the package restore locked to packages.lock.json. This file is bound: it is locked with the steps.
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent / "GreenlightTests.csproj"
TAG = re.compile(r"[A-Za-z0-9_.-]+")
FILTER_OPERATORS = "\\()&|=!~"


def escape(text: str) -> str:
    """The characters of the VSTest filter language, escaped so that a name is only ever a value."""
    return "".join("\\" + char if char in FILTER_OPERATORS else char for char in text)


def build_filter(tag: str, scenario: str | None) -> str:
    chosen = f"Category={escape(tag)}"
    return f"{chosen}&DisplayName={escape(scenario)}" if scenario else chosen


def build_command(dotnet: str, tag: str, out: Path, scenario: str | None) -> list[str]:
    return [dotnet, "test", str(PROJECT), "--nologo", "-p:RestoreLockedMode=true",
            "--filter", build_filter(tag, scenario), "--logger", f"junit;LogFilePath={out}"]


def parse(argv: list[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tag", required=True)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--seed", type=int)
    ap.add_argument("--scenario")
    args = ap.parse_args(argv)
    if not TAG.fullmatch(args.tag):
        ap.error(f"--tag {args.tag!r} is not a feature tag such as FEAT-007")
    return args


def main(argv: list[str]) -> int:
    args = parse(argv)
    dotnet = shutil.which("dotnet")
    if dotnet is None:
        print("dotnet is not on PATH: install the .NET SDK", file=sys.stderr)
        return 127
    args.out.unlink(missing_ok=True)                          # a report left over from an earlier run is not this run's
    env = dict(os.environ)
    env.pop("GREENLIGHT_BDD_SEED", None)
    if args.seed is not None:
        env["GREENLIGHT_BDD_SEED"] = str(args.seed)
    return subprocess.run(build_command(dotnet, args.tag, args.out.resolve(), args.scenario), env=env, check=False).returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
