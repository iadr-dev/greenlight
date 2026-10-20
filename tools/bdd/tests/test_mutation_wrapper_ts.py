"""The Stryker wrapper of the ts-playwright-bdd adapter: its rules, and one real run when the CI job allows it.

The rules need `node` only. The real run installs the pinned Stryker with npm (network) and is switched on by
GREENLIGHT_NODE_MUTATION_TESTS=1, which the CI job for the adapter sets.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from bddlib import adapter
from bddlib import config as cfg

REPO = Path(__file__).resolve().parents[3]
WRAPPER = REPO / "adapters" / "ts-playwright-bdd" / "templates" / "tests" / "tools" / "mutate-ts.mjs"
NODE = shutil.which("node")
NPM = shutil.which("npm")
STRYKER = "@stryker-mutator/core@10.0.0"
REAL = os.environ.get("GREENLIGHT_NODE_MUTATION_TESTS") == "1" and NODE and NPM

PROBE = """
import { checkFiles, checkReport, countsFromReport, strykerConfig } from {module};
const root = process.argv[2];
const out = {};
for (const [name, call] of Object.entries({
  files: () => checkFiles(root, JSON.parse(process.argv[3])),
  report: () => checkReport(root, process.argv[3]),
  counts: () => countsFromReport(JSON.parse(process.argv[3])),
  config: () => strykerConfig(['src/a.js'], 'npm test', '/tmp/r.json'),
})) {
  if (name !== process.argv[4]) continue;
  try { out.value = call(); } catch (error) { out.error = error.message; }
}
console.log(JSON.stringify(out));
"""

DISCOUNT = "export function discount(total) {\n  if (total >= 1000) {\n    return Math.floor(total / 10);\n  }\n  return 0;\n}\n"
STRONG = ('import test from "node:test";\nimport assert from "node:assert/strict";\n'
          'import { discount } from "../src/discount.js";\n'
          'test("threshold", () => {\n  assert.equal(discount(999), 0);\n  assert.equal(discount(1000), 100);\n});\n')
WEAK = ('import test from "node:test";\nimport assert from "node:assert/strict";\n'
        'import { discount } from "../src/discount.js";\n'
        'test("returns something", () => {\n  assert.notEqual(discount(5000), undefined);\n});\n')


@unittest.skipUnless(NODE, "needs node")
class RulesTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name).resolve()
        (self.root / "src").mkdir()
        (self.root / "src" / "a.js").write_text("export const a = 1;\n", encoding="utf-8")
        (self.root / "notes.txt").write_text("n\n", encoding="utf-8")
        self.script = self.root.parent / f"{self.root.name}-probe.mjs"
        self.script.write_text(PROBE.replace("{module}", json.dumps(WRAPPER.as_uri())), encoding="utf-8")
        self.addCleanup(self.script.unlink)

    def ask(self, what: str, argument: str) -> dict:
        done = subprocess.run([NODE, str(self.script), str(self.root), argument, what], capture_output=True, text=True,
                              check=True)
        return json.loads(done.stdout)

    def test_files_are_relative_existing_script_files_inside_the_project(self):
        self.assertEqual(self.ask("files", json.dumps(["src/a.js", "src/a.js"])), {"value": ["src/a.js"]})
        for names in (["../x.js"], ["/etc/x.js"], ["src/missing.js"], ["notes.txt"], ["src"], []):
            with self.subTest(names=names):
                self.assertIn("error", self.ask("files", json.dumps(names)))

    def test_the_report_is_an_absolute_path_outside_the_project(self):
        with tempfile.TemporaryDirectory() as elsewhere:
            good = str(Path(elsewhere).resolve() / "report.json")
            self.assertIn("value", self.ask("report", good))
        self.assertIn("error", self.ask("report", "report.json"))
        self.assertIn("error", self.ask("report", str(self.root / "report.json")))

    def test_counts_follow_the_rules_for_doubt(self):
        report = {"files": {"a.js": {"mutants": [{"status": "Killed"}, {"status": "Killed"}, {"status": "Survived"},
                                                 {"status": "NoCoverage"}, {"status": "Timeout"}, {"status": "RuntimeError"},
                                                 {"status": "CompileError"}, {"status": "Ignored"}, {"status": "Other"}]}}}
        self.assertEqual(self.ask("counts", json.dumps(report))["value"],
                         {"killed": 2, "survived": 2, "timeout": 1, "suspicious": 1, "skipped": 2})

    def test_stryker_gets_a_config_file_with_the_test_command_as_data(self):
        config = self.ask("config", "")["value"]
        self.assertEqual((config["testRunner"], config["commandRunner"], config["mutate"]),
                         ("command", {"command": "npm test"}, ["src/a.js"]))

    def test_a_refused_call_exits_with_its_own_status(self):
        done = subprocess.run([NODE, str(WRAPPER), "--report", "relative.json", "--test-command", "npm test", "--", "src/a.js"],
                              cwd=self.root, capture_output=True, text=True, check=False)
        self.assertEqual(done.returncode, 2)
        self.assertIn("absolute", done.stderr)

    def test_a_missing_stryker_is_a_tool_failure_not_a_result(self):
        with tempfile.TemporaryDirectory() as elsewhere:
            report = Path(elsewhere).resolve() / "report.json"
            done = subprocess.run([NODE, str(WRAPPER), "--report", str(report), "--test-command", "npm test", "--", "src/a.js"],
                                  cwd=self.root, capture_output=True, text=True, check=False)
            self.assertEqual(done.returncode, 3)
            self.assertIn("Stryker is not installed", done.stderr)
            self.assertFalse(report.exists())


class ShippedTest(unittest.TestCase):
    def test_the_adapter_copies_it_and_lists_it_as_a_support_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / ".bdd").mkdir()
            created, _ = adapter.apply(root, "ts-playwright-bdd")
            self.assertIn("tests/tools/mutate-ts.mjs", created)
            names = {p.relative_to(root).as_posix() for p in cfg.load(root).support_files}
            self.assertIn("tests/tools/mutate-ts.mjs", names)


@unittest.skipUnless(REAL, "needs node, npm, network and GREENLIGHT_NODE_MUTATION_TESTS=1")
class RealStrykerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.TemporaryDirectory()
        cls.root = Path(cls.dir.name).resolve()
        (cls.root / "src").mkdir()
        (cls.root / "test").mkdir()
        (cls.root / "tests" / "tools").mkdir(parents=True)
        (cls.root / "package.json").write_text('{"name": "fixture", "private": true, "type": "module"}\n', encoding="utf-8")
        (cls.root / "src" / "discount.js").write_text(DISCOUNT, encoding="utf-8")
        shutil.copyfile(WRAPPER, cls.root / "tests" / "tools" / "mutate-ts.mjs")
        subprocess.run([NPM, "install", "--no-audit", "--no-fund", "--save-dev", "--save-exact", STRYKER], cwd=cls.root,
                       check=True, capture_output=True, text=True)

    @classmethod
    def tearDownClass(cls):
        cls.dir.cleanup()

    def measure(self, tests: str) -> dict:
        (self.root / "test" / "discount.test.js").write_text(tests, encoding="utf-8")
        with tempfile.TemporaryDirectory() as elsewhere:
            report = Path(elsewhere).resolve() / "report.json"
            done = subprocess.run([NODE, "tests/tools/mutate-ts.mjs", "--report", str(report), "--test-command",
                                   "node --test", "--", "src/discount.js"], cwd=self.root, capture_output=True,
                                  text=True, check=False)
            print(f"\nStryker {STRYKER}: {done.stdout.strip()}", file=sys.stderr)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            return json.loads(report.read_text(encoding="utf-8"))

    def test_strong_tests_kill_the_mutants_and_weak_tests_do_not(self):
        strong = self.measure(STRONG)
        weak = self.measure(WEAK)
        self.assertEqual(strong["survived"], 0)
        self.assertGreater(strong["killed"], 0)
        self.assertGreater(weak["survived"], strong["survived"])
        self.assertLess(weak["killed"], strong["killed"])


if __name__ == "__main__":
    unittest.main()
