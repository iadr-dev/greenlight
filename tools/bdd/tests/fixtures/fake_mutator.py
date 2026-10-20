"""A stand-in mutation tool for the mutation tests: writes the report in FAKE_MUTANTS, and the files it was given.

    fake_mutator.py --report OUT FILE...
"""
import json
import os
import sys


def main(argv):
    out = argv[argv.index("--report") + 1]
    files = [a for a in argv if a not in ("--report", out)]
    if os.environ.get("FAKE_NO_REPORT") != "1":
        with open(out, "w", encoding="utf-8") as handle:
            handle.write(os.environ["FAKE_MUTANTS"])
    with open(out + ".files", "w", encoding="utf-8") as handle:
        handle.write(json.dumps(files))
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
