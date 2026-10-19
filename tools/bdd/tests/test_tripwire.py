import contextlib
import io
import json
import os
import unittest
from pathlib import Path
from unittest import mock

from bddlib import guard, lockfile, tripwire
from bddlib.errors import UsageError

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

    def check(self, tool="Bash"):
        return tripwire.check(self.root, self.plugin, tool)

    def fire(self, *argv: str, payload=None) -> tuple[int, str]:
        err = io.StringIO()
        body = payload if isinstance(payload, str) else json.dumps(
            payload if payload is not None else {"cwd": str(self.root), "tool_name": "Bash"})
        with mock.patch("sys.stdin", io.StringIO(body)), mock.patch.dict(os.environ, {"CLAUDE_PLUGIN_ROOT": str(self.plugin)}), \
                contextlib.redirect_stderr(err):
            code = tripwire.main(list(argv))
        return code, err.getvalue()


class EnforcementFilesTest(TripwireCase):
    def test_the_first_run_takes_what_is_there_as_the_baseline(self):
        self.assertEqual(self.check(), [])
        self.assertIn(self.root.joinpath(".claude/settings.json").resolve().as_posix(), tripwire.load_baseline(self.root))
        self.assertEqual(tripwire.violations(self.root), [])

    def test_a_change_is_reported_once_and_stays_open_until_undone(self):
        self.check()
        settings = self.root / ".claude" / "settings.json"
        settings.write_text('{"disableAllHooks": true}\n', encoding="utf-8", newline="\n")
        (new,) = self.check("Write")
        self.assertEqual((new["kind"], new["tool"], new["open"]), ("changed", "Write", True))
        self.assertEqual(self.check(), [])                                  # not reported again
        self.assertEqual(len(tripwire.open_violations(self.root)), 1)
        settings.write_text('{"permissions": {}}\n', encoding="utf-8", newline="\n")
        self.assertEqual(self.check(), [])
        self.assertEqual(tripwire.open_violations(self.root), [])
        self.assertIn("closed_at", tripwire.violations(self.root)[0])

    def test_added_and_removed_files_are_violations(self):
        self.check()
        self.write(".claude/hooks/evil.sh", "exit 0\n")
        (hook,) = self.check()
        self.assertEqual(hook["kind"], "added")
        (self.root / ".claude" / "settings.json").unlink()
        (gone,) = self.check()
        self.assertEqual(gone["kind"], "removed")

    def test_the_plugin_the_user_settings_and_the_project_config_are_watched(self):
        self.check()
        self.write("plugin/tools/bdd/bddlib/guard.py", "x = 2\n")
        self.write("user-claude/settings.json", "{}\n")
        self.config('enforcement = "soft"\n')
        paths = {Path(v["path"]).name for v in self.check()}
        self.assertEqual(paths, {"guard.py", "settings.json", "config.toml"})

    def test_line_endings_alone_are_not_a_change(self):
        self.check()
        (self.root / ".claude" / "settings.json").write_bytes(b'{"permissions": {}}\r\n')
        self.assertEqual(self.check(), [])


class LockedFilesTest(TripwireCase):
    def lock(self):
        lockfile.lock(self.root, self.feature_dir, "FEAT-007", "spec", [self.spec])

    def test_a_locked_file_that_changed_is_a_violation_until_restored(self):
        self.lock()
        self.check()
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
        self.check()
        settings = self.root / ".claude" / "settings.json"
        settings.write_text("{}\n", encoding="utf-8", newline="\n")
        self.check()
        for name in ("implement", "verify"):
            with self.subTest(gate=name), self.assertRaises(UsageError) as cm:
                self.gate(name)
            self.assertIn("integrity violation #1 is open", str(cm.exception))
        settings.write_text('{"permissions": {}}\n', encoding="utf-8", newline="\n")
        self.check()
        self.assertEqual(self.gate("implement")["phase"], "verify")


class AcceptTest(TripwireCase):
    def test_a_change_between_prompts_becomes_the_new_baseline(self):
        self.check()
        (self.root / ".claude" / "settings.json").write_text('{"model": "x"}\n', encoding="utf-8", newline="\n")
        self.assertTrue(tripwire.accept(self.root, self.plugin))
        self.assertEqual(self.check(), [])

    def test_nothing_is_accepted_while_a_violation_is_open(self):
        self.check()
        settings = self.root / ".claude" / "settings.json"
        settings.write_text("{}\n", encoding="utf-8", newline="\n")
        self.check()
        self.assertFalse(tripwire.accept(self.root, self.plugin))
        self.assertEqual(len(tripwire.open_violations(self.root)), 1)


class HookEntryTest(TripwireCase):
    def test_a_violation_is_reported_to_the_model_with_exit_2(self):
        self.assertEqual(self.fire(), (0, ""))
        (self.root / ".claude" / "settings.json").write_text("{}\n", encoding="utf-8", newline="\n")
        code, message = self.fire()
        self.assertEqual(code, 2)
        self.assertIn("settings.json", message)
        self.assertIn("implement and verify gates will refuse", message)
        self.assertEqual(self.fire(), (0, ""))                      # once

    def test_accept_mode_and_ignored_input(self):
        self.assertEqual(self.fire("--accept"), (0, ""))
        self.assertIsNotNone(tripwire.load_baseline(self.root))
        for payload in ("not json", "[]", {"cwd": str(self.root.parent), "tool_name": "Bash"}):
            with self.subTest(payload=payload):
                self.assertEqual(self.fire(payload=payload), (0, ""))
        self.assertEqual(self.fire("--bogus")[0], 2)

    def test_unreadable_data_never_blocks_the_tool(self):
        self.check()
        self.write(".bdd/.integrity/violations.json", "{broken")
        code, message = self.fire()
        self.assertEqual(code, 0)
        self.assertIn("could not compare", message)


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
