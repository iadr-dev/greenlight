import contextlib
import io
import os
import unittest

from bddlib import approvecmd, enforcement, state

from tests.helpers import ProjectCase, typed


class CommandCase(ProjectCase):
    def run_cmd(self, *args: str) -> tuple[int, str, str]:
        out, err, here = io.StringIO(), io.StringIO(), os.getcwd()
        os.chdir(self.root)
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = approvecmd.run(list(args))
        finally:
            os.chdir(here)
        return code, out.getvalue(), err.getvalue()

    def prepare_rules(self) -> None:
        self.gate("discover")
        self.rules.write_text("# Rules\n\nR-007.1 Orders of 1000 or more get 10% off.\n", encoding="utf-8", newline="\n")


class ApproveCommandTest(CommandCase):
    def test_self_reported_approval_is_recorded_and_the_phase_reported(self):
        self.prepare_rules()
        code, out, err = self.run_cmd("FEAT-007", "rules", "--self-reported")
        self.assertEqual((code, out.strip()), (0, "FEAT-007: rules approved (self-reported); phase is now test-design"))
        self.assertIn("not verified by a hook", err)

    def test_a_rejection_keeps_its_reason(self):
        self.prepare_rules()
        code, out, _ = self.run_cmd("FEAT-007", "rules", "--self-reported", "--reject", "--reason", "rule 2 is wrong")
        self.assertEqual(code, 0)
        self.assertIn("rejected", out)
        self.assertEqual(self.data()["approvals"][0]["reason"], "rule 2 is wrong")

    def test_refusals_exit_with_status_2_and_a_message(self):
        self.prepare_rules()
        cases = [(("FEAT-007", "rules"), "choose --self-reported or --auto"),
                 (("FEAT-007", "--self-reported"), "name the gate"),
                 (("FEAT-007", "rules", "--auto"), "autonomy standard"),
                 (("FEAT-099", "rules", "--self-reported"), "FEAT-099")]
        for args, message in cases:
            with self.subTest(args=args):
                code, _, err = self.run_cmd(*args)
                self.assertEqual(code, 2)
                self.assertIn(message, err)

    def test_self_reporting_is_refused_once_hooks_have_run(self):
        self.prepare_rules()
        enforcement.touch(self.root, "s1")
        code, _, err = self.run_cmd("FEAT-007", "rules", "--self-reported")
        self.assertEqual(code, 2)
        self.assertIn("approvals have to be typed by the person", err)
        self.assertEqual(self.data()["approvals"], [])

    def test_automatic_approval_under_an_automatic_level(self):
        self.prepare_rules()
        state.switch_autonomy(self.feature_dir, "auto", "the person asked for it")
        code, out, _ = self.run_cmd("FEAT-007", "rules", "--auto")
        self.assertEqual(code, 0)
        self.assertIn("(auto)", out)

    def test_verify_reports_each_hook_approval_and_exits_1_while_pending(self):
        self.prepare_rules()
        path = self.transcript(typed("p-1"))
        self.approve("rules", grade="hook", session="s", prompt_id="p-1", transcript_path=str(path))
        code, out, _ = self.run_cmd("FEAT-007", "--verify")
        self.assertEqual(code, 0)
        self.assertIn("verified 1 approval(s)", out)
        self.assertIn("#1 rules approve: human", out)
        self.approve("rules", grade="hook", session="s", prompt_id="p-2", transcript_path=str(path))
        code, out, _ = self.run_cmd("FEAT-007", "--verify")
        self.assertEqual(code, 1)
        self.assertIn("#2 rules approve: pending", out)


class SummaryCommandTest(CommandCase):
    def test_the_summary_is_printed_and_nothing_is_written(self):
        self.prepare_rules()
        before = (self.feature_dir / "state.json").read_bytes()
        code, out, err = self.run_cmd("FEAT-007", "rules", "--summary")
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(out.splitlines()[:2], ["FEAT-007 rules, not approved before: 1 rule.",
                                                "  R-007.1  Orders of 1000 or more get 10% off."])
        self.assertEqual((self.feature_dir / "state.json").read_bytes(), before)

    def test_the_summary_needs_a_gate_and_takes_no_reason(self):
        self.prepare_rules()
        for args, message in ((("FEAT-007", "--summary"), "name the gate"),
                              (("FEAT-007", "rules", "--summary", "--reject"), "only reads"),
                              (("FEAT-007", "rules", "--summary", "--reason", "x"), "only reads")):
            with self.subTest(args=args):
                code, _, err = self.run_cmd(*args)
                self.assertEqual(code, 2)
                self.assertIn(message, err)

    def test_the_summary_cannot_be_combined_with_a_flag_that_records_or_judges(self):
        self.prepare_rules()
        for flag in ("--self-reported", "--auto", "--verify", "--check"):
            with self.subTest(flag=flag), contextlib.redirect_stderr(io.StringIO()) as err, self.assertRaises(SystemExit) as stop:
                approvecmd.run(["FEAT-007", "rules", "--summary", flag])
            self.assertEqual(stop.exception.code, 2)
            self.assertIn("not allowed with", err.getvalue())
        self.assertEqual(self.data()["approvals"], [])

    def test_the_summary_takes_no_flag_that_does_not_exist(self):
        self.prepare_rules()
        with contextlib.redirect_stderr(io.StringIO()) as err, self.assertRaises(SystemExit) as stop:
            approvecmd.run(["FEAT-007", "rules", "--summary", "--record"])
        self.assertEqual(stop.exception.code, 2)
        self.assertIn("unrecognized arguments: --record", err.getvalue())
        self.assertEqual(self.data()["approvals"], [])

    def test_a_summary_of_nothing_to_approve_is_refused_in_words(self):
        code, _, err = self.run_cmd("FEAT-007", "rules", "--summary")
        self.assertEqual(code, 2)
        self.assertIn("there is nothing to summarise", err)

    def test_the_summary_works_when_hard_enforcement_refuses_self_reporting(self):
        self.prepare_rules()
        self.config('enforcement = "hard"\n')
        self.assertEqual(self.run_cmd("FEAT-007", "rules", "--summary")[0], 0)


if __name__ == "__main__":
    unittest.main()
