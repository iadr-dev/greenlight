"""The generic-junit adapter on the two reference apps, with each app's own runner.

money-lib runs node's built-in test runner (compiled TypeScript), csv-tool runs `go test` through gotestsum. Both need
their toolchain and the network (`npm ci`, the Go module proxy), so they run only when GREENLIGHT_APP_ADAPTER_TESTS=1 is
set and the tool is on PATH; the CI jobs of the reference apps set it. The check: scaffold the adapter into a copy of the
app, swap the run line the way the evaluation harness does, and prove that a missing seam is a valid red and a working
one a valid green, through `bdd run` and `bdd classify` and nothing else."""
import contextlib
import importlib.util
import io
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from bddlib import adapter, cli, state

REPO = Path(__file__).resolve().parents[3]
ENABLED = os.environ.get("GREENLIGHT_APP_ADAPTER_TESTS") == "1"
IGNORED = shutil.ignore_patterns("node_modules", "dist", "__pycache__")

FEATURE = """@FEAT-001
Feature: Counting

  @R-001.1
  Rule: Rows are counted

    @EX-001.1.1
    Scenario: Counts the rows of a file
      When add is called with:
        | a | b |
        | 1 | 2 |
      Then the result is:
        \"\"\"
        3
        \"\"\"

    @EX-001.1.2
    Scenario: Refuses an empty file
      When add is called with:
        | a | b |
        | 1 | 2 |
      Then the result is:
        \"\"\"
        3
        \"\"\"
"""


def load_harness():
    spec = importlib.util.spec_from_file_location("run_e2e", REPO / "evals" / "run_e2e.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class HarnessTablesTest(unittest.TestCase):
    """The evaluation harness knows each request, its app, its answers and (for generic-junit) its run line."""

    @classmethod
    def setUpClass(cls):
        cls.harness = load_harness()

    def test_every_request_has_an_app_an_answers_file_and_a_toolchain(self):
        for request, (app, adapter_name) in self.harness.CASES.items():
            with self.subTest(request=request):
                self.assertTrue((REPO / "evals" / "requests" / f"{request}.md").is_file())
                self.assertTrue((REPO / "evals" / "requests" / f"{request}.answers.json").is_file())
                self.assertTrue((REPO / "evals" / "apps" / app).is_dir())
                self.assertIn(app, self.harness.TOOLCHAINS)
                self.assertEqual(app in self.harness.GENERIC_RUNS, adapter_name == "generic-junit")
                self.assertTrue((REPO / "adapters" / adapter_name / "adapter.toml").is_file())

    def test_every_request_file_is_known_to_the_harness(self):
        files = {p.stem for p in (REPO / "evals" / "requests").glob("*.md")}
        self.assertEqual(files, set(self.harness.CASES))

    def test_swapping_the_run_line_leaves_a_valid_configuration(self):
        from bddlib import config as cfg
        for request, (app, adapter_name) in self.harness.CASES.items():
            if adapter_name != "generic-junit":
                continue
            with self.subTest(request=request), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp).resolve()
                shutil.copytree(REPO / "evals" / "apps" / app, root, ignore=IGNORED, dirs_exist_ok=True)
                (root / ".bdd").mkdir()
                adapter.apply(root, "generic-junit")
                self.harness.swap_run_line(root, request)
                (run,) = cfg.load(root).runs
                self.assertIn("run_junit.py", run.by_tag)
                self.assertIn("{marker}", run.by_tag)
                self.assertFalse((root / "tests" / "run_tests.py").exists())
                self.assertIn(root / "tests" / "run_junit.py", cfg.load(root).support_files)


