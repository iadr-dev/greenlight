import contextlib
import io
import json
import os
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from bddlib import guard, integrityack, lockfile, tripwire
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

    def test_a_malformed_backup_is_a_violation_not_a_crash(self):
        self.baseline_file.unlink()
        for text in ("[]", '{"schema": 1}', '{"schema": 1, "files": {"a": 3}}', '{"schema": 9, "files": {}}', "{broken"):
            with self.subTest(text=text):
                tripwire.backup_path(self.root).write_text(text, encoding="utf-8")
                kinds = {(v["what"], v["kind"]) for v in tripwire.violations(self.root) if v["open"]} |                     {(v["what"], v["kind"]) for v in self.check()}
                self.assertIn(("baseline backup", "corrupt"), kinds)
                self.assertEqual(self.fire()[0], 0)                          # already reported, and no traceback
        self.assertEqual(tripwire.accept(self.root, self.plugin), [])        # the prompt replaces both copies
        self.assertTrue(tripwire._valid_baseline(tripwire.load_backup(self.root)))

    def test_a_malformed_project_baseline_is_reported_and_refuses_the_gates(self):
        self.baseline_file.write_text('{"schema": 1, "files": []}', encoding="utf-8")
        code, message = self.fire()
        self.assertEqual(code, 2)
        self.assertIn("integrity baseline) is corrupt", message)
        self.assertIn(("integrity baseline", "corrupt"), {(v["what"], v["kind"]) for v in tripwire.open_violations(self.root)})

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
        for name in ("baseline.json", "violations.json", "acknowledgements.json"):
            path = self.root / ".bdd" / ".integrity" / name
            with self.subTest(path=name):
                self.assertIn("managed by the bdd command line", guard.evaluate(
                    {"tool_name": "Write", "cwd": str(self.root), "tool_input": {"file_path": str(path)}}))
        self.assertIn("managed by", guard.evaluate(
            {"tool_name": "Bash", "cwd": str(self.root), "tool_input": {"command": "rm .bdd/.integrity/baseline.json"}}))


