"""`bdd stability`, the verify gate's use of it, and the CI check of the committed approval record."""
import contextlib
import io
import json
import os
import unittest

from bddlib import approvals, cli, guard, reportcmd, stability, state
from bddlib import config as cfg
from bddlib.errors import UsageError

from tests.helpers import ProjectCase
from tests.test_run_classify import ALL_GREEN, ALL_RED, RUN_TABLE, RunCase, case

FLAKY = [case("test_order_of_exactly_1000", "passed"),
         {**case("test_order_of_999", "passed", "AssertionError: 400 != 200"), "outcomes": ["passed", "failed"]},
         case("test_order_of_zero", "passed")]


class StabilityCase(RunCase):
    def setUp(self):
        super().setUp()
        self.counter = self.root / "calls.txt"

    def stability(self, *args: str, cases=None):
        return self.cli(stability.run, "FEAT-007", *args, cases=cases if cases is not None else ALL_GREEN,
                        env={"FAKE_COUNTER": str(self.counter)})

    def result(self) -> dict:
        return json.loads((self.root / ".bdd" / ".runs" / "FEAT-007" / "stability.json").read_text(encoding="utf-8"))


class StabilityRunTest(StabilityCase):
    def test_a_scenario_that_behaves_the_same_every_time_is_stable(self):
        code, out, _ = self.stability("--runs", "3")
        self.assertEqual(code, 0, out)
        record = self.result()
        self.assertEqual((record["passed"], record["runs"], record["flaky"]), (True, 3, {}))
        self.assertEqual([p["seed"] is None for p in record["plan"]], [True, False, False])   # the first run is in order
        self.assertIn("stability passed over 3 run(s)", out)

    def test_a_scenario_that_changes_outcome_is_flagged(self):
        code, out, _ = self.stability("--runs", "4", cases=FLAKY)
        self.assertEqual(code, 1)
        record = self.result()
        self.assertFalse(record["passed"])
        self.assertEqual(record["flaky"], {"Order of 999": ["pass", "expected-fail", "pass", "expected-fail"]})
        self.assertIn('flaky: "Order of 999"', out)

    def test_a_scenario_that_always_fails_is_stable_not_flaky(self):
        code, _, _ = self.stability("--runs", "2", cases=ALL_RED)
        self.assertEqual(code, 0)                            # whether it is green is the green check's business

    def test_without_shuffle_words_every_run_is_in_order(self):
        self.config(tail=RUN_TABLE.replace("shuffle = '--seed {seed}'\n", ""))
        self.assertEqual(self.stability("--runs", "2")[0], 0)
        self.assertEqual([p["seed"] for p in self.result()["plan"]], [None, None])

    def test_the_last_run_of_bdd_run_is_left_alone(self):
        self.run_feature(cases=ALL_RED)
        before = (self.root / ".bdd" / ".runs" / "FEAT-007" / "latest.json").read_bytes()
        self.stability("--runs", "2")
        self.assertEqual((self.root / ".bdd" / ".runs" / "FEAT-007" / "latest.json").read_bytes(), before)

    def test_the_number_of_runs_is_checked(self):
        for bad in ("1", "0", "51"):
            with self.subTest(runs=bad):
                code, _, err = self.stability("--runs", bad)
                self.assertEqual((code, "--runs must be from 2 to 50" in err), (2, True))

    def test_the_default_is_the_projects_number_else_three(self):
        self.stability()
        self.assertEqual(self.result()["runs"], 3)
        self.config(top_level="[stability]\nruns = 5\n", tail=RUN_TABLE)
        self.stability()
        self.assertEqual(self.result()["runs"], 5)

    def test_a_run_that_writes_no_report_fails_the_check(self):
        self.config(tail="[adapters.run]\nby_tag = '{python} -c \"print(1)\"'\nreport = '--out {out}'\n")
        code, out, _ = self.stability("--runs", "2")
        self.assertEqual(code, 1)
        self.assertIn("wrote no test report", out)


class StabilityConfigTest(ProjectCase):
    def test_runs_must_be_a_whole_number_from_two_to_fifty(self):
        self.config(top_level="[stability]\nruns = 3\n")
        self.assertEqual(cfg.load(self.root).stability_runs, 3)
        self.assertEqual(self.config() or cfg.load(self.root).stability_runs, 0)
        for bad in ("1", "51", "true", '"3"', "2.5"):
            with self.subTest(runs=bad):
                self.config(top_level=f"[stability]\nruns = {bad}\n")
                with self.assertRaises(cfg.ConfigError):
                    cfg.load(self.root)

    def test_an_agent_cannot_write_the_result(self):
        path = self.root / ".bdd" / ".runs" / "FEAT-007" / "stability.json"
        reason = guard.evaluate({"tool_name": "Write", "cwd": str(self.root), "tool_input": {"file_path": str(path)}})
        self.assertIn("managed by the bdd command line", reason)


