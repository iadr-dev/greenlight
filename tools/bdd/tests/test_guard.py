import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from bddlib import guard, lockfile, state, store

WRAPPER = Path(__file__).resolve().parents[1] / "bdd"
SPEC = "@FEAT-001\nFeature: A\n  @R-1.1 @EX-1.1.1\n  Scenario: S\n    Then the request succeeds\n"


class GuardCase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name).resolve()
        self.write(".bdd/config.toml", '[[adapters]]\nname = "x"\nfeatures = "features"\nsteps = "steps"\n')
        self.spec = self.write("features/a.feature", SPEC)
        self.step = self.write("steps/s.py", "def then_ok():\n    assert True\n")
        self.write("src/app.py", "x = 1\n")
        self.feature_dir = state.create(self.root, "FEAT-001", "A", "standard")
        lockfile.lock(self.root, self.feature_dir, "FEAT-001", "spec", [self.spec])
        lockfile.lock(self.root, self.feature_dir, "FEAT-001", "bind", [self.step])

    def write(self, rel: str, text: str) -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        return path

    def call(self, tool: str, agent: str | None = None, cwd: Path | None = None, **tool_input) -> str | None:
        payload = {"tool_name": tool, "tool_input": tool_input, "cwd": str(cwd or self.root)}
        if agent:
            payload["agent_type"] = agent
        return guard.evaluate(payload)


class LockedFilesTest(GuardCase):
    def test_every_editing_tool_is_blocked_on_a_locked_file(self):
        for tool, key in guard.WRITE_TOOLS.items():
            for target in (self.spec, self.step):
                with self.subTest(tool=tool, target=target.name):
                    reason = self.call(tool, **{key: str(target)})
                    self.assertIn("is locked by FEAT-001", reason)
                    self.assertIn("bdd unlock FEAT-001", reason)

    def test_the_reason_names_the_scope_and_the_project_relative_path(self):
        self.assertIn("features/a.feature is locked by FEAT-001 (spec)", self.call("Edit", file_path=str(self.spec)))
        self.assertIn("steps/s.py is locked by FEAT-001 (bind)", self.call("Write", file_path=str(self.step)))

    def test_other_spellings_of_the_same_path_are_still_blocked(self):
        spellings = [
            self.root / "features" / ".." / "features" / "a.feature",
            self.root / "features" / "." / "a.feature",
            Path(str(self.spec).replace("/", os.sep)),
        ]
        for path in spellings:
            with self.subTest(path=str(path)):
                self.assertIsNotNone(self.call("Edit", file_path=str(path)))

    def test_relative_paths_resolve_against_the_hook_working_directory(self):
        self.assertIsNotNone(self.call("Edit", file_path="features/a.feature"))
        self.assertIsNotNone(self.call("Edit", file_path="a.feature", cwd=self.root / "features"))
        self.assertIsNotNone(self.call("Edit", file_path="../features/a.feature", cwd=self.root / "src"))

    @unittest.skipUnless(sys.platform in ("win32", "darwin"), "case-insensitive file systems only")
    def test_case_differences_do_not_bypass_the_lock_on_case_insensitive_systems(self):
        self.assertIsNotNone(self.call("Edit", file_path=str(self.root / "FEATURES" / "A.FEATURE")))

    def test_a_symlink_to_a_locked_file_is_blocked(self):
        link = self.root / "src" / "link.feature"
        try:
            link.symlink_to(self.spec)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks are not available here")
        self.assertIsNotNone(self.call("Edit", file_path=str(link)))

    def test_unlocked_files_may_be_edited(self):
        for rel in ("src/app.py", "src/new_module.py", "features/b.feature", "steps/extra.py", "README.md"):
            with self.subTest(rel=rel):
                self.assertIsNone(self.call("Write", file_path=str(self.root / rel)))

    def test_unlocking_releases_the_file(self):
        lockfile.unlock(self.feature_dir, "FEAT-001", "spec", "customer changed the rule")
        self.assertIsNone(self.call("Edit", file_path=str(self.spec)))
        self.assertIsNotNone(self.call("Edit", file_path=str(self.step)))      # the bind scope is still locked

    def test_calls_without_a_path_or_for_other_tools_are_allowed(self):
        self.assertIsNone(self.call("Edit"))
        self.assertIsNone(self.call("Read", file_path=str(self.spec)))
        self.assertIsNone(self.call("Grep", pattern="x"))


