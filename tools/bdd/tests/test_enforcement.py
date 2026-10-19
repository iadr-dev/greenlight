import os
import time
import unittest
from pathlib import Path
from unittest import mock

from bddlib import enforcement, guard, state

from tests.helpers import ProjectCase


class SessionIdTest(unittest.TestCase):
    def test_only_safe_names_are_accepted(self):
        for good in ("20acf6d7-fc9e-4214-a7eb-d7eded46042e", "abc", "a.b_c-d", "x" * 80):
            with self.subTest(good=good):
                self.assertEqual(enforcement.safe_session(good), good)
        for bad in (None, "", ".", "..", "../etc", "a/b", "a\\b", "x" * 81, "with space", "tab\t", "semi;colon"):
            with self.subTest(bad=bad):
                self.assertIsNone(enforcement.safe_session(bad))

    def test_current_session_comes_from_the_environment(self):
        with mock.patch.dict(os.environ, {enforcement.SESSION_ENV: "sess-1"}):
            self.assertEqual(enforcement.current_session(), "sess-1")
        with mock.patch.dict(os.environ, {enforcement.SESSION_ENV: "../evil"}):
            self.assertIsNone(enforcement.current_session())


class MarkerTest(ProjectCase):
    def test_touch_creates_one_marker_per_session(self):
        self.assertFalse(enforcement.active(self.root, "s1"))
        self.assertTrue(enforcement.touch(self.root, "s1"))
        self.assertTrue(enforcement.touch(self.root, "s1"))          # idempotent
        self.assertTrue(enforcement.active(self.root, "s1"))
        self.assertFalse(enforcement.active(self.root, "s2"))
        names = sorted(p.name for p in enforcement.marker_dir(self.root).iterdir())
        self.assertEqual(names, ["_seen", "s1"])                      # one marker per session + the permanent one

    def test_unsafe_or_missing_ids_leave_no_trace(self):
        for bad in (None, "", "../escape", "a/b"):
            with self.subTest(bad=bad):
                self.assertFalse(enforcement.touch(self.root, bad))
                self.assertFalse(enforcement.active(self.root, bad))
        self.assertFalse((self.root / ".bdd" / "escape").exists())
        self.assertFalse(enforcement.marker_dir(self.root).exists())

    def test_old_markers_are_pruned_but_recent_ones_are_kept(self):
        enforcement.touch(self.root, "old")
        enforcement.touch(self.root, "recent")
        ancient = time.time() - enforcement.KEEP_SECONDS - 3600
        for name in ("old", enforcement.SEEN_MARKER):
            os.utime(enforcement.marker_dir(self.root) / name, (ancient, ancient))
        enforcement.touch(self.root, "new")                           # creating a marker prunes
        names = sorted(p.name for p in enforcement.marker_dir(self.root).iterdir())
        self.assertEqual(names, ["_seen", "new", "recent"])           # the permanent marker is never pruned

    def test_hooks_seen_survives_losing_any_single_file(self):
        self.assertFalse(enforcement.hooks_seen(self.root))
        enforcement.touch(self.root, "s1")
        self.assertTrue(enforcement.hooks_seen(self.root))
        (enforcement.marker_dir(self.root) / enforcement.SEEN_MARKER).unlink()
        self.assertTrue(enforcement.hooks_seen(self.root))            # a session marker is enough
        enforcement.touch(self.root, "s1")                            # and the next guard call repairs the permanent one
        self.assertTrue((enforcement.marker_dir(self.root) / enforcement.SEEN_MARKER).is_file())
        (enforcement.marker_dir(self.root) / "s1").unlink()
        self.assertTrue(enforcement.hooks_seen(self.root))            # the permanent marker is enough too

    def test_a_session_cannot_be_named_after_a_reserved_marker(self):
        self.assertIsNone(enforcement.safe_session(enforcement.SEEN_MARKER))
        self.assertFalse(enforcement.touch(self.root, "_anything"))


class GuardLeavesMarkersTest(ProjectCase):
    def call(self, session_id, cwd=None):
        return guard.evaluate({"tool_name": "Write", "tool_input": {"file_path": str(self.root / "src" / "a.py")},
                               "cwd": str(cwd or self.root), "session_id": session_id})

    def test_the_guard_records_that_hooks_ran_in_a_session(self):
        self.assertIsNone(self.call("sess-A"))
        self.assertTrue(enforcement.active(self.root, "sess-A"))

    def test_even_a_blocked_call_leaves_the_marker(self):
        reason = guard.evaluate({"tool_name": "Write", "session_id": "sess-B", "cwd": str(self.root),
                                 "tool_input": {"file_path": str(self.feature_dir / "state.json")}})
        self.assertIn("managed by the bdd command line", reason)
        self.assertTrue(enforcement.active(self.root, "sess-B"))

    def test_nothing_is_written_outside_a_project_or_for_unsafe_ids(self):
        self.assertIsNone(self.call("../../escape"))
        self.assertFalse((self.root / "escape").exists())
        import tempfile
        with tempfile.TemporaryDirectory() as elsewhere:
            self.assertIsNone(self.call("sess-C", cwd=Path(elsewhere)))
            self.assertEqual(list(Path(elsewhere).iterdir()), [])

    def test_the_agent_cannot_create_or_delete_markers(self):
        marker = str(enforcement.marker_dir(self.root) / "forged")
        self.assertIn("managed by the bdd command line", guard.evaluate(
            {"tool_name": "Write", "cwd": str(self.root), "tool_input": {"file_path": marker}}))
        enforcement.touch(self.root, "real")
        self.assertIn("managed by", guard.evaluate(
            {"tool_name": "Bash", "cwd": str(self.root), "tool_input": {"command": "rm .bdd/.enforcement/real"}}))


class ClassifyTest(ProjectCase):
    def level(self) -> tuple[str, list[str]]:
        return enforcement.classify(self.root, self.data())

    def record_gate_in(self, session: str | None, name: str = "discover") -> None:
        env = {enforcement.SESSION_ENV: session} if session else {}
        with mock.patch.dict(os.environ, env):
            if not session:
                os.environ.pop(enforcement.SESSION_ENV, None)
            self.gate(name)

    def test_hard_when_every_session_left_a_marker_and_nothing_was_self_reported(self):
        enforcement.touch(self.root, "s1")
        self.record_gate_in("s1")
        self.assertEqual(self.level(), ("hard", []))

    def test_soft_without_any_evidence(self):
        level, reasons = self.level()
        self.assertEqual(level, "soft")
        self.assertIn("no session left evidence that hooks were active", reasons)

    def test_soft_when_a_gate_was_recorded_outside_a_session(self):
        self.record_gate_in(None)
        level, reasons = self.level()
        self.assertEqual(level, "soft")
        self.assertIn("the discover gate was recorded outside a Claude Code session", reasons)

    def test_soft_when_hooks_left_no_trace_in_a_session(self):
        self.record_gate_in("ghost")
        level, reasons = self.level()
        self.assertEqual(level, "soft")
        self.assertIn("hooks left no trace in session ghost", reasons)

    def test_soft_when_an_approval_was_self_reported(self):
        enforcement.touch(self.root, "s1")
        self.record_gate_in("s1")
        self.config('enforcement = "soft"\n')            # the person declared that this project runs without hooks
        self.approve("rules", "self-reported")
        level, reasons = self.level()
        self.assertEqual(level, "soft")
        self.assertIn("the rules approval was self-reported, not typed by the person", reasons)


if __name__ == "__main__":
    unittest.main()
