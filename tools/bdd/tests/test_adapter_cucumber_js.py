"""The ts-cucumber-js adapter: its package is complete and pinned, the scaffold is wired the way `bdd` expects, and (where Node
is installed and the network is allowed) a fresh scaffold really runs green, every core step works and red looks like red.

The structural tests run everywhere. The contract tests need Node 22 or newer, npm, package downloads and
GREENLIGHT_NODE_ADAPTER_TESTS=1; the CI job for the adapter sets it.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from bddlib import adapter, initcmd, state
from bddlib import config as cfg

from tests import adapter_contract_support as support

REPO = Path(__file__).resolve().parents[3]
ADAPTER = REPO / "adapters" / "ts-cucumber-js"
TEMPLATES = ADAPTER / "templates"
FIXTURES = Path(__file__).parent / "fixtures" / "ts-cucumber-js"
RUN_CONTRACT = bool(shutil.which("node") and shutil.which("npm")) and os.environ.get("GREENLIGHT_NODE_ADAPTER_TESTS") == "1"


class PackageTest(unittest.TestCase):
    def test_the_contract_files_exist(self):
        for name in adapter.REQUIRED + ("ci.md",):
            self.assertTrue((ADAPTER / name).exists(), name)
        self.assertEqual(adapter.load(ADAPTER)["name"], "ts-cucumber-js")

    def test_the_config_block_is_valid_and_complete(self):
        config = support.config_of(ADAPTER)
        (scan,), (run,) = config.scans, config.runs
        self.assertEqual(run.adapter, "ts-cucumber-js")
        self.assertIn("--config tests/cucumber.mjs", run.by_tag)
        self.assertIn("--tags @{tag}", run.by_tag)
        self.assertEqual((run.shuffle, run.isolated), ("--order random:{seed}", '--name "^{scenario:js}$"'))
        self.assertIn("{out}", run.report)
        self.assertLessEqual({"NODE_", "TSX_", "CUCUMBER_"}, set(run.scrub_env))
        self.assertTrue(scan.assert_patterns and scan.sleep_patterns and scan.stub_patterns)

    def test_the_report_word_keeps_a_windows_path_in_one_piece(self):
        """cucumber-js splits a format at its colon, so the path after ``junit:`` must be quoted (a drive letter has a colon)."""
        run = support.config_of(ADAPTER).runs[0]
        self.assertEqual(run.report, "--format 'junit:\"{out}\"'")

    def test_the_test_tooling_is_pinned_and_hashed(self):
        wanted = adapter.load(ADAPTER)["requires"]["packages"]
        package = json.loads((TEMPLATES / "tests" / "package.json").read_text(encoding="utf-8"))
        lock = json.loads((TEMPLATES / "tests" / "package-lock.json").read_text(encoding="utf-8"))
        self.assertEqual(sorted(package["devDependencies"]), sorted(wanted))
        for name, version in package["devDependencies"].items():
            self.assertRegex(version, r"^\d+\.\d+\.\d+$", f"{name} is pinned to one version")
            self.assertEqual(lock["packages"][f"node_modules/{name}"]["version"], version)
        entries = [entry for key, entry in lock["packages"].items() if key]
        self.assertTrue(entries and all(entry.get("integrity", "").startswith("sha512-") for entry in entries), "every package is hashed")

    def test_every_support_file_is_shipped_and_every_step_expression_is_an_anchored_regular_expression(self):
        shipped = {p.relative_to(TEMPLATES).as_posix() for p in adapter.template_files(ADAPTER)}
        for name in adapter.load(ADAPTER)["paths"]["support"]:
            self.assertIn(name, shipped)
        source = (TEMPLATES / "tests" / "steps" / "core_steps.ts").read_text(encoding="utf-8")
        expressions = re.findall(r"(?:Given|When|Then)\(/(.+)/,", source)
        self.assertLessEqual(22, len(expressions))
        for expression in expressions:
            re.compile(expression)
            self.assertTrue(expression.startswith("^") and expression.endswith("$"), expression)

    def test_a_step_that_asserts_is_not_flagged_and_one_that_does_not_is(self):
        text = "import { Then } from '@cucumber/cucumber';\nThen(/^it is fine$/, function () {\n  return;\n});\n"
        support.assert_scan_tells_an_assertion_free_step(self, "ts-cucumber-js", "tests/steps/extra.ts", text)

    def test_init_suggests_it_for_a_node_service_and_not_for_a_web_ui(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / "package.json").write_text('{"dependencies": {"express": "5.0.0"}}', encoding="utf-8")
            self.assertIn("ts-cucumber-js", [name for name, _ in initcmd.detect(root)])
            (root / "package.json").unlink()
            self.assertEqual(initcmd.detect(root), [])

    def test_apply_registers_the_plumbing_as_bound_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / ".bdd").mkdir()
            adapter.apply(root, "ts-cucumber-js")
            bound = {p.relative_to(root).as_posix() for p in cfg.load(root).support_files}
            self.assertEqual(bound, {"tests/cucumber.mjs", "tests/package.json", "tests/package-lock.json", "tests/tsconfig.json"})

    def test_the_fixture_features_name_only_core_instructions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / ".bdd").mkdir()
            adapter.apply(root, "ts-cucumber-js")
            state.create(root, "FEAT-000", "Sample", "standard")
            shutil.copyfile(FIXTURES / "full.feature", root / "tests" / "features" / "full.feature")
            (root / "tests" / "features" / "orders.feature").write_text(support.ORDERS, encoding="utf-8", newline="\n")
            code, out, _ = support.run_bdd(root, "lint", "tests/features")
            self.assertEqual(code, 1, "the moon step is on purpose not in the vocabulary")
            self.assertEqual(out.count("L002"), 1, out)


@unittest.skipUnless(RUN_CONTRACT, "needs Node, npm, package downloads and GREENLIGHT_NODE_ADAPTER_TESTS=1")
class ContractTest(support.ContractSteps, unittest.TestCase):
    ADAPTER = "ts-cucumber-js"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        done = subprocess.run(["npm", "ci", "--ignore-scripts", "--prefix", "tests", "--no-audit", "--no-fund"], cwd=cls.root,
                              capture_output=True, text=True, shell=os.name == "nt", timeout=600)
        if done.returncode != 0:
            raise RuntimeError(f"npm ci failed:\n{done.stdout}\n{done.stderr}")

    def use_system(self, full: bool) -> None:
        drivers, features = self.root / "tests" / "drivers", self.root / "tests" / "features"
        if full:
            shutil.copyfile(FIXTURES / "system.ts.fixture", drivers / "system.ts")
            shutil.copyfile(FIXTURES / "operations.ts.fixture", drivers / "operations.ts")
            shutil.copyfile(FIXTURES / "full.feature", features / "full.feature")
            (features / "orders.feature").unlink(missing_ok=True)
        else:
            for name in ("system.ts", "operations.ts"):
                shutil.copyfile(TEMPLATES / "tests" / "drivers" / name, drivers / name)
            (features / "full.feature").unlink(missing_ok=True)
            operations = drivers / "operations.ts"
            operations.write_text(operations.read_text(encoding="utf-8").replace(
                "  // 'place order': { method: 'POST', path: '/orders' },", "  'place order': { method: 'POST', path: '/orders' },"),
                encoding="utf-8", newline="\n")
            (features / "orders.feature").write_text(support.ORDERS, encoding="utf-8", newline="\n")

    def test_the_network_guard_refuses_outside_hosts_in_every_form_and_lets_loopback_through(self):
        """``connect`` is called as ``connect(options)``, ``connect(port, host)`` and through the agent of ``http.get`` and ``fetch``;
        each of them to a public address is refused, and a local server is reached by address and by the name ``localhost``."""
        self.use_system(full=False)
        probe = self.root / "guard_probe.mjs"
        probe.write_text(GUARD_PROBE, encoding="utf-8", newline="\n")
        done = subprocess.run(["node", "--import", "./tests/node_modules/tsx/dist/loader.mjs", "guard_probe.mjs"], cwd=self.root,
                              capture_output=True, text=True, timeout=120)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        blocked = "OutboundNetworkBlocked"
        self.assertEqual(json.loads(done.stdout.strip().splitlines()[-1]),
                         {"netObject": blocked, "netPortHost": blocked, "httpGet": blocked, "fetch": blocked,
                          "loopbackFetch": "ok", "localhostFetch": "ok"})

    def test_type_check_passes_on_the_scaffold(self):
        self.use_system(full=False)
        done = subprocess.run(["node", "tests/node_modules/typescript/bin/tsc", "-p", "tests/tsconfig.json"], cwd=self.root,
                              capture_output=True, text=True, timeout=300)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)


GUARD_PROBE = r"""
import net from 'node:net';
import http from 'node:http';
const { blockNetwork } = await import('./tests/drivers/network.ts');
blockNetwork();
const name = (e) => (e?.cause?.name ?? e?.name ?? String(e));
const attempts = {
  netObject: () => new Promise((res) => { try { const s = net.connect({ host: '93.184.216.34', port: 80 }); s.on('error', (e) => res(name(e))); } catch (e) { res(name(e)); } }),
  netPortHost: () => new Promise((res) => { try { const s = net.connect(80, 'example.org'); s.on('error', (e) => res(name(e))); } catch (e) { res(name(e)); } }),
  httpGet: () => new Promise((res) => { try { http.get('http://93.184.216.34/').on('error', (e) => res(name(e))); } catch (e) { res(name(e)); } }),
  fetch: async () => { try { await fetch('http://93.184.216.34/'); return 'connected'; } catch (e) { return name(e); } },
};
const out = {};
for (const [k, f] of Object.entries(attempts)) out[k] = await f();
const server = http.createServer((_q, r) => r.end('ok')).listen(0, '127.0.0.1');
await new Promise((r) => server.once('listening', r));
const port = server.address().port;
out.loopbackFetch = await (await fetch(`http://127.0.0.1:${port}/`)).text();
out.localhostFetch = await (await fetch(`http://localhost:${port}/`).catch((e) => ({ text: async () => name(e) }))).text();
server.close();
console.log(JSON.stringify(out));"""


if __name__ == "__main__":
    unittest.main()
