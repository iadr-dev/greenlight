import json
import unittest
from datetime import datetime, timedelta, timezone

from bddlib import approvals, enforcement, lockfile
from bddlib.errors import UsageError

from tests.helpers import ProjectCase, headless, injected, typed


class RecordTest(ProjectCase):
    def test_rules_cannot_be_approved_before_discover_or_without_a_file(self):
        with self.assertRaises(UsageError) as cm:
            self.approve("rules")
        self.assertIn("the discover gate has not passed yet", str(cm.exception))
        self.gate("discover")
        self.assertEqual(self.approve("rules")["decision"], "approve")
        self.assertEqual(self.data()["phase"], "test-design")

    def test_nothing_to_approve_is_refused(self):
        self.gate("discover")
        with self.assertRaises(UsageError) as cm:
            approvals.record(self.root, self.feature_dir, "rules", "approve", "self-reported")
        self.assertIn("there is nothing to approve", str(cm.exception))

    def test_approving_examples_locks_the_spec_and_needs_the_rules(self):
        self.gate("discover")
        self.gate("test-design", "fail")
        with self.assertRaises(UsageError):
            self.approve("examples")
        self.approve("rules")
        self.gate("test-design")
        entry = self.approve("examples")
        self.assertEqual(list(entry["artifacts"]), ["features/discounts.feature"])
        self.assertIn("spec", lockfile.read_lock(self.feature_dir, "FEAT-007")["scopes"])

    def test_rejecting_examples_unlocks_the_spec_and_moves_back(self):
        self.walk_to("examples")
        self.approve("examples", decision="reject", reason="missing the boundary")
        self.assertEqual(self.data()["phase"], "examples")
        self.assertNotIn("spec", lockfile.read_lock(self.feature_dir, "FEAT-007")["scopes"])

    def test_unknown_gate_decision_or_grade(self):
        for args in (("deploy", "approve", "auto"), ("rules", "maybe", "auto"), ("rules", "approve", "psychic")):
            with self.subTest(args=args), self.assertRaises(UsageError):
                approvals.record(self.root, self.feature_dir, *args)

    def test_ids_increase_and_the_enforcement_context_is_kept(self):
        self.gate("discover")
        first = self.approve("rules")
        second = self.approve("rules", decision="reject", reason="no")
        self.assertEqual((first["id"], second["id"]), (1, 2))
        self.assertEqual((first["mode"], first["autonomy"], first["hooks_seen"]), ("auto", "standard", False))


class GradeTest(ProjectCase):
    def test_self_reported_is_accepted_only_while_no_hooks_have_run(self):
        self.gate("discover")
        enforcement.touch(self.root, "s1")
        with self.assertRaises(UsageError) as cm:
            self.approve("rules")
        self.assertIn("hooks have run in this project", str(cm.exception))

    def test_losing_the_markers_does_not_reopen_self_reporting_once_the_feature_saw_hooks(self):
        enforcement.touch(self.root, "s1")
        self.gate("discover")                              # the feature remembers that hooks ran
        for marker in enforcement.marker_dir(self.root).iterdir():
            marker.unlink()
        with self.assertRaises(UsageError):
            self.approve("rules")

    def test_soft_mode_always_accepts_self_reported_and_hard_never_does(self):
        self.gate("discover")
        enforcement.touch(self.root, "s1")
        self.config('enforcement = "soft"\n')
        self.assertEqual(self.approve("rules")["grade"], "self-reported")
        self.config('enforcement = "hard"\n')
        with self.assertRaises(UsageError) as cm:
            self.approve("rules")
        self.assertIn("requires hard enforcement", str(cm.exception))

    def test_automatic_approvals_need_an_automatic_autonomy_level_and_no_hard_mode(self):
        self.gate("discover")
        with self.assertRaises(UsageError) as cm:
            self.approve("rules", grade="auto")
        self.assertIn("autonomy standard", str(cm.exception))
        from bddlib import state
        state.switch_autonomy(self.feature_dir, "auto", "the person asked for it")
        self.assertEqual(self.approve("rules", grade="auto")["origin"], "auto")
        self.config('enforcement = "hard"\n')
        with self.assertRaises(UsageError):
            self.approve("rules", grade="auto")


class OriginTest(unittest.TestCase):
    def test_classify(self):
        cases = [(typed("p"), "human"), (headless("p"), "headless"), (injected("p"), "invalid"),
                 (injected("p", "scheduled", "task-notification"), "invalid"), ({"type": "user", "promptId": "p"}, "unverifiable"),
                 ({**typed("p"), "promptSource": "system"}, "invalid")]
        for entry, expected in cases:
            with self.subTest(entry=entry):
                self.assertEqual(approvals.classify(entry)[0], expected)

    def test_entries_for_one_prompt_must_agree_and_an_invalid_one_wins(self):
        self.assertEqual(approvals.classify_all([typed("p")])[0], "human")
        self.assertEqual(approvals.classify_all([typed("p"), injected("p")])[0], "invalid")
        origin, evidence = approvals.classify_all([typed("p"), headless("p")])
        self.assertEqual(origin, "invalid")
        self.assertIn("disagree", evidence)


