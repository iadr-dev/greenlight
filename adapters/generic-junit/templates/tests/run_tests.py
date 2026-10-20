"""The sample runner: runs the unittest cases in tests/steps/ that belong to one feature and writes a JUnit file.

    run_tests.py --tag FEAT-000 --out report.xml [--seed N] [--only "Scenario name"]

It exists so that a fresh project has something green to start from, and to show the whole contract in one small file.
Replace the ``by_tag`` command in .bdd/config.toml with your own runner's when you have one (see the runner cards).

* A test class belongs to a feature when its ``tags`` attribute contains the tag (``tags = ("FEAT-000",)``).
* The name of a test must contain the name of its scenario; greenlight ignores case and every character that is not a
  letter or a digit (``test_two_numbers_are_added`` is "Two numbers are added").
* A seam that does not exist yet fails with ``BDD_EXPECTED_MISSING`` in its message: that is an expected failure.
* A module that cannot be loaded is written to the report as an error, so it is not silent.
"""
import argparse
import importlib.util
import random
import re
import sys
import time
import unittest
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

STEPS = Path(__file__).resolve().parent / "steps"


def squash(text):
    return re.sub(r"[^a-z0-9]+", "", text.casefold())


def load_modules():
    """(modules, load errors as (module name, exception)); the steps folder is importable from the modules."""
    sys.path.insert(0, str(STEPS))
    modules, failures = [], []
    for path in sorted(STEPS.glob("*.py")):
        spec = importlib.util.spec_from_file_location(path.stem, path)
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except Exception as exc:  # any failure to load is reported, never raised: the report must exist
            failures.append((path.stem, exc))
        else:
            modules.append(module)
    return modules, failures


def tests_of(modules, tag):
    loader = unittest.TestLoader()
    found = []
    for module in modules:
        for name in dir(module):
            candidate = getattr(module, name)
            if isinstance(candidate, type) and issubclass(candidate, unittest.TestCase) and tag in getattr(candidate, "tags", ()):
                found += list(loader.loadTestsFromTestCase(candidate))
    return found


def choose(cases, only, seed):
    if only:
        cases = [case for case in cases if squash(only) in squash(case.id().rsplit(".", 1)[-1])]
    if seed is not None:
        random.Random(seed).shuffle(cases)
    return cases


class Recorder(unittest.TestResult):
    """Collects (classname, name, outcome, message, body) for every test."""

    def __init__(self):
        super().__init__()
        self.rows = []

    def row(self, test, outcome, message="", body=""):
        self.rows.append((type(test).__qualname__, test.id().rsplit(".", 1)[-1], outcome, message, body))

    def addSuccess(self, test):
        self.row(test, "passed")

    def addFailure(self, test, err):
        self.row(test, "failure", str(err[1]), self._exc_info_to_string(err, test))

    def addError(self, test, err):
        self.row(test, "error", f"{err[0].__name__}: {err[1]}", self._exc_info_to_string(err, test))

    def addSkip(self, test, reason):
        self.row(test, "skipped", reason)


def to_xml(rows):
    cases = []
    for classname, name, outcome, message, body in rows:
        inner = "" if outcome == "passed" else f"<{outcome} message={quoteattr(message)}>{escape(body)}</{outcome}>"
        cases.append(f"<testcase classname={quoteattr(classname)} name={quoteattr(name)}>{inner}</testcase>")
    return f'<?xml version="1.0" encoding="utf-8"?><testsuites><testsuite name="unittest" tests="{len(cases)}">{"".join(cases)}</testsuite></testsuites>'


def main(argv):
    ap = argparse.ArgumentParser(description="Run the unittest cases of one feature and write a JUnit file.")
    ap.add_argument("--tag", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int)
    ap.add_argument("--only")
    args = ap.parse_args(argv)
    modules, failures = load_modules()
    cases = choose(tests_of(modules, args.tag), args.only, args.seed)
    recorder = Recorder()
    started = time.perf_counter()
    unittest.TestSuite(cases).run(recorder)
    rows = recorder.rows + [("load", name, "error", f"{type(exc).__name__}: {exc}", "") for name, exc in failures]
    Path(args.out).write_text(to_xml(rows), encoding="utf-8", newline="\n")
    print(f"{len(cases)} test(s) in {time.perf_counter() - started:.2f} s")
    return 0 if recorder.wasSuccessful() and not failures else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
