"""The shop-web reference app, and the ts-playwright-bdd adapter proved on a real Next.js application.

The app's own checks are offline. The contract tests build the app, install the pinned test tooling and drive a real
browser, so they need node, npm and network access and run only when GREENLIGHT_NODE_ADAPTER_TESTS=1 is set (the CI job
for the reference apps sets it). The combined test also needs pytest and pytest-bdd in the interpreter that runs the tests.
"""
import contextlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from bddlib import adapter, cli, state
from bddlib import config as cfg

REPO = Path(__file__).resolve().parents[3]
APP = REPO / "evals" / "apps" / "shop-web"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "shop_web"
NODE, NPM = shutil.which("node"), shutil.which("npm")
RUN_NODE = os.environ.get("GREENLIGHT_NODE_ADAPTER_TESTS") == "1" and bool(NODE and NPM)
HAVE_PYTEST = all(importlib.util.find_spec(name) for name in ("pytest", "pytest_bdd"))
PORT = "3107"
START = ("  webServer: { command: 'node node_modules/next/dist/bin/next start -p " + PORT + "', cwd: '..', "
         "url: 'http://127.0.0.1:" + PORT + "/login', reuseExistingServer: false, timeout: 60_000, "
         "env: { SHOP_TEST_ENDPOINTS: '1' } },")
TEMPLATE_START = "  // webServer: { command: 'npm start', url: 'http://localhost:3000', reuseExistingServer: false },"


