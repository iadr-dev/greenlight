"""Human approvals of the two human gates, ``rules`` and ``examples``.

An approval is a record in the feature's ``state.json``:

    gate        rules | examples
    decision    approve | reject
    grade       hook            typed by the person, recorded by the UserPromptSubmit hook
                self-reported   recorded by a skill from the person's answer (sessions without hooks)
                auto            recorded by the orchestrator under the auto / autopilot levels
    origin      pending | human | headless | invalid | unverifiable | self-reported | auto
    artifacts   SHA-256 of what was approved (rules.md, or the feature files; for the examples of a feature that spans
                several repositories, each member's feature files and config.toml in a separate ``members`` map)

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
from . import approvalcommand, claudepaths, codexorigin, enforcement, featurefiles, lockfile, state, store, workspace
from .errors import UsageError

GATES = state.HUMAN_GATES
DECISIONS = ("approve", "reject")
GRADES = ("hook", "self-reported", "auto", "codex")
PREREQUISITE_GATES = {"rules": ("discover",), "examples": ("test-design",)}
PHASE_OF = {"rules": "specify", "examples": "examples"}
PENDING_TIMEOUT = timedelta(minutes=10)
TRANSCRIPT_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\.jsonl")


# -- what is being approved ----------------------------------------------------------------
def artifact_hashes(root: Path, feature_dir: Path, feature_id: str, gate: str) -> dict[str, str]:
    """Digests of the files of this repository that the approval covers; refuses if there is nothing to approve."""
    if gate == "rules":
        rules = feature_dir / "rules.md"
        if not rules.is_file():
            raise UsageError(f"there is nothing to approve: {lockfile.relative(root, rules)} does not exist yet")
        files = [rules]
    else:
        files = featurefiles.spec_files(root, feature_id)
    return {lockfile.relative(root, f): lockfile.file_digest(f) for f in files}


def member_artifacts(root: Path, feature_id: str) -> dict[str, dict[str, str]]:
    """What each other repository of a workspace contributes to the examples: member name -> {path inside the member ->
    digest} of its feature files for the feature and its ``config.toml``. They are kept apart from this repository's own
    artifacts (a map of their own in the approval), so no name of one can stand for a file of the other. Approving the
    examples covers them, so a member's specs cannot be unlocked, edited and locked again, added to, or its configuration
    changed, without the person approving again. A member that cannot be read here cannot be approved."""
    found: dict[str, dict[str, str]] = {}
    for member in cfg.load(root).workspace:
        why = workspace.unobserved(member)
        if why:
            raise UsageError(f"cannot approve the examples: {member.name} is not observed here ({why})")
        files = [member.path / cfg.BDD_DIR / "config.toml", *featurefiles.spec_files(member.path, feature_id)]
        found[member.name] = {lockfile.relative(member.path, f): lockfile.file_digest(f) for f in files}
    return found


def member_problems(root: Path, feature_id: str, recorded: dict[str, dict[str, str]]) -> list[str]:
    """How the members' contribution to the examples differs from what was approved: changed, added or removed files, a
    member that joined or left the workspace, or one that cannot be read here."""
    try:
        current = member_artifacts(root, feature_id)
    except UsageError as exc:
        return [str(exc)]
    again = "after the examples approval; it has to be approved again"
    problems: list[str] = []
    for name, files in current.items():
        old = recorded.get(name)
        if old is None:
            problems.append(f"{name} joined the workspace {again}")
            continue
        for rel, digest in files.items():
            if rel not in old:
                problems.append(f"{name}:{rel} was added {again}")
            elif old[rel] != digest:
                problems.append(f"{name}:{rel} changed {again}")
        problems += [f"{name}:{rel} was removed {again}" for rel in old if rel not in files]
    problems += [f"{name} left the workspace {again}" for name in recorded if name not in current]
    return problems


def prerequisite_problems(data: dict, gate: str) -> list[str]:
    problems = [f"the {g} gate has not passed yet" for g in PREREQUISITE_GATES[gate]
                if data["gates"].get(g, {}).get("result") != "pass"]
    rules = _last(data, "rules", "approve")
    if gate == "examples" and (not rules or rules.get("revoked")):
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
           prompt_id: str | None = None, transcript_path: str | None = None, reason: str = "",
           source: dict | None = None) -> dict:
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
    members: dict[str, dict[str, str]] = {}
    if decision == "approve":
        problems = prerequisite_problems(data, gate)
        if problems:
            raise UsageError(f"cannot approve {gate}: " + "; ".join(problems))
        artifacts = artifact_hashes(root, feature_dir, feature_id, gate)
        if gate == "examples":
            members = member_artifacts(root, feature_id)
            if not artifacts and not any(rel.endswith(".feature") for files in members.values() for rel in files):
                raise UsageError(f"there is nothing to approve: no .feature file is tagged @{feature_id}")
            ensure_spec_locked(root, feature_dir, feature_id, artifacts)
    elif gate == "examples" and "spec" in lockfile.read_lock(feature_dir, feature_id)["scopes"]:
        lockfile.unlock(feature_dir, feature_id, "spec", f"examples rejected: {reason or 'no reason given'}")
    entry = {"gate": gate, "decision": decision, "grade": grade, "at": store.utc_now(), "reason": reason,
             "origin": {"hook": "pending", "codex": "codex-unverified"}.get(grade, grade), "artifacts": artifacts, "members": members,
             "session": session,
             "prompt_id": prompt_id, "transcript_path": transcript_path, "source": source,
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


CODEX_LABEL = "codex, not provenance-verified"
CI_CODEX_MESSAGE = ("the approval was typed in Codex, where nothing proves who typed it, so the check cannot accept it by itself: "
                    "a reviewer has to accept it (pull request review and branch protection), and the project records that by "
                    "committing `[approvals] accept_codex = true` in .bdd/config.toml")


def provenance(approval: dict) -> str:
    """How an approval got here, in the words status, the report and the pull request description use."""
    return CODEX_LABEL if approval["grade"] == "codex" else str(approval["origin"])


def codex_problem(root: Path) -> str | None:
    """Why an approval typed in Codex cannot be accepted (None = it can).

    Codex's hook is an ordinary command and the agent runs as the person, so nothing proves who typed it. It is therefore never
    accepted on its own: ``hard`` refuses it outright, and every other mode needs the person's opt-in, ``[approvals]
    accept_codex = true`` in ``.bdd/config.toml`` (guard-protected), whether hooks have run or not. Accepted, it is labelled
    "codex, not provenance-verified" everywhere."""
    config = cfg.load(root)
    if config.enforcement == "hard":
        return ('this project requires hard enforcement (.bdd/config.toml: enforcement = "hard"), and an approval typed in '
                "Codex is not provenance-verified: the agent and the person are the same user there")
    if not config.accept_codex:
        return ("an approval typed in Codex is not provenance-verified (the agent and the person are the same user there). If "
                "the person accepts that, they set `[approvals] accept_codex = true` in .bdd/config.toml")
    return None


def check_grade(root: Path, data: dict, grade: str) -> None:
    if grade == "auto":
        problem, label = auto_problem(root, data["autonomy"]["level"]), "an automatic"
    elif grade == "self-reported":
        problem, label = self_reported_problem(root, data), "a self-reported"
    elif grade == "codex":
        problem, label = codex_problem(root), "a Codex"
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


def is_tool_result(entry: dict) -> bool:
    """Claude Code records each tool result as a user entry that shares the prompt's id; it is not a prompt."""
    content = (entry.get("message") or {}).get("content")
    return isinstance(content, list) and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content)


