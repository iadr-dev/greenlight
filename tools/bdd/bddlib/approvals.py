"""Human approvals of the two human gates, ``rules`` and ``examples``.

An approval is a record in the feature's ``state.json``:

    gate        rules | examples
    decision    approve | reject
    grade       hook            typed by the person, recorded by the UserPromptSubmit hook
                self-reported   recorded by a skill from the person's answer (sessions without hooks)
                auto            recorded by the orchestrator under the auto / autopilot levels
    origin      pending | human | headless | invalid | unverifiable | self-reported | auto
    artifacts   SHA-256 of what was approved (rules.md, or the feature files)

A hook-grade approval starts as ``pending``: when the hook runs, the person's prompt is not yet in
the session transcript, so who wrote it cannot be checked yet. ``verify_origins`` checks it
afterwards against the transcript, and the gates refuse an approval that is not verified.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import config as cfg
from . import claudepaths, enforcement, featurefiles, lockfile, state, store
from .errors import UsageError

GATES = state.HUMAN_GATES
DECISIONS = ("approve", "reject")
GRADES = ("hook", "self-reported", "auto")
PREREQUISITE_GATES = {"rules": ("discover",), "examples": ("test-design",)}
PHASE_OF = {"rules": "specify", "examples": "examples"}
PENDING_TIMEOUT = timedelta(minutes=10)
TRANSCRIPT_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\.jsonl")


# -- what is being approved ----------------------------------------------------------------
def artifact_hashes(root: Path, feature_dir: Path, feature_id: str, gate: str) -> dict[str, str]:
    """Digests of the files this approval covers; refuses if there is nothing to approve."""
    if gate == "rules":
        rules = feature_dir / "rules.md"
        if not rules.is_file():
            raise UsageError(f"there is nothing to approve: {lockfile.relative(root, rules)} does not exist yet")
        files = [rules]
    else:
        files = featurefiles.spec_files(root, feature_id)
        if not files:
            raise UsageError(f"there is nothing to approve: no .feature file is tagged @{feature_id}")
    return {lockfile.relative(root, f): lockfile.file_digest(f) for f in files}


def prerequisite_problems(data: dict, gate: str) -> list[str]:
    problems = [f"the {g} gate has not passed yet" for g in PREREQUISITE_GATES[gate]
                if data["gates"].get(g, {}).get("result") != "pass"]
    if gate == "examples" and not _last(data, "rules", "approve"):
        problems.append("the rules must be approved first")
    return problems


def _last(data: dict, gate: str, decision: str | None = None) -> dict | None:
    """The most recent approval record for ``gate`` (only if it has the given decision)."""
    records = [a for a in data["approvals"] if a["gate"] == gate]
    last = records[-1] if records else None
    return last if last and (decision is None or last["decision"] == decision) else None


# -- recording -----------------------------------------------------------------------------
def ensure_spec_locked(root: Path, feature_dir: Path, feature_id: str, files: dict[str, str]) -> None:
    """Lock the approved feature files (or confirm an existing lock still matches them)."""
    held = lockfile.read_lock(feature_dir, feature_id)["scopes"].get("spec")
    if held is None:
        lockfile.lock(root, feature_dir, feature_id, "spec", [root / rel for rel in files])
    elif held["files"] != files:
        raise UsageError("the feature files differ from the spec lock; unlock the spec with a reason "
                         "(bdd unlock) before approving the changed examples")


def record(root: Path, feature_dir: Path, gate: str, decision: str, grade: str, *, session: str | None = None,
           prompt_id: str | None = None, transcript_path: str | None = None, reason: str = "") -> dict:
    """Append an approval (or a rejection) and apply its effects: phase change and, for approved
    examples, the spec lock. Returns the new record."""
    if gate not in GATES:
        raise UsageError(f"only the human gates can be approved: {', '.join(GATES)}")
    if decision not in DECISIONS or grade not in GRADES:
        raise UsageError(f"decision must be one of {', '.join(DECISIONS)} and grade one of {', '.join(GRADES)}")
    state.observe_hooks(root, feature_dir)          # remember, one way, that hooks have run here
    data = state.load(feature_dir)
    feature_id = data["feature"]
    check_grade(root, data, grade)
    artifacts: dict[str, str] = {}
    if decision == "approve":
        problems = prerequisite_problems(data, gate)
        if problems:
            raise UsageError(f"cannot approve {gate}: " + "; ".join(problems))
        artifacts = artifact_hashes(root, feature_dir, feature_id, gate)
        if gate == "examples":
            ensure_spec_locked(root, feature_dir, feature_id, artifacts)
    elif gate == "examples" and "spec" in lockfile.read_lock(feature_dir, feature_id)["scopes"]:
        lockfile.unlock(feature_dir, feature_id, "spec", f"examples rejected: {reason or 'no reason given'}")
    entry = {"gate": gate, "decision": decision, "grade": grade, "at": store.utc_now(), "reason": reason,
             "origin": {"hook": "pending"}.get(grade, grade), "artifacts": artifacts, "session": session,
             "prompt_id": prompt_id, "transcript_path": transcript_path,
             "mode": cfg.load(root).enforcement, "hooks_seen": bool(data.get("hooks_seen"))}

    def mutate(current: dict) -> None:
        entry["autonomy"] = current["autonomy"]["level"]
        entry["id"] = len(current["approvals"]) + 1
        current["approvals"].append(entry)
        if decision == "approve":
            state.advance_phase(current, gate)
        else:
            current["phase"] = PHASE_OF[gate]

    state.update(feature_dir, mutate)
    return entry


def self_reported_problem(root: Path, data: dict) -> str | None:
    """Why a self-reported approval cannot be accepted for this feature (None = it can).

    ``hard`` never accepts one. ``soft`` always does: the person who owns the project config says it
    runs without hooks. ``auto`` (the default) accepts one only while hooks have never run in this
    project nor while building this feature, so that turning hooks off cannot be followed by approving
    one's own work. The decision rests on project facts the caller cannot change (a marker the guard
    writes and a flag in the CLI-managed state), not on a session id from the caller's environment."""
    mode = cfg.load(root).enforcement
    if mode == "hard":
        return 'this project requires hard enforcement (.bdd/config.toml: enforcement = "hard")'
    if mode == "auto" and (enforcement.hooks_seen(root) or data.get("hooks_seen")):
        return ("hooks have run in this project, so approvals have to be typed by the person with "
                "/greenlight:approve. If the project really runs without hooks now, the person can set "
                'enforcement = "soft" in .bdd/config.toml')
    return None


