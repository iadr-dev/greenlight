"""Which model each agent runs on: the ``model`` of its agent file, or the one the person names in ``[models]`` of
``.bdd/config.toml``.

The orchestrator passes the model ``bdd status`` names on each Agent call. Claude Code lets that parameter win over the
agent file's ``model`` (docs, sub-agents, "Choose a model"), and the parameter takes an alias only, which is why a
choice outside ``ACCEPTED`` is reported by ``bdd doctor`` and the agent stays on its default.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from . import frontmatter, guard

ACCEPTED = ("fable", "haiku", "opus", "sonnet")
CONFIG_FILE = ".bdd/config.toml"
AGENTS = tuple(guard.AGENT_WRITES)


@dataclass(frozen=True)
class Choice:
    agent: str
    model: str
    chosen: bool          # named in [models], not the agent file's default


def agents_dir() -> Path:
    plugin = os.environ.get("CLAUDE_PLUGIN_ROOT")
    return (Path(plugin) if plugin else Path(__file__).resolve().parents[3]) / "agents"


def defaults() -> dict[str, str]:
    """The ``model`` of every agent file."""
    folder = agents_dir()
    return {agent: frontmatter.parse((folder / f"{agent}.md").read_text(encoding="utf-8"))[0].get("model", "inherit")
            for agent in AGENTS}


def choices(configured: tuple[tuple[str, str], ...]) -> list[Choice]:
    """The model each agent runs on. A choice that is not an agent and a model the Agent tool accepts is left out."""
    picked = {agent: model for agent, model in configured if agent in AGENTS and model in ACCEPTED}
    return [Choice(agent, picked.get(agent, default), agent in picked) for agent, default in defaults().items()]


def problems(configured: tuple[tuple[str, str], ...]) -> list[str]:
    found = []
    for agent, model in configured:
        if agent not in AGENTS:
            found.append(f"{agent} is not a greenlight agent; the agents are {', '.join(AGENTS)}")
        elif model not in ACCEPTED:
            found.append(f'{agent} = "{model}" is not a model the Agent tool accepts ({", ".join(ACCEPTED)}); '
                         "the agent runs on the model of its agent file")
    return found


def render(configured: tuple[tuple[str, str], ...]) -> str:
    listed = ", ".join(f"{c.agent} {c.model}" + (f" ({CONFIG_FILE})" if c.chosen else "") for c in choices(configured))
    wrong = len(problems(configured))
    return f"models: {listed}" + (f"\nmodels: {wrong} choice(s) in [models] cannot be used; run `bdd doctor`" if wrong else "")