class AppCase:
    """The steps of the test; a subclass names the request and brings its steps and its toolchain check."""

    request = ""

    @classmethod
    def setUpClass(cls):
        harness = load_harness()
        app = harness.CASES[cls.request][0]
        cls.dir = tempfile.TemporaryDirectory()
        cls.root = Path(cls.dir.name).resolve()
        shutil.copytree(REPO / "evals" / "apps" / app, cls.root, ignore=IGNORED, dirs_exist_ok=True)
        (cls.root / ".bdd").mkdir()
        adapter.apply(cls.root, "generic-junit")
        harness.swap_run_line(cls.root, cls.request)
        state.create(cls.root, "FEAT-001", "Counting", "standard")
        (cls.root / "tests" / "features").mkdir(parents=True, exist_ok=True)
        (cls.root / "tests" / "features" / "counting.feature").write_text(FEATURE, encoding="utf-8", newline="\n")
        cls.prepare_app()

    @classmethod
    def prepare_app(cls):
        pass

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

    def results(self) -> list[str]:
        code, out, err = self.bdd("classify", "FEAT-001", "--json")
        self.assertIn(code, (0, 1), err)
        return [row["result"] for row in json.loads(out)["scenarios"]]

    def write_steps(self, relative: str, text: str) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")

    def test_a_missing_seam_is_a_valid_red_and_a_working_one_a_valid_green(self):
        self.write_steps(*self.red_steps)
        code, out, err = self.bdd("run", "FEAT-001")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.results(), ["expected-fail", "expected-fail"])
        self.assertEqual(self.bdd("classify", "FEAT-001", "--expect", "red")[0], 0)
        self.write_steps(*self.green_steps)
        code, out, err = self.bdd("run", "FEAT-001")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.results(), ["pass", "pass"])
        self.assertEqual(self.bdd("classify", "FEAT-001", "--expect", "green")[0], 0)


NODE_RED = """import { test } from "node:test";

test("FEAT_001_ Counts the rows of a file", () => {
  throw new Error("BDD_EXPECTED_MISSING: convert");
});

test("FEAT_001_ Refuses an empty file", () => {
  throw new Error("BDD_EXPECTED_MISSING: convert");
});
"""

NODE_GREEN = """import assert from "node:assert/strict";
import { test } from "node:test";

import { format, parse } from "../../src/money.js";

test("FEAT_001_ Counts the rows of a file", () => {
  assert.equal(format(parse("12.50", "USD")), "12.50 USD");
});

test("FEAT_001_ Refuses an empty file", () => {
  assert.throws(() => parse("twelve", "USD"));
});
"""

GO_RED = """package steps

import "testing"

func TestFEAT_001_CountsTheRowsOfAFile(t *testing.T) {
	t.Fatal("BDD_EXPECTED_MISSING: report command")
}

func TestFEAT_001_RefusesAnEmptyFile(t *testing.T) {
	t.Fatal("BDD_EXPECTED_MISSING: report command")
}
"""

GO_GREEN = """package steps

import (
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
)

func runTool(t *testing.T, content string) (string, error) {
	t.Helper()
	path := filepath.Join(t.TempDir(), "data.csv")
	if err := os.WriteFile(path, []byte(content), 0o600); err != nil {
		t.Fatal(err)
	}
	command := exec.Command("go", "run", ".", "count", path)
	command.Dir = "../.."
	output, err := command.CombinedOutput()
	return string(output), err
}

func TestFEAT_001_CountsTheRowsOfAFile(t *testing.T) {
	output, err := runTool(t, "a,b\\n1,2\\n3,4\\n")
	if err != nil || strings.TrimSpace(output) != "2 rows" {
		t.Fatalf("got %q, %v", output, err)
	}
}

func TestFEAT_001_RefusesAnEmptyFile(t *testing.T) {
	if _, err := runTool(t, ""); err == nil {
		t.Fatal("an empty file was accepted")
	}
}
"""


@unittest.skipUnless(ENABLED and shutil.which("node") and shutil.which("npm"),
                     "needs node, npm, network and GREENLIGHT_APP_ADAPTER_TESTS=1")
class MoneyLibTest(AppCase, unittest.TestCase):
    request = "money-convert"
    red_steps = ("tests/steps/counting.test.ts", NODE_RED)
    green_steps = ("tests/steps/counting.test.ts", NODE_GREEN)

    @classmethod
    def prepare_app(cls):
        import subprocess
        done = subprocess.run([shutil.which("npm"), "ci", "--ignore-scripts", "--no-audit", "--no-fund"], cwd=cls.root,
                              capture_output=True, text=True)
        if done.returncode != 0:
            raise RuntimeError(done.stdout + done.stderr)


@unittest.skipUnless(ENABLED and shutil.which("go"), "needs go, network and GREENLIGHT_APP_ADAPTER_TESTS=1")
class CsvToolTest(AppCase, unittest.TestCase):
    request = "csv-report"
    red_steps = ("tests/steps/counting_test.go", GO_RED)
    green_steps = ("tests/steps/counting_test.go", GO_GREEN)


if __name__ == "__main__":
    unittest.main()
