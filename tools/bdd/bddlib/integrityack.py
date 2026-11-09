"""The person's acknowledgement of open integrity violations: ``/greenlight:approve integrity #3,#4 <reason>``.

The approval hook calls ``acknowledge`` with the prompt as typed. It names the violations by their ids; without ids it
covers the one violation that is open, and is refused when more are. Like an approval, the record is pending: the hook
also fires for prompts the system injects, so it waits until the session transcript shows the person typed exactly that
prompt (``settle``, run by the next tool call, the next prompt and ``bdd status``). It closes only violations reported
before that prompt was written, whose file still has the content recorded when the violation was reported; a file that
changed again is a new violation. It never covers a lock (changed through ``bdd unlock``) and never takes a whole new
baseline: only the covered files enter the baseline, with the digests that were reported.

Kept in ``.bdd/.integrity/acknowledgements.json``; every prompt id used for one is kept for good in
``.bdd/.integrity/acknowledgement-prompts.json``, so no prompt counts twice. Only the command line writes them.
"""
from __future__ import annotations

import getpass
import re
from datetime import datetime
from pathlib import Path

from . import approvalcommand, config as cfg, store, tripwire
from .errors import StoreError, UsageError

EMPTY = {"schema": tripwire.SCHEMA, "items": []}
PROMPTS = "acknowledgement-prompts.json"
_CHOSEN = re.compile(r"((?:#\d+[ \t,]*)*)(.*)", re.DOTALL)


def chosen(typed: str) -> tuple[set[int], str]:
    """The ids the person named (``#3,#4``) and the reason that follows."""
    match = _CHOSEN.fullmatch(typed.strip())
    return {int(n) for n in re.findall(r"#(\d+)", match.group(1))}, match.group(2).strip()


def _is_lock(item: dict) -> bool:
    return item["what"].endswith(" lock")


def shown(item: dict) -> str:
    """How a covered violation is named back to the person: what, which file, and the start of the content's digest."""
    digest = item.get("digest")
    return f"#{item['id']} {tripwire.describe(item)}" + (f" (sha256 {digest[:12]})" if digest else " (now absent)")


def _prompts(root: Path) -> dict:
    """prompt id -> the acknowledgement it was used for (0: refused). Unreadable means nothing can be checked: StoreError."""
    data = tripwire.load(root, PROMPTS, {"schema": tripwire.SCHEMA, "prompts": {}})
    if not isinstance(data.get("prompts"), dict):
        raise StoreError(f"{tripwire.path_of(root, PROMPTS)} is not a record of prompts")
    return data["prompts"]


def _save_prompts(root: Path, prompts: dict) -> None:
    store.write_json(tripwire.path_of(root, PROMPTS), {"schema": tripwire.SCHEMA, "prompts": prompts})


def acknowledge(root: Path, plugin_root: Path | None, typed: str, *, session: str | None, prompt_id: str | None,
                transcript_path: str | None) -> tuple[dict, list[str]]:
    """Record the acknowledgement of the violations the person named. Returns the record and, for each named violation it
    does not cover, why. Raises UsageError if it covers nothing. The prompt id is kept even then."""
    ids, reason = chosen(typed)
    with tripwire.exclusive(root):
        prompts = _prompts(root)
        if prompt_id and prompt_id in prompts:
            raise UsageError("this prompt was already used for an acknowledgement")
        if prompt_id:
            prompts[prompt_id] = 0
            _save_prompts(root, prompts)
        if not reason:
            raise UsageError(f"Say why: {tripwire.ACKNOWLEDGE_COMMAND}")
        held = tripwire.open_violations(root)
        if not ids and len(held) != 1:
            raise UsageError("no integrity violation is open" if not held else
                             f"{len(held)} violations are open: name them, as in /greenlight:approve integrity "
                             + ",".join(f"#{v['id']}" for v in held) + " <reason>")
        targets = [v for v in held if not ids or v["id"] in ids]
        unknown = sorted(ids - {v["id"] for v in targets})
        if unknown:
            raise UsageError("no open violation " + ", ".join(f"#{n}" for n in unknown) + " (`bdd status` lists them)")
        current = tripwire.snapshot(root, plugin_root)
        covered, left = [], []
        for v in targets:
            if _is_lock(v):
                left.append(f"#{v['id']} {tripwire.describe(v)}: a lock is changed through `bdd unlock` with a reason")
            elif v["what"] != tripwire.FILE_WHAT:
                left.append(f"#{v['id']} {tripwire.describe(v)}: the next prompt restores it")
            elif "digest" not in v or current.get(v["path"]) != v["digest"]:
                left.append(f"#{v['id']} {tripwire.describe(v)}: it changed after it was reported; the next tool call "
                            "reports it again")
            else:
                covered.append(v)
        if not covered:
            raise UsageError("nothing to acknowledge: " + "; ".join(left))
        data = tripwire.load(root, tripwire.ACKNOWLEDGEMENTS, dict(EMPTY, items=[]))
        entry = {"id": len(data["items"]) + 1, "at": store.utc_now(), "reason": reason, "typed": typed, "user": _user(),
                 "session": session, "prompt_id": prompt_id, "transcript_path": transcript_path, "status": "pending",
                 "violations": [{"id": v["id"], "path": v["path"], "kind": v["kind"], "digest": v["digest"]} for v in covered],
                 "shown": [shown(v) for v in covered]}
        data["items"].append(entry)
        store.write_json(tripwire.path_of(root, tripwire.ACKNOWLEDGEMENTS), data)
        if prompt_id:
            prompts[prompt_id] = entry["id"]
            _save_prompts(root, prompts)
        return entry, left


