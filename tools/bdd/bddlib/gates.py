"""Recording the result of a machine gate, with the checks that make a pass mean something.

A pass is refused unless what it depends on is true right now:

* the human gates it follows have been validly approved (typed by the person, or automatic /
  self-reported where the autonomy level or the absence of hooks allows it) and what was
  approved has not changed since;
* for ``implement`` and ``verify``: the approved specs and the bound steps are still exactly what
  was locked, and no spec was added after locking;
* for ``verify``: ``implement`` has passed.
"""
from __future__ import annotations

from pathlib import Path

from . import approvals, enforcement, featurefiles, lockfile, state, store, tripwire
from .errors import UsageError

# Human gates that must be validly approved before a machine gate may pass.
APPROVALS_NEEDED = {
    "test-design": ("rules",),
    **{gate: ("rules", "examples") for gate in ("system-map", "refine", "bind", "tasks", "implement", "verify")},
}


def lock_problems(root: Path, feature_dir: Path, feature_id: str) -> list[str]:
    data = lockfile.read_lock(feature_dir, feature_id)
    problems = [f"{scope} is not locked" for scope in lockfile.SCOPES if scope not in data["scopes"]]
    current = [lockfile.relative(root, f) for f in featurefiles.spec_files(root, feature_id)]
    return problems + [str(v) for v in lockfile.check(root, feature_dir, feature_id, lockfile.SCOPES, current)]


def gate_problems(root: Path, feature_dir: Path, data: dict, gate: str) -> list[str]:
    """Reasons a *passing* result may not be recorded yet (empty list = fine)."""
    problems: list[str] = []
    for human_gate in APPROVALS_NEEDED.get(gate, ()):
        problems += approvals.effective_problems(root, data, human_gate)
    if gate in ("implement", "verify"):
        problems += lock_problems(root, feature_dir, data["feature"])
        problems += [f"integrity violation #{v['id']} is open: {tripwire.describe(v)}" for v in tripwire.open_violations(root)]
    if gate == "verify" and data["gates"].get("implement", {}).get("result") != "pass":
        problems.append("the implement gate has not passed")
    return problems


def record_gate(root: Path, feature_dir: Path, name: str, result: str, detail: dict[str, str],
                red: dict | None = None) -> dict:
    if name in state.HUMAN_GATES:
        raise UsageError(f"'{name}' is a human gate: only the person can approve it, by typing "
                         f"/greenlight:approve <feature> {name}")
    if name not in state.MACHINE_GATES:
        raise UsageError(f"unknown gate '{name}'; machine gates are: {', '.join(state.MACHINE_GATES)}")
    if result not in state.RESULTS:
        raise UsageError(f"result must be one of {', '.join(state.RESULTS)}")
    if red is not None and name != "bind":
        raise UsageError("--record-red belongs to the bind gate")
    state.observe_hooks(root, feature_dir)          # remember, one way, that hooks have run here
    if result == "pass":
        approvals.verify_origins(feature_dir)       # before the state lock is taken: it is not re-entrant

    def mutate(current: dict) -> None:
        if result == "pass":
            problems = gate_problems(root, feature_dir, current, name)
            if problems:
                raise UsageError(f"cannot record {name}=pass: " + "; ".join(problems))
        current["gates"][name] = {"result": result, "at": store.utc_now(), "detail": detail,
                                  "session": enforcement.current_session()}
        if red is not None:
            current["red"] = red
        if result == "pass":
            state.advance_phase(current, name)

    return state.update(feature_dir, mutate)