class ManagedDataTest(GuardCase):
    def test_state_lock_and_marker_files_are_not_editable(self):
        for rel in (".bdd/features/FEAT-001-a/state.json", ".bdd/features/FEAT-001-a/lock.json",
                    ".bdd/features/FEAT-001-a/state.json.lock", ".bdd/features/FEAT-001-a/state.json.x1.tmp",
                    ".bdd/.enforcement/session-1"):
            with self.subTest(rel=rel):
                self.assertIn("managed by the bdd command line", self.call("Write", file_path=str(self.root / rel)))

    def test_human_edited_files_inside_bdd_stay_editable(self):
        for rel in (".bdd/features/FEAT-001-a/rules.md", ".bdd/features/FEAT-001-a/brief.md", ".bdd/glossary.md",
                    ".bdd/vocabulary.toml"):
            with self.subTest(rel=rel):
                self.assertIsNone(self.call("Write", file_path=str(self.root / rel)))


class AgentLimitsTest(GuardCase):
    TARGETS = {"data": ".bdd/features/FEAT-001-a/rules.md", "features": "features/new.feature",
               "steps": "steps/new_steps.py", "production": "src/new.py"}
    ALLOWED = {"product-analyst": {"data"}, "qa-designer": {"data", "features"}, "system-analyst": {"data"},
               "step-engineer": {"data", "steps"}, "implementer": {"data", "production"}, "spec-auditor": set()}

    def test_the_whole_matrix(self):
        for agent, allowed in self.ALLOWED.items():
            for category, rel in self.TARGETS.items():
                with self.subTest(agent=agent, category=category):
                    reason = self.call("Write", agent=f"greenlight:{agent}", file_path=str(self.root / rel))
                    if category in allowed:
                        self.assertIsNone(reason)
                    else:
                        self.assertIn(f"the {agent} agent may not write {category} files", reason)

    def test_the_implementer_cannot_touch_tests(self):
        reason = self.call("Edit", agent="greenlight:implementer", file_path=str(self.root / "steps" / "new.py"))
        self.assertIn("it may write: data, production", reason)

    def test_the_auditor_is_read_only(self):
        reason = self.call("Write", agent="greenlight:spec-auditor", file_path=str(self.root / ".bdd" / "x" / "report.md"))
        self.assertIn("nothing (it is read-only)", reason)

    def test_the_orchestrator_and_other_plugins_agents_are_unrestricted(self):
        for agent in (None, "other-plugin:coder", "Explore"):
            with self.subTest(agent=agent):
                for rel in self.TARGETS.values():
                    self.assertIsNone(self.call("Write", agent=agent, file_path=str(self.root / rel)))

    def test_locks_apply_to_every_agent_even_ones_allowed_to_write_that_category(self):
        self.assertIn("is locked", self.call("Edit", agent="greenlight:qa-designer", file_path=str(self.spec)))
        self.assertIn("is locked", self.call("Edit", agent="greenlight:step-engineer", file_path=str(self.step)))


class OutsideAProjectTest(unittest.TestCase):
    def test_everything_is_allowed_without_a_bdd_directory(self):
        with tempfile.TemporaryDirectory() as d:
            for tool, inp in [("Write", {"file_path": str(Path(d) / "x.py")}), ("Bash", {"command": "rm -rf x"}),
                              ("CronCreate", {"prompt": "/greenlight:approve FEAT-1 rules"})]:
                with self.subTest(tool=tool):
                    self.assertIsNone(guard.evaluate({"tool_name": tool, "tool_input": inp, "cwd": d}))


