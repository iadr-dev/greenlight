"""`bdd stability FEAT-n`: rerun a feature several times and flag a scenario whose outcome changes.

    bdd stability FEAT-007 [--runs N] [--adapter NAME]
        run the feature N times (the first in the usual order, the others shuffled when the adapter can) and record
        every run; exit 1 when a scenario did not behave the same each time
    bdd stability FEAT-007 --check
        do not run anything: show the recorded result and say whether it is current

A scenario that passes in one run and fails in another is flaky (a race, shared state, an order dependency, a clock
or a random value the test does not control), and a green run of such a scenario proves little. The project asks for
the check by writing ``[stability] runs = N`` in ``.bdd/config.toml`` (2 to 50): the verify gate then wants a current
result of at least that many runs without a flaky scenario. Without the table nothing changes.

The runs do not replace ``bdd run``'s last run (the gates read that one). The result is recorded in
``.bdd/.runs/FEAT-n/stability.json``, which only this command writes (the guard keeps everyone else out of that
folder), together with the files and the interpreter it depends on.

What it can show: that the scenarios behave the same in the orders and repetitions tried. What it cannot: that a rare
race will not show on a busy machine; more runs make a missed flake less likely, never impossible.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import classify, config as cfg, junit, runner, store
from .errors import StoreError, UsageError

RESULT = "stability.json"
FOLDER = "stability"
DEFAULT_RUNS = 3


def result_path(root: Path, feature_id: str) -> Path:
    return runner.runs_dir(root, feature_id) / RESULT


def run_count(root: Path, requested: int | None) -> int:
    """How many runs: the request, else what the project asks for, else a small default."""
    count = requested if requested is not None else (cfg.load(root).stability_runs or DEFAULT_RUNS)
    if not 2 <= count <= cfg.MAX_STABILITY_RUNS:
        raise UsageError(f"--runs must be from 2 to {cfg.MAX_STABILITY_RUNS}: one run cannot show a change")
    return count


def outcomes(cases: list[junit.Case], scenarios: list[dict], rules: list[cfg.RunRules]) -> dict[str, str]:
    """The result of every scenario in one run (the worst of its cases, ``not-run`` if it had none)."""
    found: dict[str, list[dict]] = {}
    for case in cases:
        scenario = classify.scenario_for(case.name, scenarios)
        if scenario is not None:
            found.setdefault(scenario["name"], []).append(
                {"result": classify.classify_case(case, rules), "detail": ""})
    return {s["name"]: classify.scenario_row(s, found.get(s["name"], []))["result"] for s in scenarios}


def flaky_scenarios(per_run: list[dict[str, str]]) -> dict[str, list[str]]:
    """The scenarios whose result is not the same in every run, with their results in run order."""
    names = per_run[0].keys() if per_run else ()
    return {name: [run[name] for run in per_run] for name in names if len({run[name] for run in per_run}) > 1}


def current_marks(root: Path, feature_id: str) -> dict:
    return {"inputs": runner.inputs_digest(root, feature_id), "interpreter": runner.interpreter_identity(root)}


def run_stability(root: Path, feature_id: str, count: int, adapter: str | None) -> dict:
    store.find_feature_dir(root, feature_id)
    config = cfg.load(root)
    rules = runner.pick_rules(config, adapter)
    scenarios = classify.feature_scenarios(root, feature_id)
    folder = runner.runs_dir(root, feature_id) / FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    seeds = [runner.fresh_seed() if rules.shuffle and index > 1 else None for index in range(1, count + 1)]
    plan, per_run = [], []
    for index, seed in enumerate(seeds, start=1):
        entry, cases = runner.one_run(rules, root, folder, index, feature_id, seed=seed)
        plan.append({"seed": seed, "exit": entry["exit"], "seconds": entry["seconds"], "report": entry["report"],
                     "tail": "" if entry["report"] else entry["tail"]})
        per_run.append(outcomes(cases, scenarios, list(config.runs)))
    flaky = flaky_scenarios(per_run)
    silent = [str(i) for i, p in enumerate(plan, start=1) if not p["report"]]
    note = ""
    if silent:
        note = f"run(s) {', '.join(silent)} wrote no test report"
    elif flaky:
        note = f"{len(flaky)} scenario(s) did not behave the same in every run"
    record = {"schema": runner.SCHEMA, "feature": feature_id, "at": store.utc_now(), "runs": count, "plan": plan,
              "scenarios": {name: [run[name] for run in per_run] for name in per_run[0]},
              "flaky": flaky, "passed": not flaky and not silent, "note": note, **current_marks(root, feature_id)}
    store.write_json(result_path(root, feature_id), record)
    return record


def load_result(root: Path, feature_id: str) -> dict | None:
    path = result_path(root, feature_id)
    if not path.is_file():
        return None
    data = store.read_json(path, "the stability result")
    if not isinstance(data, dict) or not isinstance(data.get("passed"), bool) or not isinstance(data.get("runs"), int):
        raise StoreError(f"{path} is not a stability result")
    return data


def problems(root: Path, feature_id: str) -> list[str]:
    """Why the verify gate may not pass because of the stability check. Empty when the project did not ask for it."""
    wanted = cfg.load(root).stability_runs
    if not wanted:
        return []
    try:
        data = load_result(root, feature_id)
    except StoreError as exc:
        return [str(exc)]
    if data is None:
        return [f"a stability check is asked for ([stability] runs = {wanted}) but has not been run; run "
                f"`bdd stability {feature_id}`"]
    marks = current_marks(root, feature_id)
    if any(data.get(key) != value for key, value in marks.items()):
        return [f"the stability result is out of date: the feature files, steps or interpreter changed since "
                f"`bdd stability {feature_id}`"]
    if data["runs"] < wanted:
        return [f"the stability result has {data['runs']} run(s) and the project asks for {wanted}; run "
                f"`bdd stability {feature_id} --runs {wanted}`"]
    if not data["passed"]:
        names = ", ".join(f'"{n}"' for n in data.get("flaky", {}))
        return [f"the stability check failed: {data.get('note') or 'not stable'}" + (f" ({names})" if names else "")]
    return []


def describe(record: dict) -> str:
    lines = [f"{record['feature']}: stability {'passed' if record['passed'] else 'FAILED'} over {record['runs']} run(s)"
             + (f" ({record['note']})" if record["note"] else "")]
    for name, results in record["flaky"].items():
        lines.append(f"  flaky: \"{name}\": {', '.join(results)}")
    seeds = [str(p["seed"]) for p in record["plan"] if p["seed"]]
    if seeds:
        lines.append(f"  shuffle seeds: {', '.join(seeds)}")
    return "\n".join(lines)


def run(argv: list[str]) -> int:
    from .statecmd import guarded, project_root          # statecmd imports the gates, which import this module
    ap = argparse.ArgumentParser(prog="bdd stability", description="Rerun a feature and flag scenarios that change outcome.")
    ap.add_argument("feature", help="feature id, e.g. FEAT-007")
    ap.add_argument("--runs", type=int, help="how many runs (default: [stability] runs, else 3)")
    ap.add_argument("--adapter", help="which adapter's command to use (needed when several have one)")
    ap.add_argument("--check", action="store_true", help="do not run anything: show the recorded result and say whether it is current")
    args = ap.parse_args(argv)

    def action() -> int:
        root = project_root()
        if args.check:
            found = problems(root, args.feature) or ([] if cfg.load(root).stability_runs else
                                                      ["no [stability] table in .bdd/config.toml: the check is not asked for"])
            data = load_result(root, args.feature)
            if data:
                print(describe(data))
            for line in found:
                print(line, file=sys.stderr)
            return 1 if found else 0
        record = run_stability(root, args.feature, run_count(root, args.runs), args.adapter)
        print(describe(record))
        return 0 if record["passed"] else 1

    return guarded("stability", action)