class PluginUpdateTest(TripwireCase):
    """A new version is named at a prompt, and only when Claude Code's own record names exactly that copy."""

    def setUp(self):
        super().setUp()
        self.old = self.updated("1.2.1")
        tripwire.accept(self.root, self.old)

    def copy(self, rel: str, version: str, guard: str = "x = 1\n") -> Path:
        self.write(f"{rel}/.claude-plugin/plugin.json", f'{{"version": "{version}"}}\n')
        self.write(f"{rel}/hooks/hooks.json", '{"hooks": {}}\n')
        self.write(f"{rel}/tools/bdd/bddlib/guard.py", guard)
        self.write(f"{rel}/tools/bdd/bddlib/new_module.py", "y = 1\n")
        return self.root / rel

    def updated(self, version="1.2.2", guard="x = 1\n", record=True) -> Path:
        """Where Claude Code installs a version (its own folder in the plugin cache), and its record that it runs it."""
        copy = self.copy(f"user-claude/plugins/cache/greenlight/greenlight/{version}", version, guard)
        if record:
            self.record(copy, version)
        return copy

    def record(self, copy: Path, version: str, entries: list | None = None) -> None:
        self.write("user-claude/plugins/installed_plugins.json", json.dumps({"version": 2, "plugins": {
            "greenlight@greenlight": entries if entries is not None else [{"installPath": str(copy.resolve()), "version": version}],
            "other@market": [{"installPath": "/x", "version": "1.0.0"}]}}))

    def prompt(self, plugin: Path) -> str:
        said = io.StringIO()
        with contextlib.redirect_stdout(said):
            tripwire.run_accept(self.root, plugin)
        return said.getvalue()

    def test_a_new_version_claude_code_installed_is_named_at_the_prompt_with_one_line(self):
        new = self.updated(guard="x = 2\n")
        said = self.prompt(new)
        self.assertIn("plugin updated from 1.2.1 to 1.2.2; baseline refreshed", said)
        self.assertNotIn("plugin:", said)                                         # not a list of the plugin's files
        self.assertEqual(tripwire.check(self.root, new, "Bash"), [])
        *_, update = [h for h in json.loads(self.baseline_file.read_text(encoding="utf-8"))["accepted"] if h["kind"] == "plugin updated"]
        self.assertEqual((update["from"], update["to"]), ("1.2.1", "1.2.2"))
        self.assertEqual(tripwire.summary(self.root), ("ok", "plugin updated from 1.2.1 to 1.2.2; baseline refreshed"))

    def test_the_tool_call_check_never_takes_a_new_version(self):
        new = self.updated(guard="x = 2\n")
        found = {v["path"] for v in tripwire.check(self.root, new, "Bash")}
        self.assertIn("plugin:tools/bdd/bddlib/guard.py", found)
        self.assertEqual(tripwire.load_baseline(self.root)["plugin:tools/bdd/bddlib/guard.py"],
                         lockfile.file_digest(self.old / "tools/bdd/bddlib/guard.py"))

    def test_a_plugin_root_claude_code_does_not_name_is_reported_and_not_an_update(self):
        """A CLAUDE_PLUGIN_ROOT pointing at a tampered copy with a bumped version, in the cache but not in the record."""
        tampered = self.updated("9.9.9", guard="x = 0  # tampered\n", record=False)
        self.assertIsNone(tripwire.plugin_update(tripwire.baseline_data(self.root), tampered))
        found = {v["path"] for v in tripwire.check(self.root, tampered, "Bash")}
        self.assertIn("plugin:tools/bdd/bddlib/guard.py", found)
        self.assertNotIn("plugin updated", self.prompt(tampered))
        self.assertTrue(tripwire.open_violations(self.root))

    def test_a_record_edited_to_name_a_tampered_copy_is_a_violation(self):
        tampered = self.updated("9.9.9", guard="x = 0  # tampered\n")      # the record now names it too
        names = {Path(v["path"]).name for v in tripwire.check(self.root, tampered, "Bash")}
        self.assertTrue({"installed_plugins.json", "guard.py"} <= names)
        self.assertIsNone(tripwire.accept(self.root, tampered))

    def test_an_open_violation_on_a_plugin_file_holds_the_prompt_back(self):
        self.write("user-claude/plugins/cache/greenlight/greenlight/1.2.1/tools/bdd/bddlib/guard.py", "x = 3\n")
        self.assertTrue(tripwire.check(self.root, self.old, "Bash"))
        new = self.updated(guard="x = 3\n")                                 # the new copy carries the same change
        self.assertNotIn("plugin updated", self.prompt(new))
        self.assertEqual([v["path"] for v in tripwire.open_violations(self.root)], ["plugin:tools/bdd/bddlib/guard.py"])

    def test_a_violation_in_a_copy_that_no_longer_runs_closes_at_the_update(self):
        self.write("user-claude/plugins/cache/greenlight/greenlight/1.2.1/tools/bdd/bddlib/guard.py", "x = 3\n")
        self.assertTrue(tripwire.check(self.root, self.old, "Bash"))
        self.assertIn("plugin updated", self.prompt(self.updated()))       # the copy that runs now is as recorded
        self.assertEqual(tripwire.violations(self.root)[-1]["closed_by"], "undone")

    def test_a_record_of_another_shape_is_not_an_update(self):
        new = self.updated()
        for entries in ([], [{"installPath": str(new.resolve()), "version": "1.2.2"}] * 2,
                        [{"installPath": str(new.resolve()), "version": "1.2.1"}], ["x"], None):
            with self.subTest(entries=entries):
                if entries is None:
                    self.write("user-claude/plugins/installed_plugins.json", '["not", "a", "record"]')
                else:
                    self.record(new, "1.2.2", entries)
                self.assertFalse(tripwire.names_this_copy(new))
                self.assertIsNone(tripwire.plugin_update(tripwire.baseline_data(self.root), new))

    def test_a_new_version_outside_the_plugin_cache_is_not_an_update(self):
        other = self.copy("plugin2", "1.2.2", guard="x = 0  # tampered\n")
        self.assertIsNone(tripwire.plugin_update(tripwire.baseline_data(self.root), other))

    def test_claude_codes_record_of_its_plugins_is_watched(self):
        self.write("user-claude/plugins/installed_plugins.json", '{"greenlight": "/tmp/evil"}\n')
        self.write("user-claude/plugins/known_marketplaces.json", '{"evil": {}}\n')
        names = {Path(v["path"]).name for v in tripwire.check(self.root, self.old, "Bash")}
        self.assertEqual(names, {"installed_plugins.json", "known_marketplaces.json"})

    def test_a_plugin_file_edited_in_place_is_a_violation_even_with_a_new_version(self):
        base = "user-claude/plugins/cache/greenlight/greenlight/1.2.1"
        self.write(f"{base}/tools/bdd/bddlib/guard.py", "x = 2\n")
        self.write(f"{base}/.claude-plugin/plugin.json", '{"version": "9.9.9"}\n')
        found = {(v["path"], v["kind"]) for v in tripwire.check(self.root, self.old, "Bash")}
        self.assertEqual(found, {("plugin:tools/bdd/bddlib/guard.py", "changed"), ("plugin:.claude-plugin/plugin.json", "changed")})

    def test_a_baseline_from_before_keys_by_absolute_path_and_is_read_as_the_old_plugin(self):
        data = json.loads(self.baseline_file.read_text(encoding="utf-8"))
        old_root = self.old.resolve().as_posix()
        data["files"] = {(old_root + "/" + k.removeprefix("plugin:") if k.startswith("plugin:") else k): v
                         for k, v in data["files"].items()}
        del data["plugin"], data["taken_at"]
        self.baseline_file.write_text(json.dumps(data), encoding="utf-8")
        self.assertEqual(tripwire.check(self.root, self.old, "Bash"), [])          # same folder: nothing changed
        stale = {"id": 1, "what": "enforcement file", "kind": "added", "path": old_root + "/tools/bdd/bddlib/guard.py",
                 "at": "2026-11-05T00:00:00+00:00", "tool": "Bash", "open": True}            # what 1.2.1 opened per file
        (self.root / ".bdd/.integrity/violations.json").write_text(json.dumps({"schema": 1, "items": [stale]}), encoding="utf-8")
        self.assertIn("plugin updated from 1.2.1 to 1.2.2", self.prompt(self.updated()))
        self.assertEqual(tripwire.violations(self.root)[0]["closed_by"], "undone")


