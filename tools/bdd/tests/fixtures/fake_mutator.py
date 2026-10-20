"""A stand-in mutation tool for the mutation tests: writes the report in FAKE_MUTANTS, and the files it was given.

    fake_mutator.py --report OUT FILE...

FAKE_FILES_OUT names a file that receives the list of files; FAKE_EXIT is the exit status (default 0);
FAKE_NO_REPORT=1 writes no report; FAKE_SEE_REPORT_FIRST=<file> records whether OUT existed when the tool started.
"""
import json
import os
import sys


def main(argv):
    out = argv[argv.index("--report") + 1]
    files = [a for a in argv if a not in ("--report", out)]
    if os.environ.get("FAKE_SEE_REPORT_FIRST"):
        with open(os.environ["FAKE_SEE_REPORT_FIRST"], "w", encoding="utf-8") as handle:
            handle.write(json.dumps({"existed": os.path.exists(out), "path": out}))
    if os.environ.get("FAKE_NO_REPORT") != "1":
        with open(out, "w", encoding="utf-8") as handle:
            handle.write(os.environ["FAKE_MUTANTS"])
    if os.environ.get("FAKE_FILES_OUT"):
        with open(os.environ["FAKE_FILES_OUT"], "w", encoding="utf-8") as handle:
            handle.write(json.dumps(files))
    return int(os.environ.get("FAKE_EXIT", "0"))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
