"""Per-feature pipeline state: ``.bdd/features/FEAT-n-slug/state.json``.

The state records how far a feature has got, which gates passed (and what proved it), the
assumptions an autonomous run made, what each phase cost, and the git position at which the
tests were proven red. Human approvals live in the same file but are written only by the
approve hook (they are deliberately not part of this module's write API).
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from . import featurefiles, lockfile, store
from .errors import UsageError

STATE_FILE = "state.json"
PHASES = ("discover", "specify", "test-design", "examples", "system-map", "refine", "bind",
          "tasks", "implement", "verify", "done")
HUMAN_GATES = ("rules", "examples")
MACHINE_GATES = ("discover", "test-design", "system-map", "refine", "bind", "tasks", "implement", "verify")
# Phase a feature moves to once the named gate has passed.
GATE_NEXT = {"discover": "specify", "rules": "test-design", "test-design": "examples",
             "examples": "system-map", "system-map": "refine", "refine": "bind", "bind": "tasks",
             "tasks": "implement", "implement": "verify", "verify": "done"}
AUTONOMY = ("guided", "standard", "auto", "autopilot")
RESULTS = ("pass", "fail")


def slug(title: str) -> str:
    """ASCII, lower-case, hyphenated folder suffix for a feature title ('feature' if nothing is left)."""
    ascii_text = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")[:40] or "feature"


def path_of(feature_dir: Path) -> Path:
    return feature_dir / STATE_FILE


def new_state(feature_id: str, title: str, autonomy: str) -> dict:
    return {"schema": store.SCHEMA, "feature": feature_id, "title": title, "created_at": store.utc_now(),
            "phase": PHASES[0], "autonomy": {"level": autonomy, "switches": []}, "gates": {},
            "approvals": [], "assumptions": [], "cost": {}, "red": None}


def create(root: Path, feature_id: str, title: str, autonomy: str) -> Path:
    store.parse_feature_id(feature_id)
    if autonomy not in AUTONOMY:
        raise UsageError(f"autonomy must be one of {', '.join(AUTONOMY)}")
    if not title.strip():
        raise UsageError("a feature needs a title")
    base = store.features_dir(root)
    existing = [p.name for p in base.glob(feature_id + "*") if p.name == feature_id or p.name.startswith(feature_id + "-")]
    if existing:
        raise UsageError(f"{feature_id} already exists ({existing[0]})")
    feature_dir = base / f"{feature_id}-{slug(title)}"
    store.write_json(path_of(feature_dir), new_state(feature_id, title.strip(), autonomy))
    return feature_dir


def _missing(feature_dir: Path) -> UsageError:
    return UsageError(f"{feature_dir.name} has no {STATE_FILE}; create the feature with `bdd state init`")


def load(feature_dir: Path) -> dict:
    try:
        return store.read_json(path_of(feature_dir), "state file")
    except FileNotFoundError:
        raise _missing(feature_dir) from None


def _update(feature_dir: Path, mutate) -> dict:
    """Apply ``mutate`` to the feature's state under the file lock."""
    try:
        return store.update_json(path_of(feature_dir), "state file", mutate)
    except FileNotFoundError:
        raise _missing(feature_dir) from None


def _advance(state: dict, gate: str) -> None:
    target = GATE_NEXT.get(gate)
    if target and PHASES.index(target) > PHASES.index(state["phase"]):
        state["phase"] = target


def gate_problems(root: Path, feature_dir: Path, state: dict, gate: str) -> list[str]:
    """Reasons a *passing* result may not be recorded yet (empty list = fine).

    These are the machine-enforced gates: implementation is only done if the approved specs and
    the bound steps are still exactly what was locked, and a feature is only verified after
    implementation passed."""
    problems: list[str] = []
    if gate in ("implement", "verify"):
        feature_id = state["feature"]
        data = lockfile.read_lock(feature_dir, feature_id)
        problems += [f"{scope} is not locked" for scope in lockfile.SCOPES if scope not in data["scopes"]]
        current = [lockfile.relative(root, f) for f in featurefiles.spec_files(root, feature_id)]
        problems += [str(v) for v in lockfile.check(root, feature_dir, feature_id, lockfile.SCOPES, current)]
    if gate == "verify" and state["gates"].get("implement", {}).get("result") != "pass":
        problems.append("the implement gate has not passed")
    return problems


def record_gate(root: Path, feature_dir: Path, name: str, result: str, detail: dict[str, str],
                red: dict | None = None) -> dict:
    if name in HUMAN_GATES:
        raise UsageError(f"'{name}' is a human gate: only the person can approve it, by typing "
                         f"/greenlight:approve <feature> {name}")
    if name not in MACHINE_GATES:
        raise UsageError(f"unknown gate '{name}'; machine gates are: {', '.join(MACHINE_GATES)}")
    if result not in RESULTS:
        raise UsageError(f"result must be one of {', '.join(RESULTS)}")
    if red is not None and name != "bind":
        raise UsageError("--record-red belongs to the bind gate")

    def mutate(state: dict) -> None:
        if result == "pass":
            problems = gate_problems(root, feature_dir, state, name)
            if problems:
                raise UsageError(f"cannot record {name}=pass: " + "; ".join(problems))
        state["gates"][name] = {"result": result, "at": store.utc_now(), "detail": detail}
        if red is not None:
            state["red"] = red
        if result == "pass":
            _advance(state, name)

    return _update(feature_dir, mutate)


def add_assumption(feature_dir: Path, text: str, rationale: str, alternatives: list[str]) -> str:
    if not text.strip() or not rationale.strip():
        raise UsageError("an assumption needs both text and a rationale")
    created: list[str] = []

    def mutate(state: dict) -> None:
        digits = state["feature"].split("-", 1)[1]
        assumption_id = f"A-{digits}.{len(state['assumptions']) + 1}"
        state["assumptions"].append({"id": assumption_id, "text": text.strip(), "rationale": rationale.strip(),
                                     "alternatives": alternatives, "at": store.utc_now()})
        created.append(assumption_id)

    _update(feature_dir, mutate)
    return created[0]


def add_cost(feature_dir: Path, phase: str, tokens: int, seconds: float) -> dict:
    if phase not in PHASES:
        raise UsageError(f"unknown phase '{phase}'; phases are: {', '.join(PHASES)}")
    if tokens < 0 or seconds < 0:
        raise UsageError("tokens and seconds cannot be negative")

    def mutate(state: dict) -> None:
        entry = state["cost"].setdefault(phase, {"tokens": 0, "seconds": 0.0, "runs": 0})
        entry["tokens"] += tokens
        entry["seconds"] = round(entry["seconds"] + seconds, 3)
        entry["runs"] += 1

    return _update(feature_dir, mutate)


def switch_autonomy(feature_dir: Path, level: str, reason: str) -> dict:
    if level not in AUTONOMY:
        raise UsageError(f"autonomy must be one of {', '.join(AUTONOMY)}")
    if not reason.strip():
        raise UsageError("a mode switch needs --reason: quote what the user said")

    def mutate(state: dict) -> None:
        current = state["autonomy"]["level"]
        if current == level:
            raise UsageError(f"autonomy is already {level}")
        state["autonomy"]["switches"].append({"from": current, "to": level, "reason": reason.strip(),
                                              "at": store.utc_now(), "phase": state["phase"]})
        state["autonomy"]["level"] = level

    return _update(feature_dir, mutate)