class FirstPromptTest(ProjectCase):
    """`bdd init` takes no baseline; the person's first prompt does, and clears the missing baseline a tool call saw."""

    def setUp(self):
        super().setUp()
        patcher = mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": str(self.root / "user-claude")})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_the_first_prompt_takes_the_baseline_and_clears_it_missing(self):
        (missing,) = tripwire.check(self.root, None, "Bash")
        self.assertEqual((missing["what"], missing["kind"]), ("integrity baseline", "missing"))
        self.assertEqual(tripwire.accept(self.root, None), [])
        self.assertEqual(tripwire.open_violations(self.root), [])
        self.assertEqual(tripwire.check(self.root, None, "Bash"), [])

    def test_a_change_made_with_both_copies_gone_is_still_a_violation(self):
        tripwire.accept(self.root, None)
        self.config('enforcement = "soft"\n')
        (self.root / ".bdd/.integrity/baseline.json").unlink()
        tripwire.backup_path(self.root).write_text("{broken", encoding="utf-8")
        found = {(v["what"], v["kind"]) for v in tripwire.check(self.root, None, "Bash")}
        self.assertIn(("baseline backup", "corrupt"), found)


class CheckFailureTest(TripwireCase):
    def test_a_check_that_crashes_fails_closed(self):
        self.walk_to("tasks")
        tripwire.accept(self.root, self.plugin)
        with mock.patch.object(tripwire, "check", side_effect=AttributeError("'list' object has no attribute 'get'")):
            code, message = self.fire()
        self.assertEqual(code, 2)
        self.assertIn("could not run", message)
        with self.assertRaises(UsageError):
            self.gate("implement")
        self.assertIsNone(tripwire.accept(self.root, self.plugin))
        self.assertEqual(self.check(), [])                                        # the next check that runs closes it
        self.assertEqual(tripwire.open_violations(self.root), [])

    def test_a_prompt_check_that_crashes_never_blocks_the_prompt(self):
        with mock.patch.object(tripwire, "accept", side_effect=TypeError("bad shape")):
            self.assertEqual(self.fire("--accept")[0], 0)


