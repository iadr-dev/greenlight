"""The generic-junit adapter: its package is complete, the scaffold runs green with the standard library alone, the
wrapper merges reports, and the classification defaults tell a missing seam from a broken test."""
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from bddlib import adapter, cards, classify, cli, initcmd, junit, state
from bddlib import config as cfg
from bddlib.errors import UsageError

REPO = Path(__file__).resolve().parents[3]
ADAPTER = REPO / "adapters" / "generic-junit"
TEMPLATES = ADAPTER / "templates"
RUNNER_CARDS = {"junit-gradle", "junit-maven", "pytest", "jest", "go-test", "dotnet-test", "godog", "cucumber-js", "cucumber-jvm",
                "behave", "reqnroll", "flutter-test"}

ORDERS = """@FEAT-001
Feature: Orders

  @R-001.1
  Rule: Orders can be placed

    @EX-001.1.1
    Scenario: An order is placed
      When add is called with:
        | a | b |
        | 1 | 2 |
      Then the result is:
        \"\"\"
        3
        \"\"\"

    @EX-001.1.2
    Scenario: An order is cancelled
      When add is called with:
        | a | b |
        | 1 | 2 |
      Then the result is:
        \"\"\"
        3
        \"\"\"
"""

RED_TESTS = '''
import unittest


class Orders(unittest.TestCase):
    tags = ("FEAT-001",)

    def test_an_order_is_placed(self):
        raise AssertionError("BDD_EXPECTED_MISSING: order service")

    def test_an_order_is_cancelled(self):
        self.assertEqual(1 + 1, 3)
'''


class PackageTest(unittest.TestCase):
    def test_the_contract_files_exist(self):
        for name in adapter.REQUIRED + ("ci.md",):
            self.assertTrue((ADAPTER / name).exists(), name)
        self.assertEqual(adapter.load(ADAPTER)["name"], "generic-junit")

    def test_the_config_block_is_valid_and_complete(self):
        text = adapter.config_block(adapter.load(ADAPTER))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".bdd").mkdir()
            (root / ".bdd" / "config.toml").write_text(text, encoding="utf-8")
            config = cfg.load(root)
        (scan,), (run,) = config.scans, config.runs
        self.assertEqual(run.adapter, "generic-junit")
        self.assertIn("{tag}", run.by_tag)
        self.assertIn("{out}", run.report)
        self.assertIn("BDD_EXPECTED_MISSING", "".join(run.expected_fail))
        self.assertTrue(scan.assert_patterns and scan.sleep_patterns)
        self.assertEqual({p.name for p in config.support_files}, {"run_tests.py", "run_junit.py"})

    def test_it_is_never_suggested_by_detection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "pyproject.toml").write_text("[project]\nname = 'x'\n[tool.pytest]\n", encoding="utf-8")
            self.assertNotIn("generic-junit", [name for name, _ in initcmd.detect(root)])

    def test_every_runner_card_is_indexed_and_has_its_sections(self):
        listed = {c["id"] for c in json.loads((REPO / "cards" / "index.json").read_text(encoding="utf-8"))["cards"]
                  if c["kind"] == "runner"}
        self.assertEqual(listed, RUNNER_CARDS)
        self.assertEqual(cards.run(["build", "--check"]), 0)


class ApplyTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name).resolve()
        (self.root / ".bdd").mkdir()

    def test_apply_copies_registers_and_never_overwrites(self):
        (self.root / "tests").mkdir()
        (self.root / "tests" / "run_tests.py").write_text("# mine\n", encoding="utf-8")
        created, kept = adapter.apply(self.root, "generic-junit")
        self.assertEqual(kept, ["tests/run_tests.py"])
        self.assertIn("tests/run_junit.py", created)
        self.assertEqual((self.root / "tests" / "run_tests.py").read_text(encoding="utf-8"), "# mine\n")
        self.assertEqual(cfg.load(self.root).runs[0].adapter, "generic-junit")
        with self.assertRaises(UsageError):
            adapter.apply(self.root, "generic-junit")


class ScaffoldCase(unittest.TestCase):
    """A fresh scaffold in a temporary project; nothing but the standard library is needed to run it."""

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.TemporaryDirectory()
        cls.root = Path(cls.dir.name).resolve()
        (cls.root / ".bdd").mkdir()
        adapter.apply(cls.root, "generic-junit")
        state.create(cls.root, "FEAT-000", "Sample", "standard")

    @classmethod
    def tearDownClass(cls):
        cls.dir.cleanup()

    def bdd(self, *argv: str) -> tuple[int, str, str]:
        out, err, here = io.StringIO(), io.StringIO(), os.getcwd()
        os.chdir(self.root)
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = cli.main(list(argv))
        finally:
            os.chdir(here)
        return code, out.getvalue(), err.getvalue()


