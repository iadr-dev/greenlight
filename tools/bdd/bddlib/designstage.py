"""The product and design stage: run once per product, before any feature, and approved by the person by looking.

    bdd init --product SPEC        start it from a product spec (``start``)
    /greenlight:approve design     the person approves the design they saw in the gallery (the approval hook, ``record``)
    bdd change --reopen design     release the lock and revoke the approval, so the design can change (``reopen``)

``.bdd/design-stage.json`` holds the stage: the spec it started from and the design approvals, in the same shape as a
feature's approvals (``approvals``), so they are verified against the session transcript the same way, and the summary
of what changed since the last one is made the same way (``approvalsummary``). Approving locks the design
(``lockfile.lock_design``): the files of the design folder, the feature map and the architecture. Both files are written
only by the command line.

The approval is asked for only when the design checks find nothing (``designfolder``) and the ui-reviewer's report on
this very design is there: ``.bdd/design-reviews/design-ui-reviewer.md`` with a ``Verdict:`` line and a ``Design:`` line
that names the design's digest (``bdd gallery --check`` prints it). A project that never starts the stage has no design
gate: nothing here applies to it.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

from . import approvals, approvalsummary, config as cfg, designfolder, lockfile, store
from .errors import StoreError, UsageError

STATE_FILE = "design-stage.json"
GATE = "design"
REVIEWS_DIR = "design-reviews"
REVIEW = f"{cfg.BDD_DIR}/{REVIEWS_DIR}/design-ui-reviewer.md"
TEMPLATES = Path(__file__).resolve().parents[3] / "templates"
STARTING_FILES = {designfolder.ARCHITECTURE: "architecture.md", designfolder.PRODUCT_MAP: "product.md"}
GRADES = ("hook", "self-reported")
DIGEST = re.compile(r"^\s*Design:\s*([0-9a-f]{64})\s*$", re.MULTILINE)
VERDICT = re.compile(r"^\s*Verdict:\s*(PASS|FINDINGS)\b", re.IGNORECASE | re.MULTILINE)
VERIFY_COMMAND = "`bdd approve design --verify`"
NAME = "The product"


def path_of(root: Path) -> Path:
    return root / cfg.BDD_DIR / STATE_FILE


def load(root: Path) -> dict | None:
    """The stage, or None when it was never started."""
    path = path_of(root)
    return store.read_json(path, "design record") if path.exists() else None


def start(root: Path, spec: Path) -> list[str]:
    """Start the stage from ``spec`` (a file inside the project), or record a new spec for a started one. Adds the starting
    feature map and architecture when they are missing; never overwrites a file. Returns what to tell the person."""
    target = spec if spec.is_absolute() else Path.cwd() / spec
    if not target.is_file():
        raise UsageError(f"{spec} is not a file: name the product spec, for example --product product-spec.md")
    rel = lockfile.relative(root, target)
    folder = designfolder.folder_of(cfg.load(root))
    lines = []
    for made, template in STARTING_FILES.items():
        if not (root / made).exists():
            (root / made).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(TEMPLATES / template, root / made)
            lines.append(f"  + {made}")
    now = store.utc_now()
    event = {"event": "start", "at": now, "spec": rel, "spec_digest": lockfile.file_digest(target)}
    if load(root) is None:
        store.write_json(path_of(root), {"schema": store.SCHEMA, "started_at": now, "spec": rel, "folder": folder,
                                         "approvals": [], "history": [event]})
        lines.insert(0, f"design stage: started from {rel}")
    else:
        def mutate(data: dict) -> None:
            if data.get("spec") != rel or data["history"][-1].get("spec_digest") != event["spec_digest"]:
                data.update({"spec": rel})
                data["history"].append(event)
        store.update_json(path_of(root), "design record", mutate)
        lines.insert(0, f"design stage: already started; the spec is {rel}")
    lines.append(f"next: the design folder is {folder}/; follow phases/design.md, then `bdd gallery` builds the page "
                 "the person approves")
    return lines


# -- what the approval covers ---------------------------------------------------------------------------------------
def current_files(root: Path, folder: str) -> dict[str, str]:
    return {rel: lockfile.file_digest(root / rel) for rel in designfolder.artifacts(root, folder)}


def digest_of(files: dict[str, str]) -> str:
    return lockfile.files_digest(files)


def review_problems(root: Path, digest: str) -> list[str]:
    path = root / REVIEW
    if not path.is_file():
        return [f"the ui-reviewer has not reviewed it yet ({REVIEW})"]
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    if not VERDICT.search(text):
        return [f"{REVIEW} has no 'Verdict: PASS' or 'Verdict: FINDINGS' line"]
    named = DIGEST.search(text)
    if named is None or named.group(1) != digest:
        return [f"{REVIEW} reviewed another version of the design (its Design: line is not {digest[:12]}..., which "
                "`bdd gallery --check` prints for the design as it is now); the ui-reviewer reviews it again"]
    return []


def reading(root: Path, design: designfolder.Design, files: dict[str, str]) -> dict:
    """The design as items for the summary: each feature of the map, each inventory row, each section of the architecture,
    and every other file of the design whole. The other lines of the map and the inventory are the text outside."""
    found: dict[str, dict] = {}
    outside: list[str] = []
    item = approvalsummary._item
    inventory = designfolder.files_of(cfg.load(root), design.folder)["inventory"]
    row_lines: dict[str, set[int]] = {designfolder.PRODUCT_MAP: {f.line for f in design.features},
                                      inventory: {r.line for r in design.rows}}
    for rel, numbers in row_lines.items():
        if (root / rel).is_file():
            lines = (root / rel).read_text(encoding="utf-8-sig").splitlines()
            outside += [line for n, line in enumerate(lines, start=1) if n not in numbers]
    for f in design.features:
        depends = ", ".join(f.depends) or "nothing"
        found[approvalsummary.unique(found, f.id)] = item(f"{f.name}: {f.description}", {"depends": list(f.depends), "order": [f.order]},
                                                          [f"depends on: {depends}", f"order: {f.order}"], [f.id, f.name, f.description])
    for r in design.rows:
        detail = [f"states: {', '.join(r.states)}", f"feature: {', '.join(r.features)}", f"file: {r.file or 'none'}"]
        found[approvalsummary.unique(found, r.id)] = item(r.screen, {"states": list(r.states), "feature": list(r.features),
                                                                     "file": [r.file]}, detail, [r.id, r.screen])
    if (root / designfolder.ARCHITECTURE).is_file():
        for heading, (_, lines) in designfolder.sections(root / designfolder.ARCHITECTURE).items():
            said = next((" ".join(line.split()) for line in lines if line.strip() and not line.lstrip().startswith("|")), "(a table)")
            found[approvalsummary.unique(found, f"Architecture: {heading}")] = item(said[:100], {}, [], lines)
    for rel, digest in files.items():
        if rel in (designfolder.PRODUCT_MAP, designfolder.ARCHITECTURE, inventory):
            continue
        kind = "screen file" if rel in design.screens else "design file"
        found[approvalsummary.unique(found, rel)] = item(kind, {"content": [digest]}, [], [digest])
    return {"items": found, "outside": approvalsummary.outside_of(outside)}


# -- approving ------------------------------------------------------------------------------------------------------
def _started(root: Path) -> dict:
    data = load(root)
    if data is None:
        raise UsageError("the design stage has not started: the person starts it with /greenlight:init --product <spec file>")
    return data


def prerequisites(root: Path) -> tuple[designfolder.Design, dict[str, str], list[str]]:
    """The design, its files and why it cannot be approved yet (an empty list: it can)."""
    from . import gallery

    design = designfolder.load(root)
    files = current_files(root, design.folder)
    problems = review_problems(root, digest_of(files))
    if design.issues:
        problems.append(f"the design checks found {len(design.issues)} gap(s); `bdd gallery --check` lists them")
    page = root / design.folder / designfolder.GALLERY
    if not page.is_file() or page.read_text(encoding="utf-8") != gallery.build(root, page, design):
        problems.append(f"{design.folder}/{designfolder.GALLERY} does not show the design as it is now; `bdd gallery` "
                        "builds it again, and the person looks at it before approving")
    return design, files, problems


def record(root: Path, decision: str, grade: str, *, session: str | None = None, prompt_id: str | None = None,
           transcript_path: str | None = None, reason: str = "") -> dict:
    """Record the person's approval or rejection of the design. Approving locks it; rejecting releases the lock."""
    if grade not in GRADES:
        raise UsageError("the design is approved by the person, typing /greenlight:approve design")
    data = _started(root)
    if grade == "self-reported":
        problem = approvals.self_reported_problem(root, data)
        if problem:
            raise UsageError(f"a self-reported approval is not accepted: {problem}")
    files: dict[str, str] = {}
    items = outside = None
    if decision == "approve":
        design, files, problems = prerequisites(root)
        if problems:
            raise UsageError("cannot approve the design: " + "; ".join(problems))
        held = lockfile.read_design(root)
        if lockfile.design_locked(held) and held["files"] != files:
            raise UsageError("the approved design is locked, and it differs from the files on disk; a change goes through "
                             "/greenlight:change (`bdd change --reopen design`)")
        items, outside = approvalsummary.snapshot(reading(root, design, files))
    entry = {"gate": GATE, "decision": decision, "grade": grade, "at": store.utc_now(), "reason": reason,
             "origin": "pending" if grade == "hook" else grade, "artifacts": files, "items": items, "outside": outside,
             "session": session, "prompt_id": prompt_id, "transcript_path": transcript_path, "mode": cfg.load(root).enforcement}

    def mutate(current: dict) -> None:
        entry["id"] = len(current["approvals"]) + 1
        current["approvals"].append(entry)
        if grade == "hook":
            current["hooks_seen"] = True
        approvals.prune_items(root, current, GATE)

    store.update_json(path_of(root), "design record", mutate)
    if decision == "approve":
        if not lockfile.design_locked(lockfile.read_design(root)):
            lockfile.lock_design(root, designfolder.folder_of(cfg.load(root)), files, f"design approved (#{entry['id']})")
    else:
        lockfile.unlock_design(root, f"design rejected: {reason or 'no reason given'}")
    return entry


