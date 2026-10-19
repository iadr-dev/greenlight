import contextlib
import io
import json
import os
import unittest

from bddlib import reportcmd, trace

from tests.helpers import ProjectCase

SPEC = """@FEAT-007
Feature: Discounts

  @R-007.1
  Rule: Big orders get 10% off

    @EX-007.1.1
    Scenario: Order of exactly 1000
      Then the request succeeds

    @EX-007.1.2
    Scenario: Order of 999
      Then the request succeeds

  @R-007.2
  Rule: Coupons stack once

    @EX-007.2.1
    Scenario: Two coupons
      Then the request succeeds
"""
RULES = """# Rules

1. **R-007.1** Orders of 1000 or more get 10% off.
- R-007.2: Coupons stack once.
- N-007.1 Responses take under a second.
"""
DESIGN = """# Test design

- EX-007.1.1 exactly at the threshold
- EX-007.1.2 just below the threshold
- EX-007.2.1 two coupons
"""
TASKS = """# Tasks

## T-007.1 Threshold discount
Covers EX-007.1.1 and EX-007.1.2.

## T-007.2 Coupons
Covers EX-007.2.1.
"""


class TraceCase(ProjectCase):
    def setUp(self):
        super().setUp()
        self.write("features/discounts.feature", SPEC)

    def put(self, name: str, text: str) -> None:
        (self.feature_dir / name).write_text(text, encoding="utf-8", newline="\n")

    def build(self) -> dict:
        return trace.build(self.root, self.feature_dir, "FEAT-007")

    def codes(self, report: dict) -> list[str]:
        return [g["code"] for g in report["gaps"]]


class MatrixTest(TraceCase):
    def test_a_complete_feature_has_no_gaps(self):
        self.put("rules.md", RULES)
        self.put("test-design.md", DESIGN)
        self.put("tasks.md", TASKS)
        report = self.build()
        self.assertEqual(report["gaps"], [])
        by_id = {r["id"]: r for r in report["rules"]}
        first, second = by_id["R-007.1"], by_id["R-007.2"]
        self.assertEqual((first["id"], first["text"]), ("R-007.1", "Orders of 1000 or more get 10% off."))
        self.assertEqual([e["id"] for e in first["examples"]], ["EX-007.1.1", "EX-007.1.2"])
        example = first["examples"][0]
        self.assertEqual(example["tasks"], ["T-007.1"])
        self.assertEqual((example["scenarios"][0]["path"], example["scenarios"][0]["name"]),
                         ("features/discounts.feature", "Order of exactly 1000"))
        self.assertEqual(second["examples"][0]["tasks"], ["T-007.2"])
        self.assertEqual(report["totals"], {"rules": 3, "examples": 3, "scenarios": 3, "tasks": 2})

    def test_non_functional_requirements_are_listed_but_need_no_example(self):
        self.put("rules.md", RULES)
        report = self.build()
        self.assertIn("N-007.1", [r["id"] for r in report["rules"]])
        self.assertNotIn("T001", self.codes(report))

    def test_only_what_exists_is_compared(self):
        report = self.build()                              # scenarios only: no rules, design or tasks yet
        self.assertEqual(report["gaps"], [])
        self.assertEqual(report["sources"], {"rules.md": False, "test-design.md": False, "tasks.md": False, "scenarios": 3})
        self.assertEqual([r["id"] for r in report["rules"]], ["R-007.1", "R-007.2"])

    def test_rendering_is_a_markdown_table(self):
        self.put("rules.md", RULES)
        self.put("tasks.md", TASKS)
        text = trace.render(self.build())
        self.assertIn("| Rule | Example | Scenario | Task |", text)
        self.assertIn("| R-007.1 Orders of 1000 or more get 10% off. | EX-007.1.1 | features/discounts.feature:8 Order of exactly 1000 | T-007.1 |", text)
        self.assertIn("No gaps.", text)


class GapTest(TraceCase):
    def test_a_rule_without_an_example(self):
        self.put("rules.md", RULES + "- R-007.3 Free shipping over 50.\n")
        report = self.build()
        self.assertEqual(self.codes(report), ["T001"])
        self.assertIn("R-007.3 has no example", report["gaps"][0]["message"])

    def test_an_example_without_a_scenario(self):
        self.put("test-design.md", DESIGN + "- EX-007.2.2 coupon after expiry\n")
        report = self.build()
        self.assertEqual(self.codes(report), ["T002"])

    def test_a_scenario_whose_example_or_rule_is_not_in_the_design(self):
        self.put("rules.md", "- R-007.1 only this rule\n")
        self.put("test-design.md", "- EX-007.1.1 only this example\n")
        report = self.build()
        self.assertEqual(sorted(self.codes(report)), ["T003", "T003", "T004"])

    def test_tasks_must_name_known_examples_and_own_every_scenario(self):
        self.put("tasks.md", "## T-007.1 One\nCovers EX-007.1.1 and EX-007.9.9.\n")
        report = self.build()
        self.assertEqual(sorted(self.codes(report)), ["T005", "T006", "T006"])

    def test_a_scenario_without_an_example_tag_and_an_unreadable_file(self):
        self.write("features/more.feature", "@FEAT-007\nFeature: More\n  @R-007.1\n  Scenario: Untagged\n    Then the request succeeds\n")
        self.write("features/broken.feature", "@FEAT-007\nFeature: Broken\n  @dangling\n")
        report = self.build()
        self.assertEqual(sorted(self.codes(report)), ["T000", "T007"])
        self.assertIn("features/broken.feature", " ".join(g["message"] for g in report["gaps"]))


class CommandTest(TraceCase):
    def run_trace(self, *args: str) -> tuple[int, str, str]:
        out, err, here = io.StringIO(), io.StringIO(), os.getcwd()
        os.chdir(self.root)
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = reportcmd.run_trace(list(args))
        finally:
            os.chdir(here)
        return code, out.getvalue(), err.getvalue()

    def test_exit_status_follows_the_gaps_and_json_is_machine_readable(self):
        self.put("rules.md", RULES)
        self.put("test-design.md", DESIGN)
        self.put("tasks.md", TASKS)
        code, out, _ = self.run_trace("FEAT-007", "--json")
        self.assertEqual((code, json.loads(out)["gaps"]), (0, []))
        self.put("test-design.md", DESIGN + "- EX-007.2.2 more\n")
        self.assertEqual(self.run_trace("--json", "FEAT-007")[0], 1)
        code, out, _ = self.run_trace("FEAT-007")
        self.assertEqual(code, 1)
        self.assertIn("T002 EX-007.2.2 has no scenario", out)

    def test_unknown_feature(self):
        code, _, err = self.run_trace("FEAT-099")
        self.assertEqual(code, 2)
        self.assertIn("FEAT-099", err)


if __name__ == "__main__":
    unittest.main()
