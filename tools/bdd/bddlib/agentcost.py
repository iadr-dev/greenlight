"""What the phase agents cost, recorded by the tools and not estimated by a model.

Every subagent that finishes fires the ``SubagentStop`` hook. ``bdd subagent-stop`` writes one line per agent to
``.bdd/.runs/agents.jsonl``: which agent, in which session, how long it ran, and the feature it worked for with the phase
that feature was in. The feature is the one in progress; when several are, it is the one in progress that the agent's task
names (the orchestrator starts every task with the feature id), and none when the task names none or several of them.
``bdd cost FEAT-n --collect`` turns the lines of that feature into the feature's cost per phase: the time from the
hook (or, when the hook did not say, from the first and last time stamp in the agent's own transcript) and the tokens from the agent's own transcript (input, output and cache writes, each model reply counted once). The
completion notice of an agent states its own token figure, which can differ by a few percent from this count; the count here
can be repeated by anyone from the transcript, which is why it is the one that is recorded.

The orchestrator session's own tokens are counted the same way from the main transcript of the sessions that started the
feature's agents, and shown next to the record as Claude Code's figure, never added to it (D37): a session can hold other
work than this feature.

Transcripts are looked up inside the Claude Code projects folders from the session and agent ids (plain names only), never
from a path written in a file, so a forged note cannot make this read anything else.

A feature whose agent phases have no cost record is flagged by ``bdd status`` (``missing_cost``).
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

from . import claudepaths, reviewlog, roles, state, store
from . import config as cfg
from .errors import StoreError, UsageError

AGENTS_FILE = "agents.jsonl"
AGENT_GATES = ("discover", "test-design", "system-map", "refine", "bind", "implement", "verify")   # machine gates an agent works toward
PLUGIN_AGENT_PREFIX = "greenlight:"
PLAIN_ID = re.compile(r"[A-Za-z0-9_-]{1,100}")
FEATURE_ID = re.compile(r"\bFEAT-\d+\b")
USAGE_KEYS = ("input_tokens", "output_tokens", "cache_creation_input_tokens")
CONTEXT_ERRORS = (StoreError, UsageError, OSError, KeyError, TypeError, ValueError, cfg.ConfigError)


def agents_path(root: Path) -> Path:
    return root / cfg.BDD_DIR / ".runs" / AGENTS_FILE


def plain(value: object) -> bool:
    return isinstance(value, str) and PLAIN_ID.fullmatch(value) is not None


def transcript_folders() -> list[Path]:
    folders: list[Path] = []
    for root in claudepaths.transcript_roots():
        if root.is_dir():
            folders += [root, *(p for p in sorted(root.iterdir()) if p.is_dir())]
    return folders


def find_subagent_transcript(session_id: object, agent_id: object) -> Path | None:
    """A subagent's own transcript, ``<session>/subagents/agent-<id>.jsonl`` next to the session's, found in our folders."""
    if not plain(session_id) or not plain(agent_id):
        return None
    candidates = (folder / str(session_id) / "subagents" / f"agent-{agent_id}.jsonl" for folder in transcript_folders())
    return next((c for c in candidates if c.is_file()), None)


def find_session_transcript(session_id: object) -> Path | None:
    """The main transcript of a session, ``<session>.jsonl``, found in our folders."""
    if not plain(session_id):
        return None
    return next((c for c in (folder / f"{session_id}.jsonl" for folder in transcript_folders()) if c.is_file()), None)


def reply_tokens(line: str, main_thread: bool = False) -> tuple[str, int] | None:
    """(reply id, tokens) of one transcript line that carries a model reply's usage. With ``main_thread``, a subagent's
    reply written into the session's transcript (``isSidechain``) is not the session's own."""
    try:
        entry = json.loads(line)
    except ValueError:
        return None
    if not isinstance(entry, dict) or (main_thread and entry.get("isSidechain")):
        return None
    message = entry.get("message")
    usage = message.get("usage") if isinstance(message, dict) else None
    reply = message.get("id") if isinstance(message, dict) else None
    if not isinstance(usage, dict) or not reply:
        return None
    return str(reply), sum(int(usage.get(key) or 0) for key in USAGE_KEYS)


def count_replies(path: Path, counted: dict[str, int], main_thread: bool = False) -> bool:
    """Add the replies of one transcript to ``counted`` (reply id -> tokens, a reply already there is not counted again),
    reading it line by line: a session's transcript can be hundreds of megabytes. False when it cannot be read."""
    try:
        with path.open(encoding="utf-8", errors="replace") as handle:
            for line in handle:
                found = reply_tokens(line, main_thread) if '"usage"' in line else None
                if found:
                    counted.setdefault(*found)
    except OSError:
        return False
    return True


