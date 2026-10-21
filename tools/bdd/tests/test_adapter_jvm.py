"""The java-cucumber-spring and kotlin-android adapters: the packages are complete, detection finds them, the defaults
tell a missing seam from a broken test, and (where Maven or Gradle and a JDK are installed) a fresh scaffold really runs
green and red looks like red.

The real runs need a JDK and the build tool on PATH and download dependencies on the first run, so they are skipped
without them; the CI jobs of these adapters install them.
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
FIXTURES = Path(__file__).parent / "fixtures" / "jvm"
SPRING = REPO / "adapters" / "java-cucumber-spring"
KOTLIN = REPO / "adapters" / "kotlin-android"
# The real runs download dependencies and take minutes, so they run only where the adapters' CI jobs (or a person who
# set the variable) ask for them, and only with the tools installed.
WANTED = os.environ.get("GREENLIGHT_JVM_ADAPTER_TESTS") == "1"
HAVE_JAVA = WANTED and shutil.which("java") is not None
HAVE_MAVEN = HAVE_JAVA and shutil.which("mvn") is not None
HAVE_GRADLE = HAVE_JAVA and shutil.which("gradle") is not None
HAVE_ANDROID = HAVE_GRADLE and bool(os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT"))

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
      Then the order records are:
        | id |
        | 1  |

    @EX-001.1.3
    Scenario: A name nobody mapped (really) [x] and more
      When alice calls cancel order
      Then the request succeeds
"""

KOTLIN_ORDERS = """@FEAT-001
Feature: Orders

  @R-001.1
  Rule: Orders can be counted

    @EX-001.1.1
    Scenario: Seeding needs a seam
      Given the following order exist:
        | id |
        | 1  |
      Then the order records are:
        | id |
        | 1  |

    @EX-001.1.2
    Scenario: A name nobody mapped (really) [x] and more
      When cancel is called with:
        | id |
        | 1  |
      Then the result is:
        \"\"\"
        1
        \"\"\"
"""


def tool_free_config(name: str) -> cfg.Config:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / ".bdd").mkdir()
        (root / ".bdd" / "config.toml").write_text(adapter.config_block(adapter.load(REPO / "adapters" / name)), encoding="utf-8")
        return cfg.load(root)


SPRING_UNICODE = """@FEAT-004
Feature: Titles that are not plain ASCII

  @R-004.1
  Rule: A scenario keeps its title whatever the language

    @EX-004.1.1
    Scenario: Café: a product is stored and read back
      Given the following product exist:
        | id | name |
        | 1  | tea  |
      Then the product records are:
        | id | name |
        | 1  | tea  |

    @EX-004.1.2
    Scenario: 商品可以儲存並讀回
      Given the following product exist:
        | id | name |
        | 2  | milk |
      Then the product records are:
        | id | name |
        | 2  | milk |

    @EX-004.1.3
    Scenario: 茶 and 咖啡 (tea and coffee) are both stored
      Given the following product exist:
        | id | name   |
        | 3  | coffee |
      Then the product records are:
        | id | name   |
        | 3  | coffee |
"""

KOTLIN_UNICODE = """@FEAT-004
Feature: Titles that are not plain ASCII

  @R-004.1
  Rule: A scenario keeps its title whatever the language

    @EX-004.1.1
    Scenario: Café: two numbers are added
      When add is called with:
        | a | b |
        | 2 | 3 |
      Then the result is:
        \"\"\"
        5
        \"\"\"

    @EX-004.1.2
    Scenario: 兩個數字相加
      When add is called with:
        | a | b |
        | 4 | 5 |
      Then the result is:
        \"\"\"
        9
        \"\"\"

    @EX-004.1.3
    Scenario: 負數會被拒絕 (a negative number is refused)
      When add is called with:
        | a  | b |
        | -1 | 3 |
      Then the call fails with negative input
"""


