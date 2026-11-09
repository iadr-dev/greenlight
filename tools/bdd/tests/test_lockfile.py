import tempfile
import unittest
from pathlib import Path

from bddlib import gates, lockfile, store
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


class SharedPlumbingCase(unittest.TestCase):
    """FEAT-007 and FEAT-008 in one project, with a support file that is the shared plumbing."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name).resolve()
        self.configure('support = ["steps/conftest.py"]\n')
        self.dirs = {fid: store.features_dir(self.root) / f"{fid}-x" for fid in ("FEAT-007", "FEAT-008")}
        for feature_dir in self.dirs.values():
            feature_dir.mkdir(parents=True)
        (self.root / "features").mkdir()
        self.conftest = self.write("steps/conftest.py", "# shared fixtures\n")
        self.discounts = self.write("steps/discounts.py", "# FEAT-007\n")

    def configure(self, support: str) -> None:
        self.write(".bdd/config.toml", '[[adapters]]\nname = "x"\nfeatures = "features"\nsteps = "steps"\n' + support)

    def write(self, rel: str, text: str = "x\n") -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
        return path

    def bind(self, fid: str, *paths: Path) -> dict:
        return lockfile.lock_bind(self.root, self.dirs[fid], fid, list(paths) or None, {"steps/conftest.py"})[0]

    def spec_only(self, fid: str) -> None:
        feature = self.write(f"features/{fid}.feature", f"@{fid}\nFeature: F\n")
        lockfile.lock(self.root, self.dirs[fid], fid, "spec", [feature])

    def check(self, fid: str) -> list:
        return lockfile.check(self.root, self.dirs[fid], fid, ("bind",), None, lockfile.bound_files(self.root))

    def found(self, fid: str) -> list[tuple[str, str, str]]:
        return [(v.scope, v.path, v.kind) for v in self.check(fid)]

    def bind_files(self, fid: str) -> dict:
        return lockfile.read_lock(self.dirs[fid], fid)["scopes"]["bind"]["files"]

    def bind_both(self) -> None:
        self.bind("FEAT-007")
        self.write("steps/refunds.py", "# FEAT-008\n")
        self.bind("FEAT-008")


class OwnFilesTest(SharedPlumbingCase):
    def test_a_bind_lock_takes_the_features_own_files_and_the_first_one_locks_the_plumbing(self):
        self.assertEqual(set(self.bind("FEAT-007")), {"steps/discounts.py"})
        plumbing = lockfile.read_plumbing(self.root)
        self.assertEqual(set(plumbing["files"]), {"steps/conftest.py"})
        entry = lockfile.read_lock(self.dirs["FEAT-007"], "FEAT-007")["scopes"]["bind"]
        self.assertEqual(entry["plumbing"], lockfile.files_digest(plumbing["files"]))

    def test_a_file_another_feature_binds_later_is_that_features_and_not_a_violation(self):
        self.bind_both()
        self.assertEqual(set(self.bind_files("FEAT-008")), {"steps/refunds.py"})
        self.assertEqual(self.found("FEAT-007"), [])
        self.assertEqual(self.found("FEAT-008"), [])

    def test_a_feature_whose_steps_are_all_shared_binds_with_no_file_of_its_own(self):
        self.bind("FEAT-007")
        self.assertEqual(self.bind("FEAT-008"), {})
        self.assertEqual(self.found("FEAT-008"), [])

    def test_a_named_file_another_lock_covers_is_left_to_it(self):
        self.bind("FEAT-007")
        files, left_out = lockfile.lock_bind(self.root, self.dirs["FEAT-008"], "FEAT-008",
                                             [self.discounts, self.conftest], {"steps/conftest.py"})
        self.assertEqual(files, {})
        self.assertEqual(left_out, {"steps/discounts.py": "FEAT-007", "steps/conftest.py": "the shared plumbing"})

    def test_an_edit_to_a_features_own_file_fails_only_that_feature(self):
        self.bind_both()
        self.discounts.write_text("# FEAT-007, weakened\n", encoding="utf-8")
        self.assertEqual(self.found("FEAT-007"), [("bind", "steps/discounts.py", "changed")])
        self.assertEqual(self.found("FEAT-008"), [])

    def test_a_file_no_lock_covers_is_a_violation_unless_a_feature_is_still_binding(self):
        self.bind("FEAT-007")
        self.write("steps/zz_patch.py", "# makes everything pass\n")
        self.assertEqual(self.found("FEAT-007"), [("bind", "steps/zz_patch.py", "added")])
        self.spec_only("FEAT-008")                       # its step engineer may be writing that file now
        self.assertEqual(self.found("FEAT-007"), [])
        self.bind("FEAT-008")                            # and its bind lock takes it
        self.assertIn("steps/zz_patch.py", self.bind_files("FEAT-008"))

    def test_reopening_a_later_feature_leaves_the_earlier_one_intact(self):
        self.bind_both()
        lockfile.unlock(self.dirs["FEAT-008"], "FEAT-008", "bind", "change: the threshold is now 500")
        self.assertEqual(self.found("FEAT-007"), [])
        self.bind("FEAT-008")
        self.assertEqual(set(self.bind_files("FEAT-008")), {"steps/refunds.py"})

    def test_a_new_support_file_is_never_presumed_to_be_a_features(self):
        self.configure('support = ["steps/conftest.py", "steps/*/conftest.py"]\n')
        self.bind("FEAT-007")
        self.spec_only("FEAT-008")
        self.write("steps/extra/conftest.py", "# loaded by the runner\n")
        self.assertEqual(self.found("FEAT-007"), [("plumbing", "steps/extra/conftest.py", "added")])
        self.bind("FEAT-008")
        self.assertNotIn("steps/extra/conftest.py", self.bind_files("FEAT-008"))


class PlumbingChangeTest(SharedPlumbingCase):
    def test_a_changed_plumbing_file_fails_every_bound_feature(self):
        self.bind_both()
        self.conftest.write_text("# shared fixtures, changed\n", encoding="utf-8")
        for fid in self.dirs:
            with self.subTest(feature=fid):
                self.assertEqual(self.found(fid), [("plumbing", "steps/conftest.py", "changed")])

    def test_locking_the_plumbing_again_names_every_feature_to_rerun_and_reopens_none(self):
        self.bind_both()
        self.conftest.write_text("# shared fixtures, with a clock\n", encoding="utf-8")
        result = lockfile.lock_plumbing(self.root, "the fixtures gained a clock", [], {"steps/conftest.py"})
        self.assertEqual((result["changed"], result["rerun"]), (["steps/conftest.py"], ["FEAT-007", "FEAT-008"]))
        for fid in self.dirs:
            self.assertEqual(self.found(fid), [])
            self.assertTrue(self.bind_files(fid))
        history = lockfile.read_plumbing(self.root)["history"]
        self.assertEqual((history[-1]["reason"], history[-1]["changed"]), ("the fixtures gained a clock", ["steps/conftest.py"]))
        again = lockfile.lock_plumbing(self.root, "nothing new", [], {"steps/conftest.py"})
        self.assertEqual((again["changed"], again["rerun"]), ([], []))
        self.assertEqual(len(lockfile.read_plumbing(self.root)["history"]), len(history))

    def test_a_plumbing_change_needs_a_reason(self):
        self.bind("FEAT-007")
        with self.assertRaises(UsageError):
            lockfile.lock_plumbing(self.root, "  ", [], {"steps/conftest.py"})
        with self.assertRaises(UsageError):
            lockfile.unlock_plumbing(self.root, "")

    def test_while_the_plumbing_is_unlocked_the_gates_are_told_and_nothing_binds(self):
        self.bind("FEAT-007")
        lockfile.unlock_plumbing(self.root, "adding a clock fixture")
        self.conftest.write_text("# with a clock\n", encoding="utf-8")
        self.assertEqual(self.found("FEAT-007"), [])            # not tampering: it is being changed, and the gates say so
        self.assertIn("adding a clock fixture", lockfile.plumbing_problem(self.root))
        with self.assertRaises(UsageError):
            self.bind("FEAT-008")
        lockfile.lock_plumbing(self.root, "clock fixture added", [], {"steps/conftest.py"})
        self.assertIsNone(lockfile.plumbing_problem(self.root))
        self.assertEqual(self.found("FEAT-007"), [])

    def test_every_features_gate_refuses_a_changed_or_released_plumbing(self):
        self.bind_both()
        self.conftest.write_text("# changed without a plumbing change\n", encoding="utf-8")
        for fid in self.dirs:
            self.assertTrue(any("[plumbing] steps/conftest.py" in p for p in gates.lock_problems(self.root, self.dirs[fid], fid)))
        lockfile.unlock_plumbing(self.root, "fixing it")
        for fid in self.dirs:
            self.assertTrue(any("was unlocked" in p for p in gates.lock_problems(self.root, self.dirs[fid], fid)))

    def test_a_deleted_plumbing_lock_is_a_violation(self):
        self.bind("FEAT-007")
        lockfile.plumbing_path(self.root).unlink()
        self.assertEqual(self.found("FEAT-007"), [("plumbing", ".bdd/plumbing.lock.json", "missing"),
                                                  ("plumbing", "steps/conftest.py", "added")])

    def test_a_features_file_is_shared_only_as_it_was_locked(self):
        self.bind_both()
        result = lockfile.lock_plumbing(self.root, "refunds reuse the discount steps", [self.discounts], {"steps/conftest.py"})
        self.assertEqual(result["moved"], {"FEAT-007": ["steps/discounts.py"]})
        self.assertEqual(self.bind_files("FEAT-007"), {})
        self.assertIn("steps/discounts.py", lockfile.read_plumbing(self.root)["files"])
        self.assertEqual(self.found("FEAT-007"), [])
        refunds = self.write("steps/refunds.py", "# FEAT-008, changed\n")
        with self.assertRaises(UsageError) as cm:
            lockfile.lock_plumbing(self.root, "share refunds too", [refunds], {"steps/conftest.py"})
        self.assertIn("changed since FEAT-008 locked it", str(cm.exception))


class MigrationTest(SharedPlumbingCase):
    def legacy(self, fid: str, at: str, *rels: str) -> None:
        files = {rel: lockfile.file_digest(self.root / rel) for rel in rels}
        store.write_json(self.dirs[fid] / lockfile.LOCK_FILE, {
            "schema": 1, "feature": fid, "history": [], "scopes": {"bind": {"locked_at": at, "files": files}}})

    def test_old_locks_are_converted_shared_files_to_the_plumbing_and_every_check_stays_clean(self):
        self.write("steps/refunds.py", "# FEAT-008\n")
        self.legacy("FEAT-007", "2026-01-01T00:00:00+00:00", "steps/conftest.py", "steps/discounts.py")
        self.legacy("FEAT-008", "2026-01-02T00:00:00+00:00", "steps/conftest.py", "steps/discounts.py", "steps/refunds.py")
        self.assertEqual(lockfile.legacy_features(self.root), ["FEAT-007", "FEAT-008"])
        lockfile.migrate_legacy(self.root, {"steps/conftest.py"})
        self.assertEqual(lockfile.legacy_features(self.root), [])
        self.assertEqual(set(lockfile.read_plumbing(self.root)["files"]), {"steps/conftest.py"})
        self.assertEqual(set(self.bind_files("FEAT-007")), {"steps/discounts.py"})
        self.assertEqual(set(self.bind_files("FEAT-008")), {"steps/refunds.py"})
        for fid in self.dirs:
            self.assertEqual(self.found(fid), [])

    def test_an_old_lock_keeps_working_until_it_is_migrated_and_binding_waits_for_the_migration(self):
        self.legacy("FEAT-007", "2026-01-01T00:00:00+00:00", "steps/conftest.py", "steps/discounts.py")
        self.assertEqual(self.found("FEAT-007"), [])
        self.conftest.write_text("# tampered\n", encoding="utf-8")
        self.assertEqual(self.found("FEAT-007"), [("bind", "steps/conftest.py", "changed")])
        for attempt in (lambda: self.bind("FEAT-008"), lambda: lockfile.lock_plumbing(self.root, "x", [], set())):
            with self.assertRaises(UsageError) as cm:
                attempt()
            self.assertIn("bdd migrate", str(cm.exception))

    def test_an_old_lock_that_does_not_match_the_disk_is_not_converted(self):
        self.legacy("FEAT-007", "2026-01-01T00:00:00+00:00", "steps/conftest.py", "steps/discounts.py")
        self.conftest.write_text("# tampered\n", encoding="utf-8")
        with self.assertRaises(UsageError) as cm:
            lockfile.migrate_legacy(self.root, {"steps/conftest.py"})
        self.assertIn("steps/conftest.py changed since it was locked", str(cm.exception))
        self.assertFalse(lockfile.plumbing_path(self.root).exists())


if __name__ == "__main__":
    unittest.main()
