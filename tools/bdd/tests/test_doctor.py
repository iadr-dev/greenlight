import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from bddlib import doctor


class DoctorChecksTest(unittest.TestCase):
    def test_old_python_fails_with_fix(self):
        c = doctor.check_python((3, 10, 12), "/usr/bin/python3")
        self.assertEqual(c.status, "fail")
        self.assertIn("3.11", c.fix)

    def test_supported_python_ok(self):
        self.assertEqual(doctor.check_python((3, 11, 0), "/usr/bin/python3").status, "ok")

    def test_store_python_warns(self):
        c = doctor.check_python((3, 12, 1), r"C:\Users\x\AppData\Local\Microsoft\WindowsApps\python.exe")
        self.assertEqual(c.status, "warn")

    def test_missing_required_tool_fails_and_optional_warns(self):
        self.assertEqual(doctor.check_tool("sh", None, "install git", True).status, "fail")
        self.assertEqual(doctor.check_tool("x", None, "", False).status, "warn")
        self.assertEqual(doctor.check_tool("git", "/usr/bin/git", "", True).status, "ok")

    def test_latency_budget_differs_by_platform(self):
        self.assertEqual(doctor.check_latency([250, 260, 255], "linux").status, "warn")
        self.assertEqual(doctor.check_latency([250, 260, 255], "win32").status, "ok")
        self.assertEqual(doctor.check_latency([], "linux").status, "warn")
        c = doctor.check_latency([], "linux", "exit 2: can't open main.py")
        self.assertIn("can't open main.py", c.detail)

    def test_exit_code_reflects_failures(self):
        ok = [doctor.Check("a", "ok", "")]
        bad = ok + [doctor.Check("b", "fail", "", "x")]
        self.assertNotIn("fail", {c.status for c in ok})
        self.assertIn("fix: x", doctor.render(bad))


class DenyRulesTest(unittest.TestCase):
    def test_all_recommended_rules_present_is_ok(self):
        check = doctor.check_deny_rules(set(doctor.RECOMMENDED_DENY) | {"Bash(rm:*)"})
        self.assertEqual(check.status, "ok")

    def test_missing_rules_warn_with_the_line_the_person_types(self):
        check = doctor.check_deny_rules({"Bash(claude plugin disable:*)"})
        self.assertEqual(check.status, "warn")
        self.assertIn(f"{len(doctor.RECOMMENDED_DENY) - 1} of {len(doctor.RECOMMENDED_DENY)}", check.detail)
        rendered = doctor.render([check])
        self.assertIn("fix: Claude Code applies deny rules", rendered)
        line = rendered.splitlines()[-1].strip()
        self.assertTrue(line.startswith('! sh "') and line.endswith('/tools/bdd/bdd" doctor --add-deny-rules'), line)

    def test_the_settings_files_are_not_in_the_recommended_rules(self):
        """Claude may change the harmless parts of the settings; the guard judges each change by its effect."""
        self.assertFalse([rule for rule in doctor.RECOMMENDED_DENY if "settings" in rule])
        self.assertEqual(len(doctor.RECOMMENDED_DENY), 7)


class AddDenyRulesTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.settings = self.root / ".claude" / "settings.json"

    def test_the_missing_rules_are_added_and_every_other_key_is_kept(self):
        self.settings.parent.mkdir()
        self.settings.write_text(json.dumps({"env": {"A": "1"}, "permissions": {"deny": ["Bash(rm:*)"], "allow": ["Bash(ls)"]},
                                             "model": "sonnet"}), encoding="utf-8")
        code, said = doctor.add_deny_rules(self.root)
        self.assertEqual((code, said.split(":")[0]), (0, "added 7 deny rule(s) to .claude/settings.json"))
        data = json.loads(self.settings.read_text(encoding="utf-8"))
        self.assertEqual(data["permissions"]["deny"], ["Bash(rm:*)", *doctor.RECOMMENDED_DENY])
        self.assertEqual((data["env"], data["permissions"]["allow"], data["model"]), ({"A": "1"}, ["Bash(ls)"], "sonnet"))

    def test_it_creates_the_file_and_a_second_run_changes_nothing(self):
        self.assertEqual(doctor.add_deny_rules(self.root)[0], 0)
        written = self.settings.read_bytes()
        self.assertEqual(doctor.add_deny_rules(self.root), (0, "every recommended deny rule is already in .claude/settings.json"))
        self.assertEqual(self.settings.read_bytes(), written)

    def test_a_file_that_is_not_valid_settings_is_left_alone(self):
        self.settings.parent.mkdir()
        for text in ("{broken", '{"permissions": {"deny": "x"}}', '{"a": 1, "a": 2}', "[]"):
            with self.subTest(text=text):
                self.settings.write_text(text, encoding="utf-8")
                self.assertEqual(doctor.add_deny_rules(self.root)[0], 2)
                self.assertEqual(self.settings.read_text(encoding="utf-8"), text)

    def test_the_command_runs_only_inside_a_project(self):
        here = os.getcwd()
        os.chdir(self.root)
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(doctor.main(["--add-deny-rules"]), 2)
            (self.root / ".bdd").mkdir()
            with contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(doctor.main(["--add-deny-rules"]), 0)
        finally:
            os.chdir(here)
        self.assertIn("added 7 deny rule(s)", out.getvalue())

    def test_rules_are_read_from_every_existing_settings_file_and_bad_ones_are_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.json").write_text(json.dumps({"permissions": {"deny": ["Bash(x:*)", 5]}}), encoding="utf-8")
            (root / "b.json").write_text("{broken", encoding="utf-8")
            (root / "c.json").write_text(json.dumps({"permissions": {"deny": "not a list"}}), encoding="utf-8")
            (root / "d.json").write_text("[]", encoding="utf-8")
            paths = [root / name for name in ("a.json", "b.json", "c.json", "d.json", "missing.json")]
            self.assertEqual(doctor.read_denied(paths), {"Bash(x:*)"})

    def test_settings_files_cover_project_local_user_and_managed(self):
        with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": "/cfg"}):
            names = [p.as_posix() for p in doctor.settings_files(Path("/proj"))]
        self.assertEqual(names[:3], ["/proj/.claude/settings.json", "/proj/.claude/settings.local.json", "/cfg/settings.json"])
        self.assertIn("managed-settings.json", names[3])

    def test_the_check_only_runs_inside_a_project(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch("bddlib.doctor.measure_wrapper", return_value=([1.0], "")):
            here = os.getcwd()
            os.chdir(tmp)
            try:
                self.assertNotIn(doctor.DENY_RULES, [c.name for c in doctor.run_checks()])
                (Path(tmp) / ".bdd").mkdir()
                self.assertIn(doctor.DENY_RULES, [c.name for c in doctor.run_checks()])
            finally:
                os.chdir(here)


if __name__ == "__main__":
    unittest.main()