def prompt_entries(transcript_path: str, prompt_id: str) -> list[dict]:
    """Every real user entry of the transcript carrying ``prompt_id``: not meta, not a tool result.

    Normally exactly one. They are all kept so that a second prompt entry with the same id but another
    origin makes the approval invalid instead of being skipped."""
    path = find_transcript(transcript_path)
    if path is None:
        return []
    found = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if entry.get("type") == "user" and entry.get("promptId") == prompt_id:
            if not entry.get("isMeta") and not is_tool_result(entry):
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


def says_something_else(entries: list[dict], feature: str, approval: dict) -> bool:
    """Is any entry of the prompt not exactly the approval that was recorded?

    Without this an approval could borrow the prompt id of anything else the person typed."""
    return not all(approvalcommand.matches(e, feature, approval["gate"], approval["decision"]) for e in entries)


def verdict_for(approval: dict, feature: str, earlier: list[dict]) -> tuple[str, str] | None:
    """New (origin, evidence) for a pending hook approval, or None if it still cannot be decided."""
    if not approval.get("transcript_path") or not approval.get("prompt_id"):
        return "unverifiable", "the hook did not record where the prompt came from"
    if any(a.get("prompt_id") == approval["prompt_id"] for a in earlier):
        return "invalid", "this prompt was already used for another approval"
    try:
        entries = prompt_entries(approval["transcript_path"], approval["prompt_id"])
    except UsageError as exc:
        return "unverifiable", str(exc)
    if not entries:
        return ("unverifiable", "the prompt never appeared in the transcript") if _age_exceeds_timeout(approval["at"]) else None
    origin, evidence = classify_all(entries)
    if origin in ("human", "headless") and says_something_else(entries, feature, approval):
        return "invalid", f"the prompt is not the {approval['gate']} {approval['decision']} that was recorded ({evidence})"
    return origin, evidence


