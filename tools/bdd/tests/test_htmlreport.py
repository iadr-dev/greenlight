"""`bdd report`: a readable HTML report that comes from the records, is self-contained and safe to share, and is written only
where it may be."""
import contextlib
import io
import os
import shutil
import unittest
from html.parser import HTMLParser
from unittest import mock

from bddlib import cli, htmlreport, state

from tests.helpers import ProjectCase

BRIEF = """# Brief: FEAT-007 Order discounts

## Problem statement

Customers with large orders pay full price. <!-- hidden comment -->
"""
REPORT = """# Report: FEAT-007 Order discounts

Verdict: FINDINGS
Review status: UNREVIEWED (autopilot)

## Findings

- Must fix:
  - The 1000 boundary has no example
- Should fix:
- Unverifiable:
"""
VOID = {"meta", "br", "hr", "img", "input", "link"}


class Balanced(HTMLParser):
    """Checks that every tag that is opened is closed in order."""

    def __init__(self):
        super().__init__()
        self.stack: list[str] = []
        self.problems: list[str] = []
        self.tags: set[str] = set()

    def handle_starttag(self, tag, attrs):
        self.tags.add(tag)
        if tag not in VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if not self.stack or self.stack[-1] != tag:
            self.problems.append(f"</{tag}> closes {self.stack[-1:] or 'nothing'}")
        else:
            self.stack.pop()


class ReportHelpers:
    def prepare(self) -> None:
        self.write(".bdd/features/%s/brief.md" % self.feature_dir.name, BRIEF)
        self.rules.write_text("# Rules\n\nR-007.1 Orders of 1000 or more get 10% off.\n", encoding="utf-8", newline="\n")
        self.walk_to("examples")
        state.add_assumption(self.feature_dir, "Amounts are in whole cents", "the shop sells in cents", [])
        state.add_cost(self.feature_dir, "discover", 1200, 14.5)

    def cli(self, *argv: str, feature: str = "FEAT-007") -> tuple[int, str, str]:
        out, err, here = io.StringIO(), io.StringIO(), os.getcwd()
        os.chdir(self.root)
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = cli.main(["report", feature, *argv])
        finally:
            os.chdir(here)
        return code, out.getvalue(), err.getvalue()


class PageTest(ReportHelpers, ProjectCase):
    def test_the_page_is_built_from_the_records(self):
        self.prepare()
        code, page, _ = self.cli()
        self.assertEqual(code, 0)
        self.assertIn("<h1>FEAT-007: Order discounts</h1>", page)
        self.assertIn("Customers with large orders pay full price.", page)
        self.assertNotIn("hidden comment", page)
        self.assertIn("R-007.1", page)
        self.assertIn("Orders of 1000 or more get 10% off.", page)
        self.assertIn("test-design", page)
        self.assertIn("self-reported", page)
        self.assertIn("Amounts are in whole cents", page)
        self.assertIn("1200", page)
        self.assertNotIn("UNREVIEWED", page)

    def test_the_page_is_well_formed_and_marked_as_generated(self):
        self.prepare()
        _, page, _ = self.cli()
        self.assertTrue(page.startswith("<!DOCTYPE html>\n" + htmlreport.MARKER))
        parser = Balanced()
        parser.feed(page)
        self.assertEqual(parser.problems, [])
        self.assertEqual(parser.stack, [])
        self.assertLessEqual({"h1", "h2", "table", "style", "title"}, parser.tags)

    def test_the_page_is_self_contained(self):
        self.prepare()
        _, page, _ = self.cli()
        for outside in ("<script", "<link", "<img", "<iframe", "http://", "https://", "src=", "@import", "url("):
            self.assertNotIn(outside, page)

    def test_text_from_the_records_cannot_become_markup(self):
        self.prepare()
        self.rules.write_text("# Rules\n\nR-007.1 <script>alert(1)</script> & \"quotes\"\n", encoding="utf-8", newline="\n")
        state.add_assumption(self.feature_dir, "<img src=x onerror=alert(1)>", "<b>because</b>", [])
        _, page, _ = self.cli()
        self.assertNotIn("<script>alert", page)
        self.assertNotIn("<img src=x", page)
        self.assertNotIn("<b>because</b>", page)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt; &amp; &quot;quotes&quot;", page)

    def test_nothing_machine_specific_is_in_the_page(self):
        self.prepare()
        _, page, _ = self.cli()
        for private in (str(self.root), self.root.as_posix(), "transcript", "prompt_id", "session_id"):
            self.assertNotIn(private, page)

    def test_autopilot_says_unreviewed_and_soft_enforcement_says_why(self):
        state.create(self.root, "FEAT-008", "Autopilot work", "autopilot")
        code, page, _ = self.cli(feature="FEAT-008")
        self.assertEqual(code, 0)
        self.assertIn("UNREVIEWED", page)
        self.assertIn("Soft enforcement", page)

    def test_the_auditors_verdict_and_findings_are_shown(self):
        self.prepare()
        self.write(".bdd/features/%s/report.md" % self.feature_dir.name, REPORT)
        _, page, _ = self.cli()
        self.assertIn("FINDINGS", page)
        self.assertIn("The 1000 boundary has no example", page)

    def test_without_an_audit_report_it_says_so(self):
        self.prepare()
        _, page, _ = self.cli()
        self.assertIn("No audit report yet", page)

    def test_a_brand_new_feature_whose_feature_folder_is_not_made_yet_still_has_a_report(self):
        shutil.rmtree(self.root / "features")
        code, page, err = self.cli()
        self.assertEqual((code, err), (0, ""))
        self.assertIn("<h1>FEAT-007: Order discounts</h1>", page)

    def test_an_unknown_feature_is_refused(self):
        code, _, err = self.cli(feature="FEAT-099")
        self.assertNotEqual(code, 0)
        self.assertIn("FEAT-099", err)