def auto_problem(root: Path, level: str | None) -> str | None:
    """Why an automatic approval cannot be accepted (None = it can)."""
    if cfg.load(root).enforcement == "hard":
        return 'hard enforcement (.bdd/config.toml: enforcement = "hard") means a person typed every approval'
    if level not in ("auto", "autopilot"):
        return f"the feature is on autonomy {level}, so the person has to approve it"
    return None


def check_grade(root: Path, data: dict, grade: str) -> None:
    if grade == "auto":
        problem, label = auto_problem(root, data["autonomy"]["level"]), "an automatic"
    elif grade == "self-reported":
        problem, label = self_reported_problem(root, data), "a self-reported"
    else:
        return
    if problem:
        raise UsageError(f"{label} approval is not accepted: {problem}")


# -- origin verification -------------------------------------------------------------------
def find_transcript(transcript_path: str) -> Path | None:
    """The transcript file named by ``transcript_path``, looked up *inside* the Claude Code projects folders.

    Only the file name is taken from the recorded path, and only if it is a plain ``<session>.jsonl``;
    the folders searched are our own (``claudepaths.transcript_roots``), so a forged path cannot make
    this read anything else."""
    name = Path(transcript_path.replace("\\", "/")).name
    if not TRANSCRIPT_NAME.fullmatch(name):
        raise UsageError(f"not a session transcript file name: {name!r}")
    for root in claudepaths.transcript_roots():
        folders = [root, *(p for p in sorted(root.iterdir()) if p.is_dir())] if root.is_dir() else []
        for folder in folders:
            if (folder / name).is_file():
                return folder / name
    return None


def prompt_entries(transcript_path: str, prompt_id: str) -> list[dict]:
    """Every real (non-meta) user entry of the transcript carrying ``prompt_id``.

    Normally exactly one. They are all kept so that a second entry with the same id but another origin
    makes the approval invalid instead of being skipped."""
    path = find_transcript(transcript_path)
    if path is None:
        return []
    found = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if entry.get("type") == "user" and entry.get("promptId") == prompt_id and not entry.get("isMeta"):
            found.append(entry)
    return found


