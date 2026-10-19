import unittest

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

    def test_exit_code_reflects_failures(self):
        ok = [doctor.Check("a", "ok", "")]
        bad = ok + [doctor.Check("b", "fail", "", "x")]
        self.assertNotIn("fail", {c.status for c in ok})
        self.assertIn("fix: x", doctor.render(bad))


if __name__ == "__main__":
    unittest.main()
