import contextlib
import io
import json
import os
import unittest

from bddlib import config as cfg
from bddlib import reportcmd, scan

from tests.helpers import ProjectCase

SCAN_TABLE = r"""
[adapters.scan]
step_start = '^\s*@(?P<kind>given|when|then)\b'
assert_patterns = ['\bassert\b', 'pytest\.raises', 'expect_']
sleep_patterns = ['time\.sleep\(', 'asyncio\.sleep\(']
stub_patterns = ['mock\.patch\([^\w.]([\w.]+)']
"""

STEPS = '''import time
from unittest import mock

@given("an order of {amount}")
def an_order(amount):
    order.create(amount)

@when("it is submitted")
def submit():
    time.sleep(2)
    order.submit()

@then("the discount is applied")
def discount_applied():
    assert order.total == 900

@then("the request succeeds")
def succeeds():
    # assert order.ok  <- a comment is not an assertion
    print(order.status)

@then("the customer is told")
def told():
    driver.expect_message("10% off")
'''


class ScanCase(ProjectCase):
    def setUp(self):
        super().setUp()
        self.config(tail=SCAN_TABLE)
        self.write("steps/steps.py", STEPS)

    def findings(self) -> list[tuple[str, int]]:
        return [(i.code, i.line) for i in scan.scan(self.root, self.feature_dir)]


class FindingsTest(ScanCase):
    def test_assertion_free_then_steps_and_fixed_waits(self):
        self.assertEqual(self.findings(), [("E3", 10), ("S2", 17)])

    def test_the_message_names_the_file_and_line(self):
        messages = [str(i) for i in scan.scan(self.root, self.feature_dir)]
        self.assertEqual(messages[0], "steps/steps.py:10: error E3: fixed wait: wait for the condition instead of sleeping")
        self.assertIn("steps/steps.py:17: error S2: this then step never asserts anything", messages[1])

    def test_only_then_steps_need_assertions_and_the_last_step_runs_to_the_end_of_the_file(self):
        self.write("steps/more.py", '@given("x")\ndef g():\n    pass\n\n@then("y")\ndef t():\n    pass\n')
        self.assertIn(("S2", 5), [(i.code, i.line) for i in scan.scan(self.root, self.feature_dir)
                                  if i.path == "steps/more.py"])
        self.assertNotIn(("S2", 1), [(i.code, i.line) for i in scan.scan(self.root, self.feature_dir)
                                     if i.path == "steps/more.py"])

    def test_every_step_directory_of_the_adapter_is_scanned_and_binary_files_skipped(self):
        self.config(tail='drivers = "drivers"\n' + SCAN_TABLE)
        self.write("drivers/waits.py", "import time\ntime.sleep(1)\n")
        (self.root / "drivers" / "blob.bin").write_bytes(b"\xff\xfe\x00time.sleep(")
        paths = {i.path for i in scan.scan(self.root, self.feature_dir)}
        self.assertEqual(paths, {"steps/steps.py", "drivers/waits.py"})


class StubTest(ScanCase):
    def setUp(self):
        super().setUp()
        self.write("steps/stubs.py", 'from unittest import mock\n\nmock.patch("payments.gateway.charge")\nmock.patch("orders.repository.save")\n')

    def stub_findings(self):
        return [i for i in scan.scan(self.root, self.feature_dir) if i.code == "S4"]

    def test_stubs_need_a_dependencies_list_to_be_checked_against(self):
        (issue,) = [i for i in self.stub_findings() if i.line == 3]
        self.assertIn("system.md has no Dependencies list", issue.message)

    def test_only_declared_dependencies_may_be_stubbed(self):
        (self.feature_dir / "system.md").write_text(
            "# System\n\n## External dependencies\n\n- `payments` payment provider\n- email\n\n## Other\n\n- orders\n",
            encoding="utf-8", newline="\n")
        (issue,) = self.stub_findings()
        self.assertEqual(issue.line, 4)
        self.assertIn("orders.repository.save is stubbed but is not a declared dependency", issue.message)
        self.assertIn("declared: email, payments", issue.message)


class ConfigTest(ProjectCase):
    def test_no_scan_table_is_a_usage_problem(self):
        from bddlib.errors import UsageError
        with self.assertRaises(UsageError) as cm:
            scan.scan(self.root, self.feature_dir)
        self.assertIn("[adapters.scan]", str(cm.exception))

    def test_a_bad_table_is_reported(self):
        for table, message in (('[adapters.scan]\nassert_patterns = ["x"]\n', "needs step_start"),
                               ("[adapters.scan]\nstep_start = '^@then'\n", "named group (?P<kind>"),
                               ("[adapters.scan]\nstep_start = '(?P<kind>then'\n", "not a valid regular expression"),
                               ("[adapters.scan]\nstep_start = '(?P<kind>then)'\nsleep_patterns = 'x'\n", "must be a list")):
            with self.subTest(table=table):
                self.config(tail=table)
                with self.assertRaises(cfg.ConfigError) as cm:
                    cfg.load(self.root)
                self.assertIn(message, str(cm.exception))

    def test_the_table_is_read_per_adapter(self):
        self.config(tail=SCAN_TABLE)
        (rules,) = cfg.load(self.root).scans
        self.assertEqual(rules.step_dirs, (self.root / "steps",))
        self.assertEqual(len(rules.assert_patterns), 3)


class CommandTest(ScanCase):
    def run_scan(self, *args: str) -> tuple[int, str, str]:
        out, err, here = io.StringIO(), io.StringIO(), os.getcwd()
        os.chdir(self.root)
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = reportcmd.run_scan(list(args))
        finally:
            os.chdir(here)
        return code, out.getvalue(), err.getvalue()

    def test_findings_give_exit_1_and_clean_gives_0(self):
        code, out, _ = self.run_scan("FEAT-007")
        self.assertEqual(code, 1)
        self.assertIn("E3", out)
        self.write("steps/steps.py", '@then("ok")\ndef ok():\n    assert True\n')
        self.assertEqual(self.run_scan("FEAT-007"), (0, "FEAT-007: no findings\n", ""))

    def test_json(self):
        code, out, _ = self.run_scan("--json", "FEAT-007")
        self.assertEqual(code, 1)
        self.assertEqual([(f["code"], f["line"]) for f in json.loads(out)], [("E3", 10), ("S2", 17)])

    def test_problems_exit_2(self):
        self.config()
        code, _, err = self.run_scan("FEAT-007")
        self.assertEqual((code, "[adapters.scan]" in err), (2, True))
        self.config(tail="[adapters.scan]\nstep_start = '('\n")
        code, _, err = self.run_scan("FEAT-007")
        self.assertEqual((code, "bdd scan:" in err), (2, True))
        self.assertEqual(self.run_scan("FEAT-099")[0], 2)


if __name__ == "__main__":
    unittest.main()
