"""What the phase agents cost, recorded by the tools and not estimated by a model.

Every subagent that finishes fires the ``SubagentStop`` hook. ``bdd subagent-stop`` writes one line per agent to
``.bdd/.runs/agents.jsonl`` (which agent, how long it ran, where its transcript is, and the one feature in progress with the
phase it was in). ``bdd cost FEAT-n --collect`` turns the lines of that feature into the feature's cost per phase: the time
from the hook and the tokens from the agent's own transcript (input, output and cache writes, each model reply counted once).
The completion notice of an agent states its own token figure, which can differ by a few percent from this count; the count
here can be repeated by anyone from the transcript, which is why it is the one that is recorded.

A feature whose agent phases have no cost record is flagged by ``bdd status`` (``missing_cost``).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from . import config as cfg
from . import state, store
from .errors import StoreError, UsageError

AGENTS_FILE = "agents.jsonl"
AGENT_GATES = ("discover", "test-design", "system-map", "refine", "bind", "implement", "verify")   # machine gates an agent works toward
PLUGIN_AGENT_PREFIX = "greenlight:"
CONTEXT_ERRORS = (StoreError, UsageError, OSError, KeyError, TypeError, ValueError, cfg.ConfigError)


def agents_path(root: Path) -> Path:
    return root / cfg.BDD_DIR / ".runs" / AGENTS_FILE


def subagent_transcript(session_transcript: str, agent_id: str) -> Path | None:
    """Where Claude Code keeps a subagent's own transcript: next to the session's, in a folder named after the session."""
    if not session_transcript or not agent_id or any(c in agent_id for c in "/\\"):
        return None
    session = Path(session_transcript)
    return session.with_suffix("") / "subagents" / f"agent-{agent_id}.jsonl"


def transcript_tokens(path: Path) -> int | None:
    """Input, output and cache-write tokens of every model reply in a transcript, each reply counted once; None if unreadable."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    counted: set[str] = set()
    total = 0
    for line in text.splitlines():
        try:
            message = (json.loads(line) or {}).get("message") or {}
        except ValueError:
            continue
        usage = message.get("usage") if isinstance(message, dict) else None
        reply = message.get("id") if isinstance(message, dict) else None
        if not isinstance(usage, dict) or not reply or reply in counted:
            continue
        counted.add(reply)
        total += sum(int(usage.get(key) or 0) for key in ("input_tokens", "output_tokens", "cache_creation_input_tokens"))
    return total


def active_feature(root: Path) -> tuple[str, str] | tuple[None, None]:
    """The one feature in progress and its phase; (None, None) when there is none or more than one (it is not guessed)."""
    folder = store.features_dir(root)
    found: list[tuple[str, str]] = []
    for feature_dir in sorted(p for p in folder.glob("FEAT-*") if p.is_dir()) if folder.is_dir() else []:
        data = state.load(feature_dir)
        if data["phase"] != "done":
            found.append((data["feature"], data["phase"]))
    return found[0] if len(found) == 1 else (None, None)


def subagent_stop(_argv: list[str]) -> int:
    """SubagentStop hook: note that an agent of the plugin finished. Never blocks and never fails the session."""
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        if not isinstance(payload, dict) or not str(payload.get("agent_type") or "").startswith(PLUGIN_AGENT_PREFIX):
            return 0
        root = cfg.find_root(Path(payload.get("cwd") or "."))
        if root is None:
            return 0
        feature, phase = active_feature(root)
        transcript = subagent_transcript(str(payload.get("transcript_path") or ""), str(payload.get("agent_id") or ""))
        entry = {"agent_id": payload.get("agent_id"), "agent": payload.get("agent_type"), "feature": feature, "phase": phase,
                 "duration_ms": int(payload.get("duration_ms") or 0), "transcript": str(transcript) if transcript else None,
                 "at": store.utc_now()}
        path = agents_path(root)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except CONTEXT_ERRORS + (json.JSONDecodeError,):
        return 0                                        # a cost note is never worth stopping a session for
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


def collect(root: Path, feature_id: str, phase: str | None = None) -> list[str]:
    """Record the cost of the agents that finished for this feature and are not recorded yet. Returns what was recorded, one line each.

    An agent noted while the feature was the one in progress belongs to it, in the phase it was then in. One noted when several
    features were in progress (or none) has no owner and is taken only when ``phase`` says where it belongs."""
    feature_dir = store.find_feature_dir(root, feature_id)
    recorded = set(state.load(feature_dir).get("cost_agents", []))
    lines: list[str] = []
    taken: list[tuple[str, str, int, float]] = []
    for entry in read_entries(root):
        agent_id = str(entry["agent_id"])
        if agent_id in recorded or any(agent_id == t[0] for t in taken):
            continue
        owned = entry.get("feature") == feature_id
        if not owned and not (entry.get("feature") is None and phase):
            continue
        where = entry.get("phase") if owned else phase
        if where not in state.PHASES:
            lines.append(f"{agent_id} ({entry.get('agent')}): no phase known; run `bdd cost {feature_id} --collect --phase PHASE`")
            continue
        tokens = transcript_tokens(Path(entry["transcript"])) if entry.get("transcript") else None
        seconds = round(int(entry.get("duration_ms") or 0) / 1000, 3)
        if tokens is None:
            lines.append(f"{agent_id} ({entry.get('agent')}): its transcript could not be read, so only the time is recorded")
        taken.append((agent_id, where, tokens or 0, seconds))
        lines.append(f"{agent_id} ({entry.get('agent')}) {where}: {tokens if tokens is not None else 'unknown'} tokens, {seconds:g} s")

    def mutate(data: dict) -> None:
        for agent_id, where, tokens, seconds in taken:
            entry = data["cost"].setdefault(where, {"tokens": 0, "seconds": 0.0, "runs": 0})
            entry["tokens"] += tokens
            entry["seconds"] = round(entry["seconds"] + seconds, 3)
            entry["runs"] += 1
            data.setdefault("cost_agents", []).append(agent_id)

    if taken:
        state.update(feature_dir, mutate)
    return lines


def missing_cost(data: dict) -> list[str]:
    """Machine gates an agent worked toward that have passed with no cost recorded for their phase."""
    passed = [g for g in AGENT_GATES if (data.get("gates", {}).get(g) or {}).get("result") == "pass"]
    return [g for g in passed if g not in data.get("cost", {})]
