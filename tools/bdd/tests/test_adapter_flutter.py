"""The dart-flutter-test adapter: its package is complete and pinned, the scaffold is wired the way `bdd` expects, the script that
turns Flutter's JSON events into the JUnit report is right, and (where Flutter is installed and the network is allowed) a fresh
scaffold really runs green, every core step works and red looks like red.

The structural tests run everywhere. The contract tests need the Flutter SDK on PATH, package downloads and
GREENLIGHT_FLUTTER_ADAPTER_TESTS=1; the CI job for the adapter sets it.
"""
import importlib.util
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree

from bddlib import adapter, initcmd, state
from bddlib import config as cfg

from tests import adapter_contract_support as support

REPO = Path(__file__).resolve().parents[3]
ADAPTER = REPO / "adapters" / "dart-flutter-test"
TEMPLATES = ADAPTER / "templates"
FIXTURES = Path(__file__).parent / "fixtures" / "dart-flutter-test"
RUN_CONTRACT = bool(shutil.which("flutter")) and os.environ.get("GREENLIGHT_FLUTTER_ADAPTER_TESTS") == "1"

ORDERS = """@FEAT-003
Feature: Orders

  @R-003.1
  Rule: Orders can be placed

    @EX-003.1.1
    Scenario: A component that is not on the screen yet
      When alice opens the counter page
      And alice clicks checkout button
      Then alice sees count showing:
        | text |
        | 5    |

    @EX-003.1.2
    Scenario: Seeding needs a seam
      Given the following order exist:
        | id |
        | 1  |
      When alice opens the counter page
      Then alice sees count showing:
        | text |
        | 0    |

    @EX-003.1.3
    Scenario: A name nobody mapped
      When alice opens the cart page
      Then alice sees count showing:
        | text |
        | 0    |

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
      Then alice sees count showing:
        | text |
        | 0    |
"""
RED = {"EX-003.1.1": "expected-fail", "EX-003.1.2": "expected-fail", "EX-003.1.3": "test-defect",
       "EX-003.1.4": "expected-fail", "EX-003.1.5": "test-defect"}