class NothingIsAcceptedByTimingTest(TripwireCase):
    """Once a tool call has seen a change, only the person's acknowledgement closes it, however it was made."""

    def persons_edit(self, text='{"model": "x"}\n'):
        self.settings.write_text(text, encoding="utf-8", newline="\n")

    def test_the_persons_change_seen_by_a_background_agents_call_waits_for_the_acknowledgement(self):
        self.persons_edit()
        code, message = self.fire(payload={"cwd": str(self.root), "tool_name": "Bash", "tool_use_id": "bg-1"})
        self.assertEqual(code, 2)
        self.assertIn("/greenlight:approve integrity #1 <reason>", message)
        self.assertIn("settings.json (enforcement file) was changed (sha256 ", message)
        self.assertIsNone(tripwire.accept(self.root, self.plugin))

    def test_the_prompt_names_the_one_line_to_type_and_the_files(self):
        self.persons_edit()
        self.check()
        self.config('enforcement = "soft"\n')
        self.check()
        code, said = self.fire("--accept")
        self.assertEqual(code, 0)
        self.assertIn("an integrity violation is still open, so the baseline was not refreshed (2 open)", said)
        self.assertIn("type one line in Claude Code: /greenlight:approve integrity #1,#2 <reason>", said)

    def test_a_forged_call_record_changes_nothing(self):
        calls = self.root / ".bdd" / ".integrity" / "calls.json"
        calls.write_text(json.dumps({"schema": 1, "stats": {}, "calls": {"bg-1": {"started": "2999-01-01T00:00:00+00:00",
                                     "alone": True, "seen": {self.settings.resolve().as_posix(): "x"}}}}), encoding="utf-8")
        self.persons_edit()
        (new,) = self.check()
        self.assertNotIn("before_call", new)
        self.assertIsNone(tripwire.accept(self.root, self.plugin))

    def test_a_file_time_set_back_changes_nothing(self):
        self.persons_edit('{"disableAllHooks": true}\n')
        os.utime(self.settings, (1_000_000_000, 1_000_000_000))
        self.check()
        self.assertIsNone(tripwire.accept(self.root, self.plugin))

    def test_a_background_write_after_the_call_ended_is_never_accepted(self):
        self.assertEqual(self.check(), [])                                   # the call that started it ends clean
        self.persons_edit('{"disableAllHooks": true}\n')                    # the shell it left behind writes later
        self.check()                                                         # the next call sees it
        self.assertIsNone(tripwire.accept(self.root, self.plugin))
        self.assertEqual(len(tripwire.open_violations(self.root)), 1)

    def test_a_change_no_tool_call_saw_is_accepted_at_the_next_prompt(self):
        self.persons_edit()
        (accepted,) = tripwire.accept(self.root, self.plugin)
        self.assertEqual(accepted["kind"], "changed")


