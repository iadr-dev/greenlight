"""`bdd mutate FEAT-n`: the optional mutation check on the production files a feature changed.

An adapter opts in with an ``[adapters.mutation]`` table in ``.bdd/config.toml``:

    [adapters.mutation]
    command    = '{project_python} -m some_mutation_tool run {files} --report {out}'
    threshold  = 80                 # at least this percent of the mutants must be killed
    timeout    = 1800
    extensions = [".py"]            # only changed files with these suffixes are mutated

The tool is started without a shell, on the files that differ from the commit at which the red was proven, and writes
a JSON object to ``{out}``, a file in a fresh private folder outside the project that is removed afterwards, and exits 0
once it has finished (survivors are stated in the report, not by a failing exit). The object holds whole numbers
``killed`` and ``survived``, optionally ``timeout``, ``suspicious`` and ``skipped`` (reported, not counted). The result
is recorded in ``.bdd/.runs/FEAT-n/mutation.json`` with the command, the exit status and the hash of the report, which
only this command writes. Without the table nothing changes: no gate asks for the check.

The check fails, rather than passes, when it measured nothing although something changed: production files changed but
none ends in the configured ``extensions``, the tool exited non-zero, or it generated no mutants. Only a feature that
changed no production file at all has nothing to mutate.

A mutation check answers what the recorded runs cannot: whether the tests would notice a change in the code. It is the
answer to production code written to satisfy the tests instead of the rules.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import sys
import tempfile
import time
from pathlib import Path

from . import config as cfg
from . import redrecord, runner, state, store
from .errors import StoreError, UsageError

RESULT = "mutation.json"
COUNTED = ("killed", "survived")
REPORTED = ("timeout", "suspicious", "skipped")


def result_path(root: Path, feature_id: str) -> Path:
    return runner.runs_dir(root, feature_id) / RESULT


def rules_of(root: Path) -> cfg.MutationRules:
    rules = cfg.load(root).mutation
    if rules is None:
        raise UsageError("no [adapters.mutation] table in .bdd/config.toml: the mutation check is not configured")
    return rules


def build_command(rules: cfg.MutationRules, root: Path, out: Path, files: list[str]) -> list[str]:
    """The command words. ``{files}`` (a word of its own) becomes one word per file; nothing else can add words."""
    values = {"{root}": str(root), "{python}": sys.executable, "{project_python}": runner.project_python(root),
              "{out}": str(out)}
    words: list[str] = []
    for word in shlex.split(rules.command):
        if word == "{files}":
            words += files
            continue
        for placeholder, value in values.items():
            word = word.replace(placeholder, value)
        words.append(word)
    return words


def parse_report(path: Path) -> dict[str, int]:
    """The counts in the tool's report; anything else than whole non-negative numbers is refused."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise UsageError(f"the mutation report {path.name} cannot be read as JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise UsageError("the mutation report must be a JSON object")
    counts: dict[str, int] = {}
    for key in COUNTED + REPORTED:
        value = data.get(key, 0 if key in REPORTED else None)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise UsageError(f"the mutation report needs a whole number {key}" if key in COUNTED
                             else f"the mutation report's {key} must be a whole number")
        counts[key] = value
    return counts


def verdict(rules: cfg.MutationRules, counts: dict[str, int] | None, changed: int, selected: int,
            exit_status: int | None) -> tuple[float | None, bool, str]:
    """(score in percent, passed, note). Three cases are not alike: nothing changed (nothing to measure), something
    changed but nothing was selected for mutation (the check covered nothing: a failure), and a tool that ran."""
    if changed == 0:
        return None, True, "no production file changed since the red, so there is nothing to mutate"
    if selected == 0:
        wanted = ", ".join(rules.extensions)
        return None, False, (f"{changed} production file(s) changed but none ends in the configured extensions ({wanted}), "
                             "so the check covered nothing; list the suffixes of the code in `extensions`")
    if exit_status != 0:
        return None, False, (f"the mutation tool exited with status {exit_status}; a tool that completes exits 0 and "
                             "states survivors in its report")
    counted = counts["killed"] + counts["survived"]
    if counted == 0:
        return None, False, "the tool generated no mutants for the changed files, which proves nothing"
    score = round(100 * counts["killed"] / counted, 1)
    if score >= rules.threshold:
        return score, True, ""
    return score, False, f"{counts['survived']} of {counted} mutants survived; at least {rules.threshold:g}% must be killed"


def changed_files(root: Path, feature_dir: Path, rules: cfg.MutationRules) -> tuple[list[str], list[str]]:
    """(production files changed since the red, those of them that are selected for mutation)."""
    red = state.load(feature_dir).get("red")
    if not red:
        raise UsageError("no red was recorded for this feature, so there is no point to measure the change from; "
                         "pass the bind gate first")
    files = redrecord.changed_production_files(root, cfg.load(root).test_dirs, red["commit"])
    return files, [f for f in files if not rules.extensions or f.endswith(rules.extensions)]


