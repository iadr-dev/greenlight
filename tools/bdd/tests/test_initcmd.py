import contextlib
import importlib.util
import io
import os
import tempfile
import unittest
from unittest import mock
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
        self.assertEqual((config.autonomy, config.profiles), ("standard", ("base", "api", "cli", "lib", "data")))
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


class RecordsTest(InitCase):
    def write(self, rel: str, text: str = "") -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        return path

    def read(self, rel: str) -> str:
        return (self.root / rel).read_text(encoding="utf-8")

    def python_project(self) -> None:
        self.write("pyproject.toml", '[project]\nname = "x"\ndependencies = ["stripe"]\n[dependency-groups]\ndev = ["ruff", "mypy"]\n')

    def test_a_python_project_gets_its_sources_and_the_checks_it_declares_and_bdd_reads_them_back(self):
        self.python_project()
        code, out, err = self.bdd("init", "--adapter", "python-pytest-bdd")
        self.assertEqual(code, 0, err)
        self.assertIn("sources: stripe\n", out)
        self.assertIn("quality: ruff, ruff-format, mypy\n", out)
        config = cfg.load(self.root)
        self.assertEqual([(c.name, c.cwd) for c in config.quality.checks], [("ruff", ""), ("ruff-format", ""), ("mypy", "")])
        self.assertEqual(config.runs[0].adapter, "python-pytest-bdd", "the adapter's own tables are still read")
        self.assertEqual(config.quality.checks[0].command, "{project_python} -m ruff check . --extend-exclude tests",
                         "greenlight's own locked plumbing in tests/ is not held to the project's style")
        self.assertIn('[stripe]\nname = "Stripe"', self.read(".bdd/sources.toml"))

    def test_a_project_with_nothing_to_record_says_so_and_writes_no_file(self):
        code, out, _ = self.bdd("init", "--adapter", "python-pytest-bdd")
        self.assertEqual(code, 0)
        for line in ("sources: none recognised", "quality: none declared", "design: none found", "surfaces: none detected"):
            self.assertIn(line, out)
        self.assertFalse((self.root / ".bdd" / "sources.toml").exists())
        config = cfg.load(self.root)
        self.assertEqual((config.design, config.surfaces, config.quality), (None, (), None))

    def test_init_without_an_adapter_records_sources_and_defers_the_checks(self):
        self.python_project()
        _, out, _ = self.bdd("init")
        self.assertIn("sources: stripe", out)
        self.assertIn("quality: none recorded yet; add an adapter", out)
        self.assertIsNone(cfg.load(self.root).quality)
        _, out, _ = self.bdd("init", "--adapter", "python-pytest-bdd")
        self.assertIn("quality: ruff, ruff-format, mypy", out)

    def test_refresh_adds_what_is_new_and_changes_nothing_the_person_wrote(self):
        self.bdd("init", "--adapter", "python-pytest-bdd")
        config = self.read(".bdd/config.toml") + "\n[models]\nimplementer = \"opus\"\n"
        self.write(".bdd/config.toml", config)
        self.write(".bdd/sources.toml", '[stripe]\nname = "Ours"\n')
        self.python_project()
        self.write("design/DESIGN.md")
        code, out, _ = self.bdd("init", "--refresh")
        self.assertEqual(code, 0, out)
        self.assertIn("quality: ruff, ruff-format, mypy", out)
        after = self.read(".bdd/config.toml")
        self.assertTrue(after.startswith(config), "what was there is untouched; the records are appended")
        loaded = cfg.load(self.root)
        self.assertEqual([c.name for c in loaded.quality.checks], ["ruff", "ruff-format", "mypy"])
        self.assertEqual((loaded.design.system, loaded.models), ("design/DESIGN.md", (("implementer", "opus"),)))
        self.assertEqual(self.read(".bdd/sources.toml"), '[stripe]\nname = "Ours"\n')
        again, _, _ = self.bdd("init", "--refresh")
        self.assertEqual((again, self.read(".bdd/config.toml")), (0, after), "a second run finds nothing to add")

    def test_checks_surfaces_and_design_the_person_has_are_kept_even_when_malformed(self):
        self.python_project()
        self.write("design/DESIGN.md")
        self.bdd("init", "--adapter", "python-pytest-bdd")
        mine = self.read(".bdd/config.toml").replace("[adapters.quality.ruff]", "[adapters.quality.mine]\ncommand = 'x'\n\n[adapters.quality.ruff]")
        mine = mine.replace('system = "design/DESIGN.md"', 'system = 3')
        self.write(".bdd/config.toml", mine)
        _, out, _ = self.bdd("init", "--refresh")
        self.assertEqual(self.read(".bdd/config.toml"), mine)
        self.assertIn("quality: the checks already in .bdd/config.toml are kept", out)
        self.assertIn("design: already in .bdd/config.toml", out)
        self.assertEqual(cfg.load(self.root).warnings[0].count("ignored"), 1)

    def test_refresh_needs_a_project(self):
        code, _, err = self.bdd("init", "--refresh")
        self.assertEqual((code, "not inside a greenlight project" in err), (2, True))

    def test_the_adapters_own_plumbing_is_not_taken_for_the_project(self):
        self.write("go.mod", "module x\n")
        _, out, _ = self.bdd("init", "--adapter", "go-godog")
        self.assertTrue((self.root / "tests" / "go.mod").is_file())
        self.assertIn("quality: gofmt, go-vet\n", out)
        self.assertEqual([c.cwd for c in cfg.load(self.root).quality.checks], ["", ""], "tests/go.mod is not a second project")

    def test_a_folder_below_the_project_keeps_its_own_checks_in_its_own_folder(self):
        self.write("api/package.json", '{"devDependencies": {"typescript": "7"}, "dependencies": {"fastify": "5"}}')
        self.write("api/tsconfig.json", "{}")
        _, out, _ = self.bdd("init", "--adapter", "ts-cucumber-js")
        self.assertIn("quality: tsc\n", out)
        self.assertIn("frameworks: fastify", out)
        self.assertIn("surfaces: api (ts-cucumber-js)", out)
        (check,) = cfg.load(self.root).quality.checks
        self.assertEqual((check.cwd, check.command), ("api", "npx --no-install tsc --noEmit"))

    def test_the_vendor_cli_found_on_the_path_is_said_and_its_plugin_is_named(self):
        self.write("package.json", '{"dependencies": {"@supabase/supabase-js": "2", "stripe": "17"}}')
        with mock.patch.object(initcmd.shutil, "which", side_effect=lambda name: "/bin/supabase" if name == "supabase" else None):
            _, out, _ = self.bdd("init", "--adapter", "ts-cucumber-js")
        self.assertIn("vendor tools: supabase (found), stripe (not installed)", out)
        self.assertIn("vendor plugins: supabase, stripe", out)

    def test_the_records_are_not_written_when_they_would_break_the_file(self):
        self.python_project()
        self.bdd("init", "--adapter", "python-pytest-bdd")
        broken = self.read(".bdd/config.toml").replace("[adapters.quality.ruff]", "[adapters.quality.mine]\ncommand = 'x'\n\n"
                                                       "[adapters.quality.ruff]", 1)
        self.write(".bdd/config.toml", broken)
        with mock.patch.object(initcmd.toolchain, "design_text", return_value="\n[surfaces\n"):
            self.write("design/DESIGN.md")
            _, out, _ = self.bdd("init", "--refresh")
        self.assertIn("were not written", out)
        self.assertEqual(self.read(".bdd/config.toml"), broken)


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
