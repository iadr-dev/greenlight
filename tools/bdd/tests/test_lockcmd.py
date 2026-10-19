import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

from bddlib import lockcmd, store

FEATURE = "@FEAT-007\nFeature: Discounts\n  @R-7.1 @EX-7.1.1\n  Scenario: S\n    Then the request succeeds\n"
OTHER = "@FEAT-008\nFeature: Other\n  Scenario: S\n    Then the request succeeds\n"


class LockCommandTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name).resolve()
        self.write(".bdd/config.toml", '[[adapters]]\nname = "x"\nfeatures = "features"\n')
        (store.features_dir(self.root) / "FEAT-007-discounts").mkdir(parents=True)
        self.spec = self.write("features/discounts.feature", FEATURE)
        self.write("features/other.feature", OTHER)
        self.step = self.write("steps/steps.py", "def then_ok():\n    assert True\n")

    def write(self, rel: str, text: str) -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        return path

    def run_cmd(self, runner, *args: str, cwd: Path | None = None) -> tuple[int, str, str]:
        out, err, here = io.StringIO(), io.StringIO(), os.getcwd()
        os.chdir(cwd or self.root)
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = runner(list(args))
        finally:
            os.chdir(here)
        return code, out.getvalue(), err.getvalue()

    def lock(self, *args):
        return self.run_cmd(lockcmd.run_lock, "FEAT-007", *args)

    def unlock(self, *args):
        return self.run_cmd(lockcmd.run_unlock, "FEAT-007", *args)

    # -- the whole story ---------------------------------------------------------------
    def test_lock_edit_detect_unlock_relock(self):
        code, out, _ = self.lock("--scope", "spec")
        self.assertEqual(code, 0)
        self.assertIn("locked FEAT-007 spec: 1 file(s)", out)
        self.assertIn("features/discounts.feature", out)          # found by its @FEAT-007 tag; other.feature is not

        code, out, _ = self.lock("--check")
        self.assertEqual((code, out.strip()), (0, "FEAT-007: locks intact (spec: 1 file(s))"))

        self.spec.write_text(FEATURE.replace("succeeds", "is rejected"), encoding="utf-8", newline="\n")
        code, out, _ = self.lock("--check")
        self.assertEqual(code, 1)
        self.assertIn("FEAT-007: [spec] features/discounts.feature changed since it was locked", out)

        with self.assertRaises(SystemExit) as refused:             # --reason is mandatory: argparse exits 2
            self.unlock("--scope", "spec")
        self.assertEqual(refused.exception.code, 2)
        code, out, _ = self.unlock("--scope", "spec", "--reason", "rule R-7.1 changed")
        self.assertEqual((code, out.strip()), (0, "unlocked FEAT-007 spec"))
        self.assertEqual(self.lock("--scope", "spec")[0], 0)
        self.assertEqual(self.lock("--check")[0], 0)

    def test_spec_files_added_after_locking_are_caught(self):
        self.lock("--scope", "spec")
        self.write("features/more.feature", FEATURE.replace("Discounts", "More"))
        code, out, _ = self.lock("--check")
        self.assertEqual(code, 1)
        self.assertIn("[spec] features/more.feature is tagged for this feature but was never locked", out)

    def test_untagged_or_other_features_never_count_as_added(self):
        self.lock("--scope", "spec")
        self.write("features/third.feature", OTHER.replace("FEAT-008", "FEAT-009"))
        self.assertEqual(self.lock("--check")[0], 0)

    def test_bind_scope_needs_explicit_files_and_detects_weakened_steps(self):
        code, _, err = self.lock("--scope", "bind")
        self.assertEqual(code, 2)
        self.assertIn("name the files to lock", err)
        self.assertEqual(self.lock("--scope", "bind", "steps")[0], 0)
        self.step.write_text("def then_ok():\n    pass\n", encoding="utf-8", newline="\n")
        code, out, _ = self.lock("--check", "--scope", "bind")
        self.assertEqual(code, 1)
        self.assertIn("[bind] steps/steps.py changed", out)

    def test_require_fails_when_a_scope_was_never_locked(self):
        self.lock("--scope", "spec")
        self.assertEqual(self.lock("--check")[0], 0)                       # nothing demanded
        code, out, _ = self.lock("--check", "--require")
        self.assertEqual(code, 1)
        self.assertIn("[bind] is not locked", out)
        self.assertEqual(self.lock("--check", "--require", "--scope", "spec")[0], 0)

    def test_json_report(self):
        self.lock("--scope", "spec")
        self.spec.write_text("@FEAT-007\nFeature: edited\n", encoding="utf-8", newline="\n")
        code, out, _ = self.lock("--check", "--json")
        data = json.loads(out)
        self.assertEqual(code, 1)
        self.assertEqual((data["feature"], data["ok"], data["locked"]), ("FEAT-007", False, {"spec": 1}))
        self.assertEqual(data["violations"], [{"scope": "spec", "path": "features/discounts.feature", "kind": "changed"}])

    def test_nothing_locked_yet_is_not_an_error_unless_required(self):
        code, out, _ = self.lock("--check")
        self.assertEqual((code, out.strip()), (0, "FEAT-007: locks intact (nothing locked)"))

    # -- usage problems ----------------------------------------------------------------
    def test_usage_errors_exit_2_with_a_message(self):
        cases = [
            (("FEAT-999", "--scope", "spec"), "no feature directory for FEAT-999"),
            (("feat-7", "--scope", "spec"), "is not a feature id"),
            (("FEAT-007",), "--scope spec|bind is required"),
            (("FEAT-007", "--scope", "bind", "../escape.py"), "does not exist"),
        ]
        for args, message in cases:
            with self.subTest(args=args):
                code, _, err = self.run_cmd(lockcmd.run_lock, *args)
                self.assertEqual(code, 2)
                self.assertIn(message, err)

    def test_outside_a_project(self):
        with tempfile.TemporaryDirectory() as elsewhere:
            code, _, err = self.run_cmd(lockcmd.run_lock, "FEAT-007", "--check", cwd=Path(elsewhere))
        self.assertEqual(code, 2)
        self.assertIn("not inside a greenlight project", err)

    def test_corrupt_lock_file_is_reported_not_ignored(self):
        self.lock("--scope", "spec")
        (store.features_dir(self.root) / "FEAT-007-discounts" / "lock.json").write_text("{broken", encoding="utf-8")
        code, _, err = self.lock("--check")
        self.assertEqual(code, 2)
        self.assertIn("cannot read lock file", err)

    def test_spec_discovery_needs_configured_feature_directories(self):
        self.write(".bdd/config.toml", 'autonomy = "standard"\n')
        code, _, err = self.lock("--scope", "spec")
        self.assertEqual(code, 2)
        self.assertIn("no feature directories are configured", err)

    def test_no_feature_file_carries_the_tag(self):
        (store.features_dir(self.root) / "FEAT-042").mkdir()
        code, _, err = self.run_cmd(lockcmd.run_lock, "FEAT-042", "--scope", "spec")
        self.assertEqual(code, 2)
        self.assertIn("no .feature file is tagged @FEAT-042", err)


if __name__ == "__main__":
    unittest.main()
