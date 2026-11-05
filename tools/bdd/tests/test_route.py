"""`bdd route`: who writes and who reviews each task, decided from the task's scenarios and the words of its rules, and
the implement gate that waits for the routed reviews."""
import contextlib
import io
import json
import os

from bddlib import gates, reviewlog, route
from bddlib.errors import UsageError

from tests.helpers import ProjectCase

UI_SCENARIO = """
  @R-007.1
  Rule: The discount shows

    @EX-007.1.1
    Scenario: The banner
      When alice opens the orders page
      Then alice sees the discount banner showing:
        | text    |
        | 10% off |
"""
CLI_SCENARIO = """
  @R-007.2
  Rule: The export lists the discounts

    @EX-007.2.1
    Scenario: The export
      When alice runs export discounts
      Then the command succeeds
"""


class RouteCase(ProjectCase):
    def spec_with(self, *scenarios: str, background: str = "") -> None:
        self.write("features/discounts.feature", "@FEAT-007\nFeature: Discounts\n" + background + "".join(scenarios))

    def tasks(self, text: str) -> None:
        self.write(".bdd/features/FEAT-007-order-discounts/tasks.md", text)

    def routes(self) -> dict[str, route.Route]:
        return {r.task: r for r in route.routes(self.root, self.feature_dir, "FEAT-007")}


class WhoTest(RouteCase):
    def test_a_screen_task_and_a_plain_task_get_different_writers_and_reviewers(self):
        self.spec_with(UI_SCENARIO, CLI_SCENARIO)
        self.tasks("## T-007.1 Banner\nCovers: EX-007.1.1\n\n## T-007.2 Export\nCovers: EX-007.2.1\n")
        found = self.routes()
        self.assertEqual((found["T-007.1"].writer, found["T-007.1"].reviewers), ("ui-engineer", ["code-reviewer", "ui-reviewer"]))
        self.assertEqual((found["T-007.2"].writer, found["T-007.2"].reviewers), ("implementer", ["code-reviewer"]))
        self.assertEqual(found["T-007.1"].cards, ["ui-design", "accessibility"])
        self.assertIn("C.UI.OPEN", found["T-007.1"].because[0])

    def test_the_same_files_always_give_the_same_routing(self):
        self.spec_with(UI_SCENARIO, CLI_SCENARIO)
        self.tasks("## T-007.1 Both\nCovers: EX-007.1.1, EX-007.2.1\n")
        first = route.routes(self.root, self.feature_dir, "FEAT-007")
        second = route.routes(self.root, self.feature_dir, "FEAT-007")
        self.assertEqual(first, second)
        self.assertEqual(first[0].reviewers, ["code-reviewer", "ui-reviewer"])

    def test_a_signed_in_actor_in_the_background_makes_it_a_security_task(self):
        self.spec_with(CLI_SCENARIO, background="\n  Background:\n    Given alice is signed in as admin\n")
        self.tasks("## T-007.2 Export\nCovers: EX-007.2.1\n")
        found = self.routes()["T-007.2"]
        self.assertEqual(found.reviewers, ["code-reviewer", "security-reviewer"])
        self.assertIn("security", found.cards)

    def test_a_rule_about_money_makes_it_a_security_task_and_a_neutral_rule_does_not(self):
        self.spec_with(CLI_SCENARIO)
        self.tasks("## T-007.2 Export\nCovers: EX-007.2.1\n")
        self.rules.write_text("R-007.2 The export lists every discount.\n", encoding="utf-8", newline="\n")
        self.assertEqual(self.routes()["T-007.2"].reviewers, ["code-reviewer"])
        self.rules.write_text("R-007.2 The export lists every refund issued.\n", encoding="utf-8", newline="\n")
        found = self.routes()["T-007.2"]
        self.assertEqual(found.reviewers, ["code-reviewer", "security-reviewer"])
        self.assertIn("refund", found.because[-1])

    def test_a_project_step_counts_as_the_core_steps_it_composes(self):
        self.write(".bdd/vocabulary.toml", 'extends = "core"\n\n[[steps]]\nid = "D.CHECKOUT"\nkind = "when"\n'
                   'pattern = "{actor} checks out"\ncomposes = ["C.UI.OPEN", "C.UI.ACT"]\ndescription = "x"\n'
                   'justification = "x"\nowner = "x"\nmaps_to = {}\n')
        self.config(top_level='vocabulary = ".bdd/vocabulary.toml"\n')
        self.spec_with("\n  @R-007.3\n  Rule: Checkout\n\n    @EX-007.3.1\n    Scenario: C\n      When alice checks out\n")
        self.tasks("## T-007.3 Checkout\nCovers: EX-007.3.1\n")
        self.assertEqual(self.routes()["T-007.3"].writer, "ui-engineer")

    def test_examples_no_task_claims_are_still_routed_and_reviewed(self):
        self.spec_with(UI_SCENARIO, CLI_SCENARIO)
        self.tasks("## T-007.2 Export\nCovers: EX-007.2.1\n")         # the screen example left out of every task
        found = self.routes()
        self.assertEqual((found["T-007.0"].title, found["T-007.0"].writer), ("the examples no task claims", "ui-engineer"))
        self.tasks("# Tasks\n")                                          # an empty list is the whole feature
        self.assertEqual(list(self.routes()), ["T-007.0"])

    def test_a_task_md_that_uses_the_reserved_id_keeps_its_examples(self):
        self.spec_with(UI_SCENARIO, CLI_SCENARIO)
        self.tasks("## T-007.0 Export\nCovers: EX-007.2.1\n")           # the screen example claimed by nobody
        (only,) = self.routes().values()
        self.assertEqual((only.task, only.writer), ("T-007.0", "ui-engineer"))
        self.assertEqual(only.reviewers, ["code-reviewer", "ui-reviewer"], "merged, not overwritten")

    def test_without_tasks_md_the_whole_feature_is_one_task(self):
        self.spec_with(UI_SCENARIO, CLI_SCENARIO)
        (only,) = route.routes(self.root, self.feature_dir, "FEAT-007")
        self.assertEqual((only.task, only.writer), ("T-007.0", "ui-engineer"))
        self.assertEqual(only.reviewers, ["code-reviewer", "ui-reviewer"])


