"""`bdd run` and `bdd classify`.

    bdd run FEAT-007 [--adapter NAME] [--shuffle [--seed N]] [--isolated]
        run the feature's tests with the adapter's command and record what happened
    bdd classify FEAT-007 [--expect red|green] [--json]
        classify the recorded run per scenario; with --expect, exit 1 unless that verdict holds

Run the adapter's tests through ``bdd run`` and not by hand: only a recorded run can back a gate.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter

from . import classify, config as cfg, runner, store
from .errors import StoreError, UsageError
from .statecmd import guarded, project_root


def run_run(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="bdd run", description="Run a feature's tests and record the result.")
    ap.add_argument("feature", help="feature id, e.g. FEAT-007")
    ap.add_argument("--adapter", help="which adapter's command to use (needed when several have one)")
    ap.add_argument("--shuffle", action="store_true", help="random order, to expose scenarios that depend on each other")
    ap.add_argument("--seed", type=int, help="repeat a shuffled order (with --shuffle)")
    ap.add_argument("--isolated", action="store_true", help="one process per scenario, to expose shared state")
    args = ap.parse_intermixed_args(argv)
    if args.seed is not None and not args.shuffle:
        ap.error("--seed only makes sense with --shuffle")
    if args.shuffle and args.isolated:
        ap.error("--shuffle and --isolated are separate checks; run them one after the other")
    return guarded("run", lambda: do_run(args))


def do_run(args: argparse.Namespace) -> int:
    root = project_root()
    store.find_feature_dir(root, args.feature)
    rules = runner.pick_rules(cfg.load(root), args.adapter)
    names = [s["name"] for s in classify.feature_scenarios(root, args.feature)]
    record = runner.run_feature(root, args.feature, names, rules, shuffle=args.shuffle, isolated=args.isolated,
                                seed=args.seed)
    counts = Counter(c["outcome"] for c in record["cases"])
    seed = f", seed {record['seed']}" if record["seed"] else ""
    print(f"{args.feature}: {len(record['runs'])} run(s) ({record['mode']}{seed}): "
          + (", ".join(f"{n} {k}" for k, n in sorted(counts.items())) or "no test cases"))
    missing = [r for r in record["runs"] if not r["report"]]
    for r in missing:
        print(f"no test report was written by: {' '.join(r['command'])}\n{r['tail']}", file=sys.stderr)
    return 1 if missing or not record["cases"] else 0


def run_classify(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="bdd classify", description="Classify the recorded run of a feature.")
    ap.add_argument("feature", help="feature id, e.g. FEAT-007")
    ap.add_argument("--expect", choices=("red", "green"), help="exit 1 unless the run is a valid red / a green")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_intermixed_args(argv)

    def action() -> int:
        root = project_root()
        store.find_feature_dir(root, args.feature)
        record = runner.load_latest(root, args.feature)
        rules = list(cfg.load(root).runs)
        report = classify.classify_run(record, classify.feature_scenarios(root, args.feature), rules)
        print(json.dumps(report, indent=2, ensure_ascii=False) if args.json else classify.render(report))
        return 0 if args.expect is None or report[args.expect]["valid"] else 1

    try:
        return guarded("classify", action)
    except (cfg.ConfigError, StoreError, UsageError) as exc:
        print(f"bdd classify: {exc}", file=sys.stderr)
        return 2
