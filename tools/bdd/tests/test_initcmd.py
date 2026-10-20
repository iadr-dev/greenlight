import contextlib
import importlib.util
import io
import os
import tempfile
import unittest
from pathlib import Path

from bddlib import cli, initcmd, state
from bddlib import config as cfg

HAVE_RUNNER = all(importlib.util.find_spec(name) for name in ("pytest", "pytest_bdd"))


class InitCase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name).resolve()

    def bdd(self, *argv: str) -> tuple[int, str, str]:
        out, err, here = io.StringIO(), io.StringIO(), os.getcwd()
        os.chdir(self.root)
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = cli.main(list(argv))
        finally:
            os.chdir(here)
        return code, out.getvalue(), err.getvalue()


class DetectTest(InitCase):
    def test_a_python_project_that_uses_pytest_fits_the_python_adapter(self):
        (self.root / "pyproject.toml").write_text('[project]\ndependencies = ["pytest>=8"]\n', encoding="utf-8")
        code, out, _ = self.bdd("init", "--detect")
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "python-pytest-bdd: pyproject.toml mentions pytest")

    def test_requirements_files_are_found_by_pattern_and_unrelated_ones_do_not_match(self):
        (self.root / "requirements-dev.txt").write_text("FastAPI==0.1\n", encoding="utf-8")
        self.assertIn("requirements-dev.txt mentions fastapi", self.bdd("init", "--detect")[1])
        (self.root / "requirements-dev.txt").write_text("numpy\n", encoding="utf-8")
        self.assertEqual(self.bdd("init", "--detect")[1].strip(), "no adapter matched this repository")


class InitTest(InitCase):
    def test_init_with_an_adapter_creates_the_project(self):
        code, out, err = self.bdd("init", "--adapter", "python-pytest-bdd", "--autonomy", "standard")
        self.assertEqual(code, 0, err)
        config = cfg.load(self.root)
        self.assertEqual((config.autonomy, config.profiles), ("standard", ("base", "api", "cli", "lib")))
        self.assertEqual(config.runs[0].adapter, "python-pytest-bdd")
        for rel in (".bdd/config.toml", ".bdd/glossary.md", ".bdd/.gitignore", "tests/steps/core_steps.py", "tests/features/sample.feature"):
            self.assertTrue((self.root / rel).exists(), rel)
        self.assertEqual((self.root / ".bdd" / ".gitignore").read_text(encoding="utf-8").split(), [".enforcement/", ".integrity/", ".runs/"])
        self.assertIn("bdd init --smoke", out)

    def test_init_without_an_adapter_is_a_valid_project(self):
        self.assertEqual(self.bdd("init")[0], 0)
        config = cfg.load(self.root)
        self.assertEqual((config.autonomy, config.runs), ("guided", ()))

    def test_an_existing_project_is_never_overwritten(self):
        self.bdd("init")
        before = (self.root / ".bdd" / "config.toml").read_text(encoding="utf-8")
        code, _, err = self.bdd("init")
        self.assertEqual((code, "already set up" in err), (2, True))
        self.assertEqual((self.root / ".bdd" / "config.toml").read_text(encoding="utf-8"), before)

    def test_an_adapter_can_be_added_later_and_only_once(self):
        self.bdd("init")
        self.assertEqual(self.bdd("init", "--adapter", "python-pytest-bdd")[0], 0)
        self.assertEqual(cfg.load(self.root).runs[0].adapter, "python-pytest-bdd")
        code, _, err = self.bdd("init", "--adapter", "python-pytest-bdd")
        self.assertEqual((code, "already in .bdd/config.toml" in err), (2, True))

    def test_bad_input(self):
        self.assertEqual(self.bdd("init", "--adapter", "nope")[0], 2)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as cm:
            self.bdd("init", "--autonomy", "reckless")
        self.assertEqual(cm.exception.code, 2)
        self.assertFalse((self.root / ".bdd").exists())

    def test_working_inside_a_subfolder_extends_the_project_above(self):
        self.bdd("init")
        sub = self.root / "src"
        sub.mkdir()
        here = os.getcwd()
        os.chdir(sub)
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(cli.main(["init", "--adapter", "python-pytest-bdd"]), 0)
        finally:
            os.chdir(here)
        self.assertTrue((self.root / "tests" / "conftest.py").exists())
        self.assertFalse((sub / ".bdd").exists())


@unittest.skipUnless(HAVE_RUNNER, "needs pytest and pytest-bdd")
class SmokeTest(InitCase):
    def test_the_sample_runs_green_and_nothing_is_left_behind(self):
        self.bdd("init", "--adapter", "python-pytest-bdd")
        code, out, err = self.bdd("init", "--smoke")
        self.assertEqual(code, 0, out + err)
        self.assertIn("runs green", out)
        self.assertEqual([p.name for p in (self.root / ".bdd" / "features").iterdir()], [])
        self.assertFalse((self.root / ".bdd" / ".runs" / initcmd.SAMPLE).exists())
        state.create(self.root, "FEAT-001", "Next", "standard")                  # and FEAT-000 is free to use again

    def test_a_broken_sample_is_reported(self):
        self.bdd("init", "--adapter", "python-pytest-bdd")
        (self.root / "tests" / "sample_domain.py").write_text("def add(a, b):\n    return 0\n", encoding="utf-8")
        code, _, err = self.bdd("init", "--smoke")
        self.assertEqual(code, 1)
        self.assertIn("not green", err)

    def test_smoke_needs_a_project_with_a_run_command(self):
        self.assertEqual(self.bdd("init", "--smoke")[0], 2)
        self.bdd("init")
        code, _, err = self.bdd("init", "--smoke")
        self.assertEqual((code, "[adapters.run]" in err), (2, True))


if __name__ == "__main__":
    unittest.main()
