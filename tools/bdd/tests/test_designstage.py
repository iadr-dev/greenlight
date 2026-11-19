import json
import unittest

from bddlib import approvehook, changecmd, designstage, enforcement, gates, lockfile, state
from bddlib.errors import UsageError

from tests.design_fixture import INVENTORY, DesignCase
from tests.helpers import typed


class StartTest(DesignCase):
    def test_starting_records_the_spec_and_adds_only_the_missing_files(self):
        (self.root / ".bdd" / "architecture.md").unlink()
        lines = designstage.start(self.root, self.root / "product-spec.md")
        self.assertEqual(lines[0], "design stage: started from product-spec.md")
        self.assertIn("  + .bdd/architecture.md", lines)
        self.assertNotIn("  + .bdd/product.md", lines, "the feature map the person has is kept")
        self.assertEqual(designstage.load(self.root)["spec"], "product-spec.md")
        again = designstage.start(self.root, self.root / "product-spec.md")
        self.assertIn("already started", again[0])
        self.assertEqual(len(designstage.load(self.root)["history"]), 1, "starting again with the same spec changes nothing")

    def test_a_spec_outside_the_project_or_missing_is_refused(self):
        with self.assertRaises(UsageError):
            designstage.start(self.root, self.root / "nothing.md")
        with self.assertRaises(UsageError):
            designstage.start(self.root, self.root.parent / "elsewhere.md")