def _user() -> str | None:
    try:
        return getpass.getuser()
    except (OSError, KeyError, ImportError):
        return None


def settle(root: Path) -> list[dict]:
    """Decide the pending acknowledgements the transcript can decide now, and apply those the person typed."""
    with tripwire.exclusive(root):
        return settle_held(root)


def settle_held(root: Path) -> list[dict]:
    """``settle`` for a caller that holds the integrity data already. Costs one file check when nothing is pending, and
    reads a transcript again only when it changed since the last look."""
    if not tripwire.path_of(root, tripwire.ACKNOWLEDGEMENTS).is_file():
        return []
    data = tripwire.load(root, tripwire.ACKNOWLEDGEMENTS, EMPTY)
    if not any(a["status"] == "pending" for a in data["items"]):
        return []
    from . import approvals                                          # only now: it is a long import for a hook
    allowed = ("human", "headless") if cfg.load(root).allow_headless_approvals else ("human",)
    prompts = _prompts(root)
    applied, changed = [], False
    for entry in data["items"]:
        if entry["status"] != "pending":
            continue
        looked = _transcript_state(entry, approvals)
        if looked is not None and looked == entry.get("looked"):
            continue
        verdict = _verdict(entry, prompts, approvals)
        if verdict is None:
            entry["looked"], changed = looked, True
            continue
        (entry["origin"], entry["evidence"]), entry["prompt_at"] = verdict[:2], verdict[2]
        entry["status"] = "applied" if verdict[0] in allowed else "refused"
        if entry["status"] == "applied" and not _apply(root, entry):
            entry["status"], entry["evidence"] = "refused", "there is no baseline to take the files into; the next prompt restores it"
        applied += [entry] if entry["status"] == "applied" else []
        changed = True
    if changed:
        store.write_json(tripwire.path_of(root, tripwire.ACKNOWLEDGEMENTS), data)
    return applied


def _transcript_state(entry: dict, approvals) -> list[int] | None:
    try:
        path = approvals.find_transcript(entry["transcript_path"]) if entry.get("transcript_path") else None
        status = path.stat() if path is not None else None
    except (UsageError, OSError):
        return None
    return None if status is None else [status.st_size, status.st_mtime_ns]


def _when(entries: list[dict]) -> datetime | None:
    """When Claude Code wrote the prompt, from the transcript's own timestamp (every entry has one)."""
    try:
        stamps = {datetime.fromisoformat(e["timestamp"]) for e in entries}
    except (KeyError, TypeError, ValueError):
        return None
    return min(stamps) if stamps and all(s.tzinfo is not None for s in stamps) else None


def _verdict(entry: dict, prompts: dict, approvals) -> tuple[str, str, str | None] | None:
    """(origin, evidence, when the prompt was written) of an acknowledgement's prompt, or None while the transcript cannot
    tell yet."""
    if not entry.get("transcript_path") or not entry.get("prompt_id"):
        return "unverifiable", "the hook did not record where the prompt came from", None
    if prompts.get(entry["prompt_id"]) != entry["id"]:
        return "invalid", "this prompt is not on record for this acknowledgement", None
    try:
        entries = approvals.prompt_entries(entry["transcript_path"], entry["prompt_id"])
    except UsageError as exc:
        return "unverifiable", str(exc), None
    if not entries:
        return ("unverifiable", "the prompt never appeared in the transcript", None) if approvals.age_exceeds_timeout(entry["at"]) else None
    origin, evidence = approvals.classify_all(entries)
    if any(approvalcommand.parse_integrity(approvalcommand.typed_text(e)) != entry["typed"] for e in entries):
        return "invalid", f"the prompt is not this acknowledgement ({evidence})", None
    written = _when(entries) or datetime.fromisoformat(entry["at"])        # else when the hook recorded it
    return origin, evidence, written.isoformat()


def _apply(root: Path, entry: dict) -> bool:
    """Take the covered files into the baseline with the digests reported, and close their violations. A violation that
    closed meanwhile, whose file changed again, or that was reported after the prompt was written, is left alone. False
    if there is no baseline."""
    kept = tripwire.kept_baseline(root)
    if kept is None:
        return False
    written = datetime.fromisoformat(entry["prompt_at"])
    items = tripwire.violations(root)
    covered = {(c["id"], c["digest"]) for c in entry["violations"]}
    closing = [v for v in items if v["open"] and (v["id"], v.get("digest")) in covered
               and datetime.fromisoformat(v["at"]) <= written]
    files = dict(kept["files"])
    for v in closing:
        if v["digest"] is None:
            files.pop(v["path"], None)
        else:
            files[v["path"]] = v["digest"]
    now = store.utc_now()
    history = (kept.get("accepted") or []) + [{"kind": v["kind"], "path": v["path"], "what": v["what"], "at": now,
                                               "acknowledged": entry["reason"]} for v in closing]
    tripwire.write_baseline(root, {**kept, "files": files, "accepted": history[-tripwire.ACCEPTED_KEPT:]})
    for v in closing:
        tripwire.close(v, "acknowledged", now)
        v["acknowledgement"] = {"id": entry["id"], "reason": entry["reason"], "user": entry["user"], "at": entry["at"]}
    if closing:
        tripwire.save_violations(root, items)
    return True


def acknowledged(root: Path) -> list[dict]:
    """The violations the person acknowledged, newest first."""
    return [v for v in reversed(tripwire.violations(root)) if v.get("acknowledgement")]


def safe_settle(root: Path) -> None:
    """``settle`` for a reader (``bdd status``): what it cannot read is the tool-call check's to report."""
    try:
        settle(root)
    except (StoreError, OSError, KeyError, TypeError, ValueError, AttributeError):
        pass
