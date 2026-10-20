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

from bddlib import adapter, initcmd
from bddlib import config as cfg

from tests import adapter_contract_support as support

REPO = Path(__file__).resolve().parents[3]
ADAPTER = REPO / "adapters" / "dotnet-reqnroll"
TEMPLATES = ADAPTER / "templates"
FIXTURES = Path(__file__).parent / "fixtures" / "dotnet-reqnroll"
RUN_CONTRACT = bool(shutil.which("dotnet")) and os.environ.get("GREENLIGHT_DOTNET_ADAPTER_TESTS") == "1"


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
        config = support.config_of(ADAPTER)
        (scan,), (run,) = config.scans, config.runs
        self.assertEqual(run.adapter, "dotnet-reqnroll")
        self.assertIn("tests/run_dotnet.py", run.by_tag)
        self.assertEqual((run.report, run.shuffle), ("--out {out}", "--seed {seed}"))
        self.assertIn("--scenario", run.isolated)
        self.assertLessEqual({"DOTNET_STARTUP_HOOKS", "COMPlus_", "MSBUILD"}, set(run.scrub_env))
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
        self.assertLessEqual(22, len(expressions))
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

    def test_the_wrapper_refuses_a_tag_that_is_not_a_feature_tag(self):
        wrapper = load_wrapper()
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
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

            with mock.patch.object(wrapper.shutil, "which", return_value="dotnet"), mock.patch.object(wrapper.subprocess, "run", fake_run), \
                    mock.patch.dict(os.environ, {"GREENLIGHT_BDD_SEED": "stale"}):
                code = wrapper.main(["--tag", "FEAT-007", "--out", str(out), "--seed", "42"])
        self.assertEqual(code, 3, "the exit status of dotnet test is passed on")
        self.assertTrue(started["stale_report_gone"])
        self.assertEqual(started["env"]["GREENLIGHT_BDD_SEED"], "42")

    def test_a_step_that_asserts_is_not_flagged_and_one_that_does_not_is(self):
        text = '[Binding]\npublic class Extra\n{\n    [Then(@"^it is fine$")]\n    public void Fine() { }\n}\n'
        support.assert_scan_tells_an_assertion_free_step(self, "dotnet-reqnroll", "tests/steps/Extra.cs", text)

    def test_init_suggests_it_for_a_dotnet_project_and_for_nothing_else(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / "App.csproj").write_text('<Project Sdk="Microsoft.NET.Sdk"></Project>\n', encoding="utf-8")
            self.assertEqual([name for name, _ in initcmd.detect(root)], ["dotnet-reqnroll"])
            (root / "App.csproj").unlink()
            self.assertEqual(initcmd.detect(root), [])

    def test_apply_registers_the_plumbing_as_bound_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / ".bdd").mkdir()
            adapter.apply(root, "dotnet-reqnroll")
            bound = {p.relative_to(root).as_posix() for p in cfg.load(root).support_files}
            self.assertEqual(bound, {"tests/GreenlightTests.csproj", "tests/packages.lock.json", "tests/nuget.config",
                                     "tests/.editorconfig", "tests/run_dotnet.py"})


@unittest.skipUnless(RUN_CONTRACT, "needs the .NET SDK, package downloads and GREENLIGHT_DOTNET_ADAPTER_TESTS=1")
class ContractTest(support.ContractSteps, unittest.TestCase):
    ADAPTER = "dotnet-reqnroll"

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
            (features / "orders.feature").write_text(support.ORDERS, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    unittest.main()
