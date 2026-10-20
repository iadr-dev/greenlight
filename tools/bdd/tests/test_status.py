import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

from bddlib import reportcmd, state, tripwire

from tests.helpers import ProjectCase


class StatusCase(ProjectCase):
    def run_status(self, *args: str, cwd: Path | None = None) -> tuple[int, str, str]:
        out, err, here = io.StringIO(), io.StringIO(), os.getcwd()
        os.chdir(cwd or self.root)
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = reportcmd.run_status(list(args))
        finally:
            os.chdir(here)
        return code, out.getvalue(), err.getvalue()


class TableTest(StatusCase):
    def test_every_feature_has_a_row_with_what_it_waits_for(self):
        state.create(self.root, "FEAT-008", "Refunds", "auto")
        code, out, _ = self.run_status()
        self.assertEqual(code, 0)
        header, first, second = out.splitlines()[:3]
        self.assertTrue(header.startswith("FEATURE"))
        self.assertIn("FEAT-007  Order discounts  discover", first)
        self.assertIn("the discover phase", first)
        self.assertIn("FEAT-008  Refunds", second)

    def test_a_phase_that_needs_the_person_says_which_command_to_type(self):
        self.gate("discover")
        _, out, _ = self.run_status()
        self.assertIn("the person: /greenlight:approve FEAT-007 rules", out)
        self.assertIn("rules: -, examples: -", out)

    def test_approvals_and_failed_gates_are_shown(self):
        self.gate("discover")
        self.approve("rules")
        self.gate("test-design", "fail")
        _, out, _ = self.run_status()
        self.assertIn("rules: approved, examples: -", out)
        self.assertIn("(test-design failed last time)", out)
        self.rules.write_text("# changed\n", encoding="utf-8", newline="\n")
        self.assertIn("rules: approved but not valid", self.run_status()[1])

    def test_json_and_empty_project(self):
        _, out, _ = self.run_status("--json")
        data = json.loads(out)
        self.assertEqual((data["features"][0]["feature"], data["open_violations"]), ("FEAT-007", 0))
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / ".bdd").mkdir()
            code, out, _ = self.run_status(cwd=Path(tmp))
        self.assertEqual((code, out.strip()), (0, "no features yet; start one with /greenlight:feature"))

    def test_open_integrity_violations_are_listed(self):
        plugin = self.root / "plugin"
        self.write("plugin/hooks/hooks.json", "{}\n")
        tripwire.accept(self.root, plugin)
        self.write("plugin/hooks/hooks.json", '{"changed": true}\n')
        tripwire.check(self.root, plugin)
        _, out, _ = self.run_status()
        self.assertIn("integrity: 1 violation(s) open", out)
        self.assertIn("hooks.json", out)

    def test_outside_a_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, _, err = self.run_status(cwd=Path(tmp))
        self.assertEqual(code, 2)
        self.assertIn("not inside a greenlight project", err)


class BriefTest(StatusCase):
    def test_one_line_for_the_feature_in_progress(self):
        state.create(self.root, "FEAT-008", "Refunds", "standard")
        code, out, _ = self.run_status("--brief")
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "greenlight: FEAT-007 Order discounts is at discover, waiting for the discover phase; "
                                      "1 other feature(s) in progress.")

    def test_silent_when_nothing_is_in_progress_or_outside_a_project(self):
        self.walk_to("verify")
        self.assertEqual(self.run_status("--brief"), (0, "", ""))
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(self.run_status("--brief", cwd=Path(tmp)), (0, "", ""))

    def test_never_fails_even_with_broken_data(self):
        (self.feature_dir / "state.json").write_text("{broken", encoding="utf-8")
        self.assertEqual(self.run_status("--brief"), (0, "", ""))

    def test_violations_are_mentioned(self):
        self.write(".bdd/.integrity/violations.json", "{broken")
        _, out, _ = self.run_status("--brief")
        self.assertIn("the integrity data cannot be read", out)


if __name__ == "__main__":
    unittest.main()
