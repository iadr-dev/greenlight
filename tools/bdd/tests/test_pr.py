"""`bdd pr`: the pull-request description comes from records, is safe to paste and never leaves the project."""
import contextlib
import io
import json
import os
import unittest

from bddlib import cli, pr, state

from tests.helpers import ProjectCase

BRIEF = """# Brief: FEAT-007 Order discounts

## The ask

> Give big orders a discount.

## Problem statement

Customers with large orders pay full price, which loses them to competitors. <!-- hidden comment -->
"""
REPORT = """# Report: FEAT-007 Order discounts

Verdict: FINDINGS
Review status: UNREVIEWED (autopilot)

## Findings

- Must fix:
  - The 1000 boundary has no example
- Should fix:
  - Rename the coupon step
- Unverifiable:
"""


class PrHelpers:
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
                code = cli.main(["pr", feature, *argv])
        finally:
            os.chdir(here)
        return code, out.getvalue(), err.getvalue()


class DescriptionTest(PrHelpers, ProjectCase):
    def test_the_description_is_built_from_the_records(self):
        self.prepare()
        code, out, _ = self.cli()
        self.assertEqual(code, 0)
        self.assertIn("# FEAT-007: Order discounts", out)
        self.assertIn("Customers with large orders pay full price", out)
        self.assertNotIn("hidden comment", out)
        self.assertIn("| Gate | Result |", out)
        self.assertIn("| test-design | pass |", out)
        self.assertIn("- rules: approved via self-reported", out)
        self.assertIn("Enforcement: **soft**", out)
        self.assertIn("**A-007.1** Amounts are in whole cents _(because the shop sells in cents)_", out)
        self.assertIn("| discover | 1200 | 14.5 |", out)
        self.assertNotIn("UNREVIEWED", out)

    def test_nothing_machine_specific_is_printed(self):
        self.prepare()
        _, out, _ = self.cli()
        for private in (str(self.root), self.root.as_posix(), "transcript", "prompt_id", "session_id"):
            self.assertNotIn(private, out)

    def test_autopilot_says_unreviewed_first(self):
        state.create(self.root, "FEAT-008", "Autopilot work", "autopilot")
        code, out, _ = self.cli(feature="FEAT-008")
        self.assertEqual(code, 0)
        self.assertTrue(out.splitlines()[2].startswith("> **UNREVIEWED.**"))

    def test_json_carries_the_same_facts(self):
        self.prepare()
        code, out, _ = self.cli("--json")
        facts = json.loads(out)
        self.assertEqual((code, facts["feature"], facts["trace"]["totals"]["rules"] >= 1), (0, "FEAT-007", True))
        self.assertEqual(facts["assumptions"][0]["id"], "A-007.1")
        self.assertEqual(facts["cost"]["discover"]["tokens"], 1200)

    def test_an_unknown_feature_is_refused(self):
        self.assertEqual(self.cli(feature="FEAT-999")[0], 2)


class AuditTest(PrHelpers, ProjectCase):
    def test_the_auditors_verdict_and_findings_are_listed(self):
        self.prepare()
        self.write(".bdd/features/%s/report.md" % self.feature_dir.name, REPORT)
        audit = pr.audit_of(self.feature_dir)
        self.assertEqual((audit["verdict"], audit["review"]), ("FINDINGS", "UNREVIEWED (autopilot)"))
        self.assertEqual(audit["must_fix"], ["The 1000 boundary has no example"])
        self.assertEqual(audit["should_fix"], ["Rename the coupon step"])
        self.assertEqual(audit["unverifiable"], [])
        _, out, _ = self.cli()
        self.assertIn("- Verdict: **FINDINGS**", out)
        self.assertIn("  - The 1000 boundary has no example", out)

    def test_without_a_report_it_says_so(self):
        self.prepare()
        self.assertIsNone(pr.audit_of(self.feature_dir))
        self.assertIn("No audit report yet", self.cli()[1])


class OutputTest(PrHelpers, ProjectCase):
    def test_the_description_is_written_to_a_fixed_file_in_the_project_root(self):
        self.prepare()
        code, out, _ = self.cli("--write")
        self.assertEqual((code, out.strip()), (0, "FEAT-007: wrote PULL_REQUEST.md"))
        self.assertIn("# FEAT-007", (self.root / "PULL_REQUEST.md").read_text(encoding="utf-8"))

    def test_an_existing_file_is_replaced_only_with_force(self):
        self.prepare()
        self.assertEqual(self.cli("--write")[0], 0)
        code, _, err = self.cli("--write")
        self.assertEqual(code, 2)
        self.assertIn("use --force", err)
        self.assertEqual(self.cli("--write", "--force")[0], 0)

    def test_a_folder_in_the_way_is_never_replaced(self):
        self.prepare()
        (self.root / "PULL_REQUEST.md").mkdir()
        self.assertEqual(self.cli("--write", "--force")[0], 2)

    def test_the_file_is_written_in_the_root_whatever_the_current_folder(self):
        self.prepare()
        (self.root / "sub").mkdir()
        out, err, here = io.StringIO(), io.StringIO(), os.getcwd()
        os.chdir(self.root / "sub")
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = cli.main(["pr", "FEAT-007", "--write"])
        finally:
            os.chdir(here)
        self.assertEqual(code, 0, err.getvalue())
        self.assertTrue((self.root / "PULL_REQUEST.md").is_file())
        self.assertFalse((self.root / "sub" / "PULL_REQUEST.md").exists())

    def test_there_is_no_way_to_choose_the_path(self):
        self.prepare()
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.cli("--output", "../outside.md")


if __name__ == "__main__":
    unittest.main()