def load_script():
    spec = importlib.util.spec_from_file_location("run_flutter", TEMPLATES / "tests" / "run_flutter.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def events(*items: dict) -> list[str]:
    return [json.dumps(item) for item in items]


def started(test_id: int, name: str, at: int = 0) -> dict:
    return {"type": "testStart", "time": at, "test": {"id": test_id, "name": name}}


def done(test_id: int, result: str = "success", at: int = 0, **more) -> dict:
    return {"type": "testDone", "testID": test_id, "result": result, "time": at, "skipped": False, "hidden": False, **more}


class PackageTest(unittest.TestCase):
    def test_the_contract_files_exist(self):
        for name in adapter.REQUIRED + ("ci.md",):
            self.assertTrue((ADAPTER / name).exists(), name)
        self.assertEqual(adapter.load(ADAPTER)["name"], "dart-flutter-test")

    def test_the_config_block_is_valid_and_complete(self):
        config = support.config_of(ADAPTER)
        (scan,), (run,) = config.scans, config.runs
        self.assertEqual(run.adapter, "dart-flutter-test")
        self.assertIn("tests/run_flutter.py --tag {tag}", run.by_tag)
        self.assertEqual((run.report, run.shuffle, run.isolated), ("--out {out}", "--seed {seed}", '--scenario "{scenario}"'))
        self.assertLessEqual({"DART_", "FLUTTER_TEST"}, set(run.scrub_env))
        self.assertTrue(scan.assert_patterns and scan.sleep_patterns and scan.stub_patterns)

    def test_the_test_tooling_is_pinned_and_hashed(self):
        wanted = adapter.load(ADAPTER)["requires"]["packages"]
        pubspec = (TEMPLATES / "tests" / "pubspec.yaml").read_text(encoding="utf-8")
        lock = (TEMPLATES / "tests" / "pubspec.lock").read_text(encoding="utf-8")
        for name in wanted:
            self.assertIn(f"  {name}:", pubspec)
        for name in ("cucumber_gherkin", "cucumber_messages", "flutter_lints"):
            self.assertRegex(pubspec, rf"(?m)^  {name}: \d+\.\d+\.\d+$", f"{name} is pinned to one version")
        hosted = re.findall(r"(?ms)^  (\w+):\n    dependency:.*?\n    description:\n      name: \w+\n      sha256: \"?([0-9a-f]{64})\"?\n", lock)
        self.assertGreaterEqual(len(hosted), 20)
        self.assertEqual(lock.count("source: hosted"), len(hosted), "every hosted package has a hash")

    def test_every_support_file_is_shipped_and_every_step_expression_is_an_anchored_regular_expression(self):
        shipped = {p.relative_to(TEMPLATES).as_posix() for p in adapter.template_files(ADAPTER)}
        for name in adapter.load(ADAPTER)["paths"]["support"]:
            self.assertIn(name, shipped)
        source = (TEMPLATES / "tests" / "steps" / "core_steps.dart").read_text(encoding="utf-8")
        expressions = re.findall(r"(?:given|when|then)\(r'(.+?)', \(world", source)
        self.assertLessEqual(20, len(expressions))
        for expression in expressions:
            re.compile(expression)
            self.assertTrue(expression.startswith("^") and expression.endswith("$"), expression)

    def test_a_step_that_asserts_is_not_flagged_and_one_that_does_not_is(self):
        text = ("import 'definition.dart';\n\nfinal extra = <StepDefinition>[\n  then(r'^it is fine$', (world, words, argument) async {\n"
                "    return;\n  }),\n];\n")
        support.assert_scan_tells_an_assertion_free_step(self, "dart-flutter-test", "tests/steps/extra.dart", text)

    def test_init_suggests_it_for_a_flutter_app_and_not_for_a_plain_dart_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / "pubspec.yaml").write_text("name: app\ndependencies:\n  flutter:\n    sdk: flutter\n", encoding="utf-8")
            self.assertEqual([name for name, _ in initcmd.detect(root)], ["dart-flutter-test"])
            (root / "pubspec.yaml").write_text("name: tool\ndependencies:\n  args: ^2.0.0\n", encoding="utf-8")
            self.assertEqual(initcmd.detect(root), [])

    def test_apply_registers_the_plumbing_as_bound_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / ".bdd").mkdir()
            adapter.apply(root, "dart-flutter-test")
            bound = {p.relative_to(root).as_posix() for p in cfg.load(root).support_files}
            self.assertEqual(bound, {"tests/bdd_test.dart", "tests/run_flutter.py", "tests/pubspec.yaml", "tests/pubspec.lock",
                                     "tests/analysis_options.yaml"})

    def test_the_fixture_features_name_only_core_instructions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / ".bdd").mkdir()
            adapter.apply(root, "dart-flutter-test")
            state.create(root, "FEAT-000", "Sample", "standard")
            shutil.copyfile(FIXTURES / "full.feature", root / "tests" / "features" / "full.feature")
            (root / "tests" / "features" / "orders.feature").write_text(ORDERS, encoding="utf-8", newline="\n")
            code, out, _ = support.run_bdd(root, "lint", "tests/features")
            self.assertEqual(code, 1, "the moon step is on purpose not in the vocabulary")
            self.assertEqual(out.count("L002"), 1, out)


