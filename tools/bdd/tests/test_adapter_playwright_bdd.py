"""The ts-playwright-bdd adapter: its package is complete and its settings sort failures the way the red gate needs.

The contract tests run a real browser. They need node, npm and network access (they install the pinned tooling from
the adapter's lockfile), so they run only when GREENLIGHT_NODE_ADAPTER_TESTS=1 is set; the CI job for the adapter sets it.
"""
import contextlib
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from bddlib import adapter, classify, cli, initcmd, junit, state
from bddlib import config as cfg

REPO = Path(__file__).resolve().parents[3]
ADAPTER = REPO / "adapters" / "ts-playwright-bdd"
TOOLING = ADAPTER / "templates" / "tests"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "ts_playwright"
NODE, NPM = shutil.which("node"), shutil.which("npm")
RUN_CONTRACT = os.environ.get("GREENLIGHT_NODE_ADAPTER_TESTS") == "1" and bool(NODE and NPM)


def rules_of(path: Path) -> cfg.RunRules:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / ".bdd").mkdir()
        (root / ".bdd" / "config.toml").write_text(adapter.config_block(adapter.load(path)), encoding="utf-8")
        return cfg.load(root).runs[0]


class PackageTest(unittest.TestCase):
    def test_a_web_project_fits_this_adapter_and_a_python_one_does_not(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "package.json").write_text('{"dependencies": {"react": "18.0.0"}}', encoding="utf-8")
            self.assertEqual([name for name, _ in initcmd.detect(root)], ["ts-playwright-bdd"])
            (root / "package.json").write_text('{"dependencies": {"left-pad": "1.0.0"}}', encoding="utf-8")
            self.assertEqual(initcmd.detect(root), [])
            (root / "pyproject.toml").write_text('[project]\ndependencies = ["pytest>=8"]\n', encoding="utf-8")
            self.assertEqual([name for name, _ in initcmd.detect(root)], ["python-pytest-bdd"])

    def test_the_tooling_is_pinned_exactly_and_the_lockfile_agrees(self):
        package = json.loads((TOOLING / "package.json").read_text(encoding="utf-8"))
        locked = json.loads((TOOLING / "package-lock.json").read_text(encoding="utf-8"))["packages"][""]
        self.assertEqual(package["devDependencies"], locked["devDependencies"])
        for name, version in package["devDependencies"].items():
            with self.subTest(package=name):
                self.assertRegex(version, r"^\d+\.\d+\.\d+$", "a range lets a different version in")

    def test_failures_are_sorted_the_way_the_red_gate_needs(self):
        rules = [rules_of(ADAPTER)]
        expected = {
            "expected-fail": ["Error: BDD_EXPECTED_MISSING: a running application does not exist yet",
                              "Error: expect(locator).toBeVisible() failed\n\nLocator: getByTestId('banner')",
                              "Error: expect(locator).toHaveText(expected) failed",
                              "AssertionError: the order records: expected [] but got [1]",
                              "Error: status 404 for http://localhost:3000/orders"],
            "test-defect": ["Error: NotMapped: no page named 'invoices' in tests/drivers/operations.ts",
                            "Error: Cannot find module './drivers/missing'",
                            "Error: locator.click: Error: strict mode violation: getByRole('button') resolved to 2 elements",
                            "Error: Missing step definition for \"alice juggles\"",
                            "TypeError: world.page is not a function",
                            "error TS2304: Cannot find name 'wrold'"],
            "unknown": ["UnstubbedCall: the page called payments.charge but the scenario gave no response for it",
                        "Error: net::ERR_CONNECTION_REFUSED at http://localhost:3000/"],
        }
        for outcome, texts in expected.items():
            for text in texts:
                with self.subTest(text=text):
                    case = junit.Case("a scenario", "tests/x.spec.js", junit.FAILED, text)
                    self.assertEqual(classify.classify_case(case, rules), outcome)

    def test_a_fresh_scaffold_lints_and_scans_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / ".bdd").mkdir()
            created, _ = adapter.apply(root, "ts-playwright-bdd")
            self.assertIn("tests/steps/core_steps.ts", created)
            state.create(root, "FEAT-000", "Sample", "standard")
            here = os.getcwd()
            os.chdir(root)
            try:
                with contextlib.redirect_stdout(io.StringIO()) as out:
                    self.assertEqual(cli.main(["lint", "tests/features"]), 0, out.getvalue())
                with contextlib.redirect_stdout(io.StringIO()) as out:
                    self.assertEqual(cli.main(["scan", "FEAT-000"]), 0, out.getvalue())
            finally:
                os.chdir(here)

    def test_apply_registers_the_plumbing_as_bound_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / ".bdd").mkdir()
            adapter.apply(root, "ts-playwright-bdd")
            bound = {p.relative_to(root).as_posix() for p in cfg.load(root).support_files}
            self.assertEqual(bound, {"tests/bdd.config.ts", "tests/run.mjs", "tests/junit-reporter.mjs", "tests/tsconfig.json",
                                     "tests/package.json", "tests/package-lock.json"})


