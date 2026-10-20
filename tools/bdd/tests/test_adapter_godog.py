"""The go-godog adapter: its package is complete and pinned, the scaffold is wired the way `bdd` expects, and (where Go is
installed and the network is allowed) a fresh scaffold really runs green, every core step works and red looks like red.

The structural tests run everywhere. The contract tests need Go 1.24 or newer, module downloads and
GREENLIGHT_GO_ADAPTER_TESTS=1; the CI job for the adapter sets it.
"""
import contextlib
import io
import json
import os
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from bddlib import adapter, cli, initcmd, state
from bddlib import config as cfg

REPO = Path(__file__).resolve().parents[3]
ADAPTER = REPO / "adapters" / "go-godog"
TEMPLATES = ADAPTER / "templates"
FIXTURES = Path(__file__).parent / "fixtures" / "go-godog"
RUN_CONTRACT = bool(shutil.which("go")) and os.environ.get("GREENLIGHT_GO_ADAPTER_TESTS") == "1"

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


def adapter_text(*parts: str) -> str:
    return (ADAPTER.joinpath(*parts)).read_text(encoding="utf-8")


class PackageTest(unittest.TestCase):
    def test_the_contract_files_exist(self):
        for name in adapter.REQUIRED + ("ci.md",):
            self.assertTrue((ADAPTER / name).exists(), name)
        self.assertEqual(adapter.load(ADAPTER)["name"], "go-godog")

    def test_the_config_block_is_valid_and_complete(self):
        text = adapter.config_block(adapter.load(ADAPTER))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".bdd").mkdir()
            (root / ".bdd" / "config.toml").write_text(text, encoding="utf-8")
            config = cfg.load(root)
        (scan,), (run,) = config.scans, config.runs
        self.assertEqual(run.adapter, "go-godog")
        self.assertIn("-mod=readonly", run.by_tag)
        self.assertIn("-bdd.tag={tag}", run.by_tag)
        self.assertEqual((run.report, run.shuffle), ("-bdd.out {out}", "-bdd.seed {seed}"))
        self.assertIn("-bdd.scenario", run.isolated)
        self.assertTrue({"GOFLAGS", "GOENV", "GOWORK", "CGO_"} <= set(run.scrub_env))
        self.assertTrue(scan.assert_patterns and scan.sleep_patterns and scan.stub_patterns)

    def test_the_test_module_is_pinned_and_read_only(self):
        wanted = adapter.load(ADAPTER)["requires"]["packages"]
        self.assertEqual(wanted, ["github.com/cucumber/godog v0.16.0"])
        module, sums = (TEMPLATES / "tests" / "go.mod").read_text(encoding="utf-8"), (TEMPLATES / "tests" / "go.sum").read_text(encoding="utf-8")
        self.assertIn("github.com/cucumber/godog v0.16.0", module)
        self.assertNotIn("replace", module, "a replace directive would let the module graph point at local code")
        self.assertIn("github.com/cucumber/godog v0.16.0 h1:", sums)
        self.assertTrue(all(re.fullmatch(r"\S+ \S+ h1:\S+=", line) for line in sums.splitlines()), "go.sum holds only module hashes")

    def test_every_support_file_is_shipped_and_every_step_expression_is_a_regular_expression(self):
        shipped = {p.relative_to(TEMPLATES).as_posix() for p in adapter.template_files(ADAPTER)}
        for name in adapter.load(ADAPTER)["paths"]["support"]:
            self.assertIn(name, shipped)
        source = (TEMPLATES / "tests" / "steps" / "core_steps.go").read_text(encoding="utf-8")
        expressions = re.findall(r"sc\.(?:Given|When|Then)\(`([^`]+)`", source)
        self.assertGreaterEqual(len(expressions), 22)
        for expression in expressions:
            re.compile(expression)                                      # Go's syntax is a subset of what Python reads here
            self.assertTrue(expression.startswith("^") and expression.endswith("$"), expression)

    def test_a_step_that_asserts_is_not_flagged_and_one_that_does_not_is(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / ".bdd").mkdir()
            adapter.apply(root, "go-godog")
            state.create(root, "FEAT-000", "Sample", "standard")
            steps = root / "tests" / "steps" / "extra.go"
            steps.write_text('package steps\n\nfunc extra(sc *godog.ScenarioContext) {\n\tsc.Then(`^it is fine$`, func() error { return nil })\n}\n',
                             encoding="utf-8", newline="\n")
            here = os.getcwd()
            os.chdir(root)
            try:
                with contextlib.redirect_stdout(io.StringIO()) as out:
                    self.assertEqual(cli.main(["scan", "FEAT-000"]), 1)
                self.assertIn("S2", out.getvalue())
                steps.unlink()
                with contextlib.redirect_stdout(io.StringIO()) as out:
                    self.assertEqual(cli.main(["scan", "FEAT-000"]), 0, out.getvalue())
                with contextlib.redirect_stdout(io.StringIO()) as out:
                    self.assertEqual(cli.main(["lint", "tests/features"]), 0, out.getvalue())
            finally:
                os.chdir(here)

    def test_init_suggests_it_for_a_go_module_and_for_nothing_else(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / "go.mod").write_text("module example.com/app\n\ngo 1.24\n", encoding="utf-8")
            self.assertEqual([name for name, _ in initcmd.detect(root)], ["go-godog"])
            (root / "go.mod").unlink()
            self.assertEqual(initcmd.detect(root), [])

    def test_apply_registers_the_plumbing_as_bound_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / ".bdd").mkdir()
            adapter.apply(root, "go-godog")
            bound = {p.relative_to(root).as_posix() for p in cfg.load(root).support_files}
            self.assertEqual(bound, {"tests/bdd_test.go", "tests/go.mod", "tests/go.sum"})

    def test_the_fixture_features_name_only_core_instructions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / ".bdd").mkdir()
            adapter.apply(root, "go-godog")
            shutil.copyfile(FIXTURES / "full.feature", root / "tests" / "features" / "full.feature")
            (root / "tests" / "features" / "orders.feature").write_text(ORDERS, encoding="utf-8", newline="\n")
            here = os.getcwd()
            os.chdir(root)
            try:
                with contextlib.redirect_stdout(io.StringIO()) as out:
                    code = cli.main(["lint", "tests/features"])
                self.assertEqual(code, 1, "the moon step is on purpose not in the vocabulary")
                self.assertEqual(out.getvalue().count("L002"), 1, out.getvalue())
            finally:
                os.chdir(here)


