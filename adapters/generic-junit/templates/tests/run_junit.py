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
import os
import re
import shlex
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

FORBIDDEN = re.compile(rb"<!\s*(DOCTYPE|ENTITY)", re.IGNORECASE)
NO_COMMAND = 127
BATCH_SUFFIXES = (".bat", ".cmd")
CMD_METACHARACTERS = '"&|<>^%!\r\n'            # cmd.exe reads these as syntax when it runs a batch file


def executable_suffixes():
    """The suffixes Windows runs without being told (PATHEXT); none elsewhere, where the mode bit decides."""
    if os.name != "nt":
        return ()
    value = os.environ.get("PATHEXT") or ".COM;.EXE;.BAT;.CMD"
    return tuple(part.lower() for part in value.split(";") if part.startswith("."))


def find_program(word):
    """The file the command's first word names, or None.

    A word with a path separator is an explicit path (``./gradlew``). A bare name such as ``npm`` is looked up only in the
    absolute folders of PATH, never in the working directory, which Windows would otherwise search first: a file planted in
    the project cannot stand in for a tool. The full file name is returned, so ``npm.cmd`` starts without a shell."""
    path = Path(word)
    explicit = "/" in word or "\\" in word
    suffixes = executable_suffixes()
    folders = [path.parent] if explicit else [Path(entry) for entry in os.environ.get("PATH", "").split(os.pathsep)
                                              if entry and Path(entry).is_absolute()]
    names = [path.name] if not suffixes or path.suffix.lower() in suffixes else [path.name + suffix for suffix in suffixes]
    for folder in folders:
        for name in names:
            candidate = folder / name
            if candidate.is_file() and (bool(suffixes) or os.access(candidate, os.X_OK)):
                return str(candidate)
    return None


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
    program = find_program(words[0])
    if not program:
        print(f"run_junit: {words[0]!r} is not on PATH", file=sys.stderr)
        return NO_COMMAND
    if program.lower().endswith(BATCH_SUFFIXES) and any(c in word for word in words[1:] for c in CMD_METACHARACTERS):
        print(f"run_junit: {Path(program).name} is a batch file and an argument holds a character that cmd.exe reads as syntax",
              file=sys.stderr)
        return 2
    words[0] = program                          # npm is npm.cmd on Windows; the full name starts it without a shell
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
