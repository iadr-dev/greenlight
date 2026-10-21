"""What the phase agents cost, recorded by the tools and not estimated by a model.

Every subagent that finishes fires the ``SubagentStop`` hook. ``bdd subagent-stop`` writes one line per agent to
``.bdd/.runs/agents.jsonl`` (which agent, in which session, how long it ran, and the one feature in progress with the phase it
was in). ``bdd cost FEAT-n --collect`` turns the lines of that feature into the feature's cost per phase: the time from the
hook (or, when the hook did not say, from the first and last time stamp in the agent's own transcript) and the tokens from the agent's own transcript (input, output and cache writes, each model reply counted once). The
completion notice of an agent states its own token figure, which can differ by a few percent from this count; the count here
can be repeated by anyone from the transcript, which is why it is the one that is recorded.

The transcript is looked up inside the Claude Code projects folders from the session and agent ids (plain names only), never
from a path written in a file, so a forged note cannot make this read anything else.

A feature whose agent phases have no cost record is flagged by ``bdd status`` (``missing_cost``).
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

from . import claudepaths, state, store
from . import config as cfg
from .errors import StoreError, UsageError

AGENTS_FILE = "agents.jsonl"
AGENT_GATES = ("discover", "test-design", "system-map", "refine", "bind", "implement", "verify")   # machine gates an agent works toward
PLUGIN_AGENT_PREFIX = "greenlight:"
PLAIN_ID = re.compile(r"[A-Za-z0-9_-]{1,100}")
USAGE_KEYS = ("input_tokens", "output_tokens", "cache_creation_input_tokens")
CONTEXT_ERRORS = (StoreError, UsageError, OSError, KeyError, TypeError, ValueError, cfg.ConfigError)


def agents_path(root: Path) -> Path:
    return root / cfg.BDD_DIR / ".runs" / AGENTS_FILE


def find_subagent_transcript(session_id: object, agent_id: object) -> Path | None:
    """A subagent's own transcript, ``<session>/subagents/agent-<id>.jsonl`` next to the session's, found in our folders."""
    if not isinstance(session_id, str) or not isinstance(agent_id, str):
        return None
    if not PLAIN_ID.fullmatch(session_id) or not PLAIN_ID.fullmatch(agent_id):
        return None
    for root in claudepaths.transcript_roots():
        folders = [root, *(p for p in sorted(root.iterdir()) if p.is_dir())] if root.is_dir() else []
        for folder in folders:
            candidate = folder / session_id / "subagents" / f"agent-{agent_id}.jsonl"
            if candidate.is_file():
                return candidate
    return None


def reply_tokens(line: str) -> tuple[str, int] | None:
    """(reply id, tokens) of one transcript line that carries a model reply's usage."""
    try:
        message = (json.loads(line) or {}).get("message")
    except ValueError:
        return None
    usage = message.get("usage") if isinstance(message, dict) else None
    reply = message.get("id") if isinstance(message, dict) else None
    if not isinstance(usage, dict) or not reply:
        return None
    return str(reply), sum(int(usage.get(key) or 0) for key in USAGE_KEYS)


def transcript_tokens(path: Path | None) -> int | None:
    """Input, output and cache-write tokens of every model reply in a transcript, each reply counted once; None if unreadable."""
    if path is None:
        return None
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    counted: dict[str, int] = {}
    for line in text.splitlines():
        found = reply_tokens(line)
        if found:
            counted.setdefault(*found)
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


def active_feature(root: Path) -> tuple[str, str] | tuple[None, None]:
    """The one feature in progress and its phase; (None, None) when there is none or more than one (it is not guessed)."""
    folder = store.features_dir(root)
    found: list[tuple[str, str]] = []
    for feature_dir in sorted(p for p in folder.glob("FEAT-*") if p.is_dir()) if folder.is_dir() else []:
        data = state.load(feature_dir)
        if data["phase"] != "done":
            found.append((data["feature"], data["phase"]))
    return found[0] if len(found) == 1 else (None, None)


def note_agent(payload: dict) -> None:
    """Append the note for one finished agent of the plugin; other agents and other projects are not noted."""
    if not str(payload.get("agent_type") or "").startswith(PLUGIN_AGENT_PREFIX):
        return
    root = cfg.find_root(Path(payload.get("cwd") or "."))
    if root is None:
        return
    feature, phase = active_feature(root)
    entry = {"agent_id": payload.get("agent_id"), "session": payload.get("session_id"), "agent": payload.get("agent_type"),
             "feature": feature, "phase": phase, "duration_ms": int(payload.get("duration_ms") or 0), "at": store.utc_now()}
    path = agents_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


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


def phase_of(entry: dict, feature_id: str, phase: str | None) -> str | None:
    """The phase an agent's cost belongs to for this feature, or None when it belongs to another or to nobody yet.

    An agent noted while this feature was the one in progress belongs to it, in the phase it was then in. One noted when
    several features were in progress (or none) has no owner and is taken only when ``phase`` says where it belongs."""
    if entry.get("feature") == feature_id:
        return entry.get("phase")
    return phase if entry.get("feature") is None else None


def collect(root: Path, feature_id: str, phase: str | None = None) -> list[str]:
    """Record the cost of the agents that finished for this feature and are not recorded yet. Returns what was recorded, one line each."""
    feature_dir = store.find_feature_dir(root, feature_id)
    done = set(state.load(feature_dir).get("cost_agents", []))
    lines: list[str] = []
    taken: dict[str, tuple[str, int, float]] = {}
    for entry in read_entries(root):
        agent_id = str(entry["agent_id"])
        where = phase_of(entry, feature_id, phase)
        not_mine = where is None and entry.get("feature") != feature_id
        if agent_id in done or agent_id in taken or not_mine:
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


def missing_cost(data: dict) -> list[str]:
    """Machine gates an agent worked toward that have passed with no cost recorded for their phase."""
    passed = [g for g in AGENT_GATES if (data.get("gates", {}).get(g) or {}).get("result") == "pass"]
    return [g for g in passed if g not in data.get("cost", {})]
