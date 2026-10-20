"""The python-pytest-bdd adapter: its package is complete, and a fresh scaffold really runs green.

The contract tests need `pytest` and `pytest-bdd` in the interpreter that runs the tests (the CI job for
the adapter installs them) and are skipped without.
"""
import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from bddlib import adapter, cli, state
from bddlib import config as cfg
from bddlib.errors import UsageError

REPO = Path(__file__).resolve().parents[3]
ADAPTER = REPO / "adapters" / "python-pytest-bdd"
HAVE_RUNNER = all(importlib.util.find_spec(name) for name in ("pytest", "pytest_bdd"))


class PackageTest(unittest.TestCase):
    def test_the_contract_files_exist(self):
        for name in adapter.REQUIRED + ("ci.md",):
            self.assertTrue((ADAPTER / name).exists(), name)
        self.assertEqual(adapter.load(ADAPTER)["name"], "python-pytest-bdd")

    def test_the_config_block_is_valid_toml_and_complete(self):
        text = adapter.config_block(adapter.load(ADAPTER))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".bdd").mkdir()
            (root / ".bdd" / "config.toml").write_text(text, encoding="utf-8")
            config = cfg.load(root)
        (scan,), (run,) = config.scans, config.runs
        self.assertEqual(run.adapter, "python-pytest-bdd")
        self.assertIn("-m {tag}", run.by_tag)
        self.assertEqual(config.feature_dirs, (root / "tests/features",))
        self.assertTrue(scan.assert_patterns and scan.sleep_patterns and scan.stub_patterns)
        self.assertIn("BDD_EXPECTED_MISSING", run.expected_fail)
        self.assertIn("NotMapped", run.test_defect)

    def test_names_are_validated_and_templates_listed(self):
        for bad in ("", "../x", "Python", "no-such-adapter"):
            with self.subTest(name=bad), self.assertRaises(UsageError):
                adapter.find(bad)
        names = {p.relative_to(ADAPTER / "templates").as_posix() for p in adapter.template_files(ADAPTER)}
        self.assertIn("tests/steps/core_steps.py", names)
        self.assertIn("tests/features/sample.feature", names)
        self.assertNotIn("tests/__pycache__", " ".join(names))


class ApplyTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name).resolve()
        (self.root / ".bdd").mkdir()

    def test_apply_copies_registers_and_never_overwrites(self):
        (self.root / "tests").mkdir()
        (self.root / "tests" / "conftest.py").write_text("# mine\n", encoding="utf-8")
        created, kept = adapter.apply(self.root, "python-pytest-bdd")
        self.assertEqual(kept, ["tests/conftest.py"])
        self.assertIn("tests/drivers/system.py", created)
        self.assertEqual((self.root / "tests" / "conftest.py").read_text(encoding="utf-8"), "# mine\n")
        self.assertEqual(cfg.load(self.root).runs[0].adapter, "python-pytest-bdd")
        self.assertEqual({p.name for p in cfg.load(self.root).support_files}, {"pytest.ini", "conftest.py", "test_features.py", "__init__.py"})
        with self.assertRaises(UsageError) as cm:
            adapter.apply(self.root, "python-pytest-bdd")
        self.assertIn("already in .bdd/config.toml", str(cm.exception))

    def test_existing_config_is_kept_and_the_command_prints_what_happened(self):
        (self.root / ".bdd" / "config.toml").write_text('autonomy = "guided"\n', encoding="utf-8")
        out, here = io.StringIO(), os.getcwd()
        os.chdir(self.root)
        try:
            with contextlib.redirect_stdout(out):
                self.assertEqual(cli.main(["adapter", "apply", "python-pytest-bdd"]), 0)
        finally:
            os.chdir(here)
        self.assertEqual(cfg.load(self.root).autonomy, "guided")
        self.assertIn("file(s) created", out.getvalue())

    def test_list(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(adapter.run(["list"]), 0)
        self.assertIn("python-pytest-bdd", out.getvalue().split())


@unittest.skipUnless(HAVE_RUNNER, "needs pytest and pytest-bdd")
class ContractTest(unittest.TestCase):
    """A fresh scaffold: the sample passes, the checks are clean, and red looks like red."""

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.TemporaryDirectory()
        cls.root = Path(cls.dir.name).resolve()
        (cls.root / ".bdd").mkdir()
        adapter.apply(cls.root, "python-pytest-bdd")
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

    def test_1_the_sample_feature_is_green(self):
        code, out, err = self.bdd("run", "FEAT-000")
        self.assertEqual(code, 0, out + err)
        code, out, _ = self.bdd("classify", "FEAT-000", "--expect", "green")
        self.assertEqual(code, 0, out)

    def test_2_shuffled_and_isolated_runs_are_green_too(self):
        for flags in (("--shuffle", "--seed", "7"), ("--isolated",)):
            with self.subTest(flags=flags):
                code, out, err = self.bdd("run", "FEAT-000", *flags)
                self.assertEqual(code, 0, out + err)
                self.assertEqual(self.bdd("classify", "FEAT-000", "--expect", "green")[0], 0)

    def test_3_the_scaffold_passes_the_scan_and_the_lint(self):
        code, out, _ = self.bdd("scan", "FEAT-000")
        self.assertEqual((code, out.strip()), (0, "FEAT-000: no findings"), out)
        code, out, _ = self.bdd("lint", "tests/features")
        self.assertEqual(code, 0, out)

    def test_4_red_looks_like_red(self):
        state.create(self.root, "FEAT-001", "Orders", "standard")
        (self.root / "tests/features/orders.feature").write_text(ORDERS, encoding="utf-8", newline="\n")
        ops = self.root / "tests/drivers/operations.py"
        ops.write_text(ops.read_text(encoding="utf-8").replace(
            "    # \"place order\": Api(\"POST\", \"/orders\"),", "    \"place order\": Api(\"POST\", \"/orders\"),"), encoding="utf-8")
        system = self.root / "tests/drivers/system.py"
        system.write_text(system.read_text(encoding="utf-8").replace(
            'raise ExpectedMissing("an HTTP client for the application")', "return MissingApp()") + MISSING_APP, encoding="utf-8")
        self.assertEqual(self.bdd("run", "FEAT-001")[0], 0)
        code, out, _ = self.bdd("classify", "FEAT-001", "--json")
        results = {row["example"]: row["result"] for row in json.loads(out)["scenarios"]}
        self.assertEqual(results, {"EX-001.1.1": "expected-fail", "EX-001.1.2": "expected-fail", "EX-001.1.3": "test-defect"})
        self.assertEqual(self.bdd("classify", "FEAT-001", "--expect", "red")[0], 1)       # the unmapped name blocks
        (self.root / "tests/features/orders.feature").write_text(ORDERS.split("    @EX-001.1.3")[0], encoding="utf-8", newline="\n")
        self.bdd("run", "FEAT-001")
        self.assertEqual(self.bdd("classify", "FEAT-001", "--expect", "red")[0], 0)

    def test_5_the_network_is_blocked_and_unstubbed_calls_fail(self):
        probe = self.root / "tests/test_probe.py"
        probe.write_text(PROBE, encoding="utf-8", newline="\n")
        self.addCleanup(probe.unlink)
        done = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(probe)], cwd=self.root,
                              capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    def test_6_the_project_can_complete_a_request_without_editing_a_core_driver(self):
        probe = self.root / "tests/test_complete.py"
        probe.write_text(COMPLETE, encoding="utf-8", newline="\n")
        self.addCleanup(probe.unlink)
        done = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(probe)], cwd=self.root,
                              capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)