def verify(root: Path) -> int:
    """Decide the pending design approvals the transcript can decide now. Returns how many were decided."""
    data = load(root)
    verdicts = approvals.pending_verdicts(data) if data else {}
    if not verdicts:
        return 0

    def mutate(current: dict) -> None:
        for approval in current["approvals"]:
            if approval["id"] in verdicts and approval["origin"] == "pending":
                approval["origin"], approval["evidence"] = verdicts[approval["id"]]

    store.update_json(path_of(root), "design record", mutate)
    return len(verdicts)


def _words(problem: str) -> str:
    return problem.replace("`bdd approve FEAT --verify`", VERIFY_COMMAND)


def effective_problems(root: Path, data: dict) -> list[str]:
    """Why the design is not validly approved now (an empty list: it is): the approval itself, as a feature's is judged,
    a file added to the design since, and the lock."""
    problems = [_words(p) for p in approvals.effective_problems(root, data, GATE)]
    standing = approvals.counted(root, data, GATE)
    if problems or standing is None:
        return problems
    folder = designfolder.folder_of(cfg.load(root))
    problems += [f"{rel} was added to the design after its approval; it has to be approved again"
                 for rel in designfolder.artifacts(root, folder) if rel not in standing["artifacts"]]
    held = lockfile.read_design(root)
    if not lockfile.design_locked(held) or held["files"] != standing["artifacts"]:
        problems.append(f"the approved design is not locked as it was approved ({cfg.BDD_DIR}/{lockfile.DESIGN_FILE})")
    return problems


