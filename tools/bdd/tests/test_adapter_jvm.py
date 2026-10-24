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

from bddlib import adapter, classify, cli, initcmd, junit, proctree, runner, state
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


def android_sdk() -> Path | None:
    """The Android SDK: ANDROID_HOME or ANDROID_SDK_ROOT, else where Android Studio and Google's `android` tool put it."""
    named = os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT")
    candidates = [Path(named)] if named else [Path(os.environ.get("LOCALAPPDATA", "~")) / "Android" / "Sdk",
                                              Path.home() / "Library" / "Android" / "sdk", Path.home() / "Android" / "Sdk"]
    return next((path.expanduser() for path in candidates if (path.expanduser() / "platform-tools").is_dir()), None)


def connected_devices() -> list[str]:
    """The serial numbers `adb devices` lists as ready ("device"), or none when adb is missing."""
    adb = shutil.which("adb")
    if adb is None:
        return []
    done = subprocess.run([adb, "devices"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    return [line.split()[0] for line in done.stdout.splitlines()[1:] if line.strip().endswith("\tdevice")]


# Scenarios on a device need a phone or an emulator, so they run only when a person asks for them with one connected.
HAVE_DEVICE = (os.environ.get("GREENLIGHT_ANDROID_DEVICE") == "1" and shutil.which("java") is not None
               and shutil.which("gradle") is not None and android_sdk() is not None and bool(connected_devices()))

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
        self.assertEqual(kotlin["profiles"], ["base", "lib", "data", "ui"])
        for name, config in (("java-cucumber-spring", tool_free_config("java-cucumber-spring")),
                             ("kotlin-android", tool_free_config("kotlin-android"))):
            with self.subTest(adapter=name):
                (run,) = config.runs
                # Spring has no screens; Kotlin leaves the scenarios that drive one (@ui) to the device run
                wanted = 'cucumber.filter.tags="@{tag} and not @ui"' if name == "kotlin-android" else "cucumber.filter.tags=@{tag}"
                self.assertIn(wanted, run.by_tag)
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


GRADLE_SETUP_SECONDS = 600       # the whole Kotlin class ran in about a minute on every runner


def make_gradle_wrapper(root: Path) -> None:
    """Create the module's Gradle wrapper and fetch its distribution now, so that a failed download stops the set-up with
    Gradle's own message instead of surfacing later as a first test run that found no test cases."""
    for words in ([shutil.which("gradle"), "wrapper", "-q"], [str(root / ("gradlew.bat" if os.name == "nt" else "gradlew")), "--version"]):
        try:
            done = proctree.run(words, cwd=root, timeout=GRADLE_SETUP_SECONDS)
        except proctree.TimedOut as stopped:
            raise RuntimeError(f"{Path(words[0]).name} {' '.join(words[1:])} did not finish in {GRADLE_SETUP_SECONDS} s and was stopped "
                               f"with its daemons; its output so far:\n{stopped.stdout[-2000:]}\n{stopped.stderr[-2000:]}") from stopped
        if done.returncode:
            raise RuntimeError(f"{Path(words[0]).name} {' '.join(words[1:])} failed with exit {done.returncode}:\n"
                               f"{done.stdout[-2000:]}\n{done.stderr[-2000:]}")


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
        make_gradle_wrapper(cls.root)

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
        make_gradle_wrapper(cls.root)

    def test_1_the_sample_feature_is_green_as_an_android_unit_test(self):
        code, out, err = self.bdd("run", "FEAT-000")
        self.assertEqual(code, 0, out + err)
        code, out, _ = self.bdd("classify", "FEAT-000", "--expect", "green")
        self.assertEqual(code, 0, out)


DEVICE_ORDERS = """@FEAT-001
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
    Scenario: A name nobody mapped
      When cancel is called with:
        | id |
        | 1  |
      Then the result is:
        \"\"\"
        1
        \"\"\"

    @EX-001.1.3
    Scenario: A step nobody wrote
      When the moon is full
      Then the result is:
        \"\"\"
        1
        \"\"\"
"""

DEVICE_TITLES = """@FEAT-004
Feature: Titles that are not plain ASCII

  @R-004.1
  Rule: A scenario keeps its title on the device

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
        | 1 | 1 |
      Then the result is:
        \"\"\"
        2
        \"\"\"
"""


def device_block() -> str:
    """The second adapter block the guide tells a person to add to .bdd/config.toml for a device."""
    guide = (KOTLIN / "guide.md").read_text(encoding="utf-8")
    after = guide[guide.index("<!-- device adapter block"):]
    start = after.index("```toml\n") + len("```toml\n")
    return "\n".join(line.removeprefix("   ") for line in after[start:after.index("```", start)].splitlines()) + "\n"


class DeviceSettingsTest(unittest.TestCase):
    """What the device run is made of, checked without a device."""

    def config_with_the_device_block(self, root: Path) -> cfg.Config:
        (root / ".bdd").mkdir()
        text = adapter.config_block(adapter.load(KOTLIN)) + "\n" + device_block()
        (root / ".bdd" / "config.toml").write_text(text, encoding="utf-8")
        return cfg.load(root)

    def test_the_guides_block_adds_a_second_run_that_reuses_the_same_folders(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = self.config_with_the_device_block(Path(tmp))
        jvm, device = config.runs
        self.assertEqual((jvm.adapter, device.adapter), ("kotlin-android", "kotlin-android-device"))
        self.assertIn("connectedDebugAndroidTest", device.by_tag)
        self.assertIn("{scenario:device}", device.isolated)
        self.assertEqual(device.shuffle, "")                           # Cucumber-Android has no order setting
        self.assertEqual(len(config.feature_dirs), 1)                  # one set of feature files, run twice
        self.assertIn("BDD_EXPECTED_MISSING", device.expected_fail)
        self.assertIn("NotMapped", device.test_defect)
        self.assertIn("CucumberException", device.test_defect)        # e.g. no @CucumberOptions class found

    def test_the_device_plumbing_is_shipped_and_bound(self):
        support = adapter.load(KOTLIN)["paths"]["support"]
        for name in ("greenlight-device.gradle.kts", "src/device/kotlin/greenlight/RunCucumberOnDevice.kt"):
            self.assertIn(name, support)
            self.assertTrue((KOTLIN / "templates" / name).is_file(), name)
        script = (KOTLIN / "templates" / "greenlight-device.gradle.kts").read_text(encoding="utf-8")
        for needle in ("greenlight.report", "deleteRecursively()", "finalizedBy", "reports.size != 1", "RunCucumberTest.kt"):
            self.assertIn(needle, script)
        options = (KOTLIN / "templates" / "src/device/kotlin/greenlight/RunCucumberOnDevice.kt").read_text(encoding="utf-8")
        self.assertIn('@CucumberOptions(glue = ["greenlight"], features = ["features"])', options)

    def test_a_scenario_name_is_written_for_the_devices_shell(self):
        # the device's shell takes one level of backslashes away: what reaches the engine is `\ `, `\(` and `\x{E9}`
        self.assertEqual(runner.device_shell_regex("Order 999"), "Order\\\\\\ 999")
        self.assertEqual(runner.device_shell_regex("a(b)"), "a\\\\\\(b\\\\\\)")
        self.assertEqual(runner.device_shell_regex("Café"), "Caf\\\\x\\{E9\\}")
        self.assertTrue(runner.device_shell_regex("兩個 'x'; rm -rf $HOME").isascii())

    def test_the_isolated_words_reach_the_device_as_one_escaped_word(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = self.config_with_the_device_block(Path(tmp))
            words = runner.build_command(config.runs[1], Path(tmp), "@FEAT-001", Path(tmp) / "r.xml", scenario="A name; rm x")
        self.assertEqual(words[-1], "-Pandroid.testInstrumentationRunnerArguments.name=\\\\AA\\\\\\ name\\\\\\;\\\\\\ rm\\\\\\ x\\\\z")


@unittest.skipUnless(HAVE_DEVICE, "set GREENLIGHT_ANDROID_DEVICE=1 with a JDK, Gradle, the Android SDK and a device in `adb devices`")
class DeviceContractTest(ScaffoldCase):
    """The scenarios on a real device (or an emulator), through Cucumber-Android: the sample is green, red looks like red,
    a title in Chinese or with an accent maps to its scenario, and one scenario runs alone."""

    fixture = "android-device"
    adapter_name = "kotlin-android"

    @classmethod
    def prepare(cls) -> None:
        if not (os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT")):
            (cls.root / "local.properties").write_text(f"sdk.dir={android_sdk().as_posix()}\n", encoding="utf-8")
        config = cls.root / ".bdd" / "config.toml"
        config.write_text(config.read_text(encoding="utf-8") + "\n" + device_block(), encoding="utf-8", newline="\n")
        make_gradle_wrapper(cls.root)

    @classmethod
    def tearDownClass(cls):
        wrapper = cls.root / ("gradlew.bat" if os.name == "nt" else "gradlew")
        subprocess.run([str(wrapper), "--stop"], cwd=cls.root, capture_output=True, timeout=120)   # a daemon holds the folder
        super().tearDownClass()

    def run_on_device(self, feature: str, *flags: str) -> tuple[int, str]:
        code, out, err = self.bdd("run", feature, "--adapter", "kotlin-android-device", *flags)
        return code, out + err

    def test_1_the_sample_feature_is_green_on_the_device(self):
        code, out = self.run_on_device("FEAT-000")
        self.assertEqual(code, 0, out)
        self.assertIn("3 passed", out)
        code, out, _ = self.bdd("classify", "FEAT-000", "--expect", "green")
        self.assertEqual(code, 0, out)

    def test_2_red_looks_like_red_on_the_device(self):
        self.add_feature("src/test/resources/features/orders.feature", DEVICE_ORDERS)
        code, out = self.run_on_device("FEAT-001")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.results("FEAT-001"),
                         {"EX-001.1.1": "expected-fail", "EX-001.1.2": "test-defect", "EX-001.1.3": "test-defect"})

    def test_3_one_scenario_runs_alone_and_titles_that_are_not_plain_ascii_map(self):
        self.add_feature("src/test/resources/features/titles.feature", DEVICE_TITLES, "FEAT-004")
        for flags in ((), ("--isolated",)):
            with self.subTest(flags=flags):
                code, out = self.run_on_device("FEAT-004", *flags)
                self.assertEqual(code, 0, out)
                self.assertEqual(self.results("FEAT-004"), {"EX-004.1.1": "pass", "EX-004.1.2": "pass"})
        record = json.loads((self.root / ".bdd/.runs/FEAT-004/latest.json").read_text(encoding="utf-8"))
        self.assertEqual(len(record["runs"]), 2)                       # one instrumentation run per scenario
        self.assertEqual(len(record["cases"]), 2)

    def test_4_both_sides_run_together_by_default(self):
        code, out, err = self.bdd("run", "FEAT-000")
        self.assertEqual(code, 0, out + err)
        self.assertIn("2 run(s)", out)                                 # the JVM run and the device run
        self.assertIn("6 passed", out)


if __name__ == "__main__":
    unittest.main()
