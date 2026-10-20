"""The dotnet-reqnroll adapter: its package is complete and pinned, the scaffold is wired the way `bdd` expects, the
Python wrapper builds a safe test filter, and (where the .NET SDK is installed and the network is allowed) a fresh
scaffold really runs green, every core step works and red looks like red.

The structural tests run everywhere. The contract tests need the .NET 10 SDK, package downloads and
GREENLIGHT_DOTNET_ADAPTER_TESTS=1; the CI job for the adapter sets it.
"""
import contextlib
import importlib.util
import io
import json
import os
import re
import shutil
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from bddlib import adapter, cli, state
from bddlib import config as cfg

REPO = Path(__file__).resolve().parents[3]
ADAPTER = REPO / "adapters" / "dotnet-reqnroll"
TEMPLATES = ADAPTER / "templates"
FIXTURES = Path(__file__).parent / "fixtures" / "dotnet-reqnroll"
RUN_CONTRACT = bool(shutil.which("dotnet")) and os.environ.get("GREENLIGHT_DOTNET_ADAPTER_TESTS") == "1"

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


def load_wrapper():
    spec = importlib.util.spec_from_file_location("run_dotnet", TEMPLATES / "tests" / "run_dotnet.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PackageTest(unittest.TestCase):
    def test_the_contract_files_exist(self):
        for name in adapter.REQUIRED + ("ci.md",):
            self.assertTrue((ADAPTER / name).exists(), name)
        self.assertEqual(adapter.load(ADAPTER)["name"], "dotnet-reqnroll")

    def test_the_config_block_is_valid_and_complete(self):
        text = adapter.config_block(adapter.load(ADAPTER))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".bdd").mkdir()
            (root / ".bdd" / "config.toml").write_text(text, encoding="utf-8")
            config = cfg.load(root)
        (scan,), (run,) = config.scans, config.runs
        self.assertEqual(run.adapter, "dotnet-reqnroll")
        self.assertIn("tests/run_dotnet.py", run.by_tag)
        self.assertEqual((run.report, run.shuffle), ("--out {out}", "--seed {seed}"))
        self.assertIn("--scenario", run.isolated)
        self.assertTrue({"DOTNET_STARTUP_HOOKS", "COMPlus_", "MSBUILD"} <= set(run.scrub_env))
        self.assertTrue(scan.assert_patterns and scan.sleep_patterns and scan.stub_patterns)

    def test_the_packages_are_pinned_and_locked(self):
        project = (TEMPLATES / "tests" / "GreenlightTests.csproj").read_text(encoding="utf-8")
        locked = json.loads((TEMPLATES / "tests" / "packages.lock.json").read_text(encoding="utf-8"))
        direct = {name: info["resolved"] for framework in locked["dependencies"].values() for name, info in framework.items()
                  if info["type"] == "Direct"}
        references = dict(re.findall(r'<PackageReference Include="([^"]+)" Version="([^"]+)"', project))
        self.assertEqual(references, direct, "every referenced package is pinned to an exact version in the lock file")
        for requirement in adapter.load(ADAPTER)["requires"]["packages"]:
            name, _, version = requirement.partition(" ")
            self.assertEqual(references.get(name), version)
        self.assertIn("<RestorePackagesWithLockFile>true</RestorePackagesWithLockFile>", project)
        self.assertIn("CS0618", project, "use of an obsolete API is an error")
        self.assertTrue(all("contentHash" in info for framework in locked["dependencies"].values() for info in framework.values()))
        sources = (TEMPLATES / "tests" / "nuget.config").read_text(encoding="utf-8")
        self.assertIn("<clear />", sources)
        self.assertEqual(sources.count("<add "), 1)

    def test_every_support_file_is_shipped_and_every_binding_has_its_expression_anchored(self):
        shipped = {p.relative_to(TEMPLATES).as_posix() for p in adapter.template_files(ADAPTER)}
        for name in adapter.load(ADAPTER)["paths"]["support"]:
            self.assertIn(name, shipped)
        source = (TEMPLATES / "tests" / "steps" / "CoreSteps.cs").read_text(encoding="utf-8")
        expressions = re.findall(r'\[(?:Given|When|Then)\(@"([^"]+)"\)\]', source)
        self.assertGreaterEqual(len(expressions), 22)
        for expression in expressions:
            re.compile(expression)
            self.assertTrue(expression.startswith("^") and expression.endswith("$"), expression)

    def test_the_wrapper_builds_a_filter_where_a_name_is_only_a_value(self):
        wrapper = load_wrapper()
        self.assertEqual(wrapper.build_filter("FEAT-007", None), "Category=FEAT-007")
        self.assertEqual(wrapper.build_filter("FEAT-007", "Order of 999"), "Category=FEAT-007&DisplayName=Order of 999")
        hostile = wrapper.build_filter("FEAT-007", "a|(b)&c=d!e~f\\g")
        self.assertEqual(hostile, "Category=FEAT-007&DisplayName=a\\|\\(b\\)\\&c\\=d\\!e\\~f\\\\g")
        command = wrapper.build_command("dotnet", "FEAT-007", Path("out.xml"), "Order of 999")
        self.assertIn("-p:RestoreLockedMode=true", command)
        self.assertEqual(command[command.index("--logger") + 1], "junit;LogFilePath=out.xml")
        with self.assertRaises(SystemExit):
            with contextlib.redirect_stderr(io.StringIO()):
                wrapper.parse(["--tag", "FEAT-007; rm -rf /", "--out", "x.xml"])

    def test_the_wrapper_says_when_dotnet_is_missing(self):
        wrapper = load_wrapper()
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(wrapper.shutil, "which", return_value=None):
            with contextlib.redirect_stderr(io.StringIO()) as err:
                code = wrapper.main(["--tag", "FEAT-007", "--out", str(Path(tmp) / "report.xml")])
        self.assertEqual(code, 127)
        self.assertIn("dotnet is not on PATH", err.getvalue())

    def test_the_wrapper_removes_a_stale_report_and_hands_over_the_seed(self):
        wrapper = load_wrapper()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "report.xml"
            out.write_text("stale", encoding="utf-8")
            started = {}

            def fake_run(command, env, check):
                started.update(command=command, env=env, stale_report_gone=not out.exists())
                return types.SimpleNamespace(returncode=3)

            with mock.patch.object(wrapper.shutil, "which", return_value="dotnet"), mock.patch.object(wrapper.subprocess, "run", fake_run),                     mock.patch.dict(os.environ, {"GREENLIGHT_BDD_SEED": "stale"}):
                code = wrapper.main(["--tag", "FEAT-007", "--out", str(out), "--seed", "42"])
        self.assertEqual(code, 3, "the exit status of dotnet test is passed on")
        self.assertTrue(started["stale_report_gone"])
        self.assertEqual(started["env"]["GREENLIGHT_BDD_SEED"], "42")

    def test_a_step_that_asserts_is_not_flagged_and_one_that_does_not_is(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / ".bdd").mkdir()
            adapter.apply(root, "dotnet-reqnroll")
            state.create(root, "FEAT-000", "Sample", "standard")
            extra = root / "tests" / "steps" / "Extra.cs"
            extra.write_text("[Binding]\npublic class Extra\n{\n    [Then(@\"^it is fine$\")]\n    public void Fine() { }\n}\n", encoding="utf-8", newline="\n")
            here = os.getcwd()
            os.chdir(root)
            try:
                with contextlib.redirect_stdout(io.StringIO()) as out:
                    self.assertEqual(cli.main(["scan", "FEAT-000"]), 1)
                self.assertIn("S2", out.getvalue())
                extra.unlink()
                with contextlib.redirect_stdout(io.StringIO()) as out:
                    self.assertEqual(cli.main(["scan", "FEAT-000"]), 0, out.getvalue())
                with contextlib.redirect_stdout(io.StringIO()) as out:
                    self.assertEqual(cli.main(["lint", "tests/features"]), 0, out.getvalue())
            finally:
                os.chdir(here)

    def test_apply_registers_the_plumbing_as_bound_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / ".bdd").mkdir()
            adapter.apply(root, "dotnet-reqnroll")
            bound = {p.relative_to(root).as_posix() for p in cfg.load(root).support_files}
            self.assertEqual(bound, {"tests/GreenlightTests.csproj", "tests/packages.lock.json", "tests/nuget.config",
                                     "tests/.editorconfig", "tests/run_dotnet.py"})


