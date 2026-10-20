"""`bdd approve`: record or check human approvals.

    bdd approve FEAT-007 rules --self-reported      the person answered in a session without hooks
    bdd approve FEAT-007 examples --auto            automatic approval (autonomy auto / autopilot)
    bdd approve FEAT-007 rules --self-reported --reject --reason "..."
    bdd approve FEAT-007 --verify                   check pending approvals against the transcript
    bdd approve FEAT-007 --check                    CI: judge the committed record alone (no session needed)

Approvals typed by the person in a session with hooks are recorded by the UserPromptSubmit hook
(``bdd approve --from-hook``, input on stdin), not by the other forms; ``--self-reported`` is
refused once hooks have run in the project.
"""
from __future__ import annotations

import argparse
import sys

from . import approvals, enforcement, state, store
from .errors import StoreError, UsageError
from .statecmd import project_root


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="bdd approve", description="Record or verify human approvals.")
    ap.add_argument("feature", help="feature id, e.g. FEAT-007")
    ap.add_argument("gate", nargs="?", choices=approvals.GATES, help="the human gate")
    how = ap.add_mutually_exclusive_group()
    how.add_argument("--self-reported", action="store_true",
                     help="record the person's answer when no hooks are active in this session")
    how.add_argument("--auto", action="store_true", help="automatic approval under autonomy auto / autopilot")
    how.add_argument("--verify", action="store_true", help="verify pending approvals against the session transcript")
    how.add_argument("--check", action="store_true",
                     help="CI check from the committed record alone: exit 1 unless every required approval is valid")
    ap.add_argument("--reject", action="store_true", help="record a rejection instead of an approval")
    ap.add_argument("--reason", default="", help="why (kept with the record)")
    return ap


def do_verify(feature_dir) -> int:
    decided = approvals.verify_origins(feature_dir)
    data = state.load(feature_dir)
    print(f"{data['feature']}: verified {decided} approval(s)")
    for a in data["approvals"]:
        if a["grade"] in ("hook", "codex"):
            print(f"  #{a['id']} {a['gate']} {a['decision']}: {a['origin']}" + (f" ({a['evidence']})" if a.get("evidence") else ""))
    return 0 if all(a["origin"] != "pending" for a in data["approvals"] if a["grade"] == "hook") else 1


def do_check(root, feature_dir) -> int:
    """Judge the approvals from what is committed (``state.json`` and the approved files), with no session: usable in CI."""
    data = state.load(feature_dir)
    found = approvals.recorded_problems(root, data)
    for gate, problems in found.items():
        last = approvals._last(data, gate)
        how = f"{last['grade']}, origin {last['origin']}" if last else "no record"
        print(f"{data['feature']}: {gate}: {'NOT valid' if problems else 'valid'} ({how})")
        for problem in problems:
            print(f"  - {problem}")
        if last and last["grade"] == "codex":
            print("  - note: typed in Codex, where nothing proves who typed it; a reviewer has to confirm this approval "
                  "(review the committed record and protect the branch)" + (f"\n    {last['evidence']}" if last.get("evidence") else ""))
    return 1 if any(found.values()) else 0


def do_record(root, feature_dir, args: argparse.Namespace) -> int:
    if not args.gate:
        raise UsageError("name the gate: rules or examples")
    if not (args.self_reported or args.auto):
        raise UsageError("choose --self-reported or --auto; approvals typed by the person are recorded by the hook")
    entry = approvals.record(root, feature_dir, args.gate, "reject" if args.reject else "approve",
                             "auto" if args.auto else "self-reported", session=enforcement.current_session(),
                             reason=args.reason)
    data = state.load(feature_dir)
    print(f"{data['feature']}: {args.gate} {'rejected' if args.reject else 'approved'} ({entry['grade']}); "
          f"phase is now {data['phase']}")
    if entry["grade"] == "self-reported":
        print("note: this approval is self-reported, not verified by a hook; the feature's enforcement is reported "
              "as soft and the audit report says so.", file=sys.stderr)
    return 0


def run(argv: list[str]) -> int:
    if argv == ["--from-hook"]:                     # UserPromptSubmit: cheap for every other prompt
        from . import approvehook
        return approvehook.main()
    args = build_parser().parse_args(argv)
    try:
        root = project_root()
        feature_dir = store.find_feature_dir(root, args.feature)
        if args.check:
            return do_check(root, feature_dir)
        return do_verify(feature_dir) if args.verify else do_record(root, feature_dir, args)
    except (UsageError, StoreError) as exc:
        print(f"bdd approve: {exc}", file=sys.stderr)
        return 2