class AcknowledgeTest(TripwireCase):
    def violate(self, text='{"disableAllHooks": true}\n'):
        self.settings.write_text(text, encoding="utf-8", newline="\n")
        self.check("Write")

    def acknowledge(self, typed="#1 tools reinstalled", prompt_id="p-1"):
        return integrityack.acknowledge(self.root, self.plugin, typed, session="s-1", prompt_id=prompt_id,
                                        transcript_path=str(self.transcripts / "s-1.jsonl"))

    def typed(self, prompt_id="p-1", typed="#1 tools reinstalled", stamp="2999-01-01T00:00:00Z", **origin):
        entry = {"type": "user", "promptId": prompt_id, "origin": origin or {"kind": "human"},
                 "message": {"role": "user", "content": f"/greenlight:approve integrity {typed}"}}
        return {**entry, "timestamp": stamp} if stamp else entry

    def test_the_acknowledgement_closes_the_violation_with_who_when_and_why_once_the_transcript_confirms_it(self):
        self.violate()
        entry, left = self.acknowledge()
        self.assertEqual((entry["status"], [v["id"] for v in entry["violations"]], left), ("pending", [1], []))
        self.assertIn("sha256", entry["shown"][0])
        self.assertEqual(integrityack.settle(self.root), [])                     # not in the transcript yet
        self.assertEqual(len(tripwire.open_violations(self.root)), 1)
        self.transcript(self.typed(), name="s-1.jsonl")
        (applied,) = integrityack.settle(self.root)
        self.assertEqual(applied["origin"], "human")
        (item,) = tripwire.violations(self.root)
        self.assertEqual((item["open"], item["closed_by"], item["acknowledgement"]["reason"]), (False, "acknowledged", "tools reinstalled"))
        self.assertIn("at", item["acknowledgement"])
        self.assertEqual(self.check(), [])
        self.assertEqual([v["id"] for v in integrityack.acknowledged(self.root)], [1])

    def test_without_ids_it_covers_the_one_open_violation_and_is_refused_with_more(self):
        self.violate()
        entry, _ = self.acknowledge("tools reinstalled")
        self.assertEqual([v["id"] for v in entry["violations"]], [1])
        self.config('enforcement = "soft"\n')
        self.check()
        with self.assertRaises(UsageError) as cm:
            self.acknowledge("they are mine", prompt_id="p-2")
        self.assertIn("#1,#2", str(cm.exception))

    def test_named_ids_close_only_those(self):
        self.violate()
        self.config('enforcement = "soft"\n')
        self.check()
        entry, _ = self.acknowledge("#2 I set soft myself")
        self.assertEqual(([v["id"] for v in entry["violations"]], entry["reason"]), ([2], "I set soft myself"))
        self.transcript(self.typed(typed="#2 I set soft myself"), name="s-1.jsonl")
        integrityack.settle(self.root)
        self.assertEqual([v["id"] for v in tripwire.open_violations(self.root)], [1])
        with self.assertRaises(UsageError):
            self.acknowledge("#9 no such one", prompt_id="p-3")

    def test_a_violation_reported_after_the_prompt_was_written_is_not_closed(self):
        self.violate()
        self.acknowledge()
        self.transcript(self.typed(stamp="2000-01-01T00:00:00Z"), name="s-1.jsonl")    # written before the violation
        (applied,) = integrityack.settle(self.root)
        self.assertEqual(applied["status"], "applied")
        self.assertEqual([v["id"] for v in tripwire.open_violations(self.root)], [1])

    def test_a_prompt_without_a_timestamp_is_dated_by_the_hook(self):
        self.violate()
        self.acknowledge()
        self.transcript(self.typed(stamp=None), name="s-1.jsonl")
        (applied,) = integrityack.settle(self.root)
        self.assertEqual(applied["prompt_at"], datetime.fromisoformat(applied["at"]).isoformat())
        self.assertEqual(tripwire.open_violations(self.root), [])

    def test_a_file_that_changed_after_it_was_reported_is_not_covered(self):
        self.violate()
        self.settings.write_text('{"disableAllHooks": true, "more": 1}\n', encoding="utf-8", newline="\n")
        with self.assertRaises(UsageError) as cm:
            self.acknowledge()
        self.assertIn("changed after it was reported", str(cm.exception))
        (new,) = self.check()                                                     # reported again, with what is there now
        self.assertEqual(new["kind"], "changed")
        self.assertEqual(tripwire.violations(self.root)[0]["closed_by"], "changed again")

    def test_a_change_after_the_acknowledgement_is_a_new_violation(self):
        self.violate()
        self.acknowledge()
        self.settings.write_text('{"disableAllHooks": true, "more": 1}\n', encoding="utf-8", newline="\n")
        self.transcript(self.typed(), name="s-1.jsonl")
        (new,) = self.check()
        self.assertEqual(new["kind"], "changed")
        self.assertTrue(tripwire.open_violations(self.root))

    def test_only_the_covered_files_enter_the_baseline(self):
        self.baseline_file.unlink()
        self.violate()                                                            # missing baseline and settings, from the backup
        self.config('enforcement = "soft"\n')                                    # changed after, not named
        self.check()
        entry, left = self.acknowledge("#2 the settings are mine")
        self.assertEqual([Path(v["path"]).name for v in entry["violations"]], ["settings.json"])
        self.transcript(self.typed(typed="#2 the settings are mine"), name="s-1.jsonl")
        integrityack.settle(self.root)
        names = {Path(v["path"]).name for v in self.check()} | {Path(v["path"]).name for v in tripwire.open_violations(self.root)}
        self.assertIn("config.toml", names)
        self.assertNotIn("settings.json", names)

    def test_a_prompt_the_person_did_not_type_does_not_count(self):
        for origin in ({"kind": "task-notification"}, {"kind": "agent"}):
            with self.subTest(origin=origin):
                self.violate()
                prompt_id = f"p-{origin['kind']}"
                self.acknowledge(prompt_id=prompt_id)
                self.transcript(self.typed(prompt_id, **origin), name="s-1.jsonl")
                self.assertEqual(integrityack.settle(self.root), [])
                self.assertTrue(tripwire.open_violations(self.root))

    def test_a_prompt_that_says_something_else_does_not_count(self):
        self.violate()
        self.acknowledge()
        self.transcript(self.typed(typed="#1 something else"), name="s-1.jsonl")
        self.assertEqual(integrityack.settle(self.root), [])
        self.assertTrue(tripwire.open_violations(self.root))

    def test_a_prompt_counts_once_for_good_even_after_the_records_are_set_aside(self):
        self.violate()
        with self.assertRaises(UsageError):                                       # a refused one keeps its prompt id too
            self.acknowledge("#9 nothing", prompt_id="p-refused")
        with self.assertRaises(UsageError) as cm:
            self.acknowledge(prompt_id="p-refused")
        self.assertIn("already used", str(cm.exception))
        self.acknowledge()
        (self.root / ".bdd/.integrity/acknowledgements.json").write_text("{broken", encoding="utf-8")
        tripwire.accept(self.root, self.plugin)                                   # sets the unreadable records aside
        with self.assertRaises(UsageError) as cm:
            self.acknowledge()
        self.assertIn("already used", str(cm.exception))

    def test_an_unchanged_transcript_is_not_read_again(self):
        self.violate()
        self.acknowledge()
        self.transcript({"type": "user", "promptId": "other"}, name="s-1.jsonl")
        integrityack.settle(self.root)
        from bddlib import approvals
        with mock.patch.object(approvals, "prompt_entries", side_effect=AssertionError("read again")):
            self.assertEqual(integrityack.settle(self.root), [])

    def test_locks_are_refused(self):
        with self.assertRaises(UsageError):
            self.acknowledge("tools reinstalled")
        lockfile.lock(self.root, self.feature_dir, "FEAT-007", "spec", [self.spec])
        self.spec.write_text(self.spec.read_text(encoding="utf-8").replace("succeeds", "fails"), encoding="utf-8", newline="\n")
        self.check()
        with self.assertRaises(UsageError) as cm:
            self.acknowledge("the lock is mine", prompt_id="p-2")
        self.assertIn("bdd unlock", str(cm.exception))

    def test_the_gates_refuse_until_the_acknowledgement_is_confirmed(self):
        self.walk_to("tasks")
        tripwire.accept(self.root, self.plugin)
        self.violate()
        self.acknowledge()
        with self.assertRaises(UsageError):
            self.gate("implement")
        self.transcript(self.typed(), name="s-1.jsonl")
        integrityack.settle(self.root)
        self.assertEqual(self.gate("implement")["phase"], "verify")