class ApprovalTest(DesignCase):
    def hook(self, prompt: str = "/greenlight:approve design", prompt_id: str = "p1") -> str:
        return approvehook.record_design({"prompt": prompt, "prompt_id": prompt_id, "transcript_path": "session.jsonl",
                                          "cwd": str(self.root), "session_id": "s1"})

    def test_the_approval_waits_for_the_review_of_this_very_design(self):
        self.start()
        self.assertIn("the ui-reviewer has not reviewed it yet", self.hook())
        self.review()
        self.write("design/DESIGN.md", "# Shop design\n\n## Design contract\nChanged after the review.\n")
        self.build()
        self.assertIn("reviewed another version of the design", self.hook())
        self.assertEqual(designstage.load(self.root)["approvals"], [])

    def test_the_approval_waits_for_a_design_without_gaps_and_for_the_page_the_person_looks_at(self):
        self.start()
        self.write("design/inventory.md", INVENTORY.replace("FEAT-002", "FEAT-009"))
        self.review()
        self.assertIn("the design checks found 1 gap(s)", self.hook())
        self.write("design/inventory.md", INVENTORY)
        self.review()
        self.write("design/gallery.html", "<p>an older page</p>")
        self.assertIn("does not show the design as it is now", self.hook())

    def test_the_persons_approval_locks_the_design_and_counts_once_the_transcript_shows_it(self):
        self.ready()
        line = self.hook()
        self.assertIn("design approved; the design folder, the feature map and the architecture are locked", line)
        held = lockfile.read_design(self.root)
        self.assertEqual(held["folder"], "design")
        self.assertIn("design/screens/home.html", held["files"])
        self.assertIn(".bdd/architecture.md", held["files"])
        self.assertEqual(designstage.status(self.root)["stage"], "approved")
        self.assertIn("still waiting for its origin", designstage.status_line(designstage.status(self.root)))
        self.transcript(typed("p1", "design"))
        self.assertEqual(designstage.verify(self.root), 1)
        self.assertEqual(designstage.status_line(designstage.status(self.root)), "design: approved, locked")

    def test_a_prompt_that_says_something_else_does_not_count(self):
        self.ready()
        self.hook()
        self.transcript(typed("p1", "FEAT-007 rules"))
        designstage.verify(self.root)
        self.assertEqual(designstage.load(self.root)["approvals"][0]["origin"], "invalid")
        self.assertIn("was not typed by a person", designstage.status_line(designstage.status(self.root)))

    def test_a_prompt_the_hook_refused_never_approves_later(self):
        self.start()
        self.assertIn("NOT recorded", self.hook())                     # no review yet: refused, its prompt id kept
        self.review()
        designstage.record(self.root, "approve", "hook", prompt_id="p1", transcript_path="session.jsonl")
        self.transcript(typed("p1", "design"))
        designstage.verify(self.root)
        approval = designstage.load(self.root)["approvals"][0]
        self.assertEqual((approval["origin"], approval["evidence"]),
                         ("invalid", "this prompt was refused when it was typed, so it cannot approve the design later"))
        self.assertNotEqual(designstage.status_line(designstage.status(self.root)), "design: approved, locked")

    def test_a_prompt_typed_long_before_the_approval_was_recorded_does_not_count(self):
        self.ready()
        self.hook()
        self.transcript(typed("p1", "design", timestamp="2020-01-01T00:00:00Z"))
        designstage.verify(self.root)
        self.assertEqual(designstage.load(self.root)["approvals"][0]["evidence"],
                         "the prompt was not typed when this approval was recorded")

    def test_a_deleted_design_record_is_not_read_as_a_stage_never_started(self):
        self.ready()
        self.hook()
        (self.root / ".bdd" / designstage.STATE_FILE).unlink()
        self.assertIn("the design record (.bdd/design-stage.json) is missing", " ".join(designstage.gate_problems(self.root)))

    def test_a_message_with_more_than_the_command_is_not_recorded(self):
        self.ready()
        self.assertIsNone(self.hook("/greenlight:approve design looks great"))
        notice = approvehook.near_miss({"prompt": "/greenlight:approve design looks great", "cwd": str(self.root)})
        self.assertIn("NOT recorded: send one approval per message", notice)

    def test_a_rejection_keeps_the_reason_and_leaves_the_design_open(self):
        self.ready()
        self.assertIn("design rejected (too dark)", self.hook("/greenlight:approve design reject too dark"))
        self.assertFalse(lockfile.design_locked(lockfile.read_design(self.root)))
        self.assertEqual(designstage.status_line(designstage.status(self.root)), "design: drafted, not approved (rejected: too dark)")

    def test_self_reported_is_refused_under_hard_enforcement_and_once_hooks_have_run(self):
        self.ready()
        self.write(".bdd/config.toml", 'enforcement = "hard"\n' + (self.root / ".bdd" / "config.toml").read_text(encoding="utf-8"))
        with self.assertRaisesRegex(UsageError, "hard enforcement"):
            designstage.record(self.root, "approve", "self-reported")
        self.write(".bdd/config.toml", (self.root / ".bdd" / "config.toml").read_text(encoding="utf-8").replace('enforcement = "hard"\n', ""))
        enforcement.touch(self.root, "s1")
        with self.assertRaisesRegex(UsageError, "hooks have run in this project"):
            designstage.record(self.root, "approve", "self-reported")

    def test_no_automatic_approval_of_the_design(self):
        self.ready()
        with self.assertRaises(UsageError):
            designstage.record(self.root, "approve", "auto")

    def test_a_changed_or_added_file_takes_the_approval_away(self):
        self.ready()
        self.hook()
        self.transcript(typed("p1", "design"))
        designstage.verify(self.root)
        self.write("design/screens/new.html", "<p>new</p>")
        self.assertIn("design/screens/new.html was added to the design after its approval",
                      designstage.status_line(designstage.status(self.root)))
        (self.root / "design" / "screens" / "new.html").unlink()
        self.write("design/tokens.css", ":root { --primary: #000; }\n")
        self.assertIn("design/tokens.css changed after the design approval", designstage.status_line(designstage.status(self.root)))

    def test_the_same_prompt_cannot_approve_twice(self):
        self.ready()
        self.hook()
        designstage.reopen(self.root, "again")
        self.review()
        self.hook()
        self.transcript(typed("p1", "design"))
        designstage.verify(self.root)
        origins = [a["origin"] for a in designstage.load(self.root)["approvals"]]
        self.assertEqual(origins, ["human", "invalid"])