def sh(command: list[str], cwd: Path) -> None:
    done = subprocess.run(command, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if done.returncode != 0:
        raise AssertionError(f"{' '.join(command)} failed in {cwd}:\n{done.stdout}\n{done.stderr}")


def copy_app(target: Path) -> None:
    shutil.copytree(APP, target, ignore=shutil.ignore_patterns("node_modules", ".next"), dirs_exist_ok=True)


def install_tooling(app: Path, tooling: Path) -> None:
    """The app's packages and the test tooling, each from its own lockfile, and the browser."""
    sh([NPM, "ci", "--ignore-scripts", "--no-audit", "--no-fund"], app)
    sh([NPM, "ci", "--ignore-scripts", "--no-audit", "--no-fund", "--prefix", str(tooling)], app)
    sh([NODE, str(tooling / "node_modules" / "@playwright" / "test" / "cli.js"), "install", "chromium"], app)


def build(app: Path) -> None:
    sh([NPM, "run", "build"], app)


def put_seams(tests: Path) -> None:
    """What the step-engineer would write for this application: the seams, the names, the start of the server."""
    for name in ("operations.ts", "system.ts"):
        shutil.copyfile(FIXTURES / name, tests / "drivers" / name)
    config = tests / "bdd.config.ts"
    text = config.read_text(encoding="utf-8")
    assert TEMPLATE_START in text, "the adapter's configuration changed: update the start of the server here"
    config.write_text(text.replace(TEMPLATE_START, START), encoding="utf-8", newline="\n")


def bdd(root: Path, *argv: str) -> tuple[int, str, str]:
    out, err, here = io.StringIO(), io.StringIO(), os.getcwd()
    os.chdir(root)
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(list(argv))
    finally:
        os.chdir(here)
    return code, out.getvalue(), err.getvalue()


class AppTest(unittest.TestCase):
    def test_the_dependencies_are_pinned_exactly_and_the_lockfile_agrees(self):
        package = json.loads((APP / "package.json").read_text(encoding="utf-8"))
        locked = json.loads((APP / "package-lock.json").read_text(encoding="utf-8"))["packages"][""]["dependencies"]
        self.assertEqual(package["dependencies"], locked)
        for name, version in package["dependencies"].items():
            with self.subTest(package=name):
                self.assertRegex(version, r"^\d+\.\d+\.\d+$")

    def test_the_app_has_no_test_setup_of_its_own(self):
        self.assertFalse((APP / "tests").exists())
        self.assertFalse((APP / ".bdd").exists())

    def test_the_evaluation_harness_knows_the_app_its_requests_and_the_answers(self):
        spec = importlib.util.spec_from_file_location("run_e2e", REPO / "evals" / "run_e2e.py")
        harness = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(harness)
        requests = {p.stem for p in (REPO / "evals" / "requests").glob("*.md")}
        web = {name: kind for name, kind in harness.REQUEST_KINDS.items() if kind["app"] == "shop-web"}
        self.assertEqual(set(web), {"minimum-order", "login-return"})
        self.assertTrue(set(web) <= requests)
        for name, kind in web.items():
            with self.subTest(request=name):
                self.assertTrue((harness.APPS / kind["app"]).is_dir())
                self.assertIn(kind["adapter"], adapter.available())
                self.assertTrue((REPO / "evals" / "requests" / f"{name}.answers.json").is_file())

    def test_the_fixture_features_and_seams_fit_the_adapter(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / ".bdd").mkdir()
            adapter.apply(root, "ts-playwright-bdd")
            put_seams(root / "tests")
            shutil.copyfile(FIXTURES / "cart.feature", root / "tests" / "features" / "cart.feature")
            state.create(root, "FEAT-020", "Cart", "standard")
            code, out, err = bdd(root, "lint", "tests/features")
            self.assertEqual(code, 0, out + err)
            self.assertEqual(bdd(root, "scan", "FEAT-020")[0], 0)


@unittest.skipUnless(RUN_NODE, "needs node, npm, network and GREENLIGHT_NODE_ADAPTER_TESTS=1")
class ShopWebContractTest(unittest.TestCase):
    """The adapter scaffolded into a copy of the Next.js app: the sample and the shop's own feature run green."""

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.TemporaryDirectory()
        cls.root = Path(cls.dir.name).resolve()
        copy_app(cls.root)
        (cls.root / ".bdd").mkdir()
        adapter.apply(cls.root, "ts-playwright-bdd")
        state.create(cls.root, "FEAT-000", "Sample", "standard")
        state.create(cls.root, "FEAT-020", "Cart", "standard")
        install_tooling(cls.root, cls.root / "tests")
        # the adapter's own sample runs before the application's seams replace the sample's page names
        cls.sample = (bdd(cls.root, "run", "FEAT-000")[0], bdd(cls.root, "classify", "FEAT-000", "--expect", "green")[0])
        put_seams(cls.root / "tests")
        shutil.copyfile(FIXTURES / "cart.feature", cls.root / "tests" / "features" / "cart.feature")
        build(cls.root)

    @classmethod
    def tearDownClass(cls):
        cls.dir.cleanup()

    def test_1_the_sample_feature_is_green_in_a_browser(self):
        self.assertEqual(self.sample, (0, 0))

    def test_2_the_shops_cart_and_checkout_run_green_against_the_real_app(self):
        code, out, err = bdd(self.root, "run", "FEAT-020")
        self.assertEqual(code, 0, out + err)
        code, out, _ = bdd(self.root, "classify", "FEAT-020", "--json")
        self.assertEqual(code, 0, out)
        report = json.loads(out)
        self.assertEqual({row["example"]: row["result"] for row in report["scenarios"]},
                         {f"EX-020.{r}.{e}": "pass" for r, e in ((1, 1), (1, 2), (2, 1), (3, 1), (3, 2), (3, 3))})

    def test_3_a_feature_that_the_app_cannot_satisfy_is_a_red(self):
        broken = self.root / "tests" / "features" / "broken.feature"
        broken.write_text(FIXTURES.joinpath("cart.feature").read_text(encoding="utf-8").replace("FEAT-020", "FEAT-021")
                          .replace("R-020", "R-021").replace("EX-020", "EX-021").replace("$17.00", "$99.99"),
                          encoding="utf-8", newline="\n")
        state.create(self.root, "FEAT-021", "Broken", "standard")
        self.addCleanup(broken.unlink)
        self.assertEqual(bdd(self.root, "run", "FEAT-021")[0], 0)
        code, out, _ = bdd(self.root, "classify", "FEAT-021", "--json")
        rows = {row["example"]: row["result"] for row in json.loads(out)["scenarios"]}
        self.assertEqual(rows["EX-021.2.1"], "expected-fail")             # the wrong total is an assertion failure
        self.assertEqual(rows["EX-021.1.1"], "pass")


COMBINED_RULES = "# Rules\n\nR-030.1 Adding two numbers gives their sum.\nR-030.2 The cart shows the total of its lines.\n"
API_FEATURE = """@FEAT-030
Feature: Totals, in the backend and on the cart page

  @R-030.1
  Rule: Adding two numbers gives their sum

    @EX-030.1.1
    Scenario: Two numbers are added
      When add is called with:
        | a | b |
        | 2 | 3 |
      Then the result is:
        \"\"\"
        5
        \"\"\"

    @EX-030.1.2
    Scenario: A negative number is refused
      When add is called with:
        | a  | b |
        | -1 | 3 |
      Then the call fails with negative input
"""


@unittest.skipUnless(RUN_NODE and HAVE_PYTEST, "needs node, npm, network, pytest and GREENLIGHT_NODE_ADAPTER_TESTS=1")
class TwoAdaptersContractTest(unittest.TestCase):
    """A backend (python-pytest-bdd in api/) and a web front end (ts-playwright-bdd in web/) in one repository."""

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.TemporaryDirectory()
        cls.root = Path(cls.dir.name).resolve()
        (cls.root / ".bdd").mkdir()
        adapter.apply(cls.root, "python-pytest-bdd", "api")
        copy_app(cls.root / "web")
        adapter.apply(cls.root, "ts-playwright-bdd", "web")
        web_tests = cls.root / "web" / "tests"
        put_seams(web_tests)
        (web_tests / "features" / "sample.feature").unlink()
        (cls.root / "api" / "tests" / "features" / "sample.feature").unlink()
        (cls.root / "api" / "tests" / "features" / "totals.feature").write_text(API_FEATURE, encoding="utf-8", newline="\n")
        cart = FIXTURES.joinpath("cart.feature").read_text(encoding="utf-8")
        web = cart.split("  @R-020.2")[1].split("  @R-020.3")[0]
        (web_tests / "features" / "cart.feature").write_text(
            "@FEAT-030\nFeature: The cart page\n\n  @R-030.2" + web.replace("EX-020.2", "EX-030.2"), encoding="utf-8", newline="\n")
        feature_dir = state.create(cls.root, "FEAT-030", "Totals", "standard")
        (feature_dir / "rules.md").write_text(COMBINED_RULES, encoding="utf-8", newline="\n")
        install_tooling(cls.root / "web", web_tests)
        build(cls.root / "web")

    @classmethod
    def tearDownClass(cls):
        cls.dir.cleanup()

    def test_1_the_configuration_has_two_adapters_in_two_folders(self):
        config = cfg.load(self.root)
        self.assertEqual({r.adapter: r.base for r in config.runs}, {"python-pytest-bdd": "api", "ts-playwright-bdd": "web"})
        self.assertEqual(config.feature_dirs, (self.root / "api/tests/features", self.root / "web/tests/features"))

    def test_2_one_run_covers_the_api_and_the_ui_scenarios(self):
        self.assertEqual(bdd(self.root, "lint", "api/tests/features", "web/tests/features")[0], 0)
        code, out, err = bdd(self.root, "run", "FEAT-030")
        self.assertEqual(code, 0, out + err)
        self.assertIn("3 passed", out)
        code, out, _ = bdd(self.root, "classify", "FEAT-030", "--json")
        report = json.loads(out)
        self.assertEqual(code, 0, out)
        self.assertEqual({row["example"]: row["result"] for row in report["scenarios"]},
                         {"EX-030.1.1": "pass", "EX-030.1.2": "pass", "EX-030.2.1": "pass"})

    def test_3_the_trace_spans_both_folders_without_gaps(self):
        code, out, err = bdd(self.root, "trace", "FEAT-030", "--json")
        self.assertIn(code, (0, 1), err)
        report = json.loads(out)
        self.assertEqual(report["totals"]["scenarios"], 3)
        self.assertEqual([g["code"] for g in report["gaps"] if g["code"] in ("T001", "T002")], [])

    def test_4_either_adapter_can_be_run_alone_and_isolated(self):
        code, out, err = bdd(self.root, "run", "FEAT-030", "--adapter", "ts-playwright-bdd")
        self.assertEqual(code, 0, out + err)
        self.assertIn("1 passed", out)
        code, out, err = bdd(self.root, "run", "FEAT-030", "--isolated")
        self.assertEqual(code, 0, out + err)
        self.assertIn("3 run(s) (isolated)", out)


if __name__ == "__main__":
    unittest.main()
