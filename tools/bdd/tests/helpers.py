"""A throwaway greenlight project, and helpers to drive a feature through its phases."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from bddlib import approvals, claudepaths, enforcement, gates, lockfile, state

SPEC = "@FEAT-007\nFeature: Discounts\n  @R-7.1 @EX-7.1.1\n  Scenario: S\n    Then the request succeeds\n"
RULES = "# Rules\n\nR-007.1 Orders of 1000 or more get 10% off.\n"
# Gates in pipeline order, with the human approvals that sit between them.
PIPELINE = ("discover", "rules", "test-design", "examples", "system-map", "refine", "bind", "tasks", "implement",
            "verify")


class ProjectCase(unittest.TestCase):
    """FEAT-007 in a temporary project. No Claude Code session is assumed: CLAUDE_CODE_SESSION_ID is cleared."""

    AUTONOMY = "standard"

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name).resolve()
        self.transcripts = self.root / "transcripts" / "projects"
        self.transcripts.mkdir(parents=True)
        patcher = mock.patch.dict(os.environ, {claudepaths.TRANSCRIPT_ROOT_ENV: str(self.transcripts)})
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop(enforcement.SESSION_ENV, None)
        self.write(".bdd/config.toml", '[[adapters]]\nname = "x"\nfeatures = "features"\nsteps = "steps"\n')
        self.spec = self.write("features/discounts.feature", SPEC)
        self.step = self.write("steps/steps.py", "def then_ok():\n    assert True\n")
        self.feature_dir = state.create(self.root, "FEAT-007", "Order discounts", self.AUTONOMY)
        self.rules = self.feature_dir / "rules.md"

    # -- files ---------------------------------------------------------------------------
    def write(self, rel: str, text: str) -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        return path

    def config(self, top_level: str = "", tail: str = "") -> None:
        """Rewrite .bdd/config.toml. ``top_level`` keys must precede the [[adapters]] table, ``tail`` tables follow."""
        self.write(".bdd/config.toml", top_level + '[[adapters]]\nname = "x"\nfeatures = "features"\nsteps = "steps"\n' + tail)

    def data(self) -> dict:
        return state.load(self.feature_dir)

    # -- gates and approvals -------------------------------------------------------------
    def gate(self, name: str, result: str = "pass", detail=None, red=None) -> dict:
        return gates.record_gate(self.root, self.feature_dir, name, result, detail or {}, red)

    def approve(self, gate: str, grade: str = "self-reported", decision: str = "approve", **extra) -> dict:
        if decision == "approve" and gate == "rules" and not self.rules.exists():
            self.rules.write_text(RULES, encoding="utf-8", newline="\n")
        return approvals.record(self.root, self.feature_dir, gate, decision, grade, **extra)

    def walk_to(self, last: str) -> None:
        """Drive the feature through the happy path up to and including ``last``."""
        for step in PIPELINE:
            if step == "rules":
                self.approve("rules")
            elif step == "examples":
                self.approve("examples")
            elif step == "bind":
                lockfile.lock(self.root, self.feature_dir, "FEAT-007", "bind", [self.step])
                self.gate("bind")
            else:
                self.gate(step)
            if step == last:
                return
        raise AssertionError(f"unknown pipeline step {last}")

    # -- transcripts ---------------------------------------------------------------------
    def transcript(self, *entries: dict, name: str = "session.jsonl") -> Path:
        path = self.transcripts / name
        path.write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")
        return path


def typed(prompt_id: str, **extra) -> dict:
    """The transcript entry Claude Code writes for a prompt the person typed."""
    return {"type": "user", "promptId": prompt_id, "promptSource": "typed", "turnOrigin": "human",
            "origin": {"kind": "human"}, **extra}


def headless(prompt_id: str) -> dict:
    return {"type": "user", "promptId": prompt_id, "turnOrigin": "sdk"}


def injected(prompt_id: str, turn: str = "scheduled", kind: str | None = None) -> dict:
    entry = {"type": "user", "promptId": prompt_id, "promptSource": "system", "turnOrigin": turn, "isMeta": True}
    if kind:
        entry["origin"] = {"kind": kind}
    return entry
