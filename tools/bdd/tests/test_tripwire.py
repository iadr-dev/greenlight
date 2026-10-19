import contextlib
import io
import json
import os
import unittest
from pathlib import Path
from unittest import mock

from bddlib import guard, lockfile, tripwire
from bddlib.errors import StoreError, UsageError

from tests.helpers import ProjectCase


class TripwireCase(ProjectCase):
    def setUp(self):
        super().setUp()
        self.claude_dir = self.root / "user-claude"
        self.claude_dir.mkdir()
        patcher = mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": str(self.claude_dir)})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.plugin = self.root / "plugin"
        self.write("plugin/hooks/hooks.json", '{"hooks": {}}\n')
        self.write("plugin/tools/bdd/bddlib/guard.py", "x = 1\n")
        self.write(".claude/settings.json", '{"permissions": {}}\n')
        tripwire.accept(self.root, self.plugin)                     # the baseline the person's first prompt takes
        self.baseline_file = self.root / ".bdd" / ".integrity" / "baseline.json"
        self.settings = self.root / ".claude" / "settings.json"

    def check(self, tool="Bash"):
        return tripwire.check(self.root, self.plugin, tool)

    def fire(self, *argv: str, payload=None) -> tuple[int, str]:
        said = io.StringIO()
        body = payload if isinstance(payload, str) else json.dumps(
            payload if payload is not None else {"cwd": str(self.root), "tool_name": "Bash"})
        with mock.patch("sys.stdin", io.StringIO(body)), mock.patch.dict(os.environ, {"CLAUDE_PLUGIN_ROOT": str(self.plugin)}), \
                contextlib.redirect_stderr(said), contextlib.redirect_stdout(said):
            code = tripwire.main(list(argv))
        return code, said.getvalue()


class EnforcementFilesTest(TripwireCase):
    def test_nothing_changed_nothing_reported(self):
        self.assertEqual(self.check(), [])
        self.assertIn(self.settings.resolve().as_posix(), tripwire.load_baseline(self.root))
        self.assertEqual(tripwire.violations(self.root), [])

    def test_a_change_is_reported_once_and_stays_open_until_undone(self):
        self.settings.write_text('{"disableAllHooks": true}\n', encoding="utf-8", newline="\n")
        (new,) = self.check("Write")
        self.assertEqual((new["kind"], new["tool"], new["open"]), ("changed", "Write", True))
        self.assertEqual(self.check(), [])                                  # not reported again
        self.assertEqual(len(tripwire.open_violations(self.root)), 1)
        self.settings.write_text('{"permissions": {}}\n', encoding="utf-8", newline="\n")
        self.assertEqual(self.check(), [])
        self.assertEqual(tripwire.open_violations(self.root), [])
        self.assertIn("closed_at", tripwire.violations(self.root)[0])

    def test_added_and_removed_files_are_violations(self):
        self.write(".claude/hooks/evil.sh", "exit 0\n")
        (hook,) = self.check()
        self.assertEqual(hook["kind"], "added")
        self.settings.unlink()
        (gone,) = self.check()
        self.assertEqual(gone["kind"], "removed")

    def test_the_plugin_the_user_settings_and_the_project_config_are_watched(self):
        self.write("plugin/tools/bdd/bddlib/guard.py", "x = 2\n")
        self.write("user-claude/settings.json", "{}\n")
        self.config('enforcement = "soft"\n')
        paths = {Path(v["path"]).name for v in self.check()}
        self.assertEqual(paths, {"guard.py", "settings.json", "config.toml"})

    def test_line_endings_alone_are_not_a_change(self):
        self.settings.write_bytes(b'{"permissions": {}}\r\n')
        self.assertEqual(self.check(), [])


class MissingBaselineTest(TripwireCase):
    def test_a_missing_baseline_is_a_violation_until_the_next_prompt_restores_it(self):
        self.baseline_file.unlink()
        (new,) = self.check()
        self.assertEqual((new["what"], new["kind"]), ("integrity baseline", "missing"))
        self.assertEqual(self.check(), [])                                  # reported once
        self.assertEqual(len(tripwire.open_violations(self.root)), 1)
        self.assertEqual(tripwire.accept(self.root, self.plugin), [])       # the person's next prompt takes a new one
        self.assertEqual(tripwire.open_violations(self.root), [])
        self.assertEqual(self.check(), [])

    def test_a_change_made_with_the_baseline_deleted_is_still_found_from_the_backup(self):
        self.baseline_file.unlink()
        self.settings.write_text("{}\n", encoding="utf-8", newline="\n")
        found = {(v["what"], v["kind"]) for v in self.check()}
        self.assertEqual(found, {("integrity baseline", "missing"), ("enforcement file", "changed")})

    def test_restoring_a_deleted_baseline_reports_what_changed_meanwhile(self):
        self.baseline_file.unlink()
        self.settings.write_text("{}\n", encoding="utf-8", newline="\n")
        self.check()
        self.assertIsNone(tripwire.accept(self.root, self.plugin))          # the change is an open violation
        self.settings.write_text('{"permissions": {}}\n', encoding="utf-8", newline="\n")
        self.check()
        self.assertEqual(tripwire.accept(self.root, self.plugin), [])
        self.baseline_file.unlink()
        self.settings.write_text('{"model": "x"}\n', encoding="utf-8", newline="\n")
        (change,) = [c for c in tripwire.accept(self.root, self.plugin)]
        self.assertEqual(change["kind"], "changed")                         # reported, from the backup copy

    def test_locked_files_are_still_checked_while_the_baseline_is_missing(self):
        lockfile.lock(self.root, self.feature_dir, "FEAT-007", "spec", [self.spec])
        self.baseline_file.unlink()
        self.spec.write_text(self.spec.read_text(encoding="utf-8").replace("succeeds", "fails"), encoding="utf-8", newline="\n")
        self.check()
        self.assertIn("FEAT-007 spec lock", {v["what"] for v in tripwire.open_violations(self.root)})
        self.assertIsNone(tripwire.accept(self.root, self.plugin))

    def test_deleting_the_baseline_to_hide_a_change_blocks_the_gates(self):
        self.walk_to("tasks")
        tripwire.accept(self.root, self.plugin)
        self.baseline_file.unlink()
        self.settings.write_text("{}\n", encoding="utf-8", newline="\n")
        self.check()
        with self.assertRaises(UsageError) as cm:
            self.gate("implement")
        self.assertIn("integrity violation #1 is open", str(cm.exception))