class FailClosedTest(GuardCase):
    def test_a_corrupt_lock_file_blocks_edits_instead_of_silently_allowing_them(self):
        (self.feature_dir / "lock.json").write_text("{corrupt", encoding="utf-8")
        reason = self.call("Write", file_path=str(self.root / "src" / "app.py"))
        self.assertIn("cannot enforce the locks", reason)
        self.assertIn("cannot read lock file", reason)

    def test_a_lock_file_from_a_newer_greenlight_blocks_too(self):
        (self.feature_dir / "lock.json").write_text(json.dumps({"schema": 99}), encoding="utf-8")
        self.assertIn("upgrade greenlight", self.call("Write", file_path=str(self.root / "src" / "app.py")))


class BashTest(GuardCase):
    def blocked(self, command: str, cwd: Path | None = None) -> bool:
        return self.call("Bash", command=command, cwd=cwd) is not None

    def test_commands_that_write_to_a_locked_file_are_blocked(self):
        for command in [
            "sed -i 's/succeeds/fails/' features/a.feature",
            "sed -i.bak s/x/y/ steps/s.py",
            "echo 'Feature: hacked' > features/a.feature",
            "echo more >> features/a.feature",
            "printf x | tee features/a.feature",
            "cp /tmp/evil.feature features/a.feature",
            "mv features/a.feature /tmp/",
            "rm features/a.feature",
            "truncate -s 0 steps/s.py",
            "git checkout -- features/a.feature",
            "git restore steps/s.py",
            "perl -pi -e 's/a/b/' features/a.feature",
            "python -c \"open('steps/s.py','w').write('pass')\"",
            "python - <<'EOF'\nfrom pathlib import Path\nPath('steps/s.py').write_text('x')\nEOF",
            'Set-Content -Path features/a.feature -Value x',
            f"sed -i s/a/b/ {self.spec}",
            f"echo x>{self.spec}",
        ]:
            with self.subTest(command=command):
                self.assertTrue(self.blocked(command), command)

    def test_a_command_that_changes_directory_first_is_still_caught_by_file_name(self):
        self.assertTrue(self.blocked("cd features && sed -i s/a/b/ a.feature"))
        self.assertTrue(self.blocked("sed -i s/a/b/ a.feature", cwd=self.root / "features"))

    def test_managed_data_files_are_protected_from_the_shell_too(self):
        data = ".bdd/features/FEAT-001-a/state.json"
        for command in (f"echo '{{}}' > {data}", f"sed -i s/standard/auto/ {data}", f"rm {data}",
                        "python -c \"open('state.json','w').write('{}')\""):
            with self.subTest(command=command):
                self.assertTrue(self.blocked(command))

    def test_reading_is_always_fine(self):
        for command in ["cat features/a.feature", "cat features/a.feature | wc -l", "grep -n Scenario features/a.feature",
                        "head -5 steps/s.py", "diff features/a.feature /tmp/x", "git diff features/a.feature",
                        "git log -- features/a.feature", "ls features", "cat .bdd/features/FEAT-001-a/state.json",
                        "cat features/a.feature > /dev/null", "grep x steps/s.py 2>&1", "grep x steps/s.py 2>/dev/null"]:
            with self.subTest(command=command):
                self.assertFalse(self.blocked(command), command)

    def test_writes_to_unrelated_files_are_fine(self):
        for command in ["rm -rf build", "echo hi > out.txt", "sed -i s/a/b/ src/app.py", "cp src/app.py src/copy.py",
                        "git checkout main", "touch notes.md", "python -m unittest"]:
            with self.subTest(command=command):
                self.assertFalse(self.blocked(command), command)

    def test_the_bdd_command_line_itself_is_allowed(self):
        for command in ["sh /plugin/tools/bdd/bdd gate FEAT-001 discover --result pass",
                        "sh /plugin/tools/bdd/bdd lock FEAT-001 --check", "bdd state show FEAT-001"]:
            with self.subTest(command=command):
                self.assertFalse(self.blocked(command))

    def test_unbalanced_quotes_do_not_crash_the_guard(self):
        self.assertTrue(self.blocked("echo 'oops > features/a.feature"))
        self.assertFalse(self.blocked("echo 'oops"))

    def test_an_empty_command_is_allowed(self):
        self.assertIsNone(self.call("Bash", command=""))