def transcript_tokens(path: Path | None, main_thread: bool = False) -> int | None:
    """Input, output and cache-write tokens of every model reply in a transcript, each reply counted once; None if unreadable."""
    counted: dict[str, int] = {}
    if path is None or not count_replies(path, counted, main_thread):
        return None
    return sum(counted.values())


def transcript_seconds(path: Path | None) -> float | None:
    """How long the agent ran: from the first to the last time stamp in its transcript; None when there are none."""
    if path is None:
        return None
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    stamps = []
    for line in text.splitlines():
        try:
            value = (json.loads(line) or {}).get("timestamp")
            stamps.append(datetime.fromisoformat(value.replace("Z", "+00:00")))
        except (ValueError, TypeError, AttributeError):
            continue
    return round((max(stamps) - min(stamps)).total_seconds(), 3) if stamps else None


def message_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(str(b.get("text", "")) for b in content if isinstance(b, dict) and b.get("type") == "text")
    return ""


def task_text(path: Path | None) -> str:
    """The task the agent was started with: the first user message of its own transcript ("" when there is none)."""
    if path is None:
        return ""
    try:
        with path.open(encoding="utf-8", errors="replace") as handle:
            for line in handle:
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue
                message = entry.get("message") if isinstance(entry, dict) and entry.get("type") == "user" else None
                if isinstance(message, dict):
                    return message_text(message.get("content"))
    except OSError:
        return ""
    return ""


def features_named(session_id: object, agent_id: object) -> set[str]:
    """The feature ids the agent's task names."""
    return set(FEATURE_ID.findall(task_text(find_subagent_transcript(session_id, agent_id))))


def feature_states(root: Path) -> list[dict]:
    """The state of every feature of the project."""
    folder = store.features_dir(root)
    return [state.load(d) for d in sorted(p for p in folder.glob("FEAT-*") if p.is_dir())] if folder.is_dir() else []


def features_in_progress(root: Path) -> dict[str, str]:
    """Every feature that is not done, with its phase."""
    return {data["feature"]: data["phase"] for data in feature_states(root) if data["phase"] != "done"}


def owner_of(root: Path, session_id: object, agent_id: object) -> tuple[str, str] | tuple[None, None]:
    """The feature an agent worked for and that feature's phase: the one in progress, or, when several are, the one of them
    its task names; (None, None) when that is not one feature (it is not guessed)."""
    in_progress = features_in_progress(root)
    if len(in_progress) == 1:
        return next(iter(in_progress.items()))
    named = features_named(session_id, agent_id) & in_progress.keys() if in_progress else set()
    if len(named) != 1:
        return None, None
    feature = named.pop()
    return feature, in_progress[feature]


def note_agent(payload: dict) -> None:
    """Append the note for one finished agent of the plugin; other agents and other projects are not noted."""
    if not str(payload.get("agent_type") or "").startswith(PLUGIN_AGENT_PREFIX):
        return
    root = cfg.find_root(Path(payload.get("cwd") or "."))
    if root is None:
        return
    feature, phase = owner_of(root, payload.get("session_id"), payload.get("agent_id"))
    entry = {"agent_id": payload.get("agent_id"), "session": payload.get("session_id"), "agent": payload.get("agent_type"),
             "feature": feature, "phase": phase, "duration_ms": int(payload.get("duration_ms") or 0), "at": store.utc_now()}
    path = agents_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    if str(payload.get("agent_type")).removeprefix(PLUGIN_AGENT_PREFIX) in roles.REVIEWERS:
        reviewlog.seal(root, payload.get("agent_id"))


def subagent_stop(_argv: list[str]) -> int:
    """SubagentStop hook. It never blocks (exit 2 would); a note that could not be written is reported with exit 1, which
    Claude Code shows and ignores."""
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        if isinstance(payload, dict):
            note_agent(payload)
    except (CONTEXT_ERRORS + (json.JSONDecodeError,)) as exc:
        print(f"greenlight: the cost of a finished agent could not be noted ({type(exc).__name__}: {exc}); "
              "record it by hand with `bdd cost`.", file=sys.stderr)
        return 1
    return 0


def read_entries(root: Path) -> list[dict]:
    path = agents_path(root)
    if not path.is_file():
        return []
    entries = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if isinstance(entry, dict) and entry.get("agent_id"):
            entries.append(entry)
    return entries


def claim(entry: dict, feature_id: str, phase: str | None, known: set[str]) -> tuple[bool, str | None]:
    """Whether an agent's cost belongs to this feature, and in which phase.

    An agent noted for a feature belongs to it, in the phase it was then in. One noted with no owner (several features in
    progress and a task that named none or several of them, or a note from before tasks were read) belongs to this
    feature when its task names it or names no feature of the project (``known``), and only ``phase`` can say where;
    without it the agent is reported as waiting for a phase when its task names this feature."""
    if entry.get("feature") is not None:
        return entry.get("feature") == feature_id, entry.get("phase")
    named = features_named(entry.get("session"), entry.get("agent_id")) & known
    if named and feature_id not in named:
        return False, None
    return (True, phase) if phase else (feature_id in named, None)


