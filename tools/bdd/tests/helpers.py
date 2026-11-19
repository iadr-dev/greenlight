"""A throwaway greenlight project, and helpers to drive a feature through its phases."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from bddlib import approvals, claudepaths, designreview, designsections, docsrecord, enforcement, gates, lockfile, route, state

SPEC = "@FEAT-007\nFeature: Discounts\n  @R-7.1 @EX-7.1.1\n  Scenario: S\n    Then the request succeeds\n"
RULES = "# Rules\n\nR-007.1 Orders of 1000 or more get 10% off.\n"


def not_applicable(section: designsections.Section, reason: str) -> str:
    cells = " | ".join([reason] + [""] * (len(section.columns) - 2))
    return f"## {section.name}\n{section.header}\n|{'---|' * len(section.columns)}\n| n/a | {cells} |\n\n"


# Every section of a technical design, none of which applies: the smallest design.md that passes its checks.
TECHNICAL_DESIGN = ("# Design: FEAT-007 Order discounts\n\n```mermaid\nflowchart LR\n  a[Order] --> b[Discount]\n```\n\n"
                    + "".join(not_applicable(s, "this test feature does not need it") for s in designsections.SECTIONS))
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

    def make_old_feature(self) -> None:
        """Make FEAT-007 a feature started before the technical design: its state has no marker."""
        state.update(self.feature_dir, lambda current: current.pop(designsections.MARKER, None))

    # -- gates and approvals -------------------------------------------------------------
    def gate(self, name: str, result: str = "pass", detail=None, red=None, reviews: bool = True) -> dict:
        """Record a gate. Before ``implement`` the routed reviews are left in ``reviews/``, as the orchestrator does in a
        real run, unless ``reviews`` is False."""
        if name in ("system-map", "tasks") and result == "pass" and reviews:
            self.write_technical_design()
        if name == "tasks" and result == "pass" and reviews:
            self.write_design_reviews()
        if name == "implement" and result == "pass" and reviews:
            self.write_reviews()
            self.write_docs()
        return gates.record_gate(self.root, self.feature_dir, name, result, detail or {}, red)

    def write_technical_design(self, text: str | None = None) -> Path:
        """A technical design with every section, as the system-analyst leaves it; kept when the test wrote its own."""
        path = self.feature_dir / designsections.DESIGN_FILE
        if text is not None or not path.is_file():
            path.write_text(TECHNICAL_DESIGN if text is None else text, encoding="utf-8", newline="\n")
        return path

    def write_design_reviews(self, verdict: str = "PASS") -> None:
        """A design review by every reviewer the design needs, of the design as it is, as they leave them before tasks."""
        digest = designreview.digest(self.feature_dir)
        for reviewer in designreview.needed(self.root, self.feature_dir, "FEAT-007"):
            path = designreview.review_path(self.feature_dir, reviewer)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"# {reviewer}: design\n\nDesign: {digest}\nVerdict: {verdict}\n", encoding="utf-8", newline="\n")

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
        raise ValueError(f"unknown pipeline step {last}")

    def write_docs(self) -> None:
        """A record that every routed task calls no library, as the orchestrator leaves them before the implement gate."""
        for found in route.routes(self.root, self.feature_dir, "FEAT-007"):
            docsrecord.add(self.root, self.feature_dir, "FEAT-007", found.task, None, None, None, "this test calls no library")

    def write_reviews(self, verdict: str = "PASS") -> None:
        """A report from every reviewer the routing names, as the orchestrator leaves them before the implement gate."""
        for found in route.routes(self.root, self.feature_dir, "FEAT-007"):
            for reviewer in found.reviewers:
                path = route.review_path(self.feature_dir, found.task, reviewer)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(f"# {reviewer}: {found.task}\n\nVerdict: {verdict}\n", encoding="utf-8", newline="\n")

    # -- transcripts ---------------------------------------------------------------------
    def transcript(self, *entries: dict, name: str = "session.jsonl") -> Path:
        path = self.transcripts / name
        path.write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")
        return path


def command_message(args: str = "FEAT-007 rules") -> dict:
    """How Claude Code stores a typed slash command in the transcript."""
    text = ("<command-message>greenlight:approve</command-message>\n<command-name>/greenlight:approve</command-name>\n"
            f"<command-args>{args}</command-args>")
    return {"role": "user", "content": text}


def typed(prompt_id: str, args: str = "FEAT-007 rules", **extra) -> dict:
    """The transcript entry Claude Code writes for an approval command the person typed."""
    return {"type": "user", "promptId": prompt_id, "promptSource": "typed", "turnOrigin": "human",
            "origin": {"kind": "human"}, "message": command_message(args), **extra}


def headless(prompt_id: str, args: str = "FEAT-007 rules") -> dict:
    return {"type": "user", "promptId": prompt_id, "turnOrigin": "sdk", "message": command_message(args)}


def injected(prompt_id: str, turn: str = "scheduled", kind: str | None = None) -> dict:
    entry = {"type": "user", "promptId": prompt_id, "promptSource": "system", "turnOrigin": turn, "isMeta": True}
    if kind:
        entry["origin"] = {"kind": kind}
    return entry
