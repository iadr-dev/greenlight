"""The mutmut wrapper of the python-pytest-bdd adapter: its rules with a fake mutmut, and one real run when mutmut is there.

The real run needs mutmut in the interpreter that runs the tests (CI installs the pinned version with uv) and a system
mutmut supports: it does not run natively on Windows.
"""
import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from bddlib import adapter, cli, mutation, redrecord, state
from bddlib import config as cfg

from tests.test_redrecord import GIT, run_git

REPO = Path(__file__).resolve().parents[3]
WRAPPER = REPO / "adapters" / "python-pytest-bdd" / "templates" / "tests" / "tools" / "mutate_python.py"
HAVE_MUTMUT = importlib.util.find_spec("mutmut") is not None and os.name != "nt"
TABLE = """
[adapters.mutation]
command    = '{project_python} -I tests/tools/mutate_python.py --report {out} -- {files}'
threshold  = 70
timeout    = 900
extensions = [".py"]
"""

spec = importlib.util.spec_from_file_location("mutate_python", WRAPPER)
wrapper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wrapper)

FAKE_MUTMUT = '''import json, os, sys
from pathlib import Path

if sys.argv[1] == "run":
    settings = Path("pyproject.toml").read_text(encoding="utf-8")
    Path("settings-seen.txt").write_text(settings, encoding="utf-8")
    sys.exit(int(os.environ.get("FAKE_RUN_EXIT", "0")))
if sys.argv[1] == "export-cicd-stats":
    Path("mutants").mkdir(exist_ok=True)
    Path("mutants/mutmut-cicd-stats.json").write_text(os.environ["FAKE_STATS"], encoding="utf-8")
'''


class ArgumentsTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name).resolve()
        (self.root / "shop").mkdir()
        (self.root / "shop" / "discount.py").write_text("X = 1\n", encoding="utf-8")
        (self.root / "notes.txt").write_text("n\n", encoding="utf-8")

    def test_files_are_relative_existing_python_files_inside_the_project(self):
        self.assertEqual(wrapper.check_files(self.root, ["shop/discount.py", "shop/discount.py"]), ["shop/discount.py"])
        for name in ("../x.py", "/etc/passwd.py", "shop/missing.py", "notes.txt", "shop", "shop/../../out.py"):
            with self.subTest(name=name), self.assertRaises(wrapper.Refused):
                wrapper.check_files(self.root, [name])
        with self.assertRaises(wrapper.Refused):
            wrapper.check_files(self.root, [])

    def test_the_report_is_an_absolute_path_outside_the_project(self):
        with tempfile.TemporaryDirectory() as elsewhere:
            good = Path(elsewhere).resolve() / "report.json"
            self.assertEqual(wrapper.check_report(self.root, str(good)), good)
        for name in ("report.json", str(self.root / "report.json"), str(self.root / "no-folder" / "r.json")):
            with self.subTest(name=name), self.assertRaises(wrapper.Refused):
                wrapper.check_report(self.root, name)

    def test_settings_name_only_the_given_files_and_the_projects_test_settings(self):
        text = wrapper.mutmut_settings(["shop/discount.py", "top.py"])
        self.assertIn('source_paths = ["shop", "top.py"]', text)
        self.assertIn('only_mutate = ["shop/discount.py", "top.py"]', text)
        self.assertIn('"tests/pytest.ini"', text)
        self.assertIn("[tool.mutmut]", text)

    def test_counts_follow_the_rules_for_doubt(self):
        stats = {"killed": 8, "survived": 2, "no_tests": 1, "timeout": 3, "suspicious": 1, "segfault": 2, "skipped": 4,
                 "total": 99}
        self.assertEqual(wrapper.counts_from_stats(stats),
                         {"killed": 8, "survived": 3, "timeout": 3, "suspicious": 3, "skipped": 4})
        self.assertEqual(wrapper.counts_from_stats({"killed": "x", "survived": -1}),
                         {"killed": 0, "survived": 0, "timeout": 0, "suspicious": 0, "skipped": 0})

    def test_the_copy_leaves_out_the_environment_and_the_history(self):
        for name in (".git", ".venv", ".bdd", "mutants"):
            (self.root / name).mkdir()
            (self.root / name / "f.txt").write_text("x", encoding="utf-8")
        with tempfile.TemporaryDirectory() as elsewhere:
            target = Path(elsewhere) / "copy"
            wrapper.copy_project(self.root, target)
            self.assertEqual(sorted(p.name for p in target.iterdir()), ["notes.txt", "shop"])