def current_marks(root: Path, feature_id: str) -> dict[str, str]:
    """What the result depends on: the production source and the tests as they are now."""
    return {"source_hash": redrecord.source_digest(root, cfg.load(root).test_dirs),
            "inputs": runner.inputs_digest(root, feature_id)}


def run_tool(root: Path, rules: cfg.MutationRules, files: list[str]) -> dict:
    """Run the tool with its report in a fresh private folder outside the project, so nothing in the project (the
    agent, the tool's own configuration) can have written it beforehand. Returns the facts about the run."""
    scrub = next((r.scrub_env for r in cfg.load(root).runs if r.adapter == rules.adapter), ())
    with tempfile.TemporaryDirectory(prefix="greenlight-mutation-") as scratch:
        report = Path(scratch) / "report.json"
        words = build_command(rules, root, report, files)
        started = time.perf_counter()
        status, output = runner.execute(words, root, rules.timeout, scrub)
        tail = output[-runner.TAIL_CHARS:]
        if not report.is_file():
            raise UsageError(f"the mutation tool wrote no report ({' '.join(words)}):\n{tail}")
        raw = report.read_bytes()
        counts = parse_report(report)
    return {"command": words, "exit": status, "seconds": round(time.perf_counter() - started, 2), "tail": tail,
            "counts": counts, "report_sha256": hashlib.sha256(raw).hexdigest()}


def run_mutation(root: Path, feature_id: str) -> dict:
    rules = rules_of(root)
    feature_dir = store.find_feature_dir(root, feature_id)
    changed, files = changed_files(root, feature_dir, rules)
    runner.runs_dir(root, feature_id).mkdir(parents=True, exist_ok=True)
    record = {"schema": runner.SCHEMA, "feature": feature_id, "at": store.utc_now(), "changed": changed, "files": files,
              "threshold": rules.threshold, "command": None, "exit": None, "seconds": 0.0, "tail": "", "counts": None,
              "report_sha256": None, **current_marks(root, feature_id)}
    if files:
        record.update(run_tool(root, rules, files))
    record["score"], record["passed"], record["note"] = verdict(rules, record["counts"], len(changed), len(files),
                                                                record["exit"])
    store.write_json(result_path(root, feature_id), record)
    return record


def load_result(root: Path, feature_id: str) -> dict | None:
    path = result_path(root, feature_id)
    if not path.is_file():
        return None
    data = store.read_json(path, "the mutation result")
    if not isinstance(data, dict) or not isinstance(data.get("passed"), bool):
        raise StoreError(f"{path} is not a mutation result")
    return data


def problems(root: Path, feature_id: str) -> list[str]:
    """Why the verify gate may not pass because of the mutation check. Empty when it is not configured."""
    rules = cfg.load(root).mutation
    if rules is None:
        return []
    try:
        data = load_result(root, feature_id)
    except StoreError as exc:
        return [str(exc)]
    if data is None:
        return [f"the mutation check is configured but has not been run; run `bdd mutate {feature_id}`"]
    marks = current_marks(root, feature_id)
    if any(data.get(key) != value for key, value in marks.items()):
        return [f"the mutation result is out of date: the source or the tests changed since `bdd mutate {feature_id}`"]
    if not data["passed"]:
        return [f"the mutation check failed: {data.get('note') or 'below the threshold'}"]
    return []


def describe(record: dict) -> str:
    score = "no score" if record["score"] is None else f"{record['score']:g}% killed"
    counts = record["counts"]
    detail = "" if counts is None else " (" + ", ".join(f"{n} {k}" for k, n in counts.items() if n) + ")"
    line = f"{record['feature']}: mutation check {'passed' if record['passed'] else 'FAILED'}: {score}{detail}, " \
           f"threshold {record['threshold']:g}%, {len(record['files'])} file(s)"
    return line + (f"\n  {record['note']}" if record["note"] else "")


def run(argv: list[str]) -> int:
    from .statecmd import guarded, project_root          # statecmd imports the gates, which import this module
    ap = argparse.ArgumentParser(prog="bdd mutate", description="Run the optional mutation check on a feature's changed "
                                                                 "production files and record the result.")
    ap.add_argument("feature", help="feature id, e.g. FEAT-007")
    ap.add_argument("--check", action="store_true", help="do not run anything: show the recorded result and say whether it is current")
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
        record = run_mutation(root, args.feature)
        print(describe(record))
        return 0 if record["passed"] else 1

    return guarded("mutate", action)