class PackageTest(unittest.TestCase):
    def test_the_profiles_and_run_tables_say_what_the_guides_say(self):
        spring, kotlin = adapter.load(SPRING), adapter.load(KOTLIN)
        self.assertEqual(spring["profiles"], ["base", "api", "data"])
        self.assertEqual(kotlin["profiles"], ["base", "lib", "data"])
        for name, config in (("java-cucumber-spring", tool_free_config("java-cucumber-spring")),
                             ("kotlin-android", tool_free_config("kotlin-android"))):
            with self.subTest(adapter=name):
                (run,) = config.runs
                self.assertIn("cucumber.filter.tags=@{tag}", run.by_tag)
                self.assertIn("cucumber.plugin=junit:{out}", run.report)
                self.assertIn("cucumber.execution.order=random", run.shuffle)
                self.assertIn("cucumber.execution.order.random.seed={seed}", run.shuffle)
                self.assertIn("{scenario:regex}", run.isolated)             # a name is escaped, never pasted into a pattern
                self.assertNotIn("\\Q", run.isolated)

    def test_the_run_words_escape_a_scenario_name_that_tries_to_end_the_quotation(self):
        for name in ("java-cucumber-spring", "kotlin-android"):
            with self.subTest(adapter=name):
                (run,) = tool_free_config(name).runs
                from bddlib import runner
                with tempfile.TemporaryDirectory() as tmp:
                    words = runner.build_command(run, Path(tmp), "FEAT-001", Path("out.xml"), scenario="a\\E.*(b)")
                filter_word = next(w for w in words if "filter.name" in w)
                self.assertTrue(filter_word.split("=", 1)[1].startswith("\\A"), filter_word)
                self.assertIn("a\\\\E\\.\\*\\(b\\)", filter_word)               # every metacharacter, the backslash too

    def test_detection_finds_the_adapters_in_their_build_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "pom.xml").write_text("<artifactId>spring-boot-starter-parent</artifactId>", encoding="utf-8")
            self.assertEqual([n for n, _ in initcmd.detect(root) if n.endswith("spring")], ["java-cucumber-spring"])
            (root / "pom.xml").unlink()
            (root / "build.gradle.kts").write_text('plugins { id("com.android.application") }', encoding="utf-8")
            self.assertEqual([n for n, _ in initcmd.detect(root) if n == "kotlin-android"], ["kotlin-android"])
            (root / "build.gradle.kts").write_text('plugins { kotlin("jvm") }', encoding="utf-8")
            self.assertEqual([n for n, _ in initcmd.detect(root) if n == "kotlin-android"], [])

    def test_the_bound_plumbing_is_listed_as_support(self):
        for path in (SPRING, KOTLIN):
            with self.subTest(adapter=path.name):
                support = adapter.load(path)["paths"]["support"]
                self.assertTrue(any(name.endswith("junit-platform.properties") for name in support))
                self.assertTrue(any("RunCucumberTest" in name for name in support))

    def test_the_gradle_script_forwards_cucumber_settings_and_always_runs(self):
        text = (KOTLIN / "templates" / "greenlight.gradle.kts").read_text(encoding="utf-8")
        for needle in ('startsWith("cucumber.")', "upToDateWhen { false }", "useJUnitPlatform()"):
            self.assertIn(needle, text)

    def test_an_adapter_with_a_data_profile_binds_the_query_count_and_ships_a_counter(self):
        self.assertIn("C.QUERY.COUNT", (SPRING / "templates/src/test/java/greenlight/steps/CoreSteps.java").read_text(encoding="utf-8"))
        self.assertIn("C.QUERY.COUNT", (KOTLIN / "templates/src/test/kotlin/greenlight/steps/CoreSteps.kt").read_text(encoding="utf-8"))
        self.assertTrue((SPRING / "templates/src/test/java/greenlight/drivers/QueryCounter.java").is_file())
        self.assertTrue((KOTLIN / "templates/src/test/kotlin/greenlight/drivers/QueryCounter.kt").is_file())


class ClassifyDefaultsTest(unittest.TestCase):
    def kind(self, name: str, text: str, outcome: str = junit.FAILED) -> str:
        return classify.classify_case(junit.Case("t", "c", outcome, text), list(tool_free_config(name).runs))

    def test_unbuilt_seams_and_failed_assertions_are_expected_on_both_stacks(self):
        for name in ("java-cucumber-spring", "kotlin-android"):
            for text in ("greenlight.drivers.Errors$ExpectedMissing: BDD_EXPECTED_MISSING: a way to create order records does not exist yet",
                         "java.lang.AssertionError: the request should succeed but got status 404: null",
                         "org.opentest4j.AssertionFailedError: expected: <5> but was: <4>"):
                with self.subTest(adapter=name, text=text[:40]):
                    self.assertEqual(self.kind(name, text), classify.EXPECTED)

    def test_broken_wiring_and_builds_are_defects_even_when_an_assertion_is_mentioned(self):
        spring = ("io.cucumber.core.runner.UndefinedStepException: The step 'x' is undefined",
                  "Failed to load ApplicationContext for [WebMergedContextConfiguration] AssertionError",
                  "NotMapped: no API operation named 'cancel order' in Operations.java",
                  "[ERROR] COMPILATION ERROR : cannot find symbol",
                  "java.lang.ClassNotFoundException: contract.Application")
        kotlin = ("io.cucumber.core.runner.UndefinedStepException: The step 'x' is undefined",
                  "e: file:///x/Operations.kt:12:5 Unresolved reference 'cancel'",
                  "java.lang.RuntimeException: Method getMainLooper in android.os.Looper not mocked.",
                  "NotMapped: no library operation named 'cancel' in Operations.kt")
        for name, texts in (("java-cucumber-spring", spring), ("kotlin-android", kotlin)):
            for text in texts:
                with self.subTest(adapter=name, text=text[:40]):
                    self.assertEqual(self.kind(name, text), classify.DEFECT)

    def test_anything_else_blocks_as_unknown(self):
        for name in ("java-cucumber-spring", "kotlin-android"):
            self.assertEqual(self.kind(name, "java.lang.NullPointerException"), classify.UNKNOWN)