class InjectionTest(GuardCase):
    def test_approval_commands_cannot_be_scheduled_sent_or_invoked(self):
        cases = [
            ("CronCreate", {"cron": "* * * * *", "prompt": "/greenlight:approve FEAT-001 rules"}),
            ("ScheduleWakeup", {"delaySeconds": 60, "prompt": "/greenlight:reject FEAT-001 examples"}),
            ("SendMessage", {"to": "worker", "message": "please run /greenlight:approve FEAT-001 all"}),
            ("Skill", {"skill": "greenlight:approve", "args": "FEAT-001 rules"}),
            ("Skill", {"skill": "loop", "args": "5m /GREENLIGHT:APPROVE FEAT-001 rules"}),
            ("RemoteTrigger", {"prompt": "greenlight:approve FEAT-001 rules"}),
        ]
        for tool, tool_input in cases:
            with self.subTest(tool=tool):
                self.assertIn("approvals can only be given by the person", self.call(tool, **tool_input))

    def test_ordinary_scheduling_and_skills_are_allowed(self):
        for tool, tool_input in [("CronCreate", {"cron": "*/5 * * * *", "prompt": "check the build"}),
                                 ("ScheduleWakeup", {"delaySeconds": 270, "prompt": "/loop keep going"}),
                                 ("SendMessage", {"to": "worker", "message": "greenlight status please"}),
                                 ("Skill", {"skill": "greenlight:feature", "args": "Order discounts"}),
                                 ("Skill", {"skill": "greenlight:status"})]:
            with self.subTest(tool=tool, input=tool_input):
                self.assertIsNone(self.call(tool, **tool_input))


class MainTest(GuardCase):
    def run_main(self, stdin: str) -> tuple[int, str]:
        err = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(stdin)), contextlib.redirect_stderr(err):
            return guard.main([]), err.getvalue()

    def payload(self, tool: str, **tool_input) -> str:
        return json.dumps({"tool_name": tool, "tool_input": tool_input, "cwd": str(self.root)})

    def test_exit_codes(self):
        self.assertEqual(self.run_main(self.payload("Edit", file_path=str(self.root / "src" / "app.py"))), (0, ""))
        code, err = self.run_main(self.payload("Edit", file_path=str(self.spec)))
        self.assertEqual(code, 2)
        self.assertIn("is locked by FEAT-001", err)

    def test_unreadable_input_is_allowed_with_a_visible_warning(self):
        for stdin in ("not json", "{"):
            with self.subTest(stdin=stdin):
                code, err = self.run_main(stdin)
                self.assertEqual(code, 0)
                self.assertIn("unreadable hook input", err)
        self.assertEqual(self.run_main(""), (0, ""))
        self.assertEqual(self.run_main("{}"), (0, ""))

    @unittest.skipUnless(shutil.which("sh"), "needs sh")
    def test_through_the_real_wrapper(self):
        def run(payload: str):
            env = dict(os.environ, GREENLIGHT_CACHE_DIR=str(self.root / ".cache"))
            return subprocess.run([shutil.which("sh"), str(WRAPPER), "guard"], input=payload, capture_output=True,
                                  text=True, encoding="utf-8", env=env, timeout=60)
        blocked = run(self.payload("Edit", file_path=str(self.spec)))
        self.assertEqual(blocked.returncode, 2)
        self.assertIn("locked by FEAT-001", blocked.stderr)
        allowed = run(self.payload("Edit", file_path=str(self.root / "src" / "app.py")))
        self.assertEqual((allowed.returncode, allowed.stdout, allowed.stderr), (0, "", ""))