def collect(root: Path, feature_id: str, phase: str | None = None) -> list[str]:
    """Record the cost of the agents that finished for this feature and are not recorded yet. Returns what was recorded, one line each."""
    feature_dir = store.find_feature_dir(root, feature_id)
    features = feature_states(root)
    done = {str(a) for data in features for a in data.get("cost_agents", [])}   # an agent is recorded for one feature only
    lines: list[str] = []
    taken: dict[str, tuple[str, int, float]] = {}
    known = {data["feature"] for data in features}
    for entry in read_entries(root):
        agent_id = str(entry["agent_id"])
        if agent_id in done or agent_id in taken:
            continue
        mine, where = claim(entry, feature_id, phase, known)
        if not mine:
            continue
        label = f"{agent_id} ({entry.get('agent')})"
        if where not in state.PHASES:
            lines.append(f"{label}: no phase known; run `bdd cost {feature_id} --collect --phase PHASE`")
            continue
        transcript = find_subagent_transcript(entry.get("session"), agent_id)
        tokens = transcript_tokens(transcript)
        reported = int(entry.get("duration_ms") or 0)             # the hook's own figure, when it gives one
        seconds = round(reported / 1000, 3) if reported > 0 else (transcript_seconds(transcript) or 0.0)
        taken[agent_id] = (where, tokens or 0, seconds)
        lines.append(f"{label} {where}: {tokens} tokens, {seconds:g} s" if tokens is not None
                     else f"{label} {where}: its transcript could not be found, so only the time is recorded ({seconds:g} s)")

    def mutate(data: dict) -> None:
        for agent_id, (where, tokens, seconds) in taken.items():
            cost = data["cost"].setdefault(where, {"tokens": 0, "seconds": 0.0, "runs": 0})
            cost["tokens"] += tokens
            cost["seconds"] = round(cost["seconds"] + seconds, 3)
            cost["runs"] += 1
            data.setdefault("cost_agents", []).append(agent_id)

    if taken:
        state.update(feature_dir, mutate)
    return lines


def session_replies(session_id: str, cache: dict[str, dict[str, int] | None]) -> dict[str, int] | None:
    """The main-thread replies of one session (reply id -> tokens), read once per command; None when not found."""
    if session_id not in cache:
        path, replies = find_session_transcript(session_id), {}
        cache[session_id] = replies if path is not None and count_replies(path, replies, main_thread=True) else None
    return cache[session_id]


def orchestrator_tokens(root: Path, data: dict, entries: list[dict] | None = None,
                        cache: dict[str, dict[str, int] | None] | None = None) -> dict | None:
    """Claude Code's own count of the main sessions that started this feature's recorded agents: how many sessions, how
    many transcripts were found and their tokens, a reply that two sessions share (a resumed one) counted once. None
    when no recorded agent was noted by the hook. ``entries`` and ``cache`` let a command that shows several features
    read the notes and each transcript once."""
    recorded = set(data.get("cost_agents", []))
    notes = read_entries(root) if entries is None else entries
    sessions = sorted({e["session"] for e in notes if str(e["agent_id"]) in recorded and plain(e.get("session"))})
    if not sessions:
        return None
    cache = {} if cache is None else cache
    found = [r for r in (session_replies(s, cache) for s in sessions) if r is not None]
    counted: dict[str, int] = {}
    for replies in found:
        for reply, tokens in replies.items():
            counted.setdefault(reply, tokens)
    return {"sessions": len(sessions), "found": len(found), "tokens": sum(counted.values())}


def describe_orchestrator(figure: dict | None) -> str:
    if figure is None:
        return "Orchestrator session: not known (no agent of this feature was noted by the hook)"
    if not figure["found"]:
        return "Orchestrator session: not known (the session transcript could not be found)"
    sessions = "the session" if figure["sessions"] == 1 else f"the {figure['sessions']} sessions"
    missing = figure["sessions"] - figure["found"]
    return (f"Orchestrator session: {figure['tokens']:,} tokens, Claude Code's own count of {sessions} that started this "
            "feature's agents, including any other work done there; not part of the recorded cost"
            + (f" ({missing} transcript(s) not found)" if missing else ""))


def missing_cost(data: dict) -> list[str]:
    """Machine gates an agent worked toward that have passed with no cost recorded for their phase."""
    passed = [g for g in AGENT_GATES if (data.get("gates", {}).get(g) or {}).get("result") == "pass"]
    return [g for g in passed if g not in data.get("cost", {})]