class UnreadableDataTest(TripwireCase):
    """Data that cannot be read is a finding, and the comparison still runs."""

    def test_unreadable_acknowledgements_are_a_violation_and_changes_are_still_found(self):
        (self.root / ".bdd/.integrity/acknowledgements.json").write_text('{"schema": 1, "items": [{}]}', encoding="utf-8")
        self.settings.write_text('{"disableAllHooks": true}\n', encoding="utf-8", newline="\n")
        code, message = self.fire()
        self.assertEqual(code, 2)
        found = {(v["what"], v["kind"]) for v in tripwire.open_violations(self.root)}
        self.assertEqual(found, {("integrity acknowledgements", "corrupt"), ("enforcement file", "changed")})

    def test_the_next_prompt_sets_unreadable_acknowledgements_aside(self):
        path = self.root / ".bdd/.integrity/acknowledgements.json"
        path.write_text("{broken", encoding="utf-8")
        self.check()
        self.assertEqual(tripwire.accept(self.root, self.plugin), [])
        self.assertFalse(path.exists())
        self.assertEqual(tripwire.open_violations(self.root), [])

    def test_an_unreadable_baseline_is_a_violation_and_the_backup_still_finds_changes(self):
        self.walk_to("tasks")
        tripwire.accept(self.root, self.plugin)
        self.baseline_file.write_text('{"schema": 1, "files": []}', encoding="utf-8")
        self.settings.write_text('{"disableAllHooks": true}\n', encoding="utf-8", newline="\n")
        found = {(v["what"], v["kind"]) for v in self.check()}
        self.assertEqual(found, {("integrity baseline", "corrupt"), ("enforcement file", "changed")})
        with self.assertRaises(UsageError):
            self.gate("implement")


class CodexTest(TripwireCase):
    def test_the_plugin_copy_codex_runs_is_not_watched_and_claude_codes_stays_recorded(self):
        self.write("plugin/tools/bdd/bddlib/guard.py", "x = 0  # changed\n")
        self.assertEqual(tripwire.check(self.root, None, "Bash"), [])                  # what Codex's hook calls
        self.assertEqual(tripwire.accept(self.root, None), [])
        self.assertIn("plugin:tools/bdd/bddlib/guard.py", tripwire.load_baseline(self.root))
        (found,) = self.check()                                                      # Claude Code's hook still sees it
        self.assertEqual(found["path"], "plugin:tools/bdd/bddlib/guard.py")

    def test_codex_is_not_offered_an_acknowledgement_it_cannot_type(self):
        self.settings.write_text("{}\n", encoding="utf-8", newline="\n")
        self.check()
        said = io.StringIO()
        with contextlib.redirect_stdout(said):
            tripwire.run_accept(self.root, None, offer_ack=False)
        self.assertIn("still open", said.getvalue())
        self.assertNotIn("/greenlight:approve", said.getvalue())


if __name__ == "__main__":
    unittest.main()
