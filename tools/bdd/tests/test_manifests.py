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

    def test_wrapper_uses_lf_line_endings(self):
        raw = (ROOT / "tools/bdd/bdd").read_bytes()
        self.assertNotIn(b"\r\n", raw, "tools/bdd/bdd must use LF line endings")
        self.assertTrue(raw.startswith(b"#!/bin/sh"))


if __name__ == "__main__":
    unittest.main()
