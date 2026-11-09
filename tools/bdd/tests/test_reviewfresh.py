"""A review older than the production code of its task: found by hash at the implement gate."""
import json
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from bddlib import agentcost, guard, reviewfresh, reviewlog, route, state
from bddlib.errors import UsageError

from tests.test_route import CLI_SCENARIO, UI_SCENARIO, RouteCase
from tests.test_redrecord import run_git

GIT = shutil.which("git")
REPORT = "# {reviewer}: {task}\n\nVerdict: PASS\n"
ONE_TASK = "## T-007.1 Banner\nCovers: EX-007.1.1\nAreas: src/app.py\n"
TWO_TASKS = ("## T-007.1 Banner\nCovers: EX-007.1.1\nAreas: src/\n\n## T-007.2 Export\nCovers: EX-007.2.1\nAreas: src/\n")


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
        self.assertEqual(reviewfresh.task_of(Path("t-007.1-code-reviewer.md")), "t-007.1")
        self.assertIsNone(reviewfresh.task_of(Path("notes.md")))


@unittest.skipUnless(GIT, "needs git")
class FreshCase(RouteCase):
    """FEAT-007 in a git repository whose red was proven with src/app.py as it was, then src/app.py changed."""

    TASKS = ONE_TASK
    SCENARIOS = (UI_SCENARIO,)

    def setUp(self):
        super().setUp()
        self.spec_with(*self.SCENARIOS)
        self.tasks(self.TASKS)
        self.walk_to("tasks")
        self.write("src/app.py", "def price():\n    return 1\n")
        self.write("src/other.py", "x = 1\n")
        run_git(self.root, "init", "-q")
        run_git(self.root, "add", "-A")
        run_git(self.root, "commit", "-q", "-m", "red")
        head = subprocess.run(["git", "-C", self.root, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        state.update(self.feature_dir, lambda data: data.update(red={"commit": head}))
        self.write("src/app.py", "def price():\n    return 2\n")

    def reviewer_writes(self, reviewer: str, task: str = "T-007.1", agent: str | None = None) -> None:
        path = route.review_path(self.feature_dir, task, reviewer)
        content = REPORT.format(reviewer=reviewer, task=task)
        payload = {"tool_name": "Write", "agent_type": f"greenlight:{reviewer}", "agent_id": agent or f"a-{reviewer}-{task}",
                   "cwd": str(self.root), "tool_input": {"file_path": str(path), "content": content}}
        self.assertIsNone(guard.evaluate(payload))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")

    def reviewer_stops(self, reviewer: str, task: str = "T-007.1", agent: str | None = None) -> None:
        agentcost.note_agent({"agent_type": f"greenlight:{reviewer}", "agent_id": agent or f"a-{reviewer}-{task}",
                              "cwd": str(self.root), "session_id": "s", "duration_ms": 1})

    def review(self, reviewer: str, task: str = "T-007.1") -> None:
        self.reviewer_writes(reviewer, task)
        self.reviewer_stops(reviewer, task)

    def review_task_1(self) -> None:
        self.review("code-reviewer")
        self.review("ui-reviewer")

    def problems(self) -> list[str]:
        return route.review_problems(self.root, self.feature_dir, "FEAT-007", hooks_seen=True)

    def edit(self, text: str) -> None:
        self.write("src/app.py", f"def price():\n    return {text}\n")


class WhichFilesTest(FreshCase):
    def judge(self, task: str = "T-007.1") -> dict:
        return reviewfresh.judge(self.root, self.feature_dir, task)

    def test_the_files_of_a_task_are_the_changed_files_its_areas_name(self):
        self.write("src/other.py", "x = 2\n")
        code = self.judge()
        self.assertEqual((list(code["files"]), code["areas"]), (["src/app.py"], ["src/app.py"]))
        self.assertRegex(code["red"], "^[0-9a-f]{40}$")

    def test_a_task_without_areas_in_a_feature_of_one_task_covers_every_changed_file(self):
        self.tasks("## T-007.1 Banner\nCovers: EX-007.1.1\nAreas:\n")
        self.write("src/other.py", "x = 2\n")
        code = self.judge()
        self.assertEqual((sorted(code["files"]), code["areas"]), (["src/app.py", "src/other.py"], None))

    def test_areas_that_match_no_changed_file_fall_back_to_the_rule_without_areas(self):
        self.tasks("## T-007.1 Banner\nCovers: EX-007.1.1\nAreas: lib/missing/\n")
        self.assertEqual(list(self.judge()["files"]), ["src/app.py"])

    def test_with_several_tasks_and_no_areas_nothing_says_which_file_is_whose(self):
        self.tasks("## T-007.1 Banner\nCovers: EX-007.1.1\n\n## T-007.2 Other\nCovers: EX-007.2.1\n")
        with self.assertRaises(reviewfresh.Unjudged):
            self.judge()

    def test_pictures_logs_and_traces_a_reviewer_leaves_behind_are_not_code(self):
        for name in ("shot.png", "SHOT.PNG", "run.log", "page.har", "trace.zip", "heap.heapsnapshot"):
            self.write(name, "x")
        self.tasks("## T-007.1 Banner\nCovers: EX-007.1.1\nAreas:\n")
        self.assertEqual(list(self.judge()["files"]), ["src/app.py"])

    def test_what_a_test_tool_generates_is_not_code(self):
        for name in (".coverage", "coverage.xml", "htmlcov/index.html", "mutants/src/app.py", ".pytest_cache/v/lastfailed", "src/__pycache__/x.pyc"):
            self.write(name, "x")
        self.tasks("## T-007.1 Banner\nCovers: EX-007.1.1\nAreas:\n")
        self.assertEqual(list(self.judge()["files"]), ["src/app.py"])

    def test_areas_written_with_backslashes_are_read(self):
        self.assertEqual(reviewfresh.area_paths("src\\api\\, web\\app.ts"), ["src/api/", "web/app.ts"])

    def test_a_feature_without_a_red_record_is_not_judged(self):
        state.update(self.feature_dir, lambda data: data.update(red=None))
        with self.assertRaises(reviewfresh.Unjudged):
            self.judge()


class SealTest(FreshCase):
    def sealed(self, reviewer: str = "code-reviewer", task: str = "T-007.1") -> dict | None:
        return reviewlog.seals(self.root).get((reviewlog.key(self.root, route.review_path(self.feature_dir, task, reviewer)), reviewer))

    def test_a_reviewer_that_finishes_gets_a_seal_with_the_hashes_of_its_files(self):
        self.review("code-reviewer")
        seal = self.sealed()
        self.assertEqual(list(seal["code"]["files"]), ["src/app.py"])
        self.assertEqual((seal["agent_id"], seal["why"]), ("a-code-reviewer-T-007.1", None))

    def test_sealing_twice_adds_nothing(self):
        self.review("code-reviewer")
        self.assertFalse(reviewlog.seal(self.root, "a-code-reviewer-T-007.1"))

    def test_only_a_named_agent_seals(self):
        self.reviewer_writes("code-reviewer", agent="a1")
        for nobody in (None, ""):
            self.assertFalse(reviewlog.seal(self.root, nobody))
        self.assertIsNone(self.sealed())

    def test_a_report_without_an_agent_is_not_sealed_by_a_payload_without_one(self):
        path = route.review_path(self.feature_dir, "T-007.1", "code-reviewer")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("Verdict: PASS\n", encoding="utf-8")
        reviewlog.record(self.root, path, "code-reviewer", "Verdict: PASS\n", agent_id=None, phase="implement")
        self.assertFalse(reviewlog.seal(self.root, None))
        self.assertIsNone(self.sealed())

    def test_an_agent_that_finishes_late_cannot_seal_a_newer_report(self):
        self.reviewer_writes("code-reviewer", agent="old")
        self.reviewer_writes("code-reviewer", agent="new")
        self.assertFalse(reviewlog.seal(self.root, "old"))
        self.assertIsNone(self.sealed())
        self.assertTrue(reviewlog.seal(self.root, "new"))
        self.assertEqual(self.sealed()["agent_id"], "new")

    def test_a_replayed_old_seal_can_only_record_older_hashes_which_the_gate_reports(self):
        self.reviewer_writes("code-reviewer", agent="a1")
        reviewlog.seal(self.root, "a1")
        first = self.sealed()
        self.edit("3")
        self.reviewer_writes("code-reviewer", agent="a1")                        # the same agent, the same content again
        self.assertIsNone(self.sealed(), "the seal made before the new line does not cover it")
        log = self.root / reviewlog.LOG
        with log.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(first) + "\n")                              # the old seal put back after the new line
        self.assertIsNotNone(self.sealed())
        self.assertEqual(reviewfresh.changed(self.root, first["code"]), {"src/app.py": mock.ANY})

    def test_a_seal_for_another_hash_or_agent_is_ignored(self):
        self.reviewer_writes("code-reviewer", agent="a1")
        reviewlog.seal(self.root, "a1")
        seal = self.sealed()
        for forged in ({**seal, "seal": "0" * 64}, {**seal, "agent_id": "someone-else"}):
            lines = (self.root / reviewlog.LOG).read_text(encoding="utf-8").splitlines()
            lines = [line for line in lines if '"seal"' not in line] + [json.dumps(forged)]
            (self.root / reviewlog.LOG).write_text("\n".join(lines) + "\n", encoding="utf-8")
            self.assertIsNone(self.sealed())

    def test_a_task_that_cannot_be_judged_is_sealed_as_such(self):
        self.tasks("## T-007.1 Banner\nCovers: EX-007.1.1\n\n## T-007.2 Other\nCovers: EX-007.2.1\n")
        self.review("code-reviewer")
        seal = self.sealed()
        self.assertIsNone(seal["code"])
        self.assertIn("several tasks", seal["why"])

    def test_two_reports_of_one_agent_are_both_sealed(self):
        self.tasks(TWO_TASKS)
        self.reviewer_writes("code-reviewer", "T-007.1", agent="a1")
        self.reviewer_writes("code-reviewer", "T-007.2", agent="a1")
        self.assertTrue(reviewlog.seal(self.root, "a1"))
        self.assertIsNotNone(self.sealed("code-reviewer", "T-007.1"))
        self.assertIsNotNone(self.sealed("code-reviewer", "T-007.2"))

    def test_a_failure_while_sealing_never_reaches_the_agent_and_the_seal_says_why(self):
        self.reviewer_writes("code-reviewer", agent="a1")
        with mock.patch.object(reviewfresh, "judge", side_effect=RuntimeError("git is gone")):
            self.assertTrue(reviewlog.seal(self.root, "a1"))
        self.assertEqual(self.sealed()["error"], "RuntimeError: git is gone")
        self.assertIsNone(self.sealed()["code"])

    def test_one_report_that_cannot_be_sealed_does_not_stop_the_others(self):
        self.tasks(TWO_TASKS)
        self.reviewer_writes("code-reviewer", "T-007.1", agent="a1")
        self.reviewer_writes("code-reviewer", "T-007.2", agent="a1")
        real = reviewfresh.judge

        def judge(root, feature_dir, task):
            if task == "T-007.1":
                raise RuntimeError("no")
            return real(root, feature_dir, task)

        with mock.patch.object(reviewfresh, "judge", judge):
            reviewlog.seal(self.root, "a1")
        self.assertEqual(self.sealed("code-reviewer", "T-007.1")["error"], "RuntimeError: no")
        self.assertIsNotNone(self.sealed("code-reviewer", "T-007.2")["code"])

    def test_the_report_line_keeps_the_path_as_it_is_spelled_on_disk(self):
        self.reviewer_writes("code-reviewer", agent="a1")
        line = next(iter(reviewlog.recorded(self.root).values()))
        self.assertEqual(line["file"], f".bdd/features/{self.feature_dir.name}/reviews/T-007.1-code-reviewer.md")

    def test_a_folded_path_in_a_line_from_before_is_still_sealed_where_the_file_system_allows(self):
        self.reviewer_writes("code-reviewer", agent="a1")
        log = self.root / reviewlog.LOG
        lines = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
        for line in lines:
            line.pop("file", None)
        log.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")
        self.assertTrue(reviewlog.seal(self.root, "a1"))

    def test_writers_at_once_do_not_cut_each_others_lines(self):
        script = ("import sys; from pathlib import Path; from bddlib import reviewlog\n"
                  "root, who = Path(sys.argv[1]), sys.argv[2]\n"
                  "for n in range(25):\n"
                  "    reviewlog.record(root, root / '.bdd' / 'features' / 'x' / 'reviews' / f'T-007.{n}-code-reviewer.md',"
                  " 'code-reviewer', who * 4000, agent_id=who, phase='implement')\n")
        (self.root / ".bdd" / "features" / "x" / "reviews").mkdir(parents=True)
        bdd = Path(reviewlog.__file__).resolve().parents[1]
        workers = [subprocess.Popen([sys.executable, "-c", script, str(self.root), who], cwd=bdd,
                                    env={**os.environ, "PYTHONPATH": str(bdd)}) for who in "abcd"]
        self.assertEqual([w.wait() for w in workers], [0, 0, 0, 0])
        lines = (self.root / reviewlog.LOG).read_text(encoding="utf-8").splitlines()
        self.assertEqual(len([line for line in lines if json.loads(line)["agent_id"] in "abcd"]), 100)


class GateTest(FreshCase):
    def test_a_review_of_the_code_as_it_is_stands(self):
        self.review_task_1()
        self.assertEqual(self.problems(), [])

    def test_a_production_edit_after_the_review_makes_it_older_than_the_code(self):
        self.review_task_1()
        self.edit("3")
        self.assertEqual(self.problems(), [
            "reviews/T-007.1-code-reviewer.md is older than the code it covers: src/app.py changed after the "
            "code-reviewer finished; run the code-reviewer again",
            "reviews/T-007.1-ui-reviewer.md is older than the code it covers: src/app.py changed after the "
            "ui-reviewer finished; run the ui-reviewer again"])

    def test_the_gate_refuses_it_and_a_review_written_after_the_edit_passes(self):
        self.write_docs()
        state.update(self.feature_dir, lambda data: data.update(hooks_seen=True))
        self.review_task_1()
        self.edit("3")
        with self.assertRaises(UsageError) as refused:
            self.gate("implement", reviews=False)
        self.assertIn("reviews/T-007.1-code-reviewer.md is older than the code it covers", str(refused.exception))
        self.review_task_1()
        self.assertEqual(self.problems(), [])

    def test_putting_the_file_back_as_it_was_is_no_change(self):
        self.review_task_1()
        self.edit("3")
        self.edit("2")
        self.assertEqual(self.problems(), [])

    def test_a_new_file_in_the_area_after_the_review_counts(self):
        self.tasks("## T-007.1 Banner\nCovers: EX-007.1.1\nAreas: src/\n")
        self.review_task_1()
        self.write("src/extra.py", "y = 1\n")
        self.assertIn("src/extra.py changed after the code-reviewer finished", " ".join(self.problems()))

    def test_a_deleted_file_counts(self):
        self.review_task_1()
        (self.root / "src" / "app.py").unlink()
        self.assertIn("src/app.py changed after the code-reviewer finished", " ".join(self.problems()))

    def test_a_change_outside_the_areas_of_the_task_does_not(self):
        self.review_task_1()
        self.write("src/other.py", "x = 99\n")
        self.assertEqual(self.problems(), [])

    def test_many_changed_files_are_summarised(self):
        self.tasks("## T-007.1 Banner\nCovers: EX-007.1.1\nAreas: src/\n")
        self.review_task_1()
        for name in ("a", "b", "c", "d", "e"):
            self.write(f"src/{name}.py", "z = 1\n")
        (found,) = [p for p in self.problems() if "code-reviewer" in p]
        self.assertIn("src/a.py, src/b.py, src/c.py and 2 more changed", found)

    def test_a_report_nobody_sealed_fails_closed(self):
        with mock.patch.object(reviewlog, "seal", return_value=False):
            self.review_task_1()
        self.assertEqual(self.problems(), [
            "reviews/T-007.1-code-reviewer.md has no record of the code it was written against (the code-reviewer's "
            "SubagentStop did not seal it): run the code-reviewer again",
            "reviews/T-007.1-ui-reviewer.md has no record of the code it was written against (the ui-reviewer's "
            "SubagentStop did not seal it): run the ui-reviewer again"])

    def test_a_task_the_seal_says_cannot_be_judged_is_not_refused_for_it(self):
        self.tasks("## T-007.1 Banner\nCovers: EX-007.1.1\n\n## T-007.2 Other\nCovers: EX-007.2.1\n")
        self.review_task_1()
        self.review("code-reviewer", "T-007.2")
        self.edit("3")
        self.assertEqual(self.problems(), [])

    def test_in_verify_the_way_out_is_to_go_back_to_implement(self):
        self.review_task_1()
        self.edit("3")
        found = route.review_problems(self.root, self.feature_dir, "FEAT-007", hooks_seen=True, gate="verify")
        self.assertEqual(len(found), 2)
        self.assertIn("src/app.py changed after the code-reviewer finished; the feature is in verify: go back to implement "
                      "with /greenlight:change, run the code-reviewer there and pass the implement gate again", found[0])

    def test_a_report_written_without_an_agent_id_says_it_cannot_be_sealed(self):
        path = route.review_path(self.feature_dir, "T-007.1", "code-reviewer")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("Verdict: PASS\n", encoding="utf-8")
        reviewlog.record(self.root, path, "code-reviewer", "Verdict: PASS\n", agent_id=None, phase="implement")
        self.assertIn("T-007.1-code-reviewer.md was written without an agent id, so it cannot be sealed",
                      " ".join(self.problems()))

    def test_a_seal_that_carries_an_error_is_refused_with_the_error(self):
        self.reviewer_writes("code-reviewer", agent="a1")
        with mock.patch.object(reviewfresh, "judge", side_effect=RuntimeError("git is gone")):
            reviewlog.seal(self.root, "a1")
        self.reviewer_stops("code-reviewer", agent="a1")
        self.assertIn("T-007.1-code-reviewer.md: the code it covers could not be read when the code-reviewer finished "
                      "(RuntimeError: git is gone); run the code-reviewer again", " ".join(self.problems()))

    def test_without_hooks_nothing_is_judged(self):
        self.review_task_1()
        self.edit("3")
        self.assertEqual(route.review_problems(self.root, self.feature_dir, "FEAT-007", hooks_seen=False), [])

    def test_editing_tasks_md_after_the_review_cannot_hide_a_change(self):
        self.review_task_1()
        self.edit("3")
        self.tasks("## T-007.1 Banner\nCovers: EX-007.1.1\nAreas: docs/\n")
        self.assertIn("src/app.py changed after the code-reviewer finished", " ".join(self.problems()))
        self.tasks("not a task list at all\nAreas: nothing\n")
        self.assertTrue(self.problems())

    def test_a_check_that_cannot_run_is_a_problem_not_a_pass(self):
        self.review_task_1()
        with mock.patch.object(reviewfresh, "changed", side_effect=UsageError("git took longer than 30 s")):
            found = self.problems()
        self.assertEqual(len(found), 2)
        self.assertIn("could not be checked (UsageError: git took longer than 30 s); run the code-reviewer again", found[0])

    def test_a_seal_with_a_malformed_record_of_the_code_is_a_problem(self):
        self.review_task_1()
        log = self.root / reviewlog.LOG
        kept = [line for line in log.read_text(encoding="utf-8").splitlines() if '"seal"' not in line or "ui-reviewer" in line]
        report = next(json.loads(line) for line in kept if '"code-reviewer"' in line and '"sha256"' in line)
        for bad in ({"red": "nope", "areas": None, "files": {}}, {"red": "a" * 40, "areas": "src", "files": {}},
                    {"red": "a" * 40, "areas": None, "files": {"src/app.py": 1}}, {}):
            with self.subTest(bad=bad):
                seal = {"seal": report["sha256"], "path": report["path"], "reviewer": "code-reviewer",
                        "agent_id": report["agent_id"], "code": bad, "why": None}
                log.write_text("\n".join(kept + [json.dumps(seal)]) + "\n", encoding="utf-8")
                self.assertIn("T-007.1-code-reviewer.md: whether the code it covers changed could not be checked",
                              " ".join(self.problems()))


class OverlappingAreasTest(FreshCase):
    TASKS = TWO_TASKS
    SCENARIOS = (UI_SCENARIO, CLI_SCENARIO)

    def test_a_later_task_changing_a_shared_file_does_not_age_the_earlier_review_when_its_own_reviewer_read_it(self):
        self.review("code-reviewer", "T-007.1")
        self.review("ui-reviewer", "T-007.1")
        self.edit("3")                                                           # T-007.2's work, in the same folder
        self.review("code-reviewer", "T-007.2")
        self.assertEqual(self.problems(), ["reviews/T-007.1-ui-reviewer.md is older than the code it covers: src/app.py "
                                           "changed after the ui-reviewer finished; run the ui-reviewer again"])

    def test_a_report_that_was_changed_afterwards_excuses_nothing(self):
        self.review("code-reviewer", "T-007.1")
        self.review("ui-reviewer", "T-007.1")
        self.edit("3")
        self.review("code-reviewer", "T-007.2")
        route.review_path(self.feature_dir, "T-007.2", "code-reviewer").write_text("Verdict: FINDINGS\nedited\n", encoding="utf-8")
        self.assertTrue(any("T-007.1-code-reviewer.md is older than the code it covers" in p for p in self.problems()))

    def test_the_earlier_review_is_aged_when_no_later_review_of_that_kind_read_the_file(self):
        self.review("code-reviewer", "T-007.1")
        self.review("ui-reviewer", "T-007.1")
        self.review("code-reviewer", "T-007.2")
        self.edit("3")
        self.assertEqual(len(self.problems()), 3)


if __name__ == "__main__":
    unittest.main()