class ScaffoldTest(ScaffoldCase):
    def test_1_the_sample_feature_is_green(self):
        code, out, err = self.bdd("run", "FEAT-000")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.bdd("classify", "FEAT-000", "--expect", "green")[0], 0)

    def test_2_shuffled_and_isolated_runs_are_green_too(self):
        for flags in (("--shuffle", "--seed", "7"), ("--isolated",)):
            with self.subTest(flags=flags):
                code, out, err = self.bdd("run", "FEAT-000", *flags)
                self.assertEqual(code, 0, out + err)
                self.assertEqual(self.bdd("classify", "FEAT-000", "--expect", "green")[0], 0)

    def test_3_the_scaffold_passes_the_scan_and_the_lint(self):
        self.assertEqual(self.bdd("scan", "FEAT-000")[:2], (0, "FEAT-000: no findings\n"))
        code, out, _ = self.bdd("lint", "tests/features")
        self.assertEqual(code, 0, out)

    def test_4_red_looks_like_red(self):
        state.create(self.root, "FEAT-001", "Orders", "standard")
        (self.root / "tests/features/orders.feature").write_text(ORDERS, encoding="utf-8", newline="\n")
        (self.root / "tests/steps/orders_tests.py").write_text(RED_TESTS, encoding="utf-8", newline="\n")
        self.assertEqual(self.bdd("run", "FEAT-001")[0], 0)                 # bdd ran it; the tests failing is the point
        code, out, _ = self.bdd("classify", "FEAT-001", "--json")
        results = {row["example"]: row["result"] for row in json.loads(out)["scenarios"]}
        self.assertEqual(results, {"EX-001.1.1": "expected-fail", "EX-001.1.2": "expected-fail"})
        self.assertEqual(self.bdd("classify", "FEAT-001", "--expect", "red")[0], 0)

    def test_5_a_module_that_cannot_be_loaded_is_not_silent(self):
        state.create(self.root, "FEAT-002", "Broken", "standard")
        (self.root / "tests/features/broken.feature").write_text(
            ORDERS.replace("FEAT-001", "FEAT-002").replace("R-001.1", "R-002.1").replace("EX-001.1", "EX-002.1"),
            encoding="utf-8", newline="\n")
        (self.root / "tests/steps/broken_tests.py").write_text("import module_that_is_not_there\n", encoding="utf-8")
        self.addCleanup((self.root / "tests/steps/broken_tests.py").unlink)
        self.bdd("run", "FEAT-002")
        record = json.loads((self.root / ".bdd/.runs/FEAT-002/latest.json").read_text(encoding="utf-8"))
        loads = [c for c in record["cases"] if c["classname"] == "load"]
        self.assertEqual(len(loads), 1)
        self.assertIn("ModuleNotFoundError", loads[0]["text"])
        code, _, _ = self.bdd("classify", "FEAT-002", "--expect", "red")
        self.assertEqual(code, 1)                                           # the scenarios did not run: no red