class StabilityGateTest(StabilityCase):
    """The verify gate asks for the check only when the project does."""

    def setUp(self):
        super().setUp()
        self.config(top_level="[stability]\nruns = 3\n", tail=RUN_TABLE)
        self.walk_to("refine")
        from bddlib import lockfile
        lockfile.lock(self.root, self.feature_dir, "FEAT-007", "bind", [self.step])
        self.run_feature(cases=ALL_RED)
        self.gate("bind")
        self.gate("tasks")
        self.gate("implement")
        self.run_feature(cases=ALL_GREEN)

    def refused(self) -> str:
        with self.assertRaises(UsageError) as cm:
            self.gate("verify")
        return str(cm.exception)

    def test_verify_wants_the_check_when_the_project_asks(self):
        self.assertIn("has not been run; run `bdd stability FEAT-007`", self.refused())

    def test_a_stable_current_result_lets_verify_pass(self):
        self.assertEqual(self.stability("--runs", "3")[0], 0)
        self.assertEqual(self.gate("verify")["phase"], "done")

    def test_a_flaky_result_blocks_verify(self):
        self.stability("--runs", "3", cases=FLAKY)
        self.assertIn("the stability check failed", self.refused())

    def test_too_few_runs_block_verify(self):
        self.stability("--runs", "2")
        self.assertIn("project asks for 3", self.refused())

    def test_a_result_goes_stale_when_a_step_changes(self):
        self.stability("--runs", "3")
        self.step.write_text("def then_ok():\n    assert 1 == 1\n", encoding="utf-8", newline="\n")
        self.assertIn("lock", self.refused().lower())       # the bound step also differs from its lock
        self.assertIn("out of date", "; ".join(stability.problems(self.root, "FEAT-007")))

    def test_without_the_table_nothing_changes(self):
        self.config(tail=RUN_TABLE)
        self.assertEqual(stability.problems(self.root, "FEAT-007"), [])
        self.assertEqual(self.gate("verify")["phase"], "done")

    def test_check_shows_the_recorded_result(self):
        self.stability("--runs", "3")
        code, out, _ = self.stability("--check")
        self.assertEqual(code, 0)
        self.assertIn("stability passed", out)


class RecordedApprovalsTest(ProjectCase):
    """`bdd approve FEAT-n --check` judges the committed record alone, as a CI job can."""

    def check(self) -> tuple[int, str]:
        out, here = io.StringIO(), os.getcwd()
        os.chdir(self.root)
        try:
            with contextlib.redirect_stdout(out):
                return cli.main(["approve", "FEAT-007", "--check"]), out.getvalue()
        finally:
            os.chdir(here)

    def test_a_feature_that_has_not_reached_the_gates_has_nothing_to_check(self):
        self.assertEqual(self.check(), (0, ""))

    def test_valid_approvals_pass_and_say_how_they_were_given(self):
        self.walk_to("system-map")
        code, out = self.check()
        self.assertEqual(code, 0, out)
        self.assertIn("rules: valid (self-reported, origin self-reported)", out)
        self.assertIn("examples: valid", out)

    def test_an_approved_file_that_changed_afterwards_fails(self):
        self.walk_to("system-map")
        self.rules.write_text(self.rules.read_text(encoding="utf-8") + "\nR-007.2 More.\n", encoding="utf-8", newline="\n")
        code, out = self.check()
        self.assertEqual(code, 1)
        self.assertIn("changed after the rules approval", out)

    def test_a_phase_that_rests_on_an_approval_that_is_not_there_fails(self):
        self.walk_to("system-map")

        def forget(current: dict) -> None:
            current["approvals"] = []

        state.update(self.feature_dir, forget)
        code, out = self.check()
        self.assertEqual(code, 1)
        self.assertIn("rules has not been approved", out)
        self.assertIn("examples has not been approved", out)

    def test_a_hook_approval_that_was_never_verified_fails_and_says_where_to_verify(self):
        self.walk_to("discover")
        self.rules.write_text("# Rules\n\nR-007.1 A rule.\n", encoding="utf-8", newline="\n")
        self.gate("discover")
        approvals.record(self.root, self.feature_dir, "rules", "approve", "hook", prompt_id="p1", transcript_path="s.jsonl")
        code, out = self.check()
        self.assertEqual(code, 1)
        self.assertIn("waiting for its origin to be verified", out)
        self.assertIn("transcript", out)

    def test_required_gates_follow_the_phase(self):
        self.assertEqual(approvals.required_gates({"phase": "specify"}), [])
        self.assertEqual(approvals.required_gates({"phase": "test-design"}), ["rules"])
        self.assertEqual(approvals.required_gates({"phase": "done"}), ["rules", "examples"])

    def test_status_done_lists_only_finished_features(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            reportcmd.print_done(self.root)
        self.assertEqual(out.getvalue(), "")

        def finish(current: dict) -> None:
            current["phase"] = "done"

        state.update(self.feature_dir, finish)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            reportcmd.print_done(self.root)
        self.assertEqual(out.getvalue().split(), ["FEAT-007"])


if __name__ == "__main__":
    unittest.main()