def status(root: Path) -> dict:
    """Where the stage stands: ``stage`` is not started, drafted or approved; ``locked``; ``problems`` of an approval."""
    data = load(root)
    if data is None:
        return {"stage": "not started", "locked": False, "problems": [], "reopened": None}
    locked = lockfile.design_locked(lockfile.read_design(root))
    standing = approvals.counted(root, data, GATE)
    reopened = next((e["reason"] for e in reversed(data["history"]) if e["event"] == "reopen"), None)
    if standing is None or standing["decision"] != "approve" or standing.get("revoked"):
        rejected = standing["reason"] if standing and standing["decision"] == "reject" else None
        return {"stage": "drafted", "locked": locked, "problems": [], "reopened": reopened, "rejected": rejected}
    return {"stage": "approved", "locked": locked, "problems": effective_problems(root, data), "reopened": None}


def status_line(info: dict) -> str:
    if info["stage"] == "not started":
        return "design: not started (the person starts it with /greenlight:init --product <spec file>)"
    if info["stage"] == "drafted":
        why = (f" (rejected: {info['rejected']})" if info.get("rejected") else
               f" (reopened: {info['reopened']})" if info.get("reopened") else "")
        return f"design: drafted, not approved{why}"
    line = "design: approved, " + ("locked" if info["locked"] else "not locked")
    return line + ("; not valid: " + "; ".join(info["problems"]) if info["problems"] else "")


