"""`bdd check FEAT-n`: the optional quality checks of the project's own tools (format, lint, type check, deprecations).

An adapter or project opts in with named tables in ``.bdd/config.toml``:

    [adapters.quality.lint]
    command = '{project_python} -m ruff check {root}'
    timeout = 300                   # seconds, optional (default 600)

    [adapters.quality.typecheck]
    command = '{project_python} -m mypy {root}'

Each command is split into words before ``{root}``, ``{python}`` and ``{project_python}`` are filled in and is started
without a shell, in the project, with the same environment rules as ``bdd run`` (variables that steer a program are not
passed on). The exit status is the verdict: 0 passes, anything else fails. A tool that is not installed, or that runs
too long, is a failed check with the reason, not a crash. greenlight reads nothing else from the tool's output, so any
language's formatter, linter, compiler or deprecation switch fits.

The result is recorded in ``.bdd/.runs/FEAT-n/quality.json``, which only this command writes (the guard keeps everyone
else out of that folder), together with what it depends on: the production source and the tests as they are now, the
interpreter, and the project's ``.bdd/standards.md``. The implement and verify gates ask for a current, passing result
only when checks are configured; without them nothing changes. A feature of kind ``adopt`` is not held to it: the code
it describes already exists and is not judged.
"""
from __future__ import annotations

import argparse
import shlex
import sys
import time
from pathlib import Path

from . import config as cfg
from . import lockfile, redrecord, runner, store
from .errors import StoreError, UsageError

RESULT = "quality.json"
STANDARDS = "standards.md"


def result_path(root: Path, feature_id: str) -> Path:
    return runner.runs_dir(root, feature_id) / RESULT


def standards_path(root: Path) -> Path:
    return root / cfg.BDD_DIR / STANDARDS


def rules_of(root: Path) -> cfg.QualityRules:
    rules = cfg.load(root).quality
    if rules is None:
        raise UsageError("no [adapters.quality.NAME] table in .bdd/config.toml: no quality check is configured")
    return rules


def build_command(check: cfg.QualityCheck, root: Path) -> list[str]:
    """The command words. A value is put into a word of its own and can never add words."""
    values = {"{root}": str(root), "{python}": sys.executable, "{project_python}": runner.project_python(root)}
    words = []
    for word in shlex.split(check.command):
        for placeholder, value in values.items():
            word = word.replace(placeholder, value)
        words.append(word)
    return words


def uses_project_python(rules: cfg.QualityRules) -> bool:
    return any("{project_python}" in check.command for check in rules.checks)


def standards_digest(root: Path) -> str | None:
    path = standards_path(root)
    return lockfile.file_digest(path) if path.is_file() else None


def current_marks(root: Path, feature_id: str, rules: cfg.QualityRules) -> dict:
    """What the result depends on, as it is right now."""
    return {"source_hash": redrecord.source_digest(root, cfg.load(root).test_dirs),
            "inputs": runner.inputs_digest(root, feature_id), "standards": standards_digest(root),
            "interpreter": runner.interpreter_identity(root) if uses_project_python(rules) else None}


def run_check(root: Path, check: cfg.QualityCheck, scrub: tuple[str, ...]) -> dict:
    started = time.perf_counter()
    words: list[str] = []
    note = ""
    status: int | None = None
    tail = ""
    try:
        words = build_command(check, root)
        status, output = runner.execute(words, root, check.timeout, scrub)
        tail = output[-runner.TAIL_CHARS:]
    except UsageError as exc:                    # not installed, not startable, too slow: the check failed, say why
        note = str(exc)
    return {"name": check.name, "command": words, "exit": status, "passed": status == 0,
            "seconds": round(time.perf_counter() - started, 2), "tail": tail, "note": note}


def run_checks(root: Path, feature_id: str) -> dict:
    rules = rules_of(root)
    store.find_feature_dir(root, feature_id)             # the feature must exist
    scrub = next((r.scrub_env for r in cfg.load(root).runs if r.adapter == rules.adapter), ())
    results = [run_check(root, check, scrub) for check in rules.checks]
    runner.runs_dir(root, feature_id).mkdir(parents=True, exist_ok=True)
    record = {"schema": runner.SCHEMA, "feature": feature_id, "at": store.utc_now(), "checks": results,
              "passed": all(r["passed"] for r in results), **current_marks(root, feature_id, rules)}
    store.write_json(result_path(root, feature_id), record)
    return record


def load_result(root: Path, feature_id: str) -> dict | None:
    path = result_path(root, feature_id)
    if not path.is_file():
        return None
    data = store.read_json(path, "the quality result")
    if not isinstance(data, dict) or not isinstance(data.get("passed"), bool) or not isinstance(data.get("checks"), list):
        raise StoreError(f"{path} is not a quality result")
    return data


def problems(root: Path, feature_id: str) -> list[str]:
    """Why the implement or verify gate may not pass because of the quality checks. Empty when none are configured."""
    rules = cfg.load(root).quality
    if rules is None:
        return []
    try:
        data = load_result(root, feature_id)
    except StoreError as exc:
        return [str(exc)]
    if data is None:
        return [f"quality checks are configured but have not been run; run `bdd check {feature_id}`"]
    marks = current_marks(root, feature_id, rules)
    if any(data.get(key) != value for key, value in marks.items()):
        return [f"the quality result is out of date: the source, the tests, the interpreter or .bdd/standards.md changed "
                f"since `bdd check {feature_id}`"]
    names = {check.name for check in rules.checks}
    if names != {c.get("name") for c in data["checks"]}:
        return [f"the quality checks changed since `bdd check {feature_id}`; run it again"]
    if not data["passed"]:
        failed = [c["name"] for c in data["checks"] if not c.get("passed")]
        return [f"quality check(s) failed: {', '.join(failed)}; fix the code and run `bdd check {feature_id}` again"]
    return []


def describe(record: dict) -> str:
    lines = [f"{record['feature']}: quality checks {'passed' if record['passed'] else 'FAILED'}"]
    for result in record["checks"]:
        state = "ok  " if result["passed"] else "FAIL"
        detail = result["note"] or ("" if result["passed"] else f"exit {result['exit']}")
        lines.append(f"  {state} {result['name']}" + (f": {detail}" if detail else ""))
        if not result["passed"] and result["tail"]:
            lines += ["       " + line for line in result["tail"].strip().splitlines()[-12:]]
    return "\n".join(lines)


def run(argv: list[str]) -> int:
    from .statecmd import guarded, project_root          # statecmd imports the gates, which import this module
    ap = argparse.ArgumentParser(prog="bdd check", description="Run the project's quality checks (format, lint, type "
                                                               "check, deprecations) and record the result.")
    ap.add_argument("feature", help="feature id, e.g. FEAT-007")
    ap.add_argument("--check", action="store_true",
                    help="do not run anything: show the recorded result and say whether it is current")
    args = ap.parse_args(argv)

    def action() -> int:
        root = project_root()
        if args.check:
            rules_of(root)
            found = problems(root, args.feature)
            data = load_result(root, args.feature)
            if data:
                print(describe(data))
            for line in found:
                print(line, file=sys.stderr)
            return 1 if found else 0
        record = run_checks(root, args.feature)
        print(describe(record))
        return 0 if record["passed"] else 1

    return guarded("check", action)