class ReopenTest(DesignCase):
    def approved(self) -> None:
        self.ready()
        approvehook.record_design({"prompt": "/greenlight:approve design", "prompt_id": "p1", "transcript_path": "session.jsonl",
                                   "cwd": str(self.root)})
        self.transcript(typed("p1", "design"))
        designstage.verify(self.root)

    def test_reopening_releases_the_lock_and_revokes_the_approval(self):
        self.approved()
        line = designstage.reopen(self.root, "the list needs a filter")
        self.assertIn("design reopened (the list needs a filter): the lock is released and the approval is revoked", line)
        self.assertFalse(lockfile.design_locked(lockfile.read_design(self.root)))
        self.assertEqual(designstage.status_line(designstage.status(self.root)),
                         "design: drafted, not approved (reopened: the list needs a filter)")
        self.assertEqual(designstage.load(self.root)["approvals"][0]["revoked"], "the list needs a filter")

    def test_the_command_line_reopens_the_design_and_names_no_feature(self):
        self.approved()
        self.assertEqual(changecmd.run(["--reopen", "design", "--reason", "new filter"]), 0)
        self.assertEqual(changecmd.run(["FEAT-007", "--reopen", "design", "--reason", "x"]), 2)
        self.assertEqual(changecmd.run(["--reopen", "examples", "--reason", "x"]), 2)

    def test_after_a_change_the_summary_lists_only_what_changed(self):
        self.approved()
        first = designstage.summary_text(self.root)
        self.assertIn("no change since the approval", first)
        designstage.reopen(self.root, "no loading on the list")
        self.write("design/inventory.md", INVENTORY.replace("| loading, empty, error, success |", "| empty, error, success |"))
        text = designstage.summary_text(self.root)
        self.assertIn("1 item changed", text)
        self.assertIn("Changed:\n  S-OR-01  Order list", text)
        self.assertIn("changed: states", text)
        self.assertNotIn("S-IN-01", text.split("Changed:", 1)[1].split("Unchanged:", 1)[0])
        self.assertIn("Not ready to approve:", text, "the review names the design before the change")

    def test_the_first_summary_lists_everything(self):
        self.ready()
        text = designstage.summary_text(self.root)
        self.assertTrue(text.startswith("The product design, not approved before:"), text)
        for key in ("FEAT-001", "S-OR-01", "Architecture: Data store", "design/screens/home.html"):
            self.assertIn(key, text)
        self.assertIn("Design review: PASS", text)
        self.assertIn("To approve, the person types /greenlight:approve design, alone in the message.", text)


class GateTest(DesignCase):
    def setUp(self):
        super().setUp()
        self.feature = state.create(self.root, "FEAT-001", "Sign in", "standard")

    def test_without_the_stage_a_feature_starts_as_before(self):
        self.assertEqual(designstage.gate_problems(self.root), [])
        self.assertNotIn("design", " ".join(gates.gate_problems(self.root, self.feature, state.load(self.feature), "discover")))

    def test_with_the_stage_started_a_feature_waits_for_the_approved_design(self):
        self.ready()
        problems = gates.gate_problems(self.root, self.feature, state.load(self.feature), "discover")
        self.assertIn("the product design is not approved yet", " ".join(problems))
        approvehook.record_design({"prompt": "/greenlight:approve design", "prompt_id": "p1", "transcript_path": "session.jsonl",
                                   "cwd": str(self.root)})
        self.transcript(typed("p1", "design"))
        self.assertEqual(gates.gate_problems(self.root, self.feature, state.load(self.feature), "discover"), [])

    def test_the_stage_record_is_the_command_lines(self):
        self.ready()
        data = json.loads((self.root / ".bdd" / designstage.STATE_FILE).read_text(encoding="utf-8"))
        self.assertEqual(data["approvals"], [])
        from bddlib import guard
        self.assertIn(designstage.STATE_FILE, guard.MANAGED_NAMES)
        self.assertIn(lockfile.DESIGN_FILE, guard.MANAGED_NAMES)


if __name__ == "__main__":
    unittest.main()