class ScaffoldCase(unittest.TestCase):
    """A fresh scaffold in a temporary project; the real build tool runs it."""

    fixture = ""
    adapter_name = ""

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.TemporaryDirectory()
        cls.root = Path(cls.dir.name).resolve()
        shutil.copytree(FIXTURES / cls.fixture, cls.root, dirs_exist_ok=True)
        (cls.root / ".bdd").mkdir()
        adapter.apply(cls.root, cls.adapter_name)
        state.create(cls.root, "FEAT-000", "Sample", "standard")
        cls.prepare()

    @classmethod
    def prepare(cls) -> None:
        """Anything the project needs before the first run."""

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

    def edit(self, rel: str, old: str, new: str) -> None:
        path = self.root / rel
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text)
        path.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")

    def add_feature(self, rel: str, text: str, feature: str = "FEAT-001") -> None:
        state.create(self.root, feature, "Orders", "standard")
        (self.root / rel).write_text(text, encoding="utf-8", newline="\n")

    def titles_that_are_not_plain_ascii_map_to_their_scenarios(self, text: str, result: str, run_code: int) -> None:
        """An accented, a Chinese and a mixed title: each report entry must still be found (a scenario nobody found would be
        ``not-run``), in the usual order, shuffled and one scenario per process (the scenario name goes to the runner as a
        filter)."""
        self.add_feature("src/test/resources/features/unicode.feature", text, "FEAT-004")
        for flags in ((), ("--shuffle", "--seed", "3"), ("--isolated",)):
            with self.subTest(flags=flags):
                code, out, err = self.bdd("run", "FEAT-004", *flags)
                self.assertEqual(code, run_code, out + err)
                self.assertEqual(self.results("FEAT-004"), {f"EX-004.1.{n}": result for n in (1, 2, 3)})


@unittest.skipUnless(HAVE_MAVEN, "set GREENLIGHT_JVM_ADAPTER_TESTS=1 with a JDK and Maven on PATH")
class SpringContractTest(ScaffoldCase):
    fixture = "spring-contract"
    adapter_name = "java-cucumber-spring"

    def test_1_the_sample_feature_is_green(self):
        code, out, err = self.bdd("run", "FEAT-000")
        self.assertEqual(code, 0, out + err)
        code, out, _ = self.bdd("classify", "FEAT-000", "--expect", "green")
        self.assertEqual(code, 0, out)

    def test_2_the_scaffold_passes_the_scan_and_the_lint(self):
        code, out, _ = self.bdd("scan", "FEAT-000")
        self.assertEqual((code, out.strip()), (0, "FEAT-000: no findings"), out)
        code, out, _ = self.bdd("lint", "src/test/resources/features")
        self.assertEqual(code, 0, out)

    def test_3_red_looks_like_red_and_a_name_with_metacharacters_runs_alone(self):
        self.add_feature("src/test/resources/features/orders.feature", ORDERS)
        self.edit("src/test/java/greenlight/drivers/Operations.java", '// API.put("place order", new Api("POST", "/orders"));',
                  'API.put("place order", new Api("POST", "/orders"));')
        self.assertEqual(self.bdd("run", "FEAT-001")[0], 0)
        self.assertEqual(self.results("FEAT-001"),
                         {"EX-001.1.1": "expected-fail", "EX-001.1.2": "expected-fail", "EX-001.1.3": "test-defect"})
        self.assertEqual(self.bdd("classify", "FEAT-001", "--expect", "red")[0], 1)         # the unmapped name blocks
        code, out, err = self.bdd("run", "FEAT-001", "--isolated")                            # one process per scenario
        self.assertEqual(code, 0, out + err)
        self.assertIn("3 run(s) (isolated)", out)
        record = json.loads((self.root / ".bdd/.runs/FEAT-001/latest.json").read_text(encoding="utf-8"))
        self.assertEqual(len(record["cases"]), 3)                  # each process ran only its own scenario

    def test_4_a_shuffled_run_is_green(self):
        code, out, err = self.bdd("run", "FEAT-000", "--shuffle", "--seed", "7")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.bdd("classify", "FEAT-000", "--expect", "green")[0], 0)

    def test_5_titles_that_are_not_plain_ascii_map_to_their_scenarios(self):
        self.titles_that_are_not_plain_ascii_map_to_their_scenarios(SPRING_UNICODE, "expected-fail", 0)   # no seam outside the sample


