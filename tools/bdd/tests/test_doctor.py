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

    def test_missing_rules_warn_with_a_snippet_to_paste(self):
        check = doctor.check_deny_rules({"Bash(claude plugin disable:*)"})
        self.assertEqual(check.status, "warn")
        self.assertIn(f"{len(doctor.RECOMMENDED_DENY) - 1} of {len(doctor.RECOMMENDED_DENY)}", check.detail)
        snippet = json.loads(check.fix[check.fix.index("{"):])
        self.assertEqual(snippet["permissions"]["deny"], [r for r in doctor.RECOMMENDED_DENY if "plugin disable" not in r])
        rendered = doctor.render([check])
        self.assertIn("fix: Claude Code applies deny rules", rendered)
        self.assertIn('"permissions"', rendered)

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
