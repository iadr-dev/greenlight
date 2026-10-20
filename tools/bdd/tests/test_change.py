import contextlib
import io
import os
import unittest

from bddlib import approvals, changecmd, cli, lockfile
from bddlib.errors import UsageError

from tests.helpers import ProjectCase


class ChangeCase(ProjectCase):
    def setUp(self):
        super().setUp()
        self.walk_to("tasks")                                        # both approvals, both locks, gates up to tasks

    def held(self) -> set[str]:
        return set(lockfile.read_lock(self.feature_dir, "FEAT-007")["scopes"])

    def reopen(self, phase: str, reason: str = "the threshold changed") -> dict:
        return changecmd.reopen(self.root, self.feature_dir, phase, reason)


class ReopenTest(ChangeCase):
    def test_reopening_the_examples_releases_both_locks_and_revokes_only_the_examples_approval(self):
        self.assertEqual(self.held(), {"spec", "bind"})
        entry = self.reopen("examples")
        data = self.data()
        self.assertEqual(self.held(), set())
        self.assertEqual(data["phase"], "examples")
        self.assertEqual(sorted(data["gates"]), ["discover", "test-design"])        # later gate results are forgotten
        self.assertEqual((entry["unlocked"], entry["revoked"]), (["spec", "bind"], ["examples"]))
        self.assertIsNone(data["red"])
        self.assertEqual(approvals.effective_problems(self.root, data, "rules"), [])
        (problem,) = approvals.effective_problems(self.root, data, "examples")
        self.assertIn("revoked by a change (the threshold changed)", problem)

    def test_the_gates_stand_again_only_after_the_approval_is_given_again(self):
        self.reopen("examples")
        with self.assertRaises(UsageError) as cm:
            self.gate("system-map")
        self.assertIn("revoked by a change", str(cm.exception))
        self.spec.write_text(self.spec.read_text(encoding="utf-8").replace("succeeds", "is accepted"),
                             encoding="utf-8", newline="\n")                      # the edit the change asked for
        self.approve("examples")                                                  # the person approves the new examples
        self.assertEqual(self.held(), {"spec"})                                   # which locks the new text
        self.assertEqual(self.gate("system-map")["phase"], "refine")

    def test_reopening_the_rules_revokes_both_approvals(self):
        entry = self.reopen("specify", "a rule was wrong")
        self.assertEqual(entry["revoked"], ["rules", "examples"])
        self.assertEqual(sorted(self.data()["gates"]), ["discover"])
        with self.assertRaises(UsageError) as cm:
            self.approve("examples")
        self.assertIn("the rules must be approved first", str(cm.exception))
        self.approve("rules")
        self.gate("test-design")
        self.approve("examples")                                                  # the new text of the rules and examples

    def test_reopening_the_binding_releases_only_the_bound_steps(self):
        entry = self.reopen("bind", "a driver needs a new seam")
        self.assertEqual((entry["unlocked"], entry["revoked"]), (["bind"], []))
        self.assertEqual(self.held(), {"spec"})
        self.assertEqual(sorted(self.data()["gates"]), ["discover", "refine", "system-map", "test-design"])
        self.assertEqual(approvals.effective_problems(self.root, self.data(), "examples"), [])

    def test_reopening_a_late_phase_leaves_locks_and_approvals_alone(self):
        self.gate("implement")
        entry = self.reopen("implement", "the first attempt was wrong")
        self.assertEqual((entry["unlocked"], entry["revoked"], entry["gates_removed"]), ([], [], ["implement"]))
        self.assertEqual(self.held(), {"spec", "bind"})
        self.assertEqual(self.data()["phase"], "implement")

    def test_a_finished_feature_can_be_reopened_for_verification(self):
        self.gate("implement")
        self.gate("verify")
        self.assertEqual(self.data()["phase"], "done")
        self.assertEqual(self.reopen("verify", "the report was wrong")["from"], "done")

    def test_every_change_is_kept_in_the_history_and_a_repeat_is_harmless(self):
        self.reopen("examples", "first")
        again = self.reopen("examples", "second")
        self.assertEqual((again["unlocked"], again["revoked"]), ([], []))
        self.assertEqual([c["id"] for c in self.data()["changes"]], [1, 2])
        history = lockfile.read_lock(self.feature_dir, "FEAT-007")["history"]
        self.assertTrue(any(h["event"] == "unlock" and h["reason"] == "change: first" for h in history))


class RefusalTest(ChangeCase):
    def test_bad_phase_and_missing_reason(self):
        for phase, reason in (("done", "x"), ("lunch", "x"), ("examples", "   ")):
            with self.subTest(phase=phase, reason=reason), self.assertRaises(UsageError):
                self.reopen(phase, reason)
        self.assertEqual(self.held(), {"spec", "bind"})                           # nothing was touched


class CommandTest(ChangeCase):
    def bdd(self, *argv: str) -> tuple[int, str, str]:
        out, err, here = io.StringIO(), io.StringIO(), os.getcwd()
        os.chdir(self.root)
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                try:
                    code = cli.main(list(argv))
                except SystemExit as exc:
                    code = exc.code
        finally:
            os.chdir(here)
        return code, out.getvalue(), err.getvalue()

    def test_the_command_reports_what_it_did(self):
        code, out, _ = self.bdd("change", "FEAT-007", "--reopen", "examples", "--reason", "threshold is 500")
        self.assertEqual(code, 0)
        self.assertIn("FEAT-007: reopened at examples (was implement): threshold is 500", out)
        self.assertIn("unlocked: spec, bind", out)
        self.assertIn("approvals revoked: examples", out)
        self.assertIn("gate results forgotten: system-map, refine, bind, tasks", out)

    def test_status_shows_the_revoked_approval_and_the_phase(self):
        self.bdd("change", "FEAT-007", "--reopen", "examples", "--reason", "x")
        _, out, _ = self.bdd("status")
        self.assertIn("rules: approved, examples: approved but not valid", out)
        self.assertIn("the person: /greenlight:approve FEAT-007 examples", out)

    def test_usage_errors(self):
        self.assertEqual(self.bdd("change", "FEAT-007", "--reopen", "examples")[0], 2)           # reason is required
        self.assertEqual(self.bdd("change", "FEAT-007", "--reopen", "lunch", "--reason", "x")[0], 2)
        code, _, err = self.bdd("change", "FEAT-099", "--reopen", "examples", "--reason", "x")
        self.assertEqual((code, "FEAT-099" in err), (2, True))


if __name__ == "__main__":
    unittest.main()
