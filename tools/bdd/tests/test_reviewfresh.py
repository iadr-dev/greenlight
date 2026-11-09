"""A review older than the production code of its task: found by hash at the implement gate."""
import shutil
import subprocess
import unittest
from pathlib import Path
from unittest import mock

from bddlib import agentcost, guard, reviewfresh, reviewlog, route, state
from bddlib.errors import UsageError

from tests.test_route import RouteCase, UI_SCENARIO
from tests.test_redrecord import run_git

GIT = shutil.which("git")
REPORT = "# {reviewer}: T-007.1\n\nVerdict: PASS\n"


class AreaPathsTest(unittest.TestCase):
    def test_paths_and_files_are_read_and_prose_is_ignored(self):
        self.assertEqual(reviewfresh.area_paths("api/src/customers/, api/src/routes/customers.ts and the sign-in module"),
                         ["api/src/customers/", "api/src/routes/customers.ts"])
        self.assertEqual(reviewfresh.area_paths("`src/*.py`; README.md; ./web/app"), ["src/*.py", "README.md", "web/app"])

    def test_the_template_placeholder_and_an_empty_line_name_nothing(self):
        self.assertEqual(reviewfresh.area_paths("<files or modules likely touched>"), [])
        self.assertEqual(reviewfresh.area_paths(""), [])

    def test_a_task_report_names_its_task(self):
        self.assertEqual(reviewfresh.task_of(Path("T-007.12-code-reviewer.md")), "T-007.12")
        self.assertIsNone(reviewfresh.task_of(Path("notes.md")))


