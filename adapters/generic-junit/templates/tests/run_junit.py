"""Run a test command and leave exactly one JUnit file, for runners that write several or choose their own location.

    run_junit.py --command "./gradlew test --tests *FEAT_007*" --reports "build/test-results/test/*.xml" --out report.xml
                 [--add=WORD ...]

* Report files that match ``--reports`` (relative to the project) are deleted first, so a result left by an earlier run
  can never be taken for this one.
* ``--command`` is split into words and run without a shell; each ``--add`` word is appended (use ``--add=-flag`` for
  words that start with a dash). The greenlight run line uses ``--add`` to pass the shuffle seed on.
* Every ``testcase`` of every matching file is copied into one file at ``--out``.
* The exit status is the command's own, so a failing test still shows as a failing run.

It needs only the Python standard library, and it is a bound file: change it and the recorded runs become stale.
"""
import argparse
import glob
import re
import shlex
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

FORBIDDEN = re.compile(rb"<!\s*(DOCTYPE|ENTITY)", re.IGNORECASE)
NO_COMMAND = 127


def report_files(patterns):
    found = []
    for pattern in patterns:
        found += [Path(name) for name in sorted(glob.glob(pattern, recursive=True)) if Path(name).is_file()]
    return found


def allowed(pattern):
    path = Path(pattern)
    return not path.is_absolute() and ".." not in path.parts


def read_cases(path):
    data = path.read_bytes()
    if FORBIDDEN.search(data):
        raise ValueError(f"{path}: a report with a DOCTYPE or ENTITY declaration is refused")
    return list(ET.fromstring(data).iter("testcase"))


def merge(files, out):
    suite = ET.Element("testsuite", name="merged")
    for path in files:
        suite.extend(read_cases(path))
    suite.set("tests", str(len(suite)))
    root = ET.Element("testsuites")
    root.append(suite)
    ET.ElementTree(root).write(out, encoding="utf-8", xml_declaration=True)


def parse_arguments(argv):
    ap = argparse.ArgumentParser(description="Run a test command and merge its JUnit files into one.")
    ap.add_argument("--command", required=True, help="the test command, as one string")
    ap.add_argument("--reports", action="append", required=True, help="glob of the JUnit files the command writes")
    ap.add_argument("--out", required=True, help="the single JUnit file to write")
    ap.add_argument("--add", action="append", default=[], help="a word to append to the command (repeatable)")
    return ap.parse_args(argv)


def main(argv):
    args = parse_arguments(argv)
    if not all(allowed(p) for p in args.reports):
        print("run_junit: --reports must be relative to the project and must not contain '..'", file=sys.stderr)
        return 2
    words = shlex.split(args.command) + args.add
    if not shutil.which(words[0]):
        print(f"run_junit: {words[0]!r} is not on PATH", file=sys.stderr)
        return NO_COMMAND
    for stale in report_files(args.reports):
        stale.unlink()
    status = subprocess.run(words, stdin=subprocess.DEVNULL, check=False).returncode
    files = report_files(args.reports)
    if not files:
        print(f"run_junit: the command wrote no file matching {args.reports}", file=sys.stderr)
        return status or 1
    try:
        merge(files, args.out)
    except (ET.ParseError, ValueError) as exc:
        print(f"run_junit: {exc}", file=sys.stderr)
        return status or 1
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
