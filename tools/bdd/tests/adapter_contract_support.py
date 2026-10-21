"""What the contract tests of the adapters that run a real toolchain (Go, .NET) have in common.

``ContractSteps`` is a mixin, not a test case, so that discovery does not collect it: a subclass adds
``unittest.TestCase``, names the adapter and says how to put the fixtures in place (``use_system``).
"""
import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

from bddlib import adapter, cli, state
from bddlib import config as cfg

ORDERS = """@FEAT-003
Feature: Orders

  @R-003.1
  Rule: Orders can be placed

    @EX-003.1.1
    Scenario: An order is placed
      When alice calls place order with:
        | item | qty |
        | tea  | 2   |
      Then the request succeeds

    @EX-003.1.2
    Scenario: Seeding needs a seam
      Given the following order exist:
        | id |
        | 1  |
      When alice calls place order
      Then the request succeeds

    @EX-003.1.3
    Scenario: A name nobody mapped
      When alice calls cancel order
      Then the request succeeds

    @EX-003.1.4
    Scenario: An assertion fails
      When add is called with:
        | a | b |
        | 1 | 2 |
      Then the result is:
        \"\"\"
        4
        \"\"\"

    @EX-003.1.5
    Scenario: A step nobody wrote
      When the moon is full
      Then the request succeeds
"""

UNICODE_TITLES = """@FEAT-004
Feature: Titles that are not plain ASCII

  @R-004.1
  Rule: A scenario keeps its title whatever the language

    @EX-004.1.1
    Scenario: Café: two numbers are added
      When add is called with:
        | a | b |
        | 2 | 3 |
      Then the result is:
        \"\"\"
        5
        \"\"\"

    @EX-004.1.2
    Scenario: 兩個數字相加
      When add is called with:
        | a | b |
        | 4 | 5 |
      Then the result is:
        \"\"\"
        9
        \"\"\"

    @EX-004.1.3
    Scenario: 負數會被拒絕 (a negative number is refused)
      When add is called with:
        | a  | b |
        | -1 | 3 |
      Then the call fails with negative input
"""

RED = {"EX-003.1.1": "expected-fail", "EX-003.1.2": "expected-fail", "EX-003.1.3": "test-defect",
       "EX-003.1.4": "expected-fail", "EX-003.1.5": "test-defect"}


@contextlib.contextmanager
def working_in(root: Path):
    here = os.getcwd()
    os.chdir(root)
    try:
        yield
    finally:
        os.chdir(here)


def run_bdd(root: Path, *argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with working_in(root), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(list(argv))
    return code, out.getvalue(), err.getvalue()


def config_of(path: Path) -> cfg.Config:
    """The configuration the adapter's block writes into a fresh project."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / ".bdd").mkdir()
        (root / ".bdd" / "config.toml").write_text(adapter.config_block(adapter.load(path)), encoding="utf-8")
        return cfg.load(root)


def assert_scan_tells_an_assertion_free_step(case: unittest.TestCase, name: str, relative: str, text: str) -> None:
    """A scaffold is scan- and lint-clean; a ``then`` step that asserts nothing is reported (S2)."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp).resolve()
        (root / ".bdd").mkdir()
        adapter.apply(root, name)
        state.create(root, "FEAT-000", "Sample", "standard")
        extra = root / relative
        extra.write_text(text, encoding="utf-8", newline="\n")
        code, out, _ = run_bdd(root, "scan", "FEAT-000")
        case.assertEqual(code, 1)
        case.assertIn("S2", out)
        extra.unlink()
        code, out, _ = run_bdd(root, "scan", "FEAT-000")
        case.assertEqual(code, 0, out)
        code, out, _ = run_bdd(root, "lint", "tests/features")
        case.assertEqual(code, 0, out)


class ContractSteps:
    """A fresh scaffold: the sample passes, every core step works against an in-memory system, red looks like red."""

    ADAPTER = ""
    root: Path

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.TemporaryDirectory()
        cls.root = Path(cls.dir.name).resolve()
        (cls.root / ".bdd").mkdir()
        adapter.apply(cls.root, cls.ADAPTER)
        for number, title in ((0, "Sample"), (2, "Core"), (3, "Orders"), (4, "Unicode")):
            state.create(cls.root, f"FEAT-{number:03d}", title, "standard")

    @classmethod
    def tearDownClass(cls):
        cls.dir.cleanup()

    def use_system(self, full: bool) -> None:
        raise NotImplementedError

    def bdd(self, *argv: str) -> tuple[int, str, str]:
        return run_bdd(self.root, *argv)

    def results(self, feature: str) -> dict[str, str]:
        code, out, err = self.bdd("classify", feature, "--json")
        self.assertIn(code, (0, 1), err)
        return {row["example"]: row["result"] for row in json.loads(out)["scenarios"]}

    def test_1_the_sample_feature_is_green_shuffled_and_isolated(self):
        self.use_system(full=False)
        code, out, err = self.bdd("run", "FEAT-000")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.bdd("classify", "FEAT-000", "--expect", "green")[0], 0)
        for flags in (("--shuffle", "--seed", "7"), ("--isolated",)):
            with self.subTest(flags=flags):
                code, out, err = self.bdd("run", "FEAT-000", *flags)
                self.assertEqual(code, 0, out + err)
                self.assertEqual(self.bdd("classify", "FEAT-000", "--expect", "green")[0], 0)

    def test_2_red_looks_like_red(self):
        self.use_system(full=False)
        code, out, err = self.bdd("run", "FEAT-003")
        self.assertIn(code, (0, 1), out + err)
        self.assertEqual(self.results("FEAT-003"), RED)
        self.assertEqual(self.bdd("classify", "FEAT-003", "--expect", "red")[0], 1)

    def test_3_every_core_step_works_and_an_n_plus_one_is_caught(self):
        self.use_system(full=True)
        code, out, err = self.bdd("run", "FEAT-002")
        self.assertIn(code, (0, 1), out + err)
        results = self.results("FEAT-002")
        self.assertEqual({k: v for k, v in results.items() if k != "EX-002.2.1"}, {f"EX-002.1.{n}": "pass" for n in range(1, 10)})
        self.assertEqual(results["EX-002.2.1"], "expected-fail")

    def test_5_scenario_titles_that_are_not_plain_ascii_still_map_to_their_scenarios(self):
        """The title is typed with an accent, in Chinese and mixed with ASCII: the report must still say which scenario ran,
        in the usual order, shuffled and one scenario per process (the scenario name goes to the runner as a filter)."""
        self.use_system(full=False)
        (self.root / "tests" / "features" / "unicode.feature").write_text(UNICODE_TITLES, encoding="utf-8", newline="\n")
        for flags in ((), ("--shuffle", "--seed", "3"), ("--isolated",)):
            with self.subTest(flags=flags):
                code, out, err = self.bdd("run", "FEAT-004", *flags)
                self.assertEqual(code, 0, out + err)
                self.assertEqual(self.results("FEAT-004"), {f"EX-004.1.{n}": "pass" for n in (1, 2, 3)})
                self.assertEqual(self.bdd("classify", "FEAT-004", "--expect", "green")[0], 0)

    def test_4_the_scaffold_passes_the_scan_and_the_lint(self):
        self.use_system(full=False)
        (self.root / "tests" / "features" / "orders.feature").unlink()
        code, out, _ = self.bdd("scan", "FEAT-000")
        self.assertEqual((code, out.strip()), (0, "FEAT-000: no findings"), out)
        self.assertEqual(self.bdd("lint", "tests/features")[0], 0)
