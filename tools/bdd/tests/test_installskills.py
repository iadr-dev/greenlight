import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from bddlib import cli, doctor, frontmatter, installskills

SKILLS = ("approve", "change", "feature", "init", "status")


class InstallCase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name).resolve()
        (self.root / ".bdd").mkdir()
        (self.root / ".bdd" / "config.toml").write_text('autonomy = "guided"\n', encoding="utf-8", newline="\n")

    def bdd(self, *argv: str) -> tuple[int, str, str]:
        out, err, here = io.StringIO(), io.StringIO(), os.getcwd()
        os.chdir(self.root)
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = cli.main(["install-skills", *argv])
        finally:
            os.chdir(here)
        return code, out.getvalue(), err.getvalue()

    def skill(self, name: str) -> Path:
        return self.root / ".agents" / "skills" / f"greenlight-{name}" / "SKILL.md"


class CodexTest(InstallCase):
    def test_every_skill_is_installed_with_valid_front_matter_and_this_installations_paths(self):
        code, out, _ = self.bdd("codex")
        self.assertEqual(code, 0, out)
        for name in SKILLS:
            with self.subTest(skill=name):
                meta, body = frontmatter.parse(self.skill(name).read_text(encoding="utf-8"))
                self.assertEqual(set(meta), {"name", "description"})
                self.assertEqual(meta["name"], f"greenlight-{name}")
                self.assertNotIn("${CLAUDE_PLUGIN_ROOT}", body)
                self.assertNotIn("/greenlight:", body)
                self.assertIn("enforcement is soft", body)
        text = self.skill("status").read_text(encoding="utf-8")
        self.assertIn(installskills.plugin_root_text() + "/tools/bdd/bdd", text)
        self.assertNotIn("\r", text)

    def test_dry_run_changes_nothing(self):
        code, out, _ = self.bdd("codex", "--dry-run")
        self.assertEqual(code, 0)
        self.assertIn("would create", out)
        self.assertFalse((self.root / ".agents").exists())

    def test_a_second_run_changes_nothing_and_a_different_file_is_kept_without_force(self):
        self.bdd("codex")
        self.assertIn("same", self.bdd("codex")[1])
        mine = self.skill("status")
        mine.write_text("my own version\n", encoding="utf-8")
        code, out, err = self.bdd("codex")
        self.assertEqual(code, 1)
        self.assertIn("use --force", out)
        self.assertIn("nothing was written", err)
        self.assertEqual(mine.read_text(encoding="utf-8"), "my own version\n")
        self.assertEqual(self.bdd("codex", "--force")[0], 0)
        self.assertIn("name: greenlight-status", mine.read_text(encoding="utf-8"))

    def test_one_refusal_stops_the_whole_install(self):
        self.skill("status").parent.mkdir(parents=True)
        self.skill("status").write_text("mine\n", encoding="utf-8")
        self.assertEqual(self.bdd("codex")[0], 1)
        self.assertFalse(self.skill("feature").exists())

    def test_a_link_that_leaves_the_project_is_refused(self):
        with tempfile.TemporaryDirectory() as elsewhere:
            try:
                os.symlink(elsewhere, self.root / ".agents", target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("links cannot be created here")
            code, out, _ = self.bdd("codex")
            self.assertEqual(code, 1)
            self.assertIn("link", out)
            self.assertEqual(os.listdir(elsewhere), [])

    def test_user_scope_goes_to_the_home_folder(self):
        with tempfile.TemporaryDirectory() as home, mock.patch.object(Path, "home", return_value=Path(home).resolve()):
            self.assertEqual(self.bdd("codex", "--user")[0], 0)
            self.assertTrue((Path(home) / ".agents" / "skills" / "greenlight-feature" / "SKILL.md").is_file())
        self.assertFalse((self.root / ".agents").exists())

    def test_it_needs_a_project_and_user_goes_only_with_codex(self):
        self.assertEqual(self.bdd("agents-md", "--user")[0], 2)
        os.remove(self.root / ".bdd" / "config.toml")
        os.rmdir(self.root / ".bdd")
        self.assertEqual(self.bdd("codex")[0], 2)


class AgentsMdTest(InstallCase):
    path = property(lambda self: self.root / "AGENTS.md")

    def test_a_missing_file_is_created_with_the_block_and_the_soft_mode_truth(self):
        self.assertEqual(self.bdd("agents-md")[0], 0)
        text = self.path.read_text(encoding="utf-8")
        self.assertTrue(text.startswith(installskills.BEGIN.split(" (")[0]))
        self.assertIn("Enforcement here is soft", text)
        self.assertIn("lock FEAT-n --check --require", text)
        self.assertNotIn("{plugin_root}", text)

    def test_an_existing_file_keeps_its_content_and_gets_the_block_appended_once(self):
        self.path.write_text("# My project\n\nRules of the house.\n", encoding="utf-8")
        self.bdd("agents-md")
        self.bdd("agents-md")
        text = self.path.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("# My project\n\nRules of the house.\n"))
        self.assertEqual(text.count(installskills.END), 1)

    def test_a_changed_block_needs_force_and_only_the_block_is_replaced(self):
        self.path.write_text("before\n", encoding="utf-8")
        self.bdd("agents-md")
        edited = self.path.read_text(encoding="utf-8").replace("Rules you follow", "Rules I rewrote") + "after\n"
        self.path.write_text(edited, encoding="utf-8")
        code, out, _ = self.bdd("agents-md")
        self.assertEqual((code, self.path.read_text(encoding="utf-8")), (1, edited))
        self.assertIn("--force", out)
        self.assertEqual(self.bdd("agents-md", "--force")[0], 0)
        text = self.path.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("before\n"))
        self.assertTrue(text.endswith("after\n"))
        self.assertNotIn("Rules I rewrote", text)

    def test_broken_markers_are_left_alone(self):
        self.path.write_text(installskills.END + "\nthen\n" + installskills.BEGIN + "\n", encoding="utf-8")
        before = self.path.read_text(encoding="utf-8")
        self.assertEqual(self.bdd("agents-md", "--force")[0], 1)
        self.assertEqual(self.path.read_text(encoding="utf-8"), before)


class SoftModeTruthTest(unittest.TestCase):
    def test_doctor_never_calls_soft_enforcement_fine(self):
        self.assertEqual(doctor.check_enforcement("soft", False).status, "warn")
        self.assertEqual(doctor.check_enforcement("soft", True).status, "warn")
        self.assertEqual(doctor.check_enforcement("auto", False).status, "warn")
        self.assertIn("not prevented", doctor.check_enforcement("soft", False).detail)
        self.assertIn("--check --require", doctor.check_enforcement("auto", False).fix)

    def test_doctor_reports_hooks_that_have_run(self):
        self.assertEqual(doctor.check_enforcement("auto", True).status, "ok")
        self.assertEqual(doctor.check_enforcement("hard", True).status, "ok")
        self.assertEqual(doctor.check_enforcement("hard", False).status, "warn")


if __name__ == "__main__":
    unittest.main()