class VerifyTest(ProjectCase):
    def hook_approval(self, prompt_id="p-1", entries=(), transcript=True, at=None):
        self.gate("discover")
        path = self.transcript(*entries) if transcript else self.transcripts / "missing.jsonl"
        entry = self.approve("rules", grade="hook", session="s1", prompt_id=prompt_id, transcript_path=str(path))
        if at:
            from bddlib import state
            state.update(self.feature_dir, lambda d: d["approvals"][0].__setitem__("at", at))
        return entry

    def origin(self) -> str:
        return self.data()["approvals"][0]["origin"]

    def test_a_typed_prompt_becomes_human(self):
        self.hook_approval(entries=[typed("p-1")])
        self.assertEqual(approvals.verify_origins(self.feature_dir), 1)
        self.assertEqual(self.origin(), "human")

    def test_a_meta_entry_never_counts_as_the_prompt(self):
        self.hook_approval(entries=[injected("p-1")])           # meta entries are ignored, so the prompt is not found
        self.assertEqual(approvals.verify_origins(self.feature_dir), 0)
        self.assertEqual(self.origin(), "pending")

    def test_a_non_meta_system_prompt_is_invalid(self):
        self.hook_approval(entries=[{**injected("p-1"), "isMeta": False}])
        approvals.verify_origins(self.feature_dir)
        self.assertEqual(self.origin(), "invalid")

    def test_a_prompt_that_is_not_there_yet_stays_pending_then_times_out(self):
        self.hook_approval(entries=[typed("other")])
        self.assertEqual(approvals.verify_origins(self.feature_dir), 0)
        late = (datetime.now(timezone.utc) - approvals.PENDING_TIMEOUT - timedelta(minutes=1)).isoformat()
        from bddlib import state
        state.update(self.feature_dir, lambda d: d["approvals"][0].__setitem__("at", late))
        self.assertEqual(approvals.verify_origins(self.feature_dir), 1)
        self.assertEqual(self.origin(), "unverifiable")

    def test_only_transcripts_inside_the_projects_folders_are_ever_read(self):
        self.gate("discover")
        outside = self.root / "elsewhere.jsonl"
        outside.write_text(json.dumps(typed("p")) + "\n", encoding="utf-8")
        self.approve("rules", grade="hook", session="s1", prompt_id="p", transcript_path=str(outside))
        self.assertEqual(approvals.verify_origins(self.feature_dir), 0)      # not found, so still undecided
        self.assertEqual(self.origin(), "pending")

    def test_the_recorded_directory_is_ignored_and_odd_names_are_unverifiable(self):
        self.gate("discover")
        self.transcript(typed("p"), name="real.jsonl")
        self.approve("rules", grade="hook", session="s1", prompt_id="p",
                     transcript_path=str(self.root / "anywhere" / ".." / "real.jsonl"))
        approvals.verify_origins(self.feature_dir)
        self.assertEqual(self.origin(), "human")                   # found by file name inside our own folders
        self.approve("rules", grade="hook", session="s1", prompt_id="p", transcript_path="../../etc/passwd")
        approvals.verify_origins(self.feature_dir)
        second = self.data()["approvals"][1]
        self.assertEqual(second["origin"], "unverifiable")
        self.assertIn("not a session transcript file name", second["evidence"])

    def test_missing_provenance_is_unverifiable(self):
        self.gate("discover")
        self.approve("rules", grade="hook", session="s1")
        approvals.verify_origins(self.feature_dir)
        self.assertEqual(self.origin(), "unverifiable")


class EffectiveTest(ProjectCase):
    def problems(self, gate="rules"):
        return approvals.effective_problems(self.root, self.data(), gate)

    def test_hook_approvals_count_only_when_verified_human(self):
        self.gate("discover")
        path = self.transcript(typed("p-1"), headless("p-2"))
        self.approve("rules", grade="hook", session="s", prompt_id="p-1", transcript_path=str(path))
        self.assertIn("still waiting", self.problems()[0])
        approvals.verify_origins(self.feature_dir)
        self.assertEqual(self.problems(), [])

    def test_headless_is_refused_unless_the_project_allows_it(self):
        self.gate("discover")
        path = self.transcript(headless("p-2"))
        self.approve("rules", grade="hook", session="s", prompt_id="p-2", transcript_path=str(path))
        approvals.verify_origins(self.feature_dir)
        self.assertIn("headless", self.problems()[0])
        self.config(tail="[approvals]\nallow_headless = true\n")
        self.assertEqual(self.problems(), [])

    def test_the_latest_decision_wins(self):
        self.gate("discover")
        self.approve("rules")
        self.approve("rules", decision="reject", reason="wrong")
        self.assertEqual(self.problems(), ["rules was rejected: wrong"])
        self.approve("rules")
        self.assertEqual(self.problems(), [])


if __name__ == "__main__":
    unittest.main()