@unittest.skipUnless(RUN_CONTRACT, "needs Go, module downloads and GREENLIGHT_GO_ADAPTER_TESTS=1")
class ContractTest(unittest.TestCase):
    """A fresh scaffold: the sample passes, every core step works against an in-memory system, red looks like red."""

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.TemporaryDirectory()
        cls.root = Path(cls.dir.name).resolve()
        (cls.root / ".bdd").mkdir()
        adapter.apply(cls.root, "go-godog")
        for number, title in ((0, "Sample"), (2, "Core"), (3, "Orders")):
            state.create(cls.root, f"FEAT-{number:03d}", title, "standard")

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

    def results(self, feature: str) -> dict[str, str]:
        code, out, err = self.bdd("classify", feature, "--json")
        self.assertIn(code, (0, 1), err)
        return {row["example"]: row["result"] for row in json.loads(out)["scenarios"]}

    def use_system(self, full: bool) -> None:
        drivers, features = self.root / "tests" / "drivers", self.root / "tests" / "features"
        if full:
            shutil.copyfile(FIXTURES / "system.go.fixture", drivers / "system.go")
            shutil.copyfile(FIXTURES / "operations.go.fixture", drivers / "operations.go")
            shutil.copyfile(FIXTURES / "full.feature", features / "full.feature")
            (features / "orders.feature").unlink(missing_ok=True)
        else:
            for name in ("system.go", "operations.go"):
                shutil.copyfile(TEMPLATES / "tests" / "drivers" / name, drivers / name)
            (features / "full.feature").unlink(missing_ok=True)
            operations = drivers / "operations.go"
            operations.write_text(operations.read_text(encoding="utf-8").replace(
                '\t// "place order": {"POST", "/orders"},', '\t"place order": {"POST", "/orders"},'), encoding="utf-8", newline="\n")
            (features / "orders.feature").write_text(ORDERS, encoding="utf-8", newline="\n")

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
        self.assertEqual(self.results("FEAT-003"), {"EX-003.1.1": "expected-fail", "EX-003.1.2": "expected-fail",
                                                     "EX-003.1.3": "test-defect", "EX-003.1.4": "expected-fail",
                                                     "EX-003.1.5": "test-defect"})
        self.assertEqual(self.bdd("classify", "FEAT-003", "--expect", "red")[0], 1)

    def test_3_every_core_step_works_and_an_n_plus_one_is_caught(self):
        self.use_system(full=True)
        code, out, err = self.bdd("run", "FEAT-002")
        self.assertIn(code, (0, 1), out + err)
        results = self.results("FEAT-002")
        self.assertEqual({k: v for k, v in results.items() if k != "EX-002.2.1"}, {f"EX-002.1.{n}": "pass" for n in range(1, 10)})
        self.assertEqual(results["EX-002.2.1"], "expected-fail")
        _, out, _ = self.bdd("classify", "FEAT-002", "--json")
        detail = next(row["detail"] for row in json.loads(out)["scenarios"] if row["example"] == "EX-002.2.1")
        self.assertIn("ran 4 queries, more than the 2 allowed", detail)

    def test_4_the_scaffold_passes_the_scan_and_the_lint(self):
        self.use_system(full=False)
        (self.root / "tests" / "features" / "orders.feature").unlink()
        code, out, _ = self.bdd("scan", "FEAT-000")
        self.assertEqual((code, out.strip()), (0, "FEAT-000: no findings"), out)
        self.assertEqual(self.bdd("lint", "tests/features")[0], 0)


if __name__ == "__main__":
    unittest.main()
