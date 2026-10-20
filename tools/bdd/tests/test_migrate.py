import contextlib
import io
import json
import os
import unittest
from unittest import mock

from bddlib import cli, guard, migrate, state
from bddlib import config as cfg
from bddlib.errors import UsageError

from tests.helpers import ProjectCase


def add_flag(root):
    """A migration from schema 1 to 2: every feature state gets a new field."""
    notes = []
    for path in (root / ".bdd" / "features").glob("*/state.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        data["notes"] = []
        path.write_text(json.dumps(data, indent=2), encoding="utf-8", newline="\n")
        notes.append(f"added notes to {path.parent.name}")
    return notes


class MigrateCase(ProjectCase):
    def run_cli(self, *argv: str) -> tuple[int, str, str]:
        out, err, here = io.StringIO(), io.StringIO(), os.getcwd()
        os.chdir(self.root)
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = cli.main(list(argv))
        finally:
            os.chdir(here)
        return code, out.getvalue(), err.getvalue()

    def newer(self):
        """This greenlight now writes schema 2, with a migration from 1."""
        for patcher in (mock.patch.object(cfg, "SCHEMA_VERSION", 2), mock.patch.dict(migrate.MIGRATIONS, {1: add_flag})):
            patcher.start()
            self.addCleanup(patcher.stop)


class VersionTest(MigrateCase):
    def test_a_project_without_a_version_is_at_schema_1(self):
        self.assertEqual(cfg.load(self.root).version, 1)

    def test_the_version_is_read_from_config_and_validated(self):
        self.config("version = 1\n")
        self.assertEqual(cfg.load(self.root).version, 1)
        for bad in ('version = 0\n', 'version = "1"\n', 'version = true\n'):
            with self.subTest(bad=bad):
                self.config(bad)
                with self.assertRaises(cfg.ConfigError):
                    cfg.load(self.root)

    def test_a_newer_project_is_refused_with_a_message_to_upgrade(self):
        self.config("version = 2\n")
        with self.assertRaises(cfg.ConfigError) as cm:
            cfg.load(self.root)
        self.assertIn("schema 2", str(cm.exception))
        self.assertIn("upgrade greenlight", str(cm.exception))

    def test_every_command_checks_the_version_but_the_hooks_never_fail_on_it(self):
        self.config("version = 2\n")
        for argv in (["status"], ["state", "show", "FEAT-007"], ["lint"], ["gate", "FEAT-007", "discover"]):
            with self.subTest(argv=argv):
                code, _, err = self.run_cli(*argv)
                self.assertEqual(code, 2)
                self.assertIn("upgrade greenlight", err)
        for argv in (["doctor", "--json"], ["status", "--brief"]):
            with self.subTest(argv=argv):
                self.assertNotIn("upgrade greenlight", self.run_cli(*argv)[2])

    def test_the_guard_stays_closed_on_a_newer_project(self):
        self.config("version = 2\n")
        reason = guard.evaluate({"tool_name": "Write", "cwd": str(self.root), "tool_input": {"file_path": str(self.root / "a.py")}})
        self.assertIn("upgrade greenlight", reason)


class MigrateTest(MigrateCase):
    def test_up_to_date_does_nothing(self):
        self.assertEqual(self.run_cli("migrate"), (0, "already at schema 1; nothing to do\n", ""))
        self.assertFalse((self.root / ".bdd-backup-v1").exists())

    def test_an_older_project_is_refused_until_it_is_migrated(self):
        self.newer()
        code, _, err = self.run_cli("status")
        self.assertEqual(code, 2)
        self.assertIn("run `bdd migrate` first", err)
        self.assertEqual(self.run_cli("status", "--brief")[0], 0)           # hooks are never blocked by it
        self.assertEqual(guard.evaluate({"tool_name": "Write", "cwd": str(self.root),
                                         "tool_input": {"file_path": str(self.root / "a.py")}}), None)

    def test_dry_run_changes_nothing(self):
        self.newer()
        code, out, _ = self.run_cli("migrate", "--dry-run")
        self.assertEqual((code, out.strip()), (0, "would migrate schema 1 to 2 in 1 step(s): 1 -> 2"))
        self.assertEqual(cfg.load(self.root).version, 1)
        self.assertNotIn("notes", state.load(self.feature_dir))

    def test_migrating_backs_up_upgrades_the_data_and_bumps_the_version(self):
        self.newer()
        before = (self.feature_dir / "state.json").read_text(encoding="utf-8")
        code, out, _ = self.run_cli("migrate")
        self.assertEqual(code, 0)
        self.assertIn("backup: .bdd-backup-v1", out)
        self.assertIn("1 -> 2: added notes to FEAT-007-order-discounts", out)
        self.assertEqual(cfg.load(self.root).version, 2)
        self.assertEqual(state.load(self.feature_dir)["notes"], [])
        saved = self.root / ".bdd-backup-v1" / "features" / "FEAT-007-order-discounts" / "state.json"
        self.assertEqual(saved.read_text(encoding="utf-8"), before)           # nothing was lost
        self.assertEqual(self.run_cli("status")[0], 0)                        # and the commands work again
        self.assertEqual(self.run_cli("migrate")[1], "already at schema 2; nothing to do\n")

    def test_a_project_newer_than_this_greenlight_cannot_be_migrated(self):
        self.config("version = 2\n")
        code, _, err = self.run_cli("migrate")
        self.assertEqual(code, 2)
        self.assertIn("upgrade greenlight", err)
        self.assertNotIn("Traceback", err)

    def test_an_existing_backup_is_never_overwritten(self):
        self.newer()
        (self.root / ".bdd-backup-v1").mkdir()
        code, _, err = self.run_cli("migrate")
        self.assertEqual(code, 2)
        self.assertIn(".bdd-backup-v1 already exists", err)
        self.assertEqual(cfg.load(self.root).version, 1)

    def test_a_missing_step_is_reported_before_anything_is_touched(self):
        with mock.patch.object(cfg, "SCHEMA_VERSION", 3), mock.patch.dict(migrate.MIGRATIONS, {1: add_flag}, clear=True):
            code, _, err = self.run_cli("migrate")
            self.assertEqual(code, 2)
            self.assertIn("no migration from schema 2", err)
            self.assertFalse((self.root / ".bdd-backup-v1").exists())

    def test_a_failing_step_leaves_the_project_at_the_last_good_version(self):
        def broken(root):
            raise UsageError("cannot convert")
        with mock.patch.object(cfg, "SCHEMA_VERSION", 3), mock.patch.dict(migrate.MIGRATIONS, {1: add_flag, 2: broken}, clear=True):
            code, out, err = self.run_cli("migrate")
            self.assertEqual(code, 2)
            self.assertIn("cannot convert", err)
            self.assertIn("schema 2", out)
        self.assertIn("version = 2", (self.root / ".bdd" / "config.toml").read_text(encoding="utf-8"))

    def test_the_project_outside_is_not_a_project(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            here = os.getcwd()
            os.chdir(tmp)
            try:
                with contextlib.redirect_stderr(io.StringIO()) as err:
                    self.assertEqual(cli.main(["migrate"]), 2)
            finally:
                os.chdir(here)
        self.assertIn("not inside a greenlight project", err.getvalue())


class SetVersionTest(ProjectCase):
    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(cfg, "SCHEMA_VERSION", 3)          # so that the versions written here are readable
        patcher.start()
        self.addCleanup(patcher.stop)

    def text(self) -> str:
        return (self.root / ".bdd" / "config.toml").read_text(encoding="utf-8")

    def test_inserts_at_the_top_before_any_table(self):
        migrate.set_version(self.root, 2)
        self.assertTrue(self.text().startswith("version = 2\n[[adapters]]"))
        self.assertEqual(cfg.load(self.root).feature_dirs, (self.root / "features",))

    def test_replaces_an_existing_top_level_line_and_keeps_the_rest(self):
        self.config('autonomy = "guided"\nversion = 1\n', tail='[gates]\nversion = "not this one"\n')
        migrate.set_version(self.root, 3)
        text = self.text()
        self.assertIn("version = 3\n", text)
        self.assertIn('autonomy = "guided"', text)
        self.assertIn('version = "not this one"', text)             # a key inside a table is left alone
        self.assertEqual(cfg.load(self.root).autonomy, "guided")

    def test_a_missing_config_is_created(self):
        (self.root / ".bdd" / "config.toml").unlink()
        migrate.set_version(self.root, 2)
        self.assertEqual(self.text(), "version = 2\n")


if __name__ == "__main__":
    unittest.main()
