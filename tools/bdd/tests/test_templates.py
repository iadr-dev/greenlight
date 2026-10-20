import contextlib
import io
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from bddlib import cli, design, scan, state, trace

REPO = Path(__file__).resolve().parents[3]
TEMPLATES = REPO / "templates"
EXAMPLE = REPO / "docs" / "examples" / "order-discounts"

SECTIONS = {
    "brief.md": ["The ask", "The job behind it", "Problem statement", "Goals", "Non-goals", "Assumptions", "Open questions"],
    "rules.md": ["Business rules", "Non-functional requirements", "Out of scope"],
    "test-design.md": ["Coverage check"],
    "design.md": ["Components and data flow", "Key interaction"],
    "standards.md": ["Language and toolchain", "Style", "Quality rules", "Deprecation policy", "Dependencies"],
    "system.md": ["Interfaces", "Dependencies", "Clock", "Seams that do not exist yet"],
    "tasks.md": [],
    "report.md": ["Traceability", "Gates, locks and approvals", "Checklist", "Findings", "Cost"],
    "glossary.md": [],
    "change-requests.md": [],
}


class TemplateTest(unittest.TestCase):
    def test_every_template_exists_with_its_sections_and_names_its_writer(self):
        for name, headings in SECTIONS.items():
            with self.subTest(template=name):
                text = (TEMPLATES / name).read_text(encoding="utf-8")
                self.assertTrue(text.startswith("# "), "a template starts with a title")
                for heading in headings:
                    self.assertIn(f"## {heading}", text)
                self.assertIn("<!--", text, "a template says who writes it and how it is read")

    def test_the_templates_use_the_id_formats_that_trace_reads(self):
        rules = trace.read_ids(TEMPLATES / "rules.md", trace.RULE_LINE)
        self.assertEqual(sorted(rules), ["N-000.1", "R-000.1", "R-000.2"])
        examples = trace.read_ids(TEMPLATES / "test-design.md", trace.EXAMPLE_LINE)
        self.assertEqual(sorted(examples), ["EX-000.1.1", "EX-000.1.2", "EX-000.1.3"])
        tasks = trace.read_tasks(TEMPLATES / "tasks.md")
        self.assertEqual({k: v["examples"] for k, v in tasks.items()},
                         {"T-000.1": ["EX-000.1.1", "EX-000.1.2"], "T-000.2": ["EX-000.1.3"]})

    def test_the_template_design_view_passes_its_own_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            shutil.copyfile(TEMPLATES / "design.md", folder / "design.md")
            shutil.copyfile(TEMPLATES / "system.md", folder / "system.md")
            self.assertEqual(design.lint(folder), [])

    def test_the_template_system_map_lists_its_dependencies_for_the_scan(self):
        self.assertEqual(scan.declared_dependencies(TEMPLATES / "system.md"), {"payments"})


class ExampleFeatureTest(unittest.TestCase):
    """The filled-in example is consistent: lint is clean, trace has no gaps, the system map is readable."""

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.TemporaryDirectory()
        cls.root = Path(cls.dir.name).resolve()
        (cls.root / ".bdd").mkdir()
        (cls.root / ".bdd" / "config.toml").write_text(
            '[[adapters]]\nname = "x"\nfeatures = "features"\nsteps = "steps"\n', encoding="utf-8")
        shutil.copytree(EXAMPLE / "features", cls.root / "features")
        cls.feature_dir = state.create(cls.root, "FEAT-007", "Order discounts", "standard")
        for name in ("brief.md", "rules.md", "test-design.md", "system.md", "tasks.md", "design.md"):
            shutil.copyfile(EXAMPLE / name, cls.feature_dir / name)

    @classmethod
    def tearDownClass(cls):
        cls.dir.cleanup()

    def test_lint_is_clean(self):
        out, err, here = io.StringIO(), io.StringIO(), os.getcwd()
        os.chdir(self.root)
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = cli.main(["lint", "features"])
        finally:
            os.chdir(here)
        self.assertEqual(code, 0, out.getvalue() + err.getvalue())

    def test_trace_has_no_gaps_and_covers_every_rule(self):
        report = trace.build(self.root, self.feature_dir, "FEAT-007")
        self.assertEqual(report["gaps"], [])
        self.assertEqual(report["totals"], {"rules": 3, "examples": 4, "scenarios": 4, "tasks": 2})
        rules = {r["id"]: [e["id"] for e in r["examples"]] for r in report["rules"]}
        self.assertEqual(rules["R-007.1"], ["EX-007.1.1", "EX-007.1.2", "EX-007.1.3"])
        self.assertEqual(rules["R-007.2"], ["EX-007.2.1"])

    def test_the_system_map_declares_its_dependency(self):
        self.assertEqual(scan.declared_dependencies(self.feature_dir / "system.md"), {"payments"})


if __name__ == "__main__":
    unittest.main()