class FailClosedInsideAProjectTest(GuardCase):
    """A guard that can be switched off by corrupting a file is not a guard."""

    def write_target(self) -> str | None:
        return self.call("Write", file_path=str(self.root / "src" / "app.py"))

    def test_a_broken_config_blocks_instead_of_disabling_enforcement(self):
        for broken in ("profiles = [", 'profiles = ["web"]\n', "not = valid = toml"):
            with self.subTest(config=broken):
                self.write(".bdd/config.toml", broken)
                reason = self.write_target()
                self.assertIn("cannot enforce the locks", reason)

    def test_an_unexpected_internal_error_blocks_too(self):
        with mock.patch.object(guard, "evaluate_in_project", side_effect=RuntimeError("boom")):
            reason = self.write_target()
        self.assertIn("internal error (RuntimeError: boom)", reason)
        with mock.patch.object(guard, "evaluate_in_project", side_effect=AttributeError("bug")):
            self.assertIn("blocks this call", self.write_target())

    def test_main_exits_2_for_an_internal_error_inside_a_project(self):
        payload = json.dumps({"tool_name": "Write", "tool_input": {"file_path": str(self.root / "src" / "app.py")},
                              "cwd": str(self.root)})
        with mock.patch.object(guard, "evaluate_in_project", side_effect=RuntimeError("boom")), \
                mock.patch("sys.stdin", io.StringIO(payload)), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(guard.main([]), 2)

    def test_outside_a_project_nothing_is_ever_blocked_not_even_by_a_bug(self):
        with tempfile.TemporaryDirectory() as elsewhere:
            with mock.patch.object(guard, "evaluate_in_project", side_effect=RuntimeError("boom")):
                self.assertIsNone(guard.evaluate({"tool_name": "Write", "cwd": elsewhere,
                                                  "tool_input": {"file_path": "x.py"}}))

    def test_input_that_is_not_an_object_is_ignored(self):
        with mock.patch("sys.stdin", io.StringIO("[1, 2]")):
            self.assertEqual(guard.main([]), 0)


class ApprovalViaShellTest(GuardCase):
    def test_a_shell_command_cannot_run_an_approval(self):
        for command in ['claude -p "/greenlight:approve FEAT-001 rules"',
                        "echo '/greenlight:approve FEAT-001 all' | claude",
                        "claude -p '/GREENLIGHT:REJECT FEAT-001 examples'",
                        "python -c \"import subprocess; subprocess.run(['claude','-p','/greenlight:approve FEAT-001 rules'])\""]:
            with self.subTest(command=command):
                self.assertIn("approvals can only be given by the person", self.call("Bash", command=command))

    def test_ordinary_commands_that_mention_greenlight_are_fine(self):
        for command in ["bdd lint features", "ls .claude-plugin", "git log --oneline -- skills/approve", "echo greenlight"]:
            with self.subTest(command=command):
                self.assertIsNone(self.call("Bash", command=command))