class ReportScriptTest(unittest.TestCase):
    """What `flutter test --reporter json` says, as the JUnit file `bdd` reads."""

    def junit(self, *items: dict) -> ElementTree.Element:
        script = load_script()
        scenarios, loading, other = script.collect(events(*items))
        self.assertEqual(script.loading_problems(loading, other), [])
        return script.to_junit(scenarios)

    def test_a_passed_a_failed_a_thrown_and_a_skipped_scenario(self):
        suite = self.junit(
            started(1, "loading tests/bdd_test.dart"), done(1, hidden=True),
            started(2, "Two numbers are added", 10), done(2, at=40),
            started(3, "An assertion fails", 50),
            {"type": "error", "testID": 3, "error": "Expected: <4>\n  Actual: <3>", "stackTrace": "at x", "isFailure": True, "time": 60},
            done(3, "failure", at=61),
            started(4, "A seam is missing", 70),
            {"type": "error", "testID": 4, "error": "ExpectedMissing: BDD_EXPECTED_MISSING: a way to create order records does not exist yet",
             "stackTrace": "at y", "isFailure": False, "time": 71},
            done(4, "error", at=72),
            started(5, "Not today", 80), done(5, at=81, skipped=True),
        )
        cases = {case.get("name"): case for case in suite.findall("testcase")}
        self.assertEqual((suite.get("tests"), suite.get("failures")), ("4", "2"))
        self.assertIsNone(cases["Two numbers are added"].find("failure"))
        self.assertEqual(cases["Two numbers are added"].get("time"), "0.030")
        self.assertEqual(cases["An assertion fails"].find("failure").get("type"), "TestFailure")
        thrown = cases["A seam is missing"].find("failure")
        self.assertEqual(thrown.get("type"), "ExpectedMissing")
        self.assertIn("BDD_EXPECTED_MISSING", thrown.get("message"))
        self.assertIsNotNone(cases["Not today"].find("skipped"))

    def test_the_exception_a_widget_test_threw_is_read_from_the_framework_report(self):
        """A widget test fails with 'Test failed. See exception logs above.'; the real exception is only in what Flutter printed."""
        printed = ("══╡ EXCEPTION CAUGHT BY FLUTTER TEST FRAMEWORK ╞══\nThe following ExpectedMissing was thrown running a test:\n"
                   "BDD_EXPECTED_MISSING: the checkout button component on the screen does not exist yet\n\n"
                   "When the exception was thrown, this was the stack:\n#0 runStep\n")
        suite = self.junit(started(1, "A component that is not on the screen yet"), {"type": "print", "testID": 1, "message": printed},
                           {"type": "error", "testID": 1, "error": "Test failed. See exception logs above.\nThe test description was: x",
                            "stackTrace": "", "isFailure": False}, done(1, "error"))
        failure = suite.find("testcase").find("failure")
        self.assertEqual(failure.get("type"), "ExpectedMissing")
        self.assertIn("BDD_EXPECTED_MISSING", failure.get("message"))
        self.assertNotIn("exception logs above", failure.text)

    def test_a_scenario_title_in_any_script_survives(self):
        suite = self.junit(started(1, "兩個數字相加 — Café: two numbers"), done(1))
        self.assertEqual(suite.find("testcase").get("name"), "兩個數字相加 — Café: two numbers")

    def test_a_failed_loading_step_is_a_problem_and_not_a_scenario(self):
        script = load_script()
        scenarios, loading, other = script.collect(events(
            started(1, "loading tests/bdd_test.dart"),
            {"type": "error", "testID": 1, "error": "Error: Compilation failed", "stackTrace": "", "isFailure": False},
            done(1, "error", hidden=True)))
        self.assertEqual(scenarios, {})
        self.assertEqual(script.loading_problems(loading, other), ["Error: Compilation failed"])

    def test_the_tag_the_seed_and_the_scenario_travel_in_the_environment(self):
        script = load_script()
        args = script.parse_arguments(["--tag", "FEAT-007", "--out", "r.xml", "--seed", "7", "--scenario", "兩個數字相加"])
        env = script.environment(args)
        self.assertEqual((env["BDD_TAG"], env["BDD_SEED"], env["BDD_SCENARIO"]), ("FEAT-007", "7", "兩個數字相加"))