@unittest.skipUnless(HAVE_GRADLE, "set GREENLIGHT_JVM_ADAPTER_TESTS=1 with a JDK and Gradle on PATH")
class KotlinContractTest(ScaffoldCase):
    fixture = "kotlin-contract"
    adapter_name = "kotlin-android"

    @classmethod
    def prepare(cls) -> None:
        # a plain Kotlin/JVM module has the test task `test`; an Android module has testDebugUnitTest
        config = cls.root / ".bdd" / "config.toml"
        config.write_text(config.read_text(encoding="utf-8").replace("testDebugUnitTest", "test"), encoding="utf-8", newline="\n")
        subprocess.run([shutil.which("gradle"), "wrapper", "-q"], cwd=cls.root, check=True, capture_output=True, timeout=600)

    def test_1_the_sample_feature_is_green(self):
        code, out, err = self.bdd("run", "FEAT-000")
        self.assertEqual(code, 0, out + err)
        code, out, _ = self.bdd("classify", "FEAT-000", "--expect", "green")
        self.assertEqual(code, 0, out)

    def test_2_the_scaffold_passes_the_scan_and_the_lint(self):
        code, out, _ = self.bdd("scan", "FEAT-000")
        self.assertEqual((code, out.strip()), (0, "FEAT-000: no findings"), out)
        code, out, _ = self.bdd("lint", "src/test/resources/features")
        self.assertEqual(code, 0, out)

    def test_3_red_looks_like_red_and_a_name_with_metacharacters_runs_alone(self):
        self.add_feature("src/test/resources/features/orders.feature", KOTLIN_ORDERS)
        self.assertEqual(self.bdd("run", "FEAT-001")[0], 0)
        self.assertEqual(self.results("FEAT-001"), {"EX-001.1.1": "expected-fail", "EX-001.1.2": "test-defect"})
        self.assertEqual(self.bdd("classify", "FEAT-001", "--expect", "red")[0], 1)         # the unmapped name blocks
        code, out, err = self.bdd("run", "FEAT-001", "--isolated")
        self.assertEqual(code, 0, out + err)
        record = json.loads((self.root / ".bdd/.runs/FEAT-001/latest.json").read_text(encoding="utf-8"))
        self.assertEqual(len(record["cases"]), 2)

    def test_4_titles_that_are_not_plain_ascii_map_to_their_scenarios(self):
        self.titles_that_are_not_plain_ascii_map_to_their_scenarios(KOTLIN_UNICODE, "pass", 0)


@unittest.skipUnless(HAVE_ANDROID, "set GREENLIGHT_JVM_ADAPTER_TESTS=1 with a JDK, Gradle and the Android SDK (ANDROID_HOME)")
class AndroidContractTest(ScaffoldCase):
    """An Android library module: the same sources, run by the Android Gradle Plugin as local unit tests."""

    fixture = "android-contract"
    adapter_name = "kotlin-android"

    @classmethod
    def prepare(cls) -> None:
        subprocess.run([shutil.which("gradle"), "wrapper", "-q"], cwd=cls.root, check=True, capture_output=True, timeout=600)

    def test_1_the_sample_feature_is_green_as_an_android_unit_test(self):
        code, out, err = self.bdd("run", "FEAT-000")
        self.assertEqual(code, 0, out + err)
        code, out, _ = self.bdd("classify", "FEAT-000", "--expect", "green")
        self.assertEqual(code, 0, out)


if __name__ == "__main__":
    unittest.main()
