"""Consistency checks for the plugin package (manifests, skills, version numbers)."""
import json
import unittest
from pathlib import Path

from bddlib import __version__
from bddlib.frontmatter import parse

ROOT = Path(__file__).resolve().parents[3]
SKILLS = {"init", "feature", "approve", "status", "change", "adopt"}  # the only user-typed commands


def load(rel: str) -> dict:
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


class ManifestTest(unittest.TestCase):
    def test_plugin_json(self):
        m = load(".claude-plugin/plugin.json")
        self.assertEqual(m["name"], "greenlight")
        for key in ("version", "description", "license", "repository"):
            self.assertTrue(m.get(key), f"plugin.json missing {key}")

    def test_marketplace_points_at_this_plugin(self):
        mk = load(".claude-plugin/marketplace.json")
        self.assertTrue(mk.get("description"))
        self.assertTrue(mk["owner"]["name"])
        (entry,) = mk["plugins"]
        self.assertEqual(entry["name"], load(".claude-plugin/plugin.json")["name"])
        self.assertEqual(entry["source"], "./")

    def test_versions_agree(self):
        plugin = load(".claude-plugin/plugin.json")["version"]
        market = load(".claude-plugin/marketplace.json")["plugins"][0]["version"]
        self.assertEqual({plugin, market}, {__version__}, "plugin.json, marketplace.json and bddlib disagree")

    def test_skills_have_valid_frontmatter(self):
        found = {p.parent.name for p in (ROOT / "skills").glob("*/SKILL.md")}
        self.assertTrue(found <= SKILLS, f"unexpected skills (only {sorted(SKILLS)} are allowed): {found - SKILLS}")
        self.assertIn("init", found)
        for name in found:
            meta, body = parse((ROOT / "skills" / name / "SKILL.md").read_text(encoding="utf-8"))
            with self.subTest(skill=name):
                self.assertEqual(meta.get("name"), name)
                self.assertGreater(len(meta.get("description", "")), 40, "description must say what and when")
                self.assertTrue(body.strip())

    def test_hooks_cover_every_tool_the_guard_handles(self):
        from bddlib import guard
        hooks = load("hooks/hooks.json")["hooks"]["PreToolUse"]
        (entry,) = hooks
        matched = set(entry["matcher"].split("|"))
        handled = set(guard.WRITE_TOOLS) | guard.INJECTION_TOOLS | {"Bash"}
        self.assertEqual(matched, handled, "hooks.json matcher and bddlib.guard disagree")
        (command,) = entry["hooks"]
        self.assertEqual(command["type"], "command")
        self.assertEqual(command["command"], 'sh "${CLAUDE_PLUGIN_ROOT}/tools/bdd/bdd" guard')

    def test_every_prompt_reaches_the_approval_hook_and_the_baseline_refresh(self):
        (entry,) = load("hooks/hooks.json")["hooks"]["UserPromptSubmit"]
        self.assertNotIn("matcher", entry)                      # UserPromptSubmit has no matcher: it sees every prompt
        commands = [c["command"] for c in entry["hooks"]]
        self.assertEqual(commands, ['sh "${CLAUDE_PLUGIN_ROOT}/tools/bdd/bdd" approve --from-hook',
                                    'sh "${CLAUDE_PLUGIN_ROOT}/tools/bdd/bdd" tripwire --accept'])

    def test_the_tripwire_runs_after_every_tool_the_guard_checks_and_after_mcp_tools(self):
        from bddlib import guard
        (entry,) = load("hooks/hooks.json")["hooks"]["PostToolUse"]
        matched = set(entry["matcher"].split("|"))
        self.assertEqual(matched, set(guard.WRITE_TOOLS) | guard.INJECTION_TOOLS | {"Bash", "mcp__.*"})
        (command,) = entry["hooks"]
        self.assertEqual(command["command"], 'sh "${CLAUDE_PLUGIN_ROOT}/tools/bdd/bdd" tripwire')

    def test_the_approve_skill_cannot_be_invoked_by_the_model(self):
        meta, _ = parse((ROOT / "skills" / "approve" / "SKILL.md").read_text(encoding="utf-8"))
        self.assertEqual(meta.get("disable-model-invocation"), "true")

    def test_every_hook_command_is_a_real_bdd_command(self):
        """An unknown command exits 2, which would block every prompt or tool call."""
        import re
        from bddlib.cli import COMMANDS
        used = []
        for entries in load("hooks/hooks.json")["hooks"].values():
            for entry in entries:
                used += [c["command"] for c in entry["hooks"]]
        self.assertTrue(used)
        for command in used:
            with self.subTest(command=command):
                match = re.fullmatch(r'sh "\$\{CLAUDE_PLUGIN_ROOT\}/tools/bdd/bdd" (\w+)(?: .*)?', command)
                self.assertIsNotNone(match)
                self.assertIn(match.group(1), COMMANDS)

    def test_wrapper_uses_lf_line_endings(self):
        raw = (ROOT / "tools/bdd/bdd").read_bytes()
        self.assertNotIn(b"\r\n", raw, "tools/bdd/bdd must use LF line endings")
        self.assertTrue(raw.startswith(b"#!/bin/sh"))


if __name__ == "__main__":
    unittest.main()