class SmokeTest(unittest.TestCase):
    def test_init_smoke_proves_the_sample_and_leaves_nothing_behind(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, here = Path(tmp).resolve(), os.getcwd()
            (root / ".bdd").mkdir()
            adapter.apply(root, "generic-junit")
            out = io.StringIO()
            os.chdir(root)
            try:
                with contextlib.redirect_stdout(out):
                    code = cli.main(["init", "--smoke"])
            finally:
                os.chdir(here)
            self.assertEqual(code, 0, out.getvalue())
            self.assertIn("runs green", out.getvalue())
            self.assertFalse((root / ".bdd" / "features").exists() and any((root / ".bdd" / "features").iterdir()))


class WrapperTest(unittest.TestCase):
    """tests/run_junit.py: stale reports go, several files become one, the command's status survives."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name).resolve()
        (self.root / "reports").mkdir()
        self.writer = self.root / "writer.py"
        self.writer.write_text(
            "import sys\nfrom pathlib import Path\n"
            "for name in sys.argv[1:]:\n"
            "    Path('reports', name + '.xml').write_text("
            "'<testsuite><testcase classname=\"c\" name=\"' + name + '\"/></testsuite>', encoding='utf-8')\n"
            "sys.exit(1 if 'fail' in sys.argv else 0)\n", encoding="utf-8")

    def wrap(self, *extra: str, reports: str = "reports/*.xml") -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(TEMPLATES / "tests/run_junit.py"), "--reports", reports,
                               "--out", str(self.root / "merged.xml"), *extra], cwd=self.root, capture_output=True, text=True)

    def command(self, *words: str) -> str:
        return f'"{sys.executable}" writer.py ' + " ".join(words)

    def test_several_files_become_one_and_stale_ones_are_not_taken(self):
        (self.root / "reports" / "stale.xml").write_text('<testsuite><testcase name="stale"/></testsuite>', encoding="utf-8")
        done = self.wrap("--command", self.command("one", "two"))
        self.assertEqual(done.returncode, 0, done.stderr)
        names = [c.name for c in junit.parse_file(self.root / "merged.xml")]
        self.assertEqual(sorted(names), ["one", "two"])

    def test_the_commands_status_survives_and_the_report_is_still_written(self):
        done = self.wrap("--command", self.command("one", "fail"))
        self.assertEqual(done.returncode, 1)
        self.assertEqual(len(junit.parse_file(self.root / "merged.xml")), 2)

    def test_added_words_reach_the_command(self):
        done = self.wrap("--command", self.command("one"), "--add=extra")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(sorted(c.name for c in junit.parse_file(self.root / "merged.xml")), ["extra", "one"])

    def test_words_that_are_not_added_with_add_are_refused_and_the_message_says_how(self):
        """The sample runner's `--seed 5` or `--only name` is not a word of the test command: say so, run nothing."""
        done = self.wrap("--command", self.command("one"), "--seed", "5")
        self.assertEqual(done.returncode, 2)
        self.assertIn("unrecognized arguments: --seed 5", done.stderr)
        self.assertIn("--add=WORD", done.stderr)
        self.assertFalse((self.root / "merged.xml").exists())
        self.assertFalse((self.root / "reports" / "one.xml").exists())          # the command never started

    def test_no_report_is_an_error_not_a_silent_pass(self):
        done = self.wrap("--command", self.command(), reports="reports/*.xml")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("wrote no file", done.stderr)
        self.assertFalse((self.root / "merged.xml").exists())

    def test_patterns_outside_the_project_and_unknown_commands_are_refused(self):
        self.assertEqual(self.wrap("--command", self.command("one"), reports="../*.xml").returncode, 2)
        self.assertEqual(self.wrap("--command", "no-such-runner-xyz").returncode, 127)

    def test_a_program_planted_in_the_project_is_not_started(self):
        for name in ("planted-tool.bat", "planted-tool.cmd", "planted-tool"):
            (self.root / name).write_text("@echo off\n", encoding="utf-8")
        done = self.wrap("--command", "planted-tool")
        self.assertEqual(done.returncode, 127)
        self.assertIn("not on PATH", done.stderr)

    def test_a_report_with_a_doctype_is_refused(self):
        evil = self.root / "evil.py"
        evil.write_text("from pathlib import Path\nPath('reports/x.xml').write_text('<!DOCTYPE a [<!ENTITY b \"c\">]><testsuite/>')\n",
                        encoding="utf-8")
        done = self.wrap("--command", f'"{sys.executable}" evil.py')
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("DOCTYPE", done.stderr)


class ClassifyDefaultsTest(unittest.TestCase):
    def setUp(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".bdd").mkdir()
            (root / ".bdd" / "config.toml").write_text(adapter.config_block(adapter.load(ADAPTER)), encoding="utf-8")
            self.rules = list(cfg.load(root).runs)

    def kind(self, text: str, outcome: str = junit.FAILED) -> str:
        return classify.classify_case(junit.Case("t", "c", outcome, text), self.rules)

    def test_unbuilt_seams_and_failed_assertions_are_expected(self):
        for text in ("BDD_EXPECTED_MISSING: order service", "AssertionError: 4 != 5",
                     "org.opentest4j.AssertionFailedError: expected: <5> but was: <4>", "status 404"):
            with self.subTest(text=text):
                self.assertEqual(self.kind(text), classify.EXPECTED)

    def test_broken_builds_and_loads_are_defects_even_when_an_assertion_is_mentioned(self):
        for text in ("ModuleNotFoundError: No module named 'x'", "error CS0103: The name 'x' does not exist",
                     "./x_test.go:3:2: undefined: Foo", "java: cannot find symbol", "Undefined step: When I fly",
                     "ImportError while checking AssertionError"):
            with self.subTest(text=text):
                self.assertEqual(self.kind(text), classify.DEFECT)

    def test_anything_else_blocks_as_unknown(self):
        self.assertEqual(self.kind("the moon was in the wrong phase"), classify.UNKNOWN)


if __name__ == "__main__":
    unittest.main()