class EnforcementFilesTest(GuardCase):
    def test_bdd_config_is_managed_by_the_cli(self):
        self.assertIn("managed by the bdd command line", self.call("Write", file_path=str(self.root / ".bdd" / "config.toml")))
        self.assertIn("managed by the bdd command line",
                      self.call("Bash", command="echo 'profiles = []' > .bdd/config.toml"))
        self.assertIsNone(self.call("Bash", command="cat .bdd/config.toml"))

    def test_other_config_toml_files_are_not_affected(self):
        for rel in (".cargo/config.toml", "config.toml", "tools/config.toml"):
            with self.subTest(rel=rel):
                self.assertIsNone(self.call("Write", file_path=str(self.root / rel)))
        self.assertIsNone(self.call("Bash", command="echo x > .cargo/config.toml"))

    def test_claude_code_settings_cannot_be_edited_whatever_the_change_says(self):
        settings = str(self.root / ".claude" / "settings.json")
        local = str(self.root / ".claude" / "settings.local.json")
        home_settings = str(self.root / "home" / ".claude" / "settings.json")
        contents = [
            json.dumps({"disableAllHooks": True}),
            json.dumps({"enabledPlugins": {"greenlight@greenlight": False}}),
            json.dumps({"permissions": {"allow": ["Bash(ls)"]}}),            # no hook words at all
            '{"hoo\\u006bs": {}, "disableAllHoo\\u006bs": true}',          # JSON escapes: the same keys, spelled differently
            "",
        ]
        for path in (settings, local, home_settings):
            for content in contents:
                with self.subTest(path=Path(path).name, content=content[:30]):
                    self.assertIn("is a Claude Code settings file", self.call("Write", file_path=path, content=content))
        edit = self.call("Edit", file_path=settings, old_string="a", new_string="b")
        self.assertIn("is a Claude Code settings file", edit)
        multi = self.call("MultiEdit", file_path=local, edits=[{"old_string": "a", "new_string": "b"}])
        self.assertIn("is a Claude Code settings file", multi)

    def test_a_symlinked_directory_does_not_hide_the_settings_folder(self):
        (self.root / ".claude").mkdir()
        link = self.root / "innocent"
        try:
            link.symlink_to(self.root / ".claude", target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks are not available here")
        self.assertIn("is a Claude Code settings file", self.call("Write", file_path=str(link / "settings.json"), content="{}"))

    def test_a_claude_folder_that_is_a_symlink_to_somewhere_else_is_still_recognised(self):
        elsewhere = self.root / "elsewhere"
        elsewhere.mkdir()
        try:
            (self.root / ".claude").symlink_to(elsewhere, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks are not available here")
        # The resolved path no longer contains ".claude", but the path as written does.
        reason = self.call("Write", file_path=str(self.root / ".claude" / "settings.json"), content="{}")
        self.assertIn("is a Claude Code settings file", reason)

    def test_settings_json_files_elsewhere_are_ordinary_files(self):
        for rel in ("settings.json", "src/settings.json", ".vscode/settings.json"):
            with self.subTest(rel=rel):
                self.assertIsNone(self.call("Write", file_path=str(self.root / rel), content='{"hooks": 1}'))

    def test_hook_scripts_directory_is_protected(self):
        self.assertIn("is a Claude Code hook", self.call("Write", file_path=str(self.root / ".claude" / "hooks" / "x.sh")))

    def test_the_plugins_own_files_are_protected(self):
        plugin = self.root / "installed-plugin"
        (plugin / "tools" / "bdd" / "bddlib").mkdir(parents=True)
        target = plugin / "tools" / "bdd" / "bddlib" / "guard.py"
        target.write_text("# guard\n", encoding="utf-8")
        with mock.patch.dict(os.environ, {guard.PLUGIN_ROOT_ENV: str(plugin)}):
            self.assertIn("is part of the greenlight plugin", self.call("Edit", file_path=str(target)))
            self.assertIn("is part of the greenlight plugin", self.call("Write", file_path=str(plugin / "hooks" / "hooks.json")))
            self.assertIsNotNone(self.call("Bash", command=f"sed -i 's/^/#/' {target}"))
            self.assertIsNone(self.call("Bash", command=f"cat {target}"))
            self.assertIsNone(self.call("Write", file_path=str(self.root / "src" / "ok.py")))

    def test_shell_commands_cannot_write_claude_code_settings_whatever_they_contain(self):
        for command in ["echo '{\"disableAllHooks\": true}' > .claude/settings.json",
                        "echo '{\"permissions\": {}}' > .claude/settings.json",
                        "sed -i 's/a/b/' .claude/settings.local.json",
                        "cp /tmp/x.json ~/.claude/settings.json",
                        "rm -r .claude/hooks/",
                        "echo '{}' > .claude/set\"tings\".json",             # quotes splitting the name
                        "sed -i s/a/b/ \".cla\"\"ude/settings.json\"",
                        "rm -rf .claude", "rm -rf .claude/", "mv .claude .claude-old", "ln -sfn /tmp/x .claude",
                        "rm -r ~/.claude", "cp -r /tmp/evil .claude", "Remove-Item -Recurse .claude"]:
            with self.subTest(command=command):
                self.assertIn("what enforces greenlight", self.call("Bash", command=command))
        for command in ["cat .claude/settings.json", "jq .permissions .claude/settings.json",
                        "grep hooks .claude/settings.json", "ls .claude", "ls -la .claude/", "cat .claude/agents/x.md",
                        "cat .claude/settings.json > /dev/null", "echo done > notes.txt"]:
            with self.subTest(command=command):
                self.assertIsNone(self.call("Bash", command=command))


class TranscriptProtectionTest(GuardCase):
    """Approvals are verified against the session transcript, so the agent must not be able to edit it."""

    def setUp(self):
        super().setUp()
        self.config_dir = self.root / "claude-home"
        patch = mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": str(self.config_dir)})
        patch.start()
        self.addCleanup(patch.stop)
        self.transcript = self.config_dir / "projects" / "some-project" / "session-1.jsonl"

    def test_the_file_tools_cannot_write_a_transcript(self):
        for tool in ("Write", "Edit", "MultiEdit"):
            with self.subTest(tool=tool):
                self.assertIn("session transcript", self.call(tool, file_path=str(self.transcript)))

    def test_the_shell_cannot_write_to_the_transcript_folder(self):
        for command in [f"echo '{{}}' >> {self.transcript}", "echo x >> ~/.claude/projects/p/s.jsonl",
                        "sed -i s/a/b/ .claude/projects/p/s.jsonl", "cp forged.jsonl ~/.claude/projects/p/s.jsonl"]:
            with self.subTest(command=command):
                self.assertIn("what enforces greenlight", self.call("Bash", command=command))

    def test_reading_transcripts_is_allowed(self):
        self.assertIsNone(self.call("Read", file_path=str(self.transcript)))
        self.assertIsNone(self.call("Bash", command=f"grep promptId {self.transcript}"))
        self.assertIsNone(self.call("Bash", command="ls ~/.claude/projects"))


class ShellSpellingTest(GuardCase):
    """Ways of writing the same path in a shell: escapes, quotes and globs."""

    def blocked(self, command: str) -> bool:
        return guard.command_touches_enforcement(command) and self.call("Bash", command=command) is not None

    def test_backslash_escapes_and_quotes_that_still_spell_the_path(self):
        for command in [r"echo x > .cla\ude/settings.json", r"rm -rf .cl\aude", 'echo x > .claude/set"ti"ngs.json',
                        r"cp evil ~/.cla\u\de/settings.local.json", "sed -i 's/a/b/' '.claude/settings.json'"]:
            with self.subTest(command=command):
                self.assertTrue(self.blocked(command), command)

    def test_a_glob_that_can_expand_to_the_claude_folder_or_its_settings(self):
        for command in ["rm -rf .cl*", "rm -rf .*", "mv .c?aude /tmp/x", "rm .claude/*", "echo x > .claude/sett*.json",
                        "cp evil ~/.c*/settings.json", "rm -rf .claud[e]", "rm -r .claude/h*", "cp -r /tmp/x ./.cl[a-z]ude"]:
            with self.subTest(command=command):
                self.assertTrue(self.blocked(command), command)

    def test_globs_that_cannot_reach_it_are_fine(self):
        for command in ["rm -rf build/*", "rm *.pyc", "touch .gitignore*", "rm -rf .cache/*", "rm -f .coverage*",
                        "rm -rf node_modules/.cache/*", "echo x > .claude/agents/x.md", "cp a.txt b.txt", "ls .cl*"]:
            with self.subTest(command=command):
                self.assertFalse(self.blocked(command), command)

    def test_reading_with_a_glob_is_not_a_write(self):
        self.assertIsNone(self.call("Bash", command="cat .claude/sett*.json"))
        self.assertIsNone(self.call("Bash", command="ls -d .cl*"))


class NestedSessionTest(GuardCase):
    """The approval text can be assembled from pieces, so the nested session itself is refused."""

    def test_commands_that_start_a_claude_session_are_blocked(self):
        for command in ['claude -p "build it"', "claude", "/usr/local/bin/claude --print x",
                        "C:/Users/x/.local/bin/claude.exe -p x", "env FOO=1 claude -p x", "FOO=1 claude -p x",
                        "sudo claude -p x", "cd src && claude -p y", "echo hi | claude -p", "(claude -p x)",
                        "result=$(claude -p x)", "npx @anthropic-ai/claude-code -p x", "npx claude -p x",
                        "python -c \"import subprocess; subprocess.run(['claude','-p','x'])\"",
                        "node -e \"require('child_process').spawn('claude',['-p'])\"",
                        "nohup claude --resume abc &", "x='green'; y='light:approve'; claude -p \"/$x$y FEAT-001 rules\""]:
            with self.subTest(command=command):
                self.assertTrue(guard.starts_claude_session(command), command)
                self.assertIsNotNone(self.call("Bash", command=command))

    def test_read_only_claude_commands_and_the_bare_word_are_fine(self):
        for command in ["claude plugin list", "claude plugin list --json", "claude plugins list",
                        "claude plugin details greenlight", "claude plugin validate .", "claude mcp list",
                        "claude mcp get server", "claude config get theme", "claude config list", "claude --version",
                        "claude -v", "claude --help", "claude doctor",
                        "git commit -m 'ask claude later'", "ls claude-notes", "cat claude.md", "echo claude",
                        "cat .claude/settings.json", "ls ~/.claude/projects", "./.claude/hooks/run.sh",
                        "grep -r claude src", "python -m unittest"]:
            with self.subTest(command=command):
                self.assertFalse(guard.starts_claude_session(command), command)
                self.assertIsNone(self.call("Bash", command=command))

    def test_management_commands_that_change_something_are_blocked_because_they_can_switch_greenlight_off(self):
        for command in ["claude plugin disable greenlight@greenlight", "claude plugin uninstall greenlight@greenlight",
                        "claude plugin install other@market", "claude plugin enable x", "claude plugin marketplace remove greenlight",
                        "claude plugin update greenlight", "claude mcp add evil -- node x.js", "claude mcp remove x",
                        "claude config set theme dark", "claude config add a b", "claude update", "claude install",
                        "claude plugin", "claude mcp"]:
            with self.subTest(command=command):
                self.assertTrue(guard.starts_claude_session(command), command)
                self.assertIn("nested session", self.call("Bash", command=command))

    def test_a_second_claude_call_hidden_behind_a_read_only_one_is_still_found(self):
        # The first call is read-only; a match that swallowed the words after it would never see the second.
        for command in ["claude --help $(claude plugin disable greenlight)", "claude -v;claude plugin disable x",
                        "claude plugin list;claude plugin disable x", "claude --help `claude mcp add x`",
                        "claude --version && claude -p hi", "claude plugin list | claude -p x",
                        "claude doctor\nclaude plugin disable x"]:
            with self.subTest(command=command):
                self.assertTrue(guard.starts_claude_session(command), command)

    def test_read_only_calls_joined_by_separators_stay_allowed(self):
        for command in ["claude doctor; ls", "claude mcp get a | cat", "claude plugin list && claude --version",
                        "claude plugin list > plugins.txt"]:
            with self.subTest(command=command):
                self.assertFalse(guard.starts_claude_session(command), command)

    def test_the_reason_explains_what_is_allowed(self):
        reason = self.call("Bash", command="claude -p hi")
        self.assertIn("nested session", reason)
        self.assertIn("`claude plugin disable`", reason)
        self.assertIn("`claude plugin list`", reason)


class PerformanceTest(unittest.TestCase):
    def test_fifty_locked_features_are_evaluated_quickly(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d).resolve()
            (root / ".bdd").mkdir()
            (root / ".bdd" / "config.toml").write_text('[[adapters]]\nname = "x"\nfeatures = "features"\n')
            for n in range(1, 51):
                files = []
                for i in range(5):
                    f = root / "features" / f"f{n}_{i}.feature"
                    f.parent.mkdir(exist_ok=True)
                    f.write_text(f"@FEAT-{n:03d}\nFeature: F{n}\n", encoding="utf-8")
                    files.append(f)
                feature_dir = state.create(root, f"FEAT-{n:03d}", f"Feature {n}", "standard")
                lockfile.lock(root, feature_dir, f"FEAT-{n:03d}", "spec", files)
            payload = {"tool_name": "Edit", "tool_input": {"file_path": str(root / "features" / "f50_4.feature")},
                       "cwd": str(root)}
            start = time.perf_counter()
            for _ in range(5):
                reason = guard.evaluate(payload)
            per_call = (time.perf_counter() - start) / 5
            self.assertIn("locked by FEAT-050", reason)
            self.assertLess(per_call, 0.25, f"{per_call * 1000:.0f} ms per call with 50 locked features")


if __name__ == "__main__":
    unittest.main()