def safe_verify(root: Path) -> None:
    """``verify`` for a reader (``bdd status``, a gate): what it cannot read is reported by the reader itself."""
    try:
        verify(root)
    except (StoreError, UsageError, OSError, KeyError, TypeError, ValueError):
        pass


def gate_problems(root: Path) -> list[str]:
    """Why a feature cannot start yet: once the stage is started, every feature is built against the approved design."""
    data = load(root)
    if data is None:
        return []
    safe_verify(root)
    info = status(root)
    if info["stage"] != "approved":
        return ["the product design is not approved yet: the person looks at the gallery (`bdd gallery`) and types "
                "/greenlight:approve design"]
    return [f"the product design approval does not stand: {p}" for p in info["problems"]]


def reopen(root: Path, reason: str) -> str:
    """Release the design lock and revoke the approval, so the design can change and be approved again."""
    if not reason.strip():
        raise UsageError("a change needs a --reason: it is kept with the design")
    reason = reason.strip()
    _started(root)
    released = lockfile.unlock_design(root, reason)
    revoked: list[int] = []

    def mutate(current: dict) -> None:
        last = approvals._last(current, GATE, "approve")
        if last is not None and not last.get("revoked"):
            last["revoked"] = reason
            revoked.append(last["id"])
        current["history"].append({"event": "reopen", "at": store.utc_now(), "reason": reason, "unlocked": released,
                                   "revoked": revoked})

    store.update_json(path_of(root), "design record", mutate)
    done = [what for what, happened in (("the lock is released", released), ("the approval is revoked", revoked)) if happened]
    return (f"design reopened ({reason}): " + (" and ".join(done) if done else "it was not locked and no approval stood")
            + ". The person approves the changed design again with /greenlight:approve design.")


def summary_text(root: Path) -> str:
    """What the person is asked to approve: all of it the first time, after that what changed since their last approval;
    with the gaps the checks found, the review and the page to look at. Reads only."""
    data = _started(root)
    design, files, problems = prerequisites(root)
    accepted = approvals.summary_baseline(root, data, GATE)
    records = [a for a in data["approvals"] if a["gate"] == GATE]
    rejected = records[-1] if records and records[-1]["decision"] == "reject" else None
    same = accepted is None or accepted["artifacts"] == files
    summary = approvalsummary.summarise(GATE, reading(root, design, files), accepted, rejected, same, [])
    lines = [approvalsummary.render(summary, NAME)]
    product = len(design.features)
    lines.append(f"{product} feature(s) in the product map, {len(design.rows)} screen(s) in the inventory.")
    review = root / REVIEW
    verdict = VERDICT.search(review.read_text(encoding="utf-8-sig", errors="replace")) if review.is_file() else None
    if verdict:
        lines.append(f"Design review: {verdict.group(1).upper()} ({REVIEW})")
    lines.append(f"Look at {design.folder}/{designfolder.GALLERY} (`bdd gallery` builds it).")
    if problems:
        lines.append("Not ready to approve: " + "; ".join(problems))
    else:
        lines.append("To approve, the person types /greenlight:approve design, alone in the message.")
    return "\n".join(lines)

