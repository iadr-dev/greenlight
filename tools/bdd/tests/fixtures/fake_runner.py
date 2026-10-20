"""A stand-in test runner for the run and classify tests: writes JUnit XML from the cases in FAKE_CASES.

    fake_runner.py --out report.xml [--seed N] [--only NAME]
"""
import json
import os
import re
import sys
import time
from xml.sax.saxutils import escape, quoteattr


def squash(text):
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def main(argv):
    options = dict(zip(argv[::2], argv[1::2]))
    cases = json.loads(os.environ["FAKE_CASES"])
    if "--only" in options:
        cases = [c for c in cases if squash(options["--only"]) in squash(c["name"])]
    time.sleep(float(os.environ.get("FAKE_SLEEP", "0")))
    rows = []
    for case in cases:
        tag = {"passed": None, "failed": "failure", "error": "error", "skipped": "skipped"}[case["outcome"]]
        inner = f"<{tag} message={quoteattr(case.get('text', ''))}>{escape(case.get('body', ''))}</{tag}>" if tag else ""
        rows.append(f"<testcase classname={quoteattr(case.get('classname', 'suite'))} name={quoteattr(case['name'])}>{inner}</testcase>")
    with open(options["--out"], "w", encoding="utf-8") as handle:
        handle.write(f'<?xml version="1.0" encoding="utf-8"?><testsuites><testsuite name="fake">{"".join(rows)}</testsuite></testsuites>')
    with open(options["--out"] + ".argv", "w", encoding="utf-8") as handle:
        handle.write(json.dumps(argv))
    return 1 if any(c["outcome"] in ("failed", "error") for c in cases) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
