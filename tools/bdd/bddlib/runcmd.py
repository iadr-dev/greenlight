"""`bdd run` and `bdd classify`.

    bdd run FEAT-007 [--adapter NAME] [--shuffle [--seed N]] [--isolated]
        run the feature's tests with the adapter's command (with every adapter's, when a repository has several)
        and record what happened
    bdd run FEAT-007 --against-red [--adapter NAME]
        run them against the production source the red was first proven on (after a reopen past the code)
    bdd classify FEAT-007 [--expect red|green] [--json]
        classify the recorded run per scenario; with --expect, exit 1 unless that verdict holds

Run the adapter's tests through ``bdd run`` and not by hand: only a recorded run can back a gate.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter

from . import againstred, classify, config as cfg, runner, state, store
from .errors import StoreError, UsageError
from .statecmd import guarded, project_root


def run_run(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="bdd run", description="Run a feature's tests and record the result.")
    ap.add_argument("feature", help="feature id, e.g. FEAT-007")
    ap.add_argument("--adapter", help="run only this adapter's tests (by default every adapter that has a run command runs)")
    ap.add_argument("--shuffle", action="store_true", help="random order, to expose scenarios that depend on each other")
    ap.add_argument("--seed", type=int, help="repeat a shuffled order (with --shuffle)")
    ap.add_argument("--isolated", action="store_true", help="one process per scenario, to expose shared state")
    ap.add_argument("--against-red", action="store_true",
                    help="run in a temporary worktree of the production source the red was proven on, with today's "
                         "tests laid over it: proves the red again after the feature was reopened past its code")
    args = ap.parse_intermixed_args(argv)
    if args.against_red and (args.shuffle or args.isolated):
        ap.error("--against-red makes one plain run; shuffle or isolate the tests in the project afterwards")
    if args.seed is not None and not args.shuffle:
        ap.error("--seed only makes sense with --shuffle")
    if args.shuffle and args.isolated:
        ap.error("--shuffle and --isolated are separate checks; run them one after the other")
    return guarded("run", lambda: do_run(args))


def do_run(args: argparse.Namespace) -> int:
    root = project_root()
    feature_dir = store.find_feature_dir(root, args.feature)
    config = cfg.load(root)
    adapters = runner.pick_all(config, args.adapter)
    scenarios = classify.feature_scenarios(root, args.feature)
    note = ""
    if args.against_red:
        record, linked = run_against_red(root, args.feature, state.load(feature_dir), config, scenarios, adapters)
        note = links_note(linked)
    else:
        record = runner.run_feature(root, args.feature, scenarios, adapters,
                                    shuffle=args.shuffle, isolated=args.isolated, seed=args.seed)
    counts = Counter(c["outcome"] for c in record["cases"])
    seed = f", seed {record['seed']}" if record["seed"] else ""
    print(f"{args.feature}: {len(record['runs'])} run(s) ({record['mode']}{seed}): "
          + (", ".join(f"{n} {k}" for k, n in sorted(counts.items())) or "no test cases"))
    missing = [r for r in record["runs"] if not r["report"]]
    for r in missing:
        print(f"no test report was written by: {' '.join(r['command'])}\n{r['tail']}", file=sys.stderr)
    empty = [r for r in record["runs"] if r["report"] and not r.get("cases")]
    for r in empty:
        print(f"the test report holds no test cases (the runner exited with status {r['exit']}): {' '.join(r['command'])}\n"
              f"Nothing matched the feature's tag, or the runner found no tests to run. {note}Its output was:\n{r['tail']}",
              file=sys.stderr)
    return 1 if missing or empty or not record["cases"] else 0


def run_against_red(root, feature_id: str, data: dict, config: cfg.Config, scenarios: list[dict],
                    adapters: list[cfg.RunRules]) -> tuple[dict, list[str]]:
    """Run the feature's current tests against the production source of its recorded red (see ``againstred``)."""
    why = againstred.problem(data)
    if why:
        raise UsageError(why)
    red = againstred.baseline(data)
    with againstred.red_worktree(root, red, config) as (place, linked):
        record = runner.run_feature(root, feature_id, scenarios, adapters, workdir=place,
                                    against_red=againstred.describe(red))
    source = red.get("snapshot") or red.get("commit") or ""
    print(f"{feature_id}: ran against the red recorded at {red.get('at')} (production source {source[:12]})")
    return record, linked


def links_note(linked: list[str]) -> str:
    """What an empty result of a run in the temporary worktree can say about the project's installed folders."""
    if linked:
        return f"The project's folders linked or copied into the temporary worktree: {', '.join(linked)}. "
    return (f"The project has none of {', '.join(againstred.DEPENDENCY_DIRS)} to link into the temporary worktree, "
            "so tests that load packages from them find nothing there: install the project's dependencies first. ")


def run_classify(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="bdd classify", description="Classify the recorded run of a feature.")
    ap.add_argument("feature", help="feature id, e.g. FEAT-007")
    ap.add_argument("--expect", choices=("red", "green"), help="exit 1 unless the run is a valid red / a green")
    ap.add_argument("--run", choices=("latest", "red"), default="latest",
                    help="the last run (default) or the run that proved the red, kept at the bind gate")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_intermixed_args(argv)

    def action() -> int:
        root = project_root()
        feature_dir = store.find_feature_dir(root, args.feature)
        record = (runner.load_latest(root, args.feature) if args.run == "latest"
                  else runner.load_red(root, args.feature, state.load(feature_dir).get("red_run")))
        rules = list(cfg.load(root).runs)
        report = classify.classify_run(record, classify.feature_scenarios(root, args.feature), rules)
        print(json.dumps(report, indent=2, ensure_ascii=False) if args.json else classify.render(report))
        return 0 if args.expect is None or report[args.expect]["valid"] else 1

    try:
        return guarded("classify", action)
    except (cfg.ConfigError, StoreError, UsageError) as exc:
        print(f"bdd classify: {exc}", file=sys.stderr)
        return 2