class GateTest(RouteCase):
    def setUp(self):
        super().setUp()
        self.spec_with(UI_SCENARIO)
        self.tasks("## T-007.1 Banner\nCovers: EX-007.1.1\n")
        self.walk_to("tasks")

    def problems(self) -> list[str]:
        return route.review_problems(self.root, self.feature_dir, "FEAT-007")

    def test_the_implement_gate_waits_for_every_routed_review(self):
        self.assertEqual(sorted(self.problems()), ["T-007.1 has no code-reviewer report (reviews/T-007.1-code-reviewer.md)",
                                                   "T-007.1 has no ui-reviewer report (reviews/T-007.1-ui-reviewer.md)"])
        with self.assertRaises(UsageError) as refused:
            self.gate("implement", reviews=False)
        self.assertIn("no ui-reviewer report", str(refused.exception))

    def test_a_report_without_a_verdict_does_not_count(self):
        self.write_reviews()
        route.review_path(self.feature_dir, "T-007.1", "ui-reviewer").write_text("# ui-reviewer\n\nlooks fine\n", encoding="utf-8")
        self.assertEqual(self.problems(), ["reviews/T-007.1-ui-reviewer.md has no 'Verdict: PASS' or 'Verdict: FINDINGS' line"])

    def test_with_every_review_in_place_the_gate_passes(self):
        self.write_reviews(verdict="FINDINGS")              # must-fix items left are for the auditor (Q6), not a gate deadlock
        self.write_docs()
        self.assertEqual(self.problems(), [])
        self.gate("implement", reviews=False)
        self.assertEqual(self.data()["phase"], "verify")

    def reviewer_writes(self, reviewer: str, content: str) -> None:
        """What happens in a real run: the guard sees the reviewer's Write first, then the file is written."""
        from bddlib import guard
        path = route.review_path(self.feature_dir, "T-007.1", reviewer)
        payload = {"tool_name": "Write", "agent_type": f"greenlight:{reviewer}", "cwd": str(self.root),
                   "tool_input": {"file_path": str(path), "content": content}}
        self.assertIsNone(guard.evaluate(payload))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")

    def test_where_the_hooks_run_a_report_counts_only_as_its_reviewer_wrote_it(self):
        self.write_reviews()                                     # written past the guard: no reviewer wrote them
        reasons = route.review_problems(self.root, self.feature_dir, "FEAT-007", hooks_seen=True)
        self.assertEqual(len(reasons), 2)
        self.assertIn("is not what the ui-reviewer agent wrote", " ".join(reasons))
        for reviewer in ("code-reviewer", "ui-reviewer"):
            self.reviewer_writes(reviewer, f"# {reviewer}: T-007.1\n\nVerdict: FINDINGS\n\n## Must fix\n- a.py:1 - x\n")
        self.assertEqual(route.review_problems(self.root, self.feature_dir, "FEAT-007", hooks_seen=True), [])
        report = route.review_path(self.feature_dir, "T-007.1", "ui-reviewer")
        report.write_text("# ui-reviewer: T-007.1\n\nVerdict: PASS\n", encoding="utf-8")      # changed afterwards, any way
        self.assertEqual(route.review_problems(self.root, self.feature_dir, "FEAT-007", hooks_seen=True),
                         ["reviews/T-007.1-ui-reviewer.md is not what the ui-reviewer agent wrote: a report counts only "
                          "as its own reviewer wrote it, unchanged; run the reviewer again"])

    def test_an_old_report_put_back_does_not_count(self):
        self.write_reviews()
        first = "# code-reviewer: T-007.1\n\nVerdict: PASS\n"
        second = "# code-reviewer: T-007.1\n\nVerdict: FINDINGS\n\n## Must fix\n- a.py:1 - x\n"
        self.reviewer_writes("code-reviewer", first)
        self.reviewer_writes("code-reviewer", second)
        report = route.review_path(self.feature_dir, "T-007.1", "code-reviewer")
        self.assertTrue(reviewlog.written_by(self.root, report, "code-reviewer"))
        report.write_text(first, encoding="utf-8", newline="\n")                 # the earlier, passing report restored
        self.assertFalse(reviewlog.written_by(self.root, report, "code-reviewer"))

    def test_a_report_counts_only_from_the_implement_phase_and_from_a_reviewer_that_finished(self):
        text = "# x\n\nVerdict: PASS\n"
        self.reviewer_writes("code-reviewer", text)
        report = route.review_path(self.feature_dir, "T-007.1", "code-reviewer")
        self.assertTrue(reviewlog.written_by(self.root, report, "code-reviewer"))
        reviewlog.record(self.root, report, "code-reviewer", text, agent_id="a1", phase="implement")
        self.assertFalse(reviewlog.written_by(self.root, report, "code-reviewer", finished={}))
        self.assertFalse(reviewlog.written_by(self.root, report, "code-reviewer", finished={"a1": "greenlight:implementer"}))
        self.assertTrue(reviewlog.written_by(self.root, report, "code-reviewer", finished={"a1": "greenlight:code-reviewer"}))
        reviewlog.record(self.root, report, "code-reviewer", text, agent_id="a1", phase="verify")
        self.assertFalse(reviewlog.written_by(self.root, report, "code-reviewer", finished={"a1": "greenlight:code-reviewer"}))

    def test_a_report_written_under_another_reviewers_name_does_not_count(self):
        from bddlib import reviewlog
        path = route.review_path(self.feature_dir, "T-007.1", "ui-reviewer")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("Verdict: PASS\n", encoding="utf-8")
        reviewlog.record(self.root, path, "code-reviewer", "Verdict: PASS\n")
        self.assertFalse(reviewlog.written_by(self.root, path, "ui-reviewer"))

    def test_deleting_tasks_md_does_not_skip_the_reviews(self):
        (self.feature_dir / "tasks.md").unlink()
        self.assertTrue(any("T-007.0" in p for p in self.problems()))
        self.assertTrue(any("ui-reviewer" in p for p in gates.gate_problems(self.root, self.feature_dir, self.data(), "implement")))


class CommandTest(RouteCase):
    def test_the_command_prints_each_task_and_its_json(self):
        self.spec_with(UI_SCENARIO)
        self.tasks("## T-007.1 Banner\nCovers: EX-007.1.1\n")
        from bddlib import cli
        for argv, expected in ((["route", "FEAT-007"], "writer: ui-engineer"), (["route", "FEAT-007", "--json"], '"writer": "ui-engineer"')):
            out, here = io.StringIO(), os.getcwd()
            os.chdir(self.root)
            try:
                with contextlib.redirect_stdout(out):
                    self.assertEqual(cli.main(argv), 0)
            finally:
                os.chdir(here)
            self.assertIn(expected, out.getvalue())
        self.assertEqual(json.loads(out.getvalue())[0]["cards"], ["ui-design", "accessibility"])
