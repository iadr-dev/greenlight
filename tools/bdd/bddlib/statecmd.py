"""State commands.

    bdd state init FEAT-007 --title "Order discounts" [--autonomy standard]
    bdd state show FEAT-007 [--json]
    bdd gate FEAT-007 bind --result pass [--detail key=value ...] [--record-red]
    bdd assume FEAT-007 --text "..." --rationale "..." [--alt "..."]
    bdd cost FEAT-007 --phase bind --tokens 12000 --seconds 95
    bdd cost FEAT-007 --collect               the agents that finished, from the hook's notes and their transcripts
    bdd mode FEAT-007 --switch autopilot --reason "you decide"
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import config as cfg
from . import agentcost, approvals, enforcement, gates, lockfile, redrecord, state, store
from .errors import StoreError, UsageError


def project_root() -> Path:
    root = cfg.find_root()
    if root is None:
        raise UsageError("not inside a greenlight project (no .bdd directory found); run /greenlight:init first")
    return root


def guarded(prog: str, action) -> int:
    """Run ``action`` and turn the expected failures into a message and exit status 2."""
    try:
        return action()
    except (UsageError, StoreError) as exc:
        print(f"bdd {prog}: {exc}", file=sys.stderr)
        return 2


def feature_dir_of(root: Path, feature_id: str) -> Path:
    return store.find_feature_dir(root, feature_id)


# -- state init / show ---------------------------------------------------------------------
def state_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="bdd state")
    sub = ap.add_subparsers(dest="action", required=True)
    init = sub.add_parser("init", help="create a feature and its state file")
    init.add_argument("feature")
    init.add_argument("--title", required=True)
    init.add_argument("--autonomy", choices=state.AUTONOMY, help="default: from .bdd/config.toml")
    init.add_argument("--adopt", action="store_true",
                      help="the feature describes behaviour the system already has; production code must stay as it is")
    sub.add_parser("next-id", help="print the next free feature id")
    show = sub.add_parser("show", help="print where a feature stands")
    show.add_argument("feature")
    show.add_argument("--json", action="store_true")
    return ap


def summary(root: Path, feature_dir: Path, data: dict) -> dict:
    locks = lockfile.read_lock(feature_dir, data["feature"])["scopes"]
    level, reasons = enforcement.classify(root, data)
    return {**data, "locks": {scope: len(v["files"]) for scope, v in locks.items()},
            "enforcement": {"level": level, "reasons": reasons}}


def approval_how(approval: dict) -> str:
    if approval["grade"] == "codex":
        return approvals.CODEX_LABEL
    return f"typed, origin {approval['origin']}" if approval["grade"] == "hook" else approval["grade"]


def describe_approvals(entries: list[dict]) -> str:
    parts = []
    for a in entries:
        what = f"{a['gate']} {a['decision']}d" if a["decision"] == "approve" else f"{a['gate']} rejected"
        how = approval_how(a)
        parts.append(f"{what} ({how})")
    return ", ".join(parts) or "none"


def describe_red(red: dict | None) -> str:
    if not red:
        return "not recorded"
    state_text = "uncommitted source changes" if red["dirty"] else "source matches the commit"
    return f"commit {red['commit'][:8]} ({state_text})"


def render(info: dict) -> str:
    gate_text = ", ".join(f"{n} {g['result']}" for n, g in info["gates"].items()) or "none yet"
    lock_text = ", ".join(f"{s}: {n} file(s)" for s, n in sorted(info["locks"].items())) or "none"
    tokens = sum(c["tokens"] for c in info["cost"].values())
    seconds = sum(c["seconds"] for c in info["cost"].values())
    enforced = info["enforcement"]
    level = enforced["level"] + ("" if enforced["level"] == "hard" else
                                 " (violations are detected, not prevented: " + "; ".join(enforced["reasons"]) + ")")
    lines = [f"{info['feature']} {info['title']}",
             f"phase: {info['phase']}    autonomy: {info['autonomy']['level']}"
             + ("    kind: adopt (describes existing behaviour)" if info.get("kind") == "adopt" else ""),
             f"gates: {gate_text}", f"approvals: {describe_approvals(info['approvals'])}",
             f"assumptions: {len(info['assumptions'])}", f"locks: {lock_text}",
             f"red: {describe_red(info['red'])}", f"enforcement: {level}",
             f"cost: {tokens:,} tokens, {seconds:.1f} s"]
    return "\n".join(lines)


def do_state(args: argparse.Namespace) -> int:
    root = project_root()
    if args.action == "init":
        autonomy = args.autonomy or cfg.load(root).autonomy
        feature_dir = state.create(root, args.feature, args.title, autonomy, "adopt" if args.adopt else "feature")
        print(f"created {args.feature} in {lockfile.relative(root, feature_dir)}")
        return 0
    if args.action == "next-id":
        print(state.next_id(root))
        return 0
    feature_dir = feature_dir_of(root, args.feature)
    info = summary(root, feature_dir, state.load(feature_dir))
    print(json.dumps(info, ensure_ascii=False, indent=2) if args.json else render(info))
    return 0


def run_state(argv: list[str]) -> int:
    args = state_parser().parse_args(argv)
    return guarded("state", lambda: do_state(args))


# -- gate ----------------------------------------------------------------------------------
def parse_details(pairs: list[str]) -> dict[str, str]:
    details = {}
    for pair in pairs:
        key, sep, value = pair.partition("=")
        if not sep or not key.strip():
            raise UsageError(f"--detail expects key=value, got {pair!r}")
        details[key.strip()] = value
    return details


def gate_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="bdd gate", description="Record the result of a machine-checkable gate.")
    ap.add_argument("feature")
    ap.add_argument("name", help="one of: " + ", ".join(state.MACHINE_GATES))
    ap.add_argument("--result", choices=state.RESULTS, required=True)
    ap.add_argument("--detail", action="append", default=[], metavar="KEY=VALUE", help="evidence to keep with the result")
    ap.add_argument("--record-red", action="store_true",
                    help="bind gate: also record the git commit and production-source digest of this moment")
    return ap


def do_gate(args: argparse.Namespace) -> int:
    root = project_root()
    feature_dir = feature_dir_of(root, args.feature)
    if args.record_red and args.name != "bind":
        raise UsageError("--record-red belongs to the bind gate")
    red = redrecord.capture(root, cfg.load(root).test_dirs) if args.record_red else None
    data = gates.record_gate(root, feature_dir, args.name, args.result, parse_details(args.detail), red)
    print(f"{args.feature}: {args.name} {args.result}; phase is now {data['phase']}")
    return 0


def run_gate(argv: list[str]) -> int:
    args = gate_parser().parse_intermixed_args(argv)
    return guarded("gate", lambda: do_gate(args))


# -- assume / cost / mode ------------------------------------------------------------------
def run_assume(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="bdd assume", description="Record a decision made on the user's behalf.")
    ap.add_argument("feature")
    ap.add_argument("--text", required=True, help="what was assumed")
    ap.add_argument("--rationale", required=True, help="why this answer was chosen")
    ap.add_argument("--alt", action="append", default=[], help="an alternative that was rejected (repeatable)")
    args = ap.parse_args(argv)

    def action() -> int:
        feature_dir = feature_dir_of(project_root(), args.feature)
        print(state.add_assumption(feature_dir, args.text, args.rationale, args.alt))
        return 0
    return guarded("assume", action)


def run_cost(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="bdd cost", description="Add tokens and time spent in a phase, or collect what the agents "
                                 "that finished cost (their time from the hook, their tokens from their own transcripts).")
    ap.add_argument("feature")
    ap.add_argument("--phase", choices=state.PHASES, help="the phase; with --collect, only for agents the hook could not place")
    ap.add_argument("--tokens", type=int, default=0)
    ap.add_argument("--seconds", type=float, default=0.0)
    ap.add_argument("--collect", action="store_true", help="record the agents that finished and are not recorded yet")
    args = ap.parse_args(argv)
    if args.collect and (args.tokens or args.seconds):
        ap.error("--collect takes the figures from the agents' transcripts; do not give --tokens or --seconds")
    if not args.collect and not args.phase:
        ap.error("--phase is required unless --collect is given")

    def action() -> int:
        if args.collect:
            lines = agentcost.collect(project_root(), args.feature, args.phase)
            print("\n".join(lines) if lines else f"{args.feature}: no finished agent is waiting to be recorded")
            return 0
        feature_dir = feature_dir_of(project_root(), args.feature)
        entry = state.add_cost(feature_dir, args.phase, args.tokens, args.seconds)["cost"][args.phase]
        print(f"{args.feature} {args.phase}: {entry['tokens']:,} tokens, {entry['seconds']:.1f} s in {entry['runs']} run(s)")
        return 0
    return guarded("cost", action)


def run_mode(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="bdd mode", description="Switch a feature's autonomy level, recording why.")
    ap.add_argument("feature")
    ap.add_argument("--switch", required=True, choices=state.AUTONOMY, metavar="LEVEL")
    ap.add_argument("--reason", required=True, help="the user's words that asked for the switch")
    args = ap.parse_args(argv)

    def action() -> int:
        feature_dir = feature_dir_of(project_root(), args.feature)
        data = state.switch_autonomy(feature_dir, args.switch, args.reason)
        print(f"{args.feature}: autonomy is now {data['autonomy']['level']}")
        return 0
    return guarded("mode", action)