def verify_origins(feature_dir: Path) -> int:
    """Check every pending hook approval against the transcript. Returns how many were decided."""
    data = state.load(feature_dir)
    verdicts = pending_verdicts(data)
    notes = codex_notes(data, feature_dir)
    if not verdicts and not notes:
        return 0

    def mutate(current: dict) -> None:
        for approval in current["approvals"]:
            if approval["id"] in verdicts and approval["origin"] == "pending":
                approval["origin"], approval["evidence"] = verdicts[approval["id"]]
            if approval["id"] in notes and not approval.get("evidence"):
                approval["evidence"] = notes[approval["id"]]

    state.update(feature_dir, mutate)
    return len(verdicts)


def pending_verdicts(data: dict) -> dict[int, tuple[str, str]]:
    """The origins that can be decided now for pending hook approvals, by approval id."""
    verdicts = {}
    for index, approval in enumerate(data["approvals"]):
        if approval["grade"] == "hook" and approval["origin"] == "pending":
            verdict = verdict_for(approval, data["feature"], data["approvals"][:index])
            if verdict:
                verdicts[approval["id"]] = verdict
    return verdicts


def codex_notes(data: dict, feature_dir: Path) -> dict[int, str]:
    """Supporting evidence for approvals typed in Codex that have none yet. It describes what Codex's session file shows and
    decides nothing: the origin of such an approval stays ``codex-unverified``."""
    root = cfg.find_root(feature_dir)
    return {a["id"]: codexorigin.supporting_evidence(root, a, data["feature"]) for a in data["approvals"]
            if a["grade"] == "codex" and not a.get("evidence")}


# -- are the human gates satisfied? -------------------------------------------------------
def effective_problems(root: Path, data: dict, gate: str) -> list[str]:
    """Why ``gate`` is not validly approved right now (empty list = it is)."""
    last = _last(data, gate)
    if last is None:
        return [f"{gate} has not been approved"]
    if last["decision"] != "approve":
        return [f"{gate} was rejected" + (f": {last['reason']}" if last.get("reason") else "")]
    if last.get("revoked"):
        return [f"the {gate} approval was revoked by a change ({last['revoked']}); it has to be approved again"]
    problems = grade_problems(root, data, gate, last)
    for rel, digest in last["artifacts"].items():
        target = root / rel
        if not target.is_file() or lockfile.file_digest(target) != digest:
            problems.append(f"{rel} changed after the {gate} approval; it has to be approved again")
    if gate == "examples":
        problems += member_problems(root, data["feature"], last.get("members", {}))
    return problems


def grade_problems(root: Path, data: dict, gate: str, last: dict) -> list[str]:
    grade, origin = last["grade"], last["origin"]
    if grade == "codex":
        problem = codex_problem(root)
        return [f"the {gate} approval was typed in Codex, which is not accepted: {problem}"] if problem else []
    if grade in ("auto", "self-reported"):
        problem = auto_problem(root, last.get("autonomy")) if grade == "auto" else self_reported_problem(root, data)
        label = "automatic" if grade == "auto" else "self-reported"
        return [f"the {gate} approval is {label}, which is not accepted: {problem}"] if problem else []
    allowed = ("human", "headless") if cfg.load(root).allow_headless_approvals else ("human",)
    if origin in allowed:
        return []
    explanations = {
        "pending": "is still waiting for its origin to be verified; run `bdd approve FEAT --verify` in a moment "
                   "(on the machine where it was typed: the check needs the session transcript)",
        "headless": "was typed into a headless `claude -p` session, which is not accepted unless "
                    "`[approvals] allow_headless = true` is set in .bdd/config.toml",
        "invalid": "was not typed by a person (" + str(last.get("evidence", "unknown origin")) + ")",
        "unverifiable": "could not be verified (" + str(last.get("evidence", "no evidence")) + "); approve it again",
    }
    return [f"the {gate} approval " + explanations.get(origin, f"has origin {origin}")]


# -- the check that needs no session ---------------------------------------------------------
NEEDED_FROM = {"rules": "test-design", "examples": "system-map"}      # the first phase that rests on the approval


def required_gates(data: dict) -> list[str]:
    """The human gates a feature at this phase must already have passed: the phases after them rest on them."""
    phase = state.PHASES.index(data["phase"])
    return [g for g in GATES if phase >= state.PHASES.index(NEEDED_FROM[g])]


def recorded_problems(root: Path, data: dict) -> dict[str, list[str]]:
    """For every human gate that is required at this phase or has an approval record: why it is not validly approved,
    judged from the committed record alone (no transcript, no hooks): the recorded origin, the recorded kind of
    approval against the project's rules, and the hashes of the approved files against the files now. A gate that is
    fine maps to an empty list."""
    wanted = required_gates(data)
    found = {g: effective_problems(root, data, g) for g in GATES if g in wanted or _last(data, g) is not None}
    if not cfg.load(root).accept_codex:
        for gate, problems in found.items():
            last = _last(data, gate)
            if last is not None and last["decision"] == "approve" and last["grade"] == "codex":
                problems.append(CI_CODEX_MESSAGE)
    return found