@unittest.skipUnless(RUN_CONTRACT, "needs the .NET SDK, package downloads and GREENLIGHT_DOTNET_ADAPTER_TESTS=1")
class ContractTest(unittest.TestCase):
    """A fresh scaffold: the sample passes, every core step works against an in-memory system, red looks like red."""

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.TemporaryDirectory()
        cls.root = Path(cls.dir.name).resolve()
        (cls.root / ".bdd").mkdir()
        adapter.apply(cls.root, "dotnet-reqnroll")
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
            shutil.copyfile(FIXTURES / "Wiring.cs.fixture", drivers / "Wiring.cs")
            shutil.copyfile(FIXTURES / "FullSystem.cs.fixture", drivers / "FullSystem.cs")
            shutil.copyfile(FIXTURES / "Operations.cs.fixture", drivers / "Operations.cs")
            shutil.copyfile(FIXTURES / "full.feature", features / "full.feature")
            (features / "orders.feature").unlink(missing_ok=True)
        else:
            for name in ("Wiring.cs", "Operations.cs"):
                shutil.copyfile(TEMPLATES / "tests" / "drivers" / name, drivers / name)
            (drivers / "FullSystem.cs").unlink(missing_ok=True)
            (features / "full.feature").unlink(missing_ok=True)
            operations = drivers / "Operations.cs"
            operations.write_text(operations.read_text(encoding="utf-8").replace(
                '        // ["place order"] = new("POST", "/orders"),', '        ["place order"] = new("POST", "/orders"),'), encoding="utf-8", newline="\n")
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

    def test_4_the_scaffold_passes_the_scan_and_the_lint(self):
        self.use_system(full=False)
        (self.root / "tests" / "features" / "orders.feature").unlink()
        code, out, _ = self.bdd("scan", "FEAT-000")
        self.assertEqual((code, out.strip()), (0, "FEAT-000: no findings"), out)
        self.assertEqual(self.bdd("lint", "tests/features")[0], 0)


if __name__ == "__main__":
    unittest.main()
