import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from bddlib import redrecord
from bddlib.errors import UsageError

GIT = shutil.which("git")


def run_git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@example.com",
                    "-c", "commit.gpgsign=false", *args], check=True, capture_output=True)


@unittest.skipUnless(GIT, "needs git")
class RedRecordTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name).resolve()
        run_git(self.root, "init", "-q")
        self.write("src/app.py", "def price():\n    return 1\n")
        self.write("tests/features/a.feature", "Feature: A\n")
        self.write("tests/steps/steps.py", "assert True\n")
        self.write(".bdd/features/FEAT-1/state.json", "{}\n")
        self.write(".gitignore", "build/\n")
        run_git(self.root, "add", "-A")
        run_git(self.root, "commit", "-q", "-m", "initial")
        self.test_dirs = (self.root / "tests" / "features", self.root / "tests" / "steps")

    def write(self, rel: str, text: str) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")

    def capture(self) -> dict:
        return redrecord.capture(self.root, self.test_dirs)

    def test_records_head_and_a_clean_tree(self):
        head = subprocess.run(["git", "-C", str(self.root), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        record = self.capture()
        self.assertEqual((record["commit"], record["dirty"]), (head, False))
        self.assertRegex(record["source_hash"], r"^[0-9a-f]{64}$")

    def test_only_production_source_is_digested(self):
        self.assertEqual(redrecord.production_files(self.root, self.test_dirs), [".gitignore", "src/app.py"])

    def test_test_and_data_changes_do_not_change_the_source_digest(self):
        before = self.capture()["source_hash"]
        self.write("tests/steps/steps.py", "weakened\n")
        self.write("tests/features/new.feature", "Feature: new\n")
        self.write(".bdd/features/FEAT-1/state.json", '{"changed": true}\n')
        self.write("build/output.bin", "ignored by git\n")
        after = self.capture()
        self.assertEqual(after["source_hash"], before)
        self.assertFalse(after["dirty"])                        # tests and greenlight data may change; source did not

    def test_dirty_means_uncommitted_production_source(self):
        self.assertFalse(self.capture()["dirty"])
        self.write("src/app.py", "def price():\n    return 2\n")
        self.assertTrue(self.capture()["dirty"])                # modified
        run_git(self.root, "checkout", "--", "src/app.py")
        self.assertFalse(self.capture()["dirty"])
        self.write("src/new_module.py", "x = 1\n")
        self.assertTrue(self.capture()["dirty"])                # untracked
        (self.root / "src" / "new_module.py").unlink()
        (self.root / "src" / "app.py").unlink()
        self.assertTrue(self.capture()["dirty"])                # deleted

    def test_a_renamed_production_file_is_dirty_but_a_renamed_test_is_not(self):
        run_git(self.root, "mv", "tests/steps/steps.py", "tests/steps/renamed.py")
        self.assertFalse(self.capture()["dirty"])
        run_git(self.root, "mv", "src/app.py", "src/main.py")
        self.assertTrue(self.capture()["dirty"])

    def test_any_production_change_changes_the_digest(self):
        before = self.capture()["source_hash"]
        self.write("src/app.py", "def price():\n    return 2\n")
        edited = self.capture()["source_hash"]
        self.write("src/new_module.py", "x = 1\n")               # untracked, not ignored: also production source
        added = self.capture()["source_hash"]
        self.assertEqual(len({before, edited, added}), 3)

    def test_line_ending_conversion_does_not_change_the_digest(self):
        before = self.capture()["source_hash"]
        (self.root / "src" / "app.py").write_bytes(b"def price():\r\n    return 1\r\n")
        self.assertEqual(self.capture()["source_hash"], before)

    def test_files_deleted_from_the_working_tree_are_skipped(self):
        (self.root / "src" / "app.py").unlink()
        self.assertEqual(redrecord.production_files(self.root, self.test_dirs), [".gitignore"])

    def test_outside_a_git_repository(self):
        with tempfile.TemporaryDirectory() as plain:
            with self.assertRaises(UsageError) as cm:
                redrecord.capture(Path(plain), ())
        self.assertIn("git rev-parse failed", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
