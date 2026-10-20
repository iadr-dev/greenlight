"""`bdd status` and `bdd trace`: read-only reports.

    bdd status [--brief] [--json]       every feature in this project and what it is waiting for
    bdd trace FEAT-007 [--json]         rule -> example -> scenario -> task matrix and its gaps
    bdd scan FEAT-007 [--json]          assertion-free then steps, fixed waits, stubs of undeclared dependencies

``status --brief`` is for the SessionStart hook: one line, nothing at all when there is nothing in
progress, and never an error (a hook that fails would only get in the way).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import approvals, enforcement, scan, state, store, trace, tripwire
from . import config as cfg
from .errors import StoreError, UsageError
from .statecmd import guarded, project_root

WAITING_FOR_PERSON = {"specify": "rules", "examples": "examples"}


def feature_dirs(root: Path) -> list[Path]:
    base = store.features_dir(root)
    return sorted(p for p in base.glob("FEAT-*") if p.is_dir() and state.path_of(p).is_file()) if base.is_dir() else []


def waiting_for(feature: str, data: dict) -> str:
    phase = data["phase"]
    if phase == "done":
        return "nothing: done"
    if phase in WAITING_FOR_PERSON:
        gate = WAITING_FOR_PERSON[phase]
        return f"the person: /greenlight:approve {feature} {gate}"
    failed = [name for name, g in data["gates"].items() if g["result"] == "fail"]
    return f"the {phase} phase" + (f" ({', '.join(failed)} failed last time)" if failed else "")


def approval_text(root: Path, data: dict) -> str:
    parts = []
    for gate in approvals.GATES:
        last = approvals._last(data, gate)
        if last is None:
            parts.append(f"{gate}: -")
        elif approvals.effective_problems(root, data, gate):
            parts.append(f"{gate}: {last['decision']}d but not valid" if last["decision"] == "approve" else f"{gate}: rejected")
        else:
            parts.append(f"{gate}: approved")
    return ", ".join(parts)


def feature_row(root: Path, feature_dir: Path) -> dict:
    data = state.load(feature_dir)
    level, _ = enforcement.classify(root, data)
    return {"feature": data["feature"], "title": data["title"], "phase": data["phase"],
            "autonomy": data["autonomy"]["level"], "approvals": approval_text(root, data), "enforcement": level,
            "waiting_for": waiting_for(data["feature"], data), "dir": feature_dir.name}


def open_violation_count(root: Path) -> int | None:
    """Open integrity violations, or None when the integrity data cannot be read."""
    try:
        return len(tripwire.open_violations(root))
    except (StoreError, OSError, KeyError, TypeError, ValueError):
        return None


def table(rows: list[dict]) -> str:
    columns = [("FEATURE", "feature"), ("TITLE", "title"), ("PHASE", "phase"), ("AUTONOMY", "autonomy"),
               ("APPROVALS", "approvals"), ("ENFORCEMENT", "enforcement"), ("WAITING FOR", "waiting_for")]
    widths = [max(len(head), *(len(str(r[key])) for r in rows)) for head, key in columns]
    lines = ["  ".join(head.ljust(w) for (head, _), w in zip(columns, widths)).rstrip()]
    lines += ["  ".join(str(r[key]).ljust(w) for (_, key), w in zip(columns, widths)).rstrip() for r in rows]
    return "\n".join(lines)


def brief(root: Path) -> str:
    rows = [feature_row(root, d) for d in feature_dirs(root)]
    active = [r for r in rows if r["phase"] != "done"]
    violations = open_violation_count(root)
    parts = []
    if active:
        first = active[0]
        parts.append(f"{first['feature']} {first['title']} is at {first['phase']}, waiting for {first['waiting_for']}")
        if len(active) > 1:
            parts.append(f"{len(active) - 1} other feature(s) in progress")
    if violations is None:
        parts.append("the integrity data cannot be read (run `bdd status`)")
    elif violations:
        parts.append(f"{violations} integrity violation(s) open (run `bdd status`)")
    return "greenlight: " + "; ".join(parts) + "." if parts else ""


def run_status(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="bdd status", description="Where every feature stands.")
    ap.add_argument("--brief", action="store_true", help="one line for a session start; silent when nothing is in progress")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    if args.brief:
        return run_brief()
    return guarded("status", lambda: do_status(project_root(), args.json))


def run_brief() -> int:
    try:
        root = cfg.find_root()
        line = brief(root) if root else ""
    except (StoreError, UsageError, OSError, KeyError, TypeError, ValueError, cfg.ConfigError):
        return 0
    if line:
        print(line)
    return 0


def do_status(root: Path, as_json: bool) -> int:
    rows = [feature_row(root, d) for d in feature_dirs(root)]
    violations = open_violation_count(root)
    if as_json:
        print(json.dumps({"features": rows, "open_violations": violations}, indent=2, ensure_ascii=False))
        return 0
    print(table(rows) if rows else "no features yet; start one with /greenlight:feature")
    if violations is None:
        print("integrity: the data under .bdd/.integrity cannot be read")
    elif violations:
        print(f"integrity: {violations} violation(s) open")
        for v in tripwire.open_violations(root):
            print(f"  #{v['id']} {tripwire.describe(v)}")
    return 0


def run_trace(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="bdd trace", description="Rule -> example -> scenario -> task matrix.")
    ap.add_argument("feature", help="feature id, e.g. FEAT-007")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_intermixed_args(argv)

    def action() -> int:
        root = project_root()
        report = trace.build(root, store.find_feature_dir(root, args.feature), args.feature)
        print(json.dumps(report, indent=2, ensure_ascii=False) if args.json else trace.render(report))
        return 1 if report["gaps"] else 0

    return guarded("trace", action)


def run_scan(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="bdd scan", description="Deterministic checks on step definitions and drivers.")
    ap.add_argument("feature", help="feature id, e.g. FEAT-007")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_intermixed_args(argv)

    def action() -> int:
        root = project_root()
        issues = scan.scan(root, store.find_feature_dir(root, args.feature))
        if args.json:
            print(json.dumps([vars(i) for i in issues], indent=2, ensure_ascii=False))
        else:
            print("\n".join(str(i) for i in issues) if issues else f"{args.feature}: no findings")
        return 1 if issues else 0

    try:
        return guarded("scan", action)
    except cfg.ConfigError as exc:
        print(f"bdd scan: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(run_status(sys.argv[1:]))