class FixtureFeaturesTest(unittest.TestCase):
    def test_the_fixture_features_name_only_core_instructions(self):
        """The fixtures the contract tests run are valid features of the vocabulary."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / ".bdd").mkdir()
            adapter.apply(root, "ts-playwright-bdd")
            for name in ("contract.feature", "negatives.feature"):
                shutil.copyfile(FIXTURES / name, root / "tests" / "features" / name)
            here = os.getcwd()
            os.chdir(root)
            try:
                with contextlib.redirect_stdout(io.StringIO()) as out:
                    self.assertEqual(cli.main(["lint", "tests/features"]), 0, out.getvalue())
            finally:
                os.chdir(here)


@unittest.skipUnless(RUN_CONTRACT, "needs node, npm, network and GREENLIGHT_NODE_ADAPTER_TESTS=1")
class ContractTest(unittest.TestCase):
    """A fresh scaffold in a real browser: the sample is green, every core step works, failures look like red."""

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.TemporaryDirectory()
        cls.root = Path(cls.dir.name).resolve()
        (cls.root / ".bdd").mkdir()
        adapter.apply(cls.root, "ts-playwright-bdd")
        for name in ("operations.ts", "system.ts"):
            shutil.copyfile(FIXTURES / name, cls.root / "tests" / "drivers" / name)
        for page in (FIXTURES / "pages").glob("*.html"):
            shutil.copyfile(page, cls.root / "tests" / "sample" / page.name)
        for feature in FIXTURES.glob("*.feature"):
            shutil.copyfile(feature, cls.root / "tests" / "features" / feature.name)
        for number, title in ((0, "Sample"), (10, "Contract"), (11, "Negatives")):
            state.create(cls.root, f"FEAT-{number:03d}", title, "standard")
        cls.install_tooling()

    @classmethod
    def install_tooling(cls):
        for command in ([NPM, "ci", "--ignore-scripts", "--prefix", "tests", "--no-audit", "--no-fund"],
                        [NODE, "tests/node_modules/@playwright/test/cli.js", "install", "chromium"]):
            done = subprocess.run(command, cwd=cls.root, capture_output=True, text=True, encoding="utf-8", errors="replace")
            if done.returncode != 0:
                raise AssertionError(f"{' '.join(command)} failed:\n{done.stdout}\n{done.stderr}")

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

    def test_1_the_sample_feature_is_green(self):
        code, out, err = self.bdd("run", "FEAT-000")
        self.assertEqual(code, 0, out + err)
        code, out, _ = self.bdd("classify", "FEAT-000", "--expect", "green")
        self.assertEqual(code, 0, out)

    def test_2_isolated_runs_are_green_and_shuffling_is_refused(self):
        code, out, err = self.bdd("run", "FEAT-000", "--isolated")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.bdd("classify", "FEAT-000", "--expect", "green")[0], 0)
        code, _, err = self.bdd("run", "FEAT-000", "--shuffle")
        self.assertEqual((code, "no shuffle words" in err), (2, True))

    def test_3_every_core_step_works(self):
        code, out, err = self.bdd("run", "FEAT-010")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(set(self.results("FEAT-010").values()), {"pass"})
        self.assertEqual(self.bdd("scan", "FEAT-010")[0], 0)

    def test_4_failures_look_like_red(self):
        self.assertEqual(self.bdd("run", "FEAT-011")[0], 0)
        self.assertEqual(self.results("FEAT-011"), {
            "EX-011.1.1": "unknown", "EX-011.1.2": "unknown", "EX-011.1.3": "expected-fail", "EX-011.1.4": "expected-fail",
            "EX-011.1.5": "expected-fail", "EX-011.1.6": "test-defect", "EX-011.1.7": "expected-fail",
            "EX-011.1.8": "expected-fail", "EX-011.1.9": "expected-fail", "EX-011.1.10": "test-defect"})
        self.assertEqual(self.bdd("classify", "FEAT-011", "--expect", "red")[0], 1)

    def test_5_the_drivers_and_steps_type_check(self):
        done = subprocess.run([NPM, "run", "typecheck", "--prefix", "tests"], cwd=self.root, capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    def test_6_a_tag_selects_whole_features_only(self):
        report = self.root / "prefix.xml"
        done = subprocess.run([NODE, "tests/run.mjs", "--tag", "FEAT-01", "--out", str(report)], cwd=self.root,
                              capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertNotEqual(done.returncode, 0)
        self.assertEqual(junit.parse_file(report), [], "FEAT-01 must not select FEAT-010")


if __name__ == "__main__":
    unittest.main()