class ScenarioResultsTest(ReportHelpers, ProjectCase):
    """What every scenario did in the red run and in the latest run."""

    def test_the_results_of_both_runs_are_shown_next_to_each_example(self):
        self.prepare()
        self.config(tail='[adapters.run]\nby_tag = "echo {tag}"\nreport = "--out {out}"\n')
        rows = {"red": [{"example": "EX-7.1.1", "result": "expected-fail"}], "latest": [{"example": "EX-7.1.1", "result": "pass"}]}

        def classified(record, scenarios, rules):
            return {"scenarios": rows[record]}

        with (mock.patch.object(htmlreport.classify, "feature_scenarios", return_value=[]),
              mock.patch.object(htmlreport.classify, "classify_run", side_effect=classified),
              mock.patch.object(htmlreport.runner, "load_red", return_value="red"),
              mock.patch.object(htmlreport.runner, "load_latest", return_value="latest")):
            found = htmlreport.scenario_results(self.root, "FEAT-007", self.data())
        self.assertEqual(found, {"EX-7.1.1": {"red": "expected-fail", "latest": "pass"}})

    def test_a_missing_run_leaves_the_cell_empty_and_never_stops_the_report(self):
        self.prepare()
        self.config(tail='[adapters.run]\nby_tag = "echo {tag}"\nreport = "--out {out}"\n')
        code, page, _ = self.cli()
        self.assertEqual(code, 0)
        self.assertIn("Red run", page)

    def test_results_are_badges_with_their_meaning(self):
        self.assertIn("good", htmlreport.result_badge("pass"))
        self.assertIn("info", htmlreport.result_badge("expected-fail"))
        self.assertIn("bad", htmlreport.result_badge("test-defect"))
        self.assertIn("warn", htmlreport.result_badge("not-run"))
        self.assertIn("muted", htmlreport.result_badge(None))


class OutputTest(ReportHelpers, ProjectCase):
    def test_the_page_is_written_where_it_is_asked_and_folders_are_made(self):
        self.prepare()
        code, out, _ = self.cli("--out", "reports/deep/FEAT-007.html")
        self.assertEqual(code, 0)
        self.assertIn("wrote", out)
        page = (self.root / "reports" / "deep" / "FEAT-007.html").read_text(encoding="utf-8")
        self.assertIn(htmlreport.MARKER, page)

    def test_a_page_this_command_wrote_is_replaced_by_the_next_run(self):
        self.prepare()
        self.cli("--out", "report.html")
        state.add_assumption(self.feature_dir, "A second assumption", "it came later", [])
        code, _, _ = self.cli("--out", "report.html")
        self.assertEqual(code, 0)
        self.assertIn("A second assumption", (self.root / "report.html").read_text(encoding="utf-8"))

    def test_a_file_this_command_did_not_write_is_never_replaced(self):
        self.prepare()
        mine = self.write("notes.html", "<p>my own notes</p>")
        code, _, err = self.cli("--out", "notes.html")
        self.assertEqual(code, 2)
        self.assertIn("never replaced", err)
        self.assertEqual(mine.read_text(encoding="utf-8"), "<p>my own notes</p>")

    def test_the_records_folder_is_not_written_to(self):
        self.prepare()
        code, _, err = self.cli("--out", ".bdd/features/report.html")
        self.assertEqual(code, 2)
        self.assertIn("holds the records", err)
        self.assertFalse((self.root / ".bdd" / "features" / "report.html").exists())

    def test_a_folder_in_the_way_is_not_written_over(self):
        self.prepare()
        (self.root / "report.html").mkdir()
        code, _, err = self.cli("--out", "report.html")
        self.assertEqual(code, 2)
        self.assertIn("is a folder", err)

    def test_a_link_in_the_way_is_not_followed(self):
        self.prepare()
        target = self.write("elsewhere.html", "<p>keep</p>")
        link = self.root / "report.html"
        try:
            link.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("this system cannot make a symbolic link")
        code, _, err = self.cli("--out", "report.html")
        self.assertEqual(code, 2)
        self.assertIn("is a link", err)
        self.assertEqual(target.read_text(encoding="utf-8"), "<p>keep</p>")


if __name__ == "__main__":
    unittest.main()
