"""Runs the scenarios of tests/bdd_test.dart with `flutter test` and writes one JUnit report, the contract of every adapter.

    python tests/run_flutter.py --tag FEAT-007 --out REPORT [--seed N] [--scenario NAME]

`flutter test` reports as a stream of JSON events; this turns them into the JUnit file `bdd run` reads: one test case per
scenario, named by the scenario. The tag, the seed and the scenario reach the test through the environment (so a name in any
script is never squeezed through a command line). Packages are never resolved here: `--no-pub` makes a changed pubspec.yaml
an error, and the lock file in tests/ decides what runs (install with `flutter pub get --enforce-lockfile` in tests/).

The report is written only when the tests ran. A file that does not compile, or a feature that does not parse, stops the
run before any test starts; then there is no report, the reason is printed, and the exit status is 1.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from xml.etree import ElementTree

HERE = Path(__file__).resolve().parent
CLASSNAME = "bdd"
TYPE_PREFIX = re.compile(r"^([A-Za-z_]\w*)(?=:)")
# What a widget test reports when its body throws: the real exception is only in the framework's printed report.
GENERIC = "Test failed. See exception logs above."
THROWN = re.compile(r"The following (\w+) was thrown[^\n]*:\n(.*?)\n\nWhen the exception was thrown", re.DOTALL)


def parse_arguments(argv: list[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Run the feature's scenarios with flutter test and write a JUnit report.")
    ap.add_argument("--tag", required=True, help="the feature tag, e.g. FEAT-007")
    ap.add_argument("--out", required=True, type=Path, help="where the JUnit file goes")
    ap.add_argument("--seed", type=int, help="run the scenarios in a random order for this seed")
    ap.add_argument("--scenario", help="run only the scenario with this exact name")
    return ap.parse_args(argv)


def environment(args: argparse.Namespace) -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if not key.startswith("BDD_")}
    env["BDD_TAG"] = args.tag
    if args.seed is not None:
        env["BDD_SEED"] = str(args.seed)
    if args.scenario:
        env["BDD_SCENARIO"] = args.scenario
    return env


class Case:
    """What one test did, put together from the events that mention its id."""

    def __init__(self, name: str, started_ms: int) -> None:
        self.name = name
        self.started_ms = started_ms
        self.finished_ms = started_ms
        self.result = "success"
        self.skipped = False
        self.errors: list[tuple[str, str, bool]] = []     # (error, stack trace, is a test failure)
        self.output: list[str] = []


def collect(lines: list[str]) -> tuple[dict[int, Case], dict[int, Case], list[str]]:
    """The scenarios, the hidden loading steps, and the lines that are not events (compiler messages and the like)."""
    scenarios: dict[int, Case] = {}
    loading: dict[int, Case] = {}
    other: list[str] = []
    for line in lines:
        try:
            event = json.loads(line)
        except ValueError:
            other.append(line)
            continue
        if not isinstance(event, dict):
            continue
        kind, at = event.get("type"), event.get("time", 0)
        if kind == "testStart":
            test = event["test"]
            case = Case(test["name"], at)
            (loading if test["name"].startswith("loading ") else scenarios)[test["id"]] = case
            continue
        case = (scenarios.get(event.get("testID")) or loading.get(event.get("testID")))
        if case is None:
            continue
        if kind == "testDone":
            case.result, case.skipped, case.finished_ms = event["result"], bool(event.get("skipped")), at
        elif kind == "error":
            case.errors.append((event.get("error", ""), event.get("stackTrace", ""), bool(event.get("isFailure"))))
        elif kind == "print":
            case.output.append(event.get("message", ""))
    return scenarios, loading, other


def thrown_by_the_test(case: Case) -> tuple[str, str] | None:
    """The class and the message of the exception a widget test threw, read from the report the Flutter framework printed."""
    found = THROWN.search("\n".join(case.output))
    return (found.group(1), found.group(2).strip()) if found else None


def failure_type(error: str, is_failure: bool) -> str:
    if is_failure:
        return "TestFailure"
    found = TYPE_PREFIX.match(error.strip())
    return found.group(1) if found else "Error"


def to_junit(scenarios: dict[int, Case]) -> ElementTree.Element:
    suite = ElementTree.Element("testsuite", name="flutter test", tests=str(len(scenarios)))
    failures = 0
    for case in scenarios.values():
        element = ElementTree.SubElement(suite, "testcase", classname=CLASSNAME, name=case.name,
                                         time=f"{max(case.finished_ms - case.started_ms, 0) / 1000:.3f}")
        if case.skipped:
            ElementTree.SubElement(element, "skipped")
        elif case.result != "success" or case.errors:
            failures += 1
            error, stack, is_failure = case.errors[0] if case.errors else ("the test did not finish", "", False)
            kind, thrown = failure_type(error, is_failure), thrown_by_the_test(case) if error.startswith(GENERIC) else None
            if thrown:
                kind, error = thrown                      # the exception itself, not the framework's "see exception logs above"
            failure = ElementTree.SubElement(element, "failure", type=kind,
                                             message=error.strip().splitlines()[0][:300] if error.strip() else "")
            failure.text = "\n".join(part for part in (error.strip(), stack.strip()) if part)
        if case.output:
            ElementTree.SubElement(element, "system-out").text = "\n".join(case.output)
    suite.set("failures", str(failures))
    return suite


def loading_problems(loading: dict[int, Case], other: list[str]) -> list[str]:
    """Why the tests could not be started: a loading step that failed, or output the test runner printed on its own."""
    problems = [error.strip() for case in loading.values() if case.result != "success" for error, _, _ in case.errors]
    return problems or ([line for line in other if line.strip()][-20:] if not loading else [])


def write_report(suite: ElementTree.Element, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".part")
    ElementTree.ElementTree(suite).write(partial, encoding="utf-8", xml_declaration=True)
    os.replace(partial, target)


def main(argv: list[str]) -> int:
    args = parse_arguments(argv)
    flutter = shutil.which("flutter")
    if flutter is None:
        print("run_flutter.py: `flutter` is not on PATH; install the Flutter SDK (https://docs.flutter.dev/install)", file=sys.stderr)
        return 1
    command = [flutter, "test", "--no-pub", "--reporter", "json", "bdd_test.dart"]
    done = subprocess.run(command, cwd=HERE, env=environment(args), capture_output=True, text=True, encoding="utf-8", errors="replace")
    scenarios, loading, other = collect(done.stdout.splitlines())
    problems = loading_problems(loading, other + done.stderr.splitlines())
    if problems:
        print("flutter test could not run the scenarios:\n" + "\n".join(problems), file=sys.stderr)
        return 1
    write_report(to_junit(scenarios), args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
