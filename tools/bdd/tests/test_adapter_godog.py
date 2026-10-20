"""The go-godog adapter: its package is complete and pinned, the scaffold is wired the way `bdd` expects, and (where Go is
installed and the network is allowed) a fresh scaffold really runs green, every core step works and red looks like red.

The structural tests run everywhere. The contract tests need Go 1.24 or newer, module downloads and
GREENLIGHT_GO_ADAPTER_TESTS=1; the CI job for the adapter sets it.
"""
import os
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from bddlib import adapter, initcmd, state
from bddlib import config as cfg

from tests import adapter_contract_support as support

REPO = Path(__file__).resolve().parents[3]
ADAPTER = REPO / "adapters" / "go-godog"
TEMPLATES = ADAPTER / "templates"
FIXTURES = Path(__file__).parent / "fixtures" / "go-godog"
RUN_CONTRACT = bool(shutil.which("go")) and os.environ.get("GREENLIGHT_GO_ADAPTER_TESTS") == "1"


class PackageTest(unittest.TestCase):
    def test_the_contract_files_exist(self):
        for name in adapter.REQUIRED + ("ci.md",):
            self.assertTrue((ADAPTER / name).exists(), name)
        self.assertEqual(adapter.load(ADAPTER)["name"], "go-godog")

    def test_the_config_block_is_valid_and_complete(self):
        config = support.config_of(ADAPTER)
        (scan,), (run,) = config.scans, config.runs
        self.assertEqual(run.adapter, "go-godog")
        self.assertIn("-mod=readonly", run.by_tag)
        self.assertIn("-bdd.tag={tag}", run.by_tag)
        self.assertEqual((run.report, run.shuffle), ("-bdd.out {out}", "-bdd.seed {seed}"))
        self.assertIn("-bdd.scenario", run.isolated)
        self.assertLessEqual({"GOFLAGS", "GOENV", "GOWORK", "CGO_"}, set(run.scrub_env))
        self.assertTrue(scan.assert_patterns and scan.sleep_patterns and scan.stub_patterns)

    def test_the_test_module_is_pinned_and_read_only(self):
        wanted = adapter.load(ADAPTER)["requires"]["packages"]
        self.assertEqual(wanted, ["github.com/cucumber/godog v0.16.0"])
        module = (TEMPLATES / "tests" / "go.mod").read_text(encoding="utf-8")
        sums = (TEMPLATES / "tests" / "go.sum").read_text(encoding="utf-8")
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
        self.assertLessEqual(22, len(expressions))
        for expression in expressions:
            re.compile(expression)                                      # Go's syntax is a subset of what Python reads here
            self.assertTrue(expression.startswith("^") and expression.endswith("$"), expression)

    def test_a_step_that_asserts_is_not_flagged_and_one_that_does_not_is(self):
        text = 'package steps\n\nfunc extra(sc *godog.ScenarioContext) {\n\tsc.Then(`^it is fine$`, func() error { return nil })\n}\n'
        support.assert_scan_tells_an_assertion_free_step(self, "go-godog", "tests/steps/extra.go", text)

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
            state.create(root, "FEAT-000", "Sample", "standard")
            shutil.copyfile(FIXTURES / "full.feature", root / "tests" / "features" / "full.feature")
            (root / "tests" / "features" / "orders.feature").write_text(support.ORDERS, encoding="utf-8", newline="\n")
            code, out, _ = support.run_bdd(root, "lint", "tests/features")
            self.assertEqual(code, 1, "the moon step is on purpose not in the vocabulary")
            self.assertEqual(out.count("L002"), 1, out)


@unittest.skipUnless(RUN_CONTRACT, "needs Go, module downloads and GREENLIGHT_GO_ADAPTER_TESTS=1")
class ContractTest(support.ContractSteps, unittest.TestCase):
    ADAPTER = "go-godog"

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
            (features / "orders.feature").write_text(support.ORDERS, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    unittest.main()