@unittest.skipUnless(RUN_CONTRACT, "needs the Flutter SDK on PATH, package downloads and GREENLIGHT_FLUTTER_ADAPTER_TESTS=1")
class ContractTest(unittest.TestCase):
    """A fresh scaffold: the sample passes, every core step works against an in-memory system, red looks like red."""

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.TemporaryDirectory()
        cls.root = Path(cls.dir.name).resolve()
        (cls.root / ".bdd").mkdir()
        adapter.apply(cls.root, "dart-flutter-test")
        for number, title in ((0, "Sample"), (2, "Core"), (3, "Orders"), (4, "Unicode")):
            state.create(cls.root, f"FEAT-{number:03d}", title, "standard")
        done = subprocess.run([shutil.which("flutter"), "pub", "get", "--enforce-lockfile"], cwd=cls.root / "tests",
                              capture_output=True, text=True, timeout=900)
        if done.returncode != 0:
            raise RuntimeError(f"flutter pub get failed:\n{done.stdout}\n{done.stderr}")

    @classmethod
    def tearDownClass(cls):
        cls.dir.cleanup()

    def bdd(self, *argv: str) -> tuple[int, str, str]:
        return support.run_bdd(self.root, *argv)

    def results(self, feature: str) -> dict[str, str]:
        code, out, err = self.bdd("classify", feature, "--json")
        self.assertIn(code, (0, 1), err)
        return {row["example"]: row["result"] for row in json.loads(out)["scenarios"]}

    def use_system(self, full: bool) -> None:
        drivers, features = self.root / "tests" / "drivers", self.root / "tests" / "features"
        if full:
            shutil.copyfile(FIXTURES / "system.dart.fixture", drivers / "system.dart")
            shutil.copyfile(FIXTURES / "operations.dart.fixture", drivers / "operations.dart")
            shutil.copyfile(FIXTURES / "full.feature", features / "full.feature")
            (features / "orders.feature").unlink(missing_ok=True)
        else:
            for name in ("system.dart", "operations.dart"):
                shutil.copyfile(TEMPLATES / "tests" / "drivers" / name, drivers / name)
            (features / "full.feature").unlink(missing_ok=True)
            operations = drivers / "operations.dart"
            operations.write_text(operations.read_text(encoding="utf-8").replace(
                "  // 'checkout button': () => find.widgetWithText(ElevatedButton, 'Check out'),",
                "  'checkout button': () => find.widgetWithText(ElevatedButton, 'Check out'),"), encoding="utf-8", newline="\n")
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
        self.assertEqual(self.results("FEAT-003"), RED)
        self.assertEqual(self.bdd("classify", "FEAT-003", "--expect", "red")[0], 1)

    def test_3_every_core_step_works(self):
        self.use_system(full=True)
        code, out, err = self.bdd("run", "FEAT-002")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.results("FEAT-002"), {"EX-002.1.1": "pass", "EX-002.1.2": "pass", "EX-002.1.3": "pass", "EX-002.1.4": "pass",
                                                   "EX-002.2.1": "pass", "EX-002.2.2": "pass", "EX-002.3.1": "pass", "EX-002.4.1": "pass",
                                                   "EX-002.5.1": "pass", "EX-002.5.2": "pass", "EX-002.5.3": "pass"})
        self.assertEqual(self.bdd("classify", "FEAT-002", "--expect", "green")[0], 0)

    def test_4_the_scaffold_passes_the_scan_the_lint_and_the_analyzer(self):
        self.use_system(full=False)
        (self.root / "tests" / "features" / "orders.feature").unlink()
        code, out, _ = self.bdd("scan", "FEAT-000")
        self.assertEqual((code, out.strip()), (0, "FEAT-000: no findings"), out)
        self.assertEqual(self.bdd("lint", "tests/features")[0], 0)
        done = subprocess.run([shutil.which("flutter"), "analyze"], cwd=self.root / "tests", capture_output=True, text=True, timeout=600)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    def test_5_scenario_titles_that_are_not_plain_ascii_still_map_to_their_scenarios(self):
        self.use_system(full=False)
        (self.root / "tests" / "features" / "unicode.feature").write_text(support.UNICODE_TITLES, encoding="utf-8", newline="\n")
        for flags in ((), ("--shuffle", "--seed", "3"), ("--isolated",)):
            with self.subTest(flags=flags):
                code, out, err = self.bdd("run", "FEAT-004", *flags)
                self.assertEqual(code, 0, out + err)
                self.assertEqual(self.results("FEAT-004"), {f"EX-004.1.{n}": "pass" for n in (1, 2, 3)})

    def test_6_a_file_that_does_not_compile_leaves_every_scenario_not_run(self):
        self.use_system(full=False)
        broken = self.root / "tests" / "steps" / "broken.dart"
        broken.write_text("this is not dart\n", encoding="utf-8", newline="\n")
        steps = self.root / "tests" / "steps" / "project_steps.dart"
        original = steps.read_text(encoding="utf-8")
        steps.write_text("import 'broken.dart';\n" + original, encoding="utf-8", newline="\n")
        try:
            code, out, err = self.bdd("run", "FEAT-000")
            self.assertNotEqual(code, 0, out + err)
            self.assertEqual(set(self.results("FEAT-000").values()), {"not-run"})
        finally:
            steps.write_text(original, encoding="utf-8", newline="\n")
            broken.unlink()


if __name__ == "__main__":
    unittest.main()