@unittest.skipUnless(GIT, "needs git")
class StaleReviewTest(RouteCase):
    def setUp(self):
        super().setUp()
        self.spec_with(UI_SCENARIO)
        self.tasks("## T-007.1 Banner\nCovers: EX-007.1.1\nAreas: src/app.py\n")
        self.walk_to("tasks")
        self.write("src/app.py", "def price():\n    return 1\n")
        self.write("src/other.py", "x = 1\n")
        run_git(self.root, "init", "-q")
        run_git(self.root, "add", "-A")
        run_git(self.root, "commit", "-q", "-m", "red")
        head = subprocess.run(["git", "-C", str(self.root), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        state.update(self.feature_dir, lambda data: data.update(red={"commit": head}))
        self.write("src/app.py", "def price():\n    return 2\n")

    def reviewers_finish(self, *names: str) -> None:
        for reviewer in names:
            self.reviewer_writes(reviewer, REPORT.format(reviewer=reviewer))
            agentcost.note_agent({"agent_type": f"greenlight:{reviewer}", "agent_id": f"a-{reviewer}", "cwd": str(self.root),
                                  "session_id": "s", "duration_ms": 1})

    def problems(self) -> list[str]:
        return route.review_problems(self.root, self.feature_dir, "FEAT-007", hooks_seen=True)

    def reviewer_writes(self, reviewer: str, content: str) -> None:
        path = route.review_path(self.feature_dir, "T-007.1", reviewer)
        payload = {"tool_name": "Write", "agent_type": f"greenlight:{reviewer}", "agent_id": f"a-{reviewer}",
                   "cwd": str(self.root), "tool_input": {"file_path": str(path), "content": content}}
        self.assertIsNone(guard.evaluate(payload))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")

    def test_the_files_of_a_task_are_the_changed_files_its_areas_name(self):
        self.write("src/other.py", "x = 2\n")
        self.assertEqual(reviewfresh.files(self.root, self.feature_dir, "T-007.1"), ["src/app.py"])

    def test_a_task_without_areas_in_a_feature_of_one_task_covers_every_changed_file(self):
        self.tasks("## T-007.1 Banner\nCovers: EX-007.1.1\nAreas:\n")
        self.write("src/other.py", "x = 2\n")
        self.assertEqual(reviewfresh.files(self.root, self.feature_dir, "T-007.1"), ["src/app.py", "src/other.py"])

    def test_areas_that_match_no_changed_file_fall_back_to_the_rule_without_areas(self):
        self.tasks("## T-007.1 Banner\nCovers: EX-007.1.1\nAreas: lib/missing/\n")
        self.assertEqual(reviewfresh.files(self.root, self.feature_dir, "T-007.1"), ["src/app.py"])

    def test_with_several_tasks_and_no_areas_nothing_says_which_file_is_whose(self):
        self.tasks("## T-007.1 Banner\nCovers: EX-007.1.1\n\n## T-007.2 Other\nCovers: EX-007.2.1\n")
        self.assertIsNone(reviewfresh.files(self.root, self.feature_dir, "T-007.1"))
        self.assertIsNone(reviewfresh.scope(self.root, self.feature_dir, "T-007.1"))

    def test_pictures_and_logs_a_reviewer_leaves_behind_are_not_code(self):
        self.write("shot.png", "x")
        self.write("run.log", "x")
        self.tasks("## T-007.1 Banner\nCovers: EX-007.1.1\nAreas:\n")
        self.assertEqual(reviewfresh.files(self.root, self.feature_dir, "T-007.1"), ["src/app.py"])

    def test_a_feature_without_a_red_record_is_not_judged(self):
        state.update(self.feature_dir, lambda data: data.update(red=None))
        self.assertIsNone(reviewfresh.files(self.root, self.feature_dir, "T-007.1"))

    def test_a_review_of_the_code_as_it_is_stands(self):
        self.reviewers_finish("code-reviewer", "ui-reviewer")
        self.assertEqual(self.problems(), [])

    def test_a_production_edit_after_the_review_makes_it_older_than_the_code(self):
        self.reviewers_finish("code-reviewer", "ui-reviewer")
        self.write("src/app.py", "def price():\n    return 3\n")
        self.assertEqual(self.problems(), [
            "reviews/T-007.1-code-reviewer.md is older than the code it covers: src/app.py changed after the "
            "code-reviewer finished; run the code-reviewer again on it",
            "reviews/T-007.1-ui-reviewer.md is older than the code it covers: src/app.py changed after the "
            "ui-reviewer finished; run the ui-reviewer again on it"])

    def test_the_gate_refuses_it_and_a_review_written_after_the_edit_passes(self):
        self.write_docs()
        state.update(self.feature_dir, lambda data: data.update(hooks_seen=True))
        self.reviewers_finish("code-reviewer", "ui-reviewer")
        self.write("src/app.py", "def price():\n    return 3\n")
        with self.assertRaises(UsageError) as refused:
            self.gate("implement", reviews=False)
        self.assertIn("reviews/T-007.1-code-reviewer.md is older than the code it covers", str(refused.exception))
        self.reviewers_finish("code-reviewer", "ui-reviewer")
        self.assertEqual(self.problems(), [])

    def test_putting_the_file_back_as_it_was_is_no_change(self):
        self.reviewers_finish("code-reviewer", "ui-reviewer")
        self.write("src/app.py", "def price():\n    return 3\n")
        self.write("src/app.py", "def price():\n    return 2\n")
        self.assertEqual(self.problems(), [])

    def test_a_new_file_in_the_area_after_the_review_counts(self):
        self.tasks("## T-007.1 Banner\nCovers: EX-007.1.1\nAreas: src/\n")
        self.reviewers_finish("code-reviewer", "ui-reviewer")
        self.write("src/extra.py", "y = 1\n")
        self.assertIn("src/extra.py changed after the code-reviewer finished", " ".join(self.problems()))

    def test_a_change_outside_the_areas_of_the_task_does_not(self):
        self.reviewers_finish("code-reviewer", "ui-reviewer")
        self.write("src/other.py", "x = 99\n")
        self.assertEqual(self.problems(), [])

    def test_many_changed_files_are_summarised(self):
        self.tasks("## T-007.1 Banner\nCovers: EX-007.1.1\nAreas: src/\n")
        self.reviewers_finish("code-reviewer", "ui-reviewer")
        for name in ("a", "b", "c", "d", "e"):
            self.write(f"src/{name}.py", "z = 1\n")
        (found,) = [p for p in self.problems() if "code-reviewer" in p]
        self.assertIn("src/a.py, src/b.py, src/c.py and 2 more changed", found)

    def test_a_report_that_was_never_sealed_is_judged_as_before(self):
        with mock.patch.object(reviewlog, "seal", return_value=False):
            self.reviewers_finish("code-reviewer", "ui-reviewer")
        self.write("src/app.py", "def price():\n    return 3\n")
        self.assertEqual(self.problems(), [])

    def test_without_hooks_nothing_is_judged(self):
        self.reviewers_finish("code-reviewer", "ui-reviewer")
        self.write("src/app.py", "def price():\n    return 3\n")
        self.assertEqual(route.review_problems(self.root, self.feature_dir, "FEAT-007", hooks_seen=False), [])

    def test_only_a_reviewer_of_the_plugin_is_sealed(self):
        self.reviewer_writes("code-reviewer", REPORT.format(reviewer="code-reviewer"))
        agentcost.note_agent({"agent_type": "greenlight:implementer", "agent_id": "a-code-reviewer", "cwd": str(self.root),
                              "session_id": "s", "duration_ms": 1})
        self.assertNotIn("code", reviewlog.recorded(self.root)[
            (reviewlog.key(self.root, route.review_path(self.feature_dir, "T-007.1", "code-reviewer")), "code-reviewer")])
        agentcost.note_agent({"agent_type": "greenlight:code-reviewer", "agent_id": "a-code-reviewer", "cwd": str(self.root),
                              "session_id": "s", "duration_ms": 1})
        sealed = reviewlog.recorded(self.root)[
            (reviewlog.key(self.root, route.review_path(self.feature_dir, "T-007.1", "code-reviewer")), "code-reviewer")]
        self.assertEqual(list(sealed["code"]), ["src/app.py"])
        self.assertFalse(reviewlog.seal(self.root, "a-code-reviewer"))                          # sealing twice adds nothing

    def test_a_failure_while_sealing_never_reaches_the_agent(self):
        self.reviewer_writes("code-reviewer", REPORT.format(reviewer="code-reviewer"))
        (self.root / ".bdd" / "config.toml").write_text("not [valid", encoding="utf-8")
        self.assertFalse(reviewlog.seal(self.root, "a-code-reviewer"))


if __name__ == "__main__":
    unittest.main()
