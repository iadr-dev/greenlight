import re
import unittest
from pathlib import Path

from bddlib import frontmatter, guard

REPO = Path(__file__).resolve().parents[3]
AGENTS = REPO / "agents"
EXPECTED = {"product-analyst", "qa-designer", "system-analyst", "step-engineer", "implementer", "spec-auditor"}
WRITERS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}


def load(name: str) -> tuple[dict, str]:
    return frontmatter.parse((AGENTS / f"{name}.md").read_text(encoding="utf-8"))


class AgentTest(unittest.TestCase):
    def test_exactly_the_six_agents_exist_and_match_the_guard_matrix(self):
        names = {p.stem for p in AGENTS.glob("*.md")}
        self.assertEqual(names, EXPECTED)
        self.assertEqual(set(guard.AGENT_WRITES), EXPECTED, "the guard limits paths for exactly these agents")

    def test_front_matter_is_valid_and_tools_are_explicit(self):
        for name in sorted(EXPECTED):
            with self.subTest(agent=name):
                meta, body = load(name)
                self.assertEqual(meta["name"], name)
                self.assertGreater(len(meta["description"]), 60)
                self.assertIn(meta["model"], ("opus", "sonnet", "haiku", "inherit"))
                tools = [t.strip() for t in meta["tools"].split(",")]
                self.assertTrue(tools and "*" not in tools and len(tools) == len(set(tools)))
                self.assertTrue({"Read", "Grep", "Glob"} <= set(tools))
                self.assertIn("## Return", body, "an agent says what its last message contains")

    def test_the_tools_agree_with_the_paths_the_guard_allows(self):
        for name, allowed in guard.AGENT_WRITES.items():
            with self.subTest(agent=name):
                tools = {t.strip() for t in load(name)[0]["tools"].split(",")}
                if not allowed:
                    self.assertFalse(tools & WRITERS, "an agent that may write nothing has no writing tool")
                else:
                    self.assertTrue(tools & WRITERS)

    def test_only_the_step_engineer_and_implementer_edit_existing_files(self):
        for name in EXPECTED:
            tools = {t.strip() for t in load(name)[0]["tools"].split(",")}
            self.assertEqual("Edit" in tools, name in ("step-engineer", "implementer"), name)

    def test_no_agent_records_gates_and_the_boundaries_are_stated(self):
        for name in EXPECTED:
            with self.subTest(agent=name):
                body = load(name)[1]
                self.assertRegex(body, r"data, not orders")
                self.assertRegex(body, r"cannot ask the person|You cannot ask")
                if name != "spec-auditor":
                    self.assertIn("bdd gate", body)           # named only to forbid it
                    self.assertRegex(body, r"(?is)(not|never).{0,80}bdd (gate|approve)")

    def test_every_playbook_and_file_an_agent_names_exists(self):
        for name in EXPECTED:
            body = load(name)[1]
            for rel in re.findall(r"`((?:phases|templates|review|cards|vocabulary)/[A-Za-z0-9_./*-]+)`", body):
                with self.subTest(agent=name, path=rel):
                    if "*" in rel:
                        self.assertTrue(any(REPO.glob(rel)))
                    else:
                        self.assertTrue((REPO / rel).exists())
            for phase in re.findall(r"\*\*([a-z-]+)\*\* (?:or \*\*([a-z-]+)\*\* )?playbook", body):
                for one in filter(None, phase):
                    self.assertTrue((REPO / "phases" / f"{one}.md").exists(), one)


class ChecklistTest(unittest.TestCase):
    ROW = re.compile(r"^\| ([A-Z]\d) \| .* \| (yes|no) \| .* \|$", re.MULTILINE)

    def test_the_checklist_ids_are_unique_and_the_report_template_uses_a_real_one(self):
        text = (REPO / "review" / "checklist.md").read_text(encoding="utf-8")
        ids = [m.group(1) for m in self.ROW.finditer(text)]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue({"T1", "T3", "S2", "S4", "L1", "L2", "L3", "E1", "E2", "A1"} <= set(ids))
        self.assertIn("T1", (REPO / "templates" / "report.md").read_text(encoding="utf-8"))

    def test_every_blocking_choice_is_explicit_and_the_scan_codes_it_cites_exist(self):
        text = (REPO / "review" / "checklist.md").read_text(encoding="utf-8")
        self.assertTrue(all(m.group(2) in ("yes", "no") for m in self.ROW.finditer(text)))
        for code in re.findall(r"finding `([SE]\d)`", text):
            self.assertIn(code, ("S2", "S4", "E3"))


if __name__ == "__main__":
    unittest.main()