class LockedFilesTest(TripwireCase):
    def test_a_locked_file_that_changed_is_a_violation_until_restored(self):
        lockfile.lock(self.root, self.feature_dir, "FEAT-007", "spec", [self.spec])
        original = self.spec.read_text(encoding="utf-8")
        self.spec.write_text(original.replace("succeeds", "fails"), encoding="utf-8", newline="\n")
        (new,) = self.check("Edit")
        self.assertEqual((new["what"], new["kind"]), ("FEAT-007 spec lock", "changed"))
        self.spec.write_text(original, encoding="utf-8", newline="\n")
        self.check()
        self.assertEqual(tripwire.open_violations(self.root), [])


class GateTest(TripwireCase):
    def test_implement_and_verify_refuse_while_a_violation_is_open(self):
        self.walk_to("tasks")
        self.settings.write_text("{}\n", encoding="utf-8", newline="\n")
        self.check()
        for name in ("implement", "verify"):
            with self.subTest(gate=name), self.assertRaises(UsageError) as cm:
                self.gate(name)
            self.assertIn("integrity violation #1 is open", str(cm.exception))
        self.settings.write_text('{"permissions": {}}\n', encoding="utf-8", newline="\n")
        self.check()
        self.assertEqual(self.gate("implement")["phase"], "verify")

    def test_unreadable_integrity_data_refuses_the_gate_too(self):
        self.walk_to("tasks")
        self.write(".bdd/.integrity/violations.json", "{broken")
        with self.assertRaises(StoreError):
            self.gate("implement")


class AcceptTest(TripwireCase):
    def test_a_change_between_prompts_becomes_the_new_baseline_and_is_on_record(self):
        self.settings.write_text('{"model": "x"}\n', encoding="utf-8", newline="\n")
        (accepted,) = tripwire.accept(self.root, self.plugin)
        self.assertEqual(accepted["kind"], "changed")
        self.assertEqual(self.check(), [])
        history = json.loads(self.baseline_file.read_text(encoding="utf-8"))["accepted"]
        self.assertEqual([h["kind"] for h in history], ["changed"])

    def test_nothing_is_accepted_while_a_violation_is_open(self):
        self.settings.write_text("{}\n", encoding="utf-8", newline="\n")
        self.check()
        self.assertIsNone(tripwire.accept(self.root, self.plugin))
        self.assertEqual(len(tripwire.open_violations(self.root)), 1)


class HookEntryTest(TripwireCase):
    def test_a_violation_is_reported_to_the_model_with_exit_2(self):
        self.assertEqual(self.fire(), (0, ""))
        self.settings.write_text("{}\n", encoding="utf-8", newline="\n")
        code, message = self.fire()
        self.assertEqual(code, 2)
        self.assertIn("settings.json", message)
        self.assertIn("implement and verify gates will refuse", message)
        self.assertEqual(self.fire(), (0, ""))                      # once

    def test_accept_mode_says_what_it_accepted_and_never_blocks_the_prompt(self):
        self.assertEqual(self.fire("--accept"), (0, ""))
        self.settings.write_text('{"model": "x"}\n', encoding="utf-8", newline="\n")
        code, said = self.fire("--accept")
        self.assertEqual(code, 0)
        self.assertIn("accepted changes made since the last check", said)
        self.settings.write_text("{}\n", encoding="utf-8", newline="\n")
        self.fire()
        code, said = self.fire("--accept")
        self.assertEqual(code, 0)
        self.assertIn("violation is still open", said)

    def test_ignored_input(self):
        for payload in ("not json", "[]", {"cwd": str(self.root.parent), "tool_name": "Bash"}):
            with self.subTest(payload=payload):
                self.assertEqual(self.fire(payload=payload), (0, ""))
        self.assertEqual(self.fire("--bogus")[0], 2)

    def test_unreadable_data_is_reported_and_never_blocks_a_prompt(self):
        self.write(".bdd/.integrity/violations.json", "{broken")
        code, message = self.fire()
        self.assertEqual(code, 2)
        self.assertIn("could not run", message)
        code, message = self.fire("--accept")
        self.assertEqual(code, 0)
        self.assertIn("could not be refreshed", message)


class GuardProtectsTheDataTest(TripwireCase):
    def test_the_agent_cannot_write_the_baseline_or_the_violations(self):
        for name in ("baseline.json", "violations.json"):
            path = self.root / ".bdd" / ".integrity" / name
            with self.subTest(path=name):
                self.assertIn("managed by the bdd command line", guard.evaluate(
                    {"tool_name": "Write", "cwd": str(self.root), "tool_input": {"file_path": str(path)}}))
        self.assertIn("managed by", guard.evaluate(
            {"tool_name": "Bash", "cwd": str(self.root), "tool_input": {"command": "rm .bdd/.integrity/baseline.json"}}))


if __name__ == "__main__":
    unittest.main()