def classify_all(entries: list[dict]) -> tuple[str, str]:
    """One verdict for all entries of a prompt: they must agree, and an invalid one wins."""
    results = [classify(entry) for entry in entries]
    origins = {origin for origin, _ in results}
    evidence = "; ".join(text for _, text in results)
    if "invalid" in origins or len(origins) > 1:
        return "invalid", evidence + ("" if "invalid" in origins else " (entries for this prompt disagree)")
    return origins.pop(), evidence


def classify(entry: dict) -> tuple[str, str]:
    """Who produced this prompt, from Claude Code's own origin fields: (origin, evidence)."""
    kind = (entry.get("origin") or {}).get("kind")
    source, turn = entry.get("promptSource"), entry.get("turnOrigin")
    evidence = f"origin.kind={kind} turnOrigin={turn} promptSource={source}"
    if kind == "human" and turn in (None, "human") and source in (None, "typed"):
        return "human", evidence
    if turn == "sdk" or source == "sdk":
        return "headless", evidence
    if kind is None and turn is None and source is None:
        return "unverifiable", evidence
    return "invalid", evidence


def _age_exceeds_timeout(at: str) -> bool:
    try:
        return datetime.now(timezone.utc) - datetime.fromisoformat(at) > PENDING_TIMEOUT
    except ValueError:
        return True


def verdict_for(approval: dict) -> tuple[str, str] | None:
    """New (origin, evidence) for a pending hook approval, or None if it still cannot be decided."""
    if not approval.get("transcript_path") or not approval.get("prompt_id"):
        return "unverifiable", "the hook did not record where the prompt came from"
    try:
        entries = prompt_entries(approval["transcript_path"], approval["prompt_id"])
    except UsageError as exc:
        return "unverifiable", str(exc)
    if not entries:
        return ("unverifiable", "the prompt never appeared in the transcript") if _age_exceeds_timeout(approval["at"]) else None
    return classify_all(entries)


def verify_origins(feature_dir: Path) -> int:
    """Check every pending hook approval against the transcript. Returns how many were decided."""
    pending = [a for a in state.load(feature_dir)["approvals"] if a["grade"] == "hook" and a["origin"] == "pending"]
    verdicts = {a["id"]: verdict_for(a) for a in pending}
    verdicts = {i: v for i, v in verdicts.items() if v}
    if not verdicts:
        return 0

    def mutate(current: dict) -> None:
        for approval in current["approvals"]:
            if approval["id"] in verdicts and approval["origin"] == "pending":
                approval["origin"], approval["evidence"] = verdicts[approval["id"]]

    state.update(feature_dir, mutate)
    return len(verdicts)


# -- are the human gates satisfied? -------------------------------------------------------
def effective_problems(root: Path, data: dict, gate: str) -> list[str]:
    """Why ``gate`` is not validly approved right now (empty list = it is)."""
    last = _last(data, gate)
    if last is None:
        return [f"{gate} has not been approved"]
    if last["decision"] != "approve":
        return [f"{gate} was rejected" + (f": {last['reason']}" if last.get("reason") else "")]
    problems = grade_problems(root, data, gate, last)
    for rel, digest in last["artifacts"].items():
        target = root / rel
        if not target.is_file() or lockfile.file_digest(target) != digest:
            problems.append(f"{rel} changed after the {gate} approval; it has to be approved again")
    return problems


def grade_problems(root: Path, data: dict, gate: str, last: dict) -> list[str]:
    grade, origin = last["grade"], last["origin"]
    if grade in ("auto", "self-reported"):
        problem = auto_problem(root, last.get("autonomy")) if grade == "auto" else self_reported_problem(root, data)
        label = "automatic" if grade == "auto" else "self-reported"
        return [f"the {gate} approval is {label}, which is not accepted: {problem}"] if problem else []
    allowed = ("human", "headless") if cfg.load(root).allow_headless_approvals else ("human",)
    if origin in allowed:
        return []
    explanations = {
        "pending": "is still waiting for its origin to be verified; run `bdd approve FEAT --verify` in a moment",
        "headless": "was typed into a headless `claude -p` session, which is not accepted unless "
                    "`[approvals] allow_headless = true` is set in .bdd/config.toml",
        "invalid": "was not typed by a person (" + str(last.get("evidence", "unknown origin")) + ")",
        "unverifiable": "could not be verified (" + str(last.get("evidence", "no evidence")) + "); approve it again",
    }
    return [f"the {gate} approval " + explanations.get(origin, f"has origin {origin}")]
