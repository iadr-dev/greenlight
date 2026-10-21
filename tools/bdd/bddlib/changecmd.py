"""`bdd change`: reopen a feature at an earlier phase because something that was approved has to change.

    bdd change FEAT-007 --reopen examples --reason "the threshold is now 500, not 1000"

What it does, in one step, so nothing is left half-undone:

* releases the locks that guard what is being reopened (the reason is kept in the lock history);
* revokes the human approvals that no longer stand (they have to be given again by the person);
* forgets the gate results from the reopened phase onward; when the binding is reopened, the recorded red moves to
  ``red_history`` (with a copy of its kept run) instead of being dropped, because it stays the point the code is
  measured from;
* moves the feature back to that phase and writes the change into ``state.json``.

It edits nothing in the feature files, the steps or the code: the phase agents do that, and the gates then
stand again only when the approvals, the red and the locks have been redone. If the production code was already
written, the rebound tests prove their red with ``bdd run FEAT-n --against-red`` (see ``againstred``).
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from . import approvals, lockfile, runner, state, store
from .errors import UsageError
from .statecmd import guarded, project_root

REOPENABLE = state.PHASES[:-1]                       # everything but "done"
SPEC_FROM, BIND_FROM = "examples", "bind"            # reopening at or before these phases releases the locks


def index(phase: str) -> int:
    return state.PHASES.index(phase)


def locks_to_release(phase: str) -> list[str]:
    """Reopening the specification releases both locks; reopening the system map, vocabulary or binding releases
    the bound steps; later phases leave them alone."""
    if index(phase) <= index(SPEC_FROM):
        return ["spec", "bind"]
    return ["bind"] if index(phase) <= index(BIND_FROM) else []


def approvals_to_revoke(phase: str) -> list[str]:
    if index(phase) <= index("specify"):
        return ["rules", "examples"]
    return ["examples"] if index(phase) <= index(SPEC_FROM) else []


def keep_red_copy(root: Path, feature: str, kept: dict | None, change_id: int) -> dict | None:
    """Copy the kept red run next to itself as ``red-<change>.json`` so the evidence the reopened phases replace stays
    on record (the bind gate writes a new ``red.json``). Returns where the copy is, or None if no red run was kept."""
    source = runner.runs_dir(root, feature) / runner.RED
    if not kept or not source.is_file():
        return None
    name = f"red-{change_id}.json"
    shutil.copy2(source, source.with_name(name))
    return {**kept, "file": name}


def reopen(root: Path, feature_dir: Path, phase: str, reason: str) -> dict:
    if phase not in REOPENABLE:
        raise UsageError(f"a feature can be reopened at: {', '.join(REOPENABLE)}")
    if not reason.strip():
        raise UsageError("a change needs a --reason: it is kept with the feature")
    reason = reason.strip()
    data = state.load(feature_dir)
    feature = data["feature"]
    held = lockfile.read_lock(feature_dir, feature)["scopes"]
    released = [scope for scope in locks_to_release(phase) if scope in held]
    for scope in released:
        lockfile.unlock(feature_dir, feature, scope, f"change: {reason}")
    removed: list[str] = []
    revoked: list[str] = []

    def mutate(current: dict) -> None:
        for gate in state.MACHINE_GATES:
            if index(gate) >= index(phase) and gate in current["gates"]:
                del current["gates"][gate]
                removed.append(gate)
        for gate in approvals_to_revoke(phase):
            last = approvals._last(current, gate, "approve")
            if last is not None and not last.get("revoked"):
                last["revoked"] = reason
                revoked.append(gate)
        change_id = len(current.setdefault("changes", [])) + 1
        if index(phase) <= index(BIND_FROM) and current.get("red"):
            current.setdefault("red_history", []).append(
                {"red": current["red"], "red_run": keep_red_copy(root, feature, current.get("red_run"), change_id),
                 "change": change_id})
            current["red"] = None
        entry = {"id": change_id, "at": store.utc_now(), "reopened": phase,
                 "from": current["phase"], "reason": reason, "unlocked": released, "revoked": revoked,
                 "gates_removed": removed}
        current["changes"].append(entry)
        current["phase"] = phase

    return state.update(feature_dir, mutate)["changes"][-1]


def describe(entry: dict, feature: str) -> str:
    lines = [f"{feature}: reopened at {entry['reopened']} (was {entry['from']}): {entry['reason']}",
             f"  unlocked: {', '.join(entry['unlocked']) or 'nothing'}",
             f"  approvals revoked: {', '.join(entry['revoked']) or 'none'}",
             f"  gate results forgotten: {', '.join(entry['gates_removed']) or 'none'}"]
    return "\n".join(lines)


def run(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="bdd change", description="Reopen a feature at an earlier phase.")
    ap.add_argument("feature", help="feature id, e.g. FEAT-007")
    ap.add_argument("--reopen", required=True, choices=REOPENABLE, metavar="PHASE",
                    help=f"the first phase to redo ({', '.join(REOPENABLE)})")
    ap.add_argument("--reason", required=True, help="why (kept in the feature's history and the lock history)")
    args = ap.parse_args(argv)

    def action() -> int:
        root = project_root()
        entry = reopen(root, store.find_feature_dir(root, args.feature), args.reopen, args.reason)
        print(describe(entry, args.feature))
        return 0

    return guarded("change", action)


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))
