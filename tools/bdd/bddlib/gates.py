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

import json
from pathlib import Path

from . import adopt, approvals, classify, design, enforcement, featurefiles, lockfile, mutation, quality, runner, state, store, tripwire
from . import config as cfg
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
    bound = lockfile.bound_files(root)
    return problems + [str(v) for v in lockfile.check(root, feature_dir, feature_id, lockfile.SCOPES, current, bound)]


RUN_EXPECTED = {"bind": "red", "verify": "green"}


def run_problems(root: Path, feature_id: str, gate: str, raw: bytes | None) -> list[str]:
    """When the adapter has a run command, ``bind`` needs a valid red and ``verify`` a green, from a
    run that ``bdd run`` recorded against the files as they are now."""
    config = cfg.load(root)
    if gate not in RUN_EXPECTED or not config.runs:
        return []
    expect = RUN_EXPECTED[gate]
    if raw is None:
        return [f"{feature_id} has not been run yet; run `bdd run {feature_id}` first"]
    try:
        record = json.loads(raw)
        if record.get("inputs") != runner.inputs_digest(root, feature_id):
            return [f"the recorded run is out of date: the feature files or steps changed since `bdd run {feature_id}`"]
        if any("{project_python}" in r.by_tag for r in config.runs) and record.get("interpreter") != runner.interpreter_identity(root):
            return ["the recorded run used another interpreter than the project resolves to now; run it again with "
                    "`bdd run` from the project's own environment"]
        verdict = classify.classify_run(record, classify.feature_scenarios(root, feature_id), list(config.runs))[expect]
    except (UsageError, ValueError) as exc:
        return [str(exc)]
    return [] if verdict["valid"] else [f"the recorded run is not a valid {expect}: " + "; ".join(verdict["problems"])]


def gate_problems(root: Path, feature_dir: Path, data: dict, gate: str, raw: bytes | None = None) -> list[str]:
    """Reasons a *passing* result may not be recorded yet (empty list = fine)."""
    problems: list[str] = []
    for human_gate in APPROVALS_NEEDED.get(gate, ()):
        problems += approvals.effective_problems(root, data, human_gate)
    problems += run_problems(root, data["feature"], gate, raw)
    if gate == "system-map" and (feature_dir / design.DESIGN_FILE).is_file():
        problems += [str(issue) for issue in design.lint(feature_dir)]
    if gate in ("implement", "verify"):
        problems += lock_problems(root, feature_dir, data["feature"])
        problems += [f"integrity violation #{v['id']} is open: {tripwire.describe(v)}" for v in tripwire.open_violations(root)]
    if data.get("kind") == "adopt" and gate in adopt.CHECKED_GATES:
        problems += adopt.problems(root, data)
        if gate == "implement":                     # there is no implementation to wait for: the existing code must already pass
            raw = runner.latest_bytes(root, data["feature"]) if cfg.load(root).runs else None
            problems += run_problems(root, data["feature"], "verify", raw)
    if gate in ("implement", "verify") and data.get("kind") != "adopt":      # the code of an adoption already exists: not judged
        problems += quality.problems(root, data["feature"])
    if gate == "verify":
        if data.get("kind") != "adopt":             # an adopted feature has no red to measure a change from
            problems += mutation.problems(root, data["feature"])
        if data["gates"].get("implement", {}).get("result") != "pass":
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
        raw = None
        if result == "pass" and name in RUN_EXPECTED and cfg.load(root).runs:
            raw = runner.latest_bytes(root, current["feature"])          # read once: checked and kept are the same bytes
        if result == "pass":
            problems = gate_problems(root, feature_dir, current, name, raw)
            if problems:
                raise UsageError(f"cannot record {name}=pass: " + "; ".join(problems))
        current["gates"][name] = {"result": result, "at": store.utc_now(), "detail": detail,
                                  "session": enforcement.current_session()}
        if red is not None:
            current["red"] = red
        if name == "bind" and result == "pass" and raw is not None:
            current["red_run"] = runner.keep_red(root, current["feature"], raw)
        if result == "pass":
            state.advance_phase(current, name)

    return state.update(feature_dir, mutate)