class RunWithFakeMutmutTest(unittest.TestCase):
    """The exit status and the report, with a `mutmut` package in the project copy that answers like the real one."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name).resolve() / "project"
        (self.root / "shop").mkdir(parents=True)
        (self.root / "shop" / "discount.py").write_text("X = 1\n", encoding="utf-8")
        (self.root / "mutmut").mkdir()
        (self.root / "mutmut" / "__init__.py").write_text("", encoding="utf-8")
        (self.root / "mutmut" / "__main__.py").write_text(FAKE_MUTMUT, encoding="utf-8")
        self.report_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.report_dir.cleanup)
        self.report = Path(self.report_dir.name).resolve() / "report.json"

    def main(self, *files: str, **env: str) -> tuple[int, str]:
        err, here = io.StringIO(), os.getcwd()
        os.chdir(self.root)
        try:
            variables = {"FAKE_STATS": json.dumps({"killed": 9, "survived": 1}), **env}
            with mock.patch.dict(os.environ, variables), contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
                code = wrapper.main(["--report", str(self.report), "--", *files])
        finally:
            os.chdir(here)
        return code, err.getvalue()

    def test_a_finished_run_writes_the_counts_and_exits_zero_whatever_survived(self):
        code, _ = self.main("shop/discount.py", FAKE_STATS=json.dumps({"killed": 3, "survived": 7}))
        if os.name == "nt":
            self.assertEqual(code, wrapper.EXIT_TOOL_FAILED)           # mutmut does not run here; the wrapper says so
            return
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(self.report.read_text(encoding="utf-8")),
                         {"killed": 3, "survived": 7, "timeout": 0, "suspicious": 0, "skipped": 0})

    def test_a_tool_that_fails_is_not_reported_as_a_result(self):
        code, message = self.main("shop/discount.py", FAKE_RUN_EXIT="1")
        self.assertEqual(code, wrapper.EXIT_TOOL_FAILED)
        self.assertFalse(self.report.exists())
        self.assertIn("mutate_python:", message)

    def test_refused_arguments_exit_with_their_own_status(self):
        code, message = self.main("../outside.py")
        self.assertEqual(code, wrapper.EXIT_REFUSED)
        self.assertIn("without ..", message)
        self.assertFalse(self.report.exists())


STRONG_TESTS = '''from shop.discount import discount


def test_below_the_threshold_there_is_no_discount():
    assert discount(999) == 0
    assert discount(0) == 0


def test_on_the_threshold_it_is_ten_percent():
    assert discount(1000) == 100
    assert discount(2000) == 200
'''

WEAK_TESTS = '''from shop.discount import discount


def test_it_returns_a_number():
    assert discount(5000) is not None
'''

DISCOUNT = '''def discount(total):
    if total >= 1000:
        return total // 10
    return 0
'''


@unittest.skipUnless(HAVE_MUTMUT and GIT, "needs mutmut (Linux or macOS) and git")
class RealMutmutTest(unittest.TestCase):
    """`bdd mutate` with the shipped wrapper and the real mutmut: weak tests fail the threshold, strong tests pass."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name).resolve()
        (self.root / ".bdd").mkdir()
        adapter.apply(self.root, "python-pytest-bdd")
        with (self.root / ".bdd" / "config.toml").open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(TABLE)
        self.write(".gitignore", ".bdd/.runs/\n__pycache__/\nmutants/\n")
        self.write("shop/__init__.py", "")
        self.write("shop/discount.py", "def discount(total):\n    return 0\n")
        run_git(self.root, "init", "-q")
        run_git(self.root, "add", "-A")
        run_git(self.root, "commit", "-q", "-m", "initial")
        commit = redrecord.git(self.root, "rev-parse", "HEAD").strip()
        self.feature_dir = state.create(self.root, "FEAT-007", "Discounts", "standard")
        state.update(self.feature_dir, lambda d: d.update(red={"commit": commit, "dirty": False, "source_hash": "", "at": "now"}))
        self.write("shop/discount.py", DISCOUNT)

    def write(self, rel: str, text: str) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")

    def mutate(self) -> tuple[int, str, str]:
        out, err, here = io.StringIO(), io.StringIO(), os.getcwd()
        os.chdir(self.root)
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = cli.main(["mutate", "FEAT-007"])
        finally:
            os.chdir(here)
        return code, out.getvalue(), err.getvalue()

    def test_weak_tests_fail_and_strong_tests_pass(self):
        self.write("tests/steps/test_discount_unit.py", WEAK_TESTS)
        code, out, err = self.mutate()
        print(f"mutmut, weak tests: {out.strip()}", file=sys.stderr)
        self.assertEqual(code, 1, out + err)
        self.assertIn("FAILED", out)
        self.write("tests/steps/test_discount_unit.py", STRONG_TESTS)
        code, out, err = self.mutate()
        print(f"mutmut, strong tests: {out.strip()}", file=sys.stderr)
        self.assertEqual(code, 0, out + err)
        self.assertIn("passed", out)
        self.assertEqual(mutation.problems(self.root, "FEAT-007"), [])


class WrapperIsShippedTest(unittest.TestCase):
    def test_the_adapter_copies_it_and_lists_it_as_a_support_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / ".bdd").mkdir()
            created, _ = adapter.apply(root, "python-pytest-bdd")
            self.assertIn("tests/tools/mutate_python.py", created)
            names = {p.relative_to(root).as_posix() for p in cfg.load(root).support_files}
            self.assertIn("tests/tools/mutate_python.py", names)

    def test_the_example_table_is_a_valid_configuration(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / ".bdd").mkdir()
            (root / ".bdd" / "config.toml").write_text('[[adapters]]\nname = "python-pytest-bdd"\n' + TABLE, encoding="utf-8")
            rules = cfg.load(root).mutation
            self.assertEqual((rules.threshold, rules.extensions), (70.0, (".py",)))


if __name__ == "__main__":
    unittest.main()