ORDERS = """@FEAT-001
Feature: Orders

  @R-001.1
  Rule: Orders can be placed

    @EX-001.1.1
    Scenario: An order is placed
      When alice calls place order with:
        | item | qty |
        | tea  | 2   |
      Then the request succeeds

    @EX-001.1.2
    Scenario: Seeding needs a seam
      Given the following order exist:
        | id |
        | 1  |
      When alice calls place order
      Then the request succeeds

    @EX-001.1.3
    Scenario: A name nobody mapped
      When alice calls cancel order
      Then the request succeeds
"""

MISSING_APP = '''

class _NotFound:
    status_code = 404
    text = "not found"

    def json(self):
        raise ValueError("no body")


class MissingApp:
    """A stand-in for an application that has no routes yet."""

    def request(self, method, url, **options):
        return _NotFound()
'''

PROBE = '''
import socket

import pytest

from tests.drivers.errors import OutboundNetworkBlocked, UnstubbedCall
from tests.drivers.sockets import block_network
from tests.drivers.stubs import Stubs


def test_a_real_connection_is_refused():
    with block_network():
        with pytest.raises(OutboundNetworkBlocked):
            socket.socket().connect(("203.0.113.9", 80))


def test_an_unstubbed_call_fails_and_a_stubbed_one_is_recorded():
    stubs = Stubs()
    with pytest.raises(UnstubbedCall):
        stubs.call("payments", "charge", {"amount": 5})
    stubs.respond("payments", "charge", {"ok": True})
    assert stubs.call("payments", "charge", {"amount": 5}) == {"ok": True}
    stubs.assert_received("payments", "charge", {"amount": 5})
'''


COMPLETE = '''
from tests.drivers import api
from tests.drivers.operations import API, Api
from tests.drivers.system import System
from tests.drivers.world import new_world


class FakeHttp:
    def __init__(self):
        self.calls = []

    def request(self, method, url, **options):
        self.calls.append((method, url, options))
        return type("Response", (), {"status_code": 200, "json": lambda self: {}})()


class Mine(System):
    client = FakeHttp()

    def http(self):
        return self.client

    def complete(self, operation, fields):
        return {"order": 1, **fields}


def test_complete_fills_in_what_the_scenario_left_out(tmp_path):
    API["look up order"] = Api("GET", "/orders/{order}")
    world = new_world(tmp_path)
    world.system = Mine()
    api.call(world, "alice", "look up order", None)
    assert world.system.client.calls[0][:2] == ("GET", "/orders/1")
'''


if __name__ == "__main__":
    unittest.main()
