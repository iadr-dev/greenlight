import tempfile
import unittest
from pathlib import Path

from bddlib import lockfile, store
from bddlib.errors import UsageError


class LockTestBase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name).resolve()
        self.feature_dir = store.features_dir(self.root) / "FEAT-007-discounts"
        self.feature_dir.mkdir(parents=True)
        (self.root / "features").mkdir()
        (self.root / "steps").mkdir()

    def write(self, rel: str, text: str = "x\n") -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
        return path

    def lock(self, scope: str, *paths: Path) -> dict:
        return lockfile.lock(self.root, self.feature_dir, "FEAT-007", scope, list(paths))

    def check(self, scopes=lockfile.SCOPES, current=None):
        return lockfile.check(self.root, self.feature_dir, "FEAT-007", scopes, current)


class DigestTest(LockTestBase):
    def test_crlf_conversion_is_not_tampering(self):
        a = self.write("features/a.feature", "Feature: A\nScenario: S\n")
        before = lockfile.file_digest(a)
        a.write_bytes(b"Feature: A\r\nScenario: S\r\n")           # what autocrlf does on checkout
        self.assertEqual(lockfile.file_digest(a), before)

    def test_content_changes_are_detected(self):
        a = self.write("features/a.feature", "Feature: A\n")
        before = lockfile.file_digest(a)
        for text in ("Feature: B\n", "Feature: A\n\n", "Feature:  A\n", ""):
            with self.subTest(text=text):
                a.write_text(text, encoding="utf-8", newline="\n")
                self.assertNotEqual(lockfile.file_digest(a), before)

    def test_binary_files_are_hashed_byte_for_byte(self):
        b = self.root / "steps" / "blob.bin"
        b.write_bytes(b"a\r\nb\x00")
        first = lockfile.file_digest(b)
        b.write_bytes(b"a\nb\x00")
        self.assertNotEqual(lockfile.file_digest(b), first)


class LockAndCheckTest(LockTestBase):
    def test_lock_records_relative_posix_paths_and_hashes(self):
        a = self.write("features/a.feature")
        files = self.lock("spec", a)
        self.assertEqual(list(files), ["features/a.feature"])
        self.assertEqual(files["features/a.feature"], lockfile.file_digest(a))
        data = lockfile.read_lock(self.feature_dir, "FEAT-007")
        self.assertEqual(data["scopes"]["spec"]["files"], files)
        self.assertEqual(data["history"][0]["event"], "lock")

    def test_untouched_files_pass(self):
        self.lock("spec", self.write("features/a.feature"))
        self.assertEqual(self.check(), [])

    def test_changed_missing_and_added_files_are_all_detected(self):
        a = self.write("features/a.feature", "one\n")
        b = self.write("features/b.feature", "two\n")
        self.lock("spec", a, b)
        a.write_text("edited\n", encoding="utf-8")
        b.unlink()
        self.write("features/c.feature", "new\n")
        found = self.check(current=["features/a.feature", "features/c.feature"])
        self.assertEqual([(v.scope, v.path, v.kind) for v in found],
                         [("spec", "features/a.feature", "changed"), ("spec", "features/b.feature", "missing"),
                          ("spec", "features/c.feature", "added")])
        self.assertIn("changed since it was locked", str(found[0]))

    def test_added_files_are_only_looked_for_in_the_spec_scope(self):
        self.lock("bind", self.write("steps/s.py"))
        self.assertEqual(self.check(current=["steps/extra.py"]), [])

    def test_scopes_are_independent(self):
        spec, step = self.write("features/a.feature"), self.write("steps/s.py")
        self.lock("spec", spec)
        self.lock("bind", step)
        step.write_text("weakened assertion\n", encoding="utf-8")
        self.assertEqual([v.scope for v in self.check()], ["bind"])
        self.assertEqual(self.check(scopes=("spec",)), [])

    def test_directories_are_expanded_and_noise_is_skipped(self):
        self.write("steps/a.py")
        self.write("steps/sub/b.py")
        self.write("steps/__pycache__/a.pyc")
        self.write("steps/.hidden/x.py")
        files = self.lock("bind", self.root / "steps")
        self.assertEqual(sorted(files), ["steps/a.py", "steps/sub/b.py"])

    def test_a_locked_scope_cannot_be_locked_again(self):
        a = self.write("features/a.feature")
        self.lock("spec", a)
        with self.assertRaises(UsageError) as cm:
            self.lock("spec", a)
        self.assertIn("already locked", str(cm.exception))

    def test_paths_outside_the_project_are_refused(self):
        with tempfile.TemporaryDirectory() as other:
            outside = Path(other) / "secret.feature"
            outside.write_text("x", encoding="utf-8")
            with self.assertRaises(UsageError) as cm:
                self.lock("spec", outside)
            self.assertIn("outside the project", str(cm.exception))
        with self.assertRaises(UsageError):
            self.lock("spec", self.root / "features" / ".." / ".." / "escape.feature")

    def test_nothing_to_lock_and_unknown_inputs(self):
        with self.assertRaises(UsageError):
            self.lock("spec", self.root / "features")                  # empty directory
        with self.assertRaises(UsageError):
            self.lock("spec", self.root / "nope.feature")
        with self.assertRaises(UsageError):
            self.lock("everything", self.write("features/a.feature"))


class UnlockTest(LockTestBase):
    def test_unlock_needs_a_reason_and_keeps_the_history(self):
        a = self.write("features/a.feature")
        self.lock("spec", a)
        with self.assertRaises(UsageError):
            lockfile.unlock(self.feature_dir, "FEAT-007", "spec", "   ")
        lockfile.unlock(self.feature_dir, "FEAT-007", "spec", "customer changed rule R-007.1")
        data = lockfile.read_lock(self.feature_dir, "FEAT-007")
        self.assertEqual(data["scopes"], {})
        self.assertEqual([h["event"] for h in data["history"]], ["lock", "unlock"])
        self.assertEqual(data["history"][1]["reason"], "customer changed rule R-007.1")
        self.assertEqual(data["history"][1]["files"], ["features/a.feature"])

    def test_after_unlocking_the_new_content_can_be_locked(self):
        a = self.write("features/a.feature", "v1\n")
        self.lock("spec", a)
        lockfile.unlock(self.feature_dir, "FEAT-007", "spec", "edit")
        a.write_text("v2\n", encoding="utf-8")
        self.lock("spec", a)
        self.assertEqual(self.check(), [])
        self.assertEqual(len(lockfile.read_lock(self.feature_dir, "FEAT-007")["history"]), 3)

    def test_unlocking_something_that_is_not_locked(self):
        with self.assertRaises(UsageError) as cm:
            lockfile.unlock(self.feature_dir, "FEAT-007", "bind", "why")
        self.assertIn("not locked", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
