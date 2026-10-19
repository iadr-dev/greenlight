import os
import unittest
from unittest import mock

from bddlib import enforcement, lockfile
from bddlib.errors import UsageError

from tests.helpers import ProjectCase, typed


class GateOrderTest(ProjectCase):
    def test_passing_gates_move_the_phase_forward_in_order(self):
        seen = []
        for step in ("discover", "rules", "test-design", "examples", "system-map", "refine"):
            if step in ("rules", "examples"):
                self.approve(step)
                seen.append(self.data()["phase"])
            else:
                seen.append(self.gate(step)["phase"])
        self.assertEqual(seen, ["specify", "test-design", "examples", "system-map", "refine", "bind"])

    def test_failing_gates_do_not_advance_and_keep_their_evidence(self):
        data = self.gate("discover", "fail", {"blocking_questions": "2"})
        self.assertEqual(data["phase"], "discover")
        self.assertEqual(data["gates"]["discover"]["result"], "fail")
        self.assertEqual(data["gates"]["discover"]["detail"], {"blocking_questions": "2"})

    def test_the_phase_never_moves_backwards(self):
        self.walk_to("test-design")
        self.assertEqual(self.gate("discover")["phase"], "examples")       # re-running an early gate

    def test_human_gates_cannot_be_recorded_here(self):
        for name in ("rules", "examples"):
            with self.assertRaises(UsageError) as cm:
                self.gate(name)
            self.assertIn("only the person can approve", str(cm.exception))
            self.assertIn(f"/greenlight:approve <feature> {name}", str(cm.exception))
        self.assertEqual(self.data()["gates"], {})

    def test_unknown_gate_and_bad_result(self):
        with self.assertRaises(UsageError):
            self.gate("deploy")
        with self.assertRaises(UsageError):
            self.gate("discover", "maybe")

    def test_red_may_only_accompany_the_bind_gate(self):
        with self.assertRaises(UsageError):
            self.gate("discover", red={"commit": "abc"})
        self.walk_to("refine")
        lockfile.lock(self.root, self.feature_dir, "FEAT-007", "bind", [self.step])
        data = self.gate("bind", red={"commit": "abc", "dirty": False, "source_hash": "h", "at": "now"})
        self.assertEqual(data["red"]["commit"], "abc")

    def test_every_gate_remembers_which_session_recorded_it(self):
        with mock.patch.dict(os.environ, {enforcement.SESSION_ENV: "sess-9"}):
            data = self.gate("discover")
        self.assertEqual(data["gates"]["discover"]["session"], "sess-9")
        self.assertIsNone(self.gate("test-design", "fail")["gates"]["test-design"]["session"])


class ApprovalsAreRequiredTest(ProjectCase):
    def test_test_design_needs_the_rules_approved(self):
        self.gate("discover")
        with self.assertRaises(UsageError) as cm:
            self.gate("test-design")
        self.assertIn("rules has not been approved", str(cm.exception))
        self.approve("rules")
        self.assertEqual(self.gate("test-design")["phase"], "examples")

    def test_later_gates_need_both_approvals(self):
        self.gate("discover")
        self.approve("rules")
        self.gate("test-design")
        for name in ("system-map", "refine", "bind", "tasks", "implement", "verify"):
            with self.subTest(gate=name):
                with self.assertRaises(UsageError) as cm:
                    self.gate(name)
                self.assertIn("examples has not been approved", str(cm.exception))

    def test_a_rejection_blocks_the_gates_that_depend_on_it(self):
        self.gate("discover")
        self.approve("rules")
        self.approve("rules", decision="reject", reason="rule 2 is wrong")
        with self.assertRaises(UsageError) as cm:
            self.gate("test-design")
        self.assertIn("rules was rejected: rule 2 is wrong", str(cm.exception))

    def test_changing_what_was_approved_invalidates_the_approval(self):
        self.gate("discover")
        self.approve("rules")
        self.rules.write_text("# Rules\n\nR-007.1 changed after approval.\n", encoding="utf-8", newline="\n")
        with self.assertRaises(UsageError) as cm:
            self.gate("test-design")
        self.assertIn("changed after the rules approval", str(cm.exception))

    def test_failing_results_never_need_approvals(self):
        self.assertEqual(self.gate("test-design", "fail")["gates"]["test-design"]["result"], "fail")

    def test_a_typed_approval_counts_once_its_origin_is_verified_at_the_gate(self):
        self.gate("discover")
        self.rules.write_text("# Rules\n", encoding="utf-8", newline="\n")
        path = self.transcript(typed("p-1"))
        self.approve("rules", grade="hook", session="s1", prompt_id="p-1", transcript_path=str(path))
        self.assertEqual(self.data()["approvals"][0]["origin"], "pending")
        data = self.gate("test-design")                     # the gate verifies pending approvals first
        self.assertEqual(data["approvals"][0]["origin"], "human")
        self.assertEqual(data["phase"], "examples")


class EnforcedGateTest(ProjectCase):
    def test_implement_cannot_pass_while_nothing_is_locked(self):
        self.gate("discover")
        self.approve("rules")
        self.gate("test-design")
        self.approve("examples")                           # locks the spec, but not the bound steps
        for name in ("system-map", "refine", "bind", "tasks"):
            self.gate(name)
        with self.assertRaises(UsageError) as cm:
            self.gate("implement")
        self.assertIn("bind is not locked", str(cm.exception))
        self.assertNotIn("implement", self.data()["gates"])

    def test_implement_passes_with_intact_locks_and_moves_to_verify(self):
        self.walk_to("tasks")
        self.assertEqual(self.gate("implement")["phase"], "verify")

    def test_implement_is_refused_if_a_locked_step_was_weakened(self):
        self.walk_to("tasks")
        self.step.write_text("def then_ok():\n    pass\n", encoding="utf-8", newline="\n")
        with self.assertRaises(UsageError) as cm:
            self.gate("implement")
        self.assertIn("steps/steps.py changed since it was locked", str(cm.exception))

    def test_implement_is_refused_if_a_spec_was_added_after_locking(self):
        self.walk_to("tasks")
        self.write("features/extra.feature", "@FEAT-007\nFeature: Extra\n")
        with self.assertRaises(UsageError) as cm:
            self.gate("implement")
        self.assertIn("never locked", str(cm.exception))

    def test_a_failing_result_is_always_recordable(self):
        self.assertEqual(self.gate("implement", "fail")["gates"]["implement"]["result"], "fail")

    def test_verify_needs_implement_to_have_passed(self):
        self.walk_to("tasks")
        with self.assertRaises(UsageError) as cm:
            self.gate("verify")
        self.assertIn("implement gate has not passed", str(cm.exception))
        self.gate("implement")
        self.assertEqual(self.gate("verify")["phase"], "done")

    def test_the_whole_pipeline_runs_to_done(self):
        self.walk_to("verify")
        self.assertEqual(self.data()["phase"], "done")


if __name__ == "__main__":
    unittest.main()
