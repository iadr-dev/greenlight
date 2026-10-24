"""The screen steps of the kotlin-android adapter (the ui profile): what they are made of, checked without a device, and (with an
emulator or a device in `adb devices`) a Compose app whose screen the scenarios really drive through UI Automator.

The structural tests run everywhere. The device tests need a JDK, Gradle, the Android SDK, a device and
GREENLIGHT_ANDROID_DEVICE=1, like the device tests of the adapter in test_adapter_jvm.py.
"""
import re
import subprocess
import unittest
from pathlib import Path

from bddlib import adapter

from tests import test_adapter_jvm as jvm

KOTLIN = jvm.KOTLIN
TEMPLATES = KOTLIN / "templates"
UI_STEPS = TEMPLATES / "src" / "device-ui" / "kotlin" / "greenlight" / "steps" / "UiSteps.kt"
UI_DRIVER = TEMPLATES / "src" / "device-ui" / "kotlin" / "greenlight" / "drivers" / "UiDriver.kt"

COUNTER = """@FEAT-005
Feature: Counter screen

  @R-005.1
  Rule: The counter counts presses

    @EX-005.1.1 @ui
    Scenario: Pressing the button adds one
      When alice opens the counter page
      And alice clicks add button
      Then alice sees count showing:
        | text |
        | 1    |

    @EX-005.1.2 @ui
    Scenario: A person fills in the form
      When alice opens the counter page
      Then alice sees error message showing:
        | text        |
        | Agree first |
      When alice fills name field with:
        | value |
        | Ada   |
      And alice toggles agree box
      Then alice sees name field showing:
        | text |
        | Ada  |
      And alice sees agree box showing:
        | checked |
        | true    |
      And alice does not see error message
"""

RED = """@FEAT-006
Feature: Checkout screen

  @R-006.1
  Rule: A person can check out

    @EX-006.1.1 @ui
    Scenario: A component that is not on the screen yet
      When alice opens the counter page
      And alice clicks checkout button
      Then alice sees count showing:
        | text |
        | 1    |

    @EX-006.1.2 @ui
    Scenario: A screen nobody mapped
      When alice opens the cart page
      Then alice sees count showing:
        | text |
        | 0    |

    @EX-006.1.3 @ui
    Scenario: A file cannot be handed to a screen
      When alice opens the counter page
      And alice uploads name field with:
        | value |
        | photo.png |
      Then alice sees count showing:
        | text |
        | 0    |

    @EX-006.1.4 @ui
    Scenario: The state of the application is not readable yet
      Given the application state is:
        | key   | value |
        | theme | dark  |
      When alice opens the counter page
      Then alice sees count showing:
        | text |
        | 0    |
"""
RED_RESULTS = {"EX-006.1.1": "expected-fail", "EX-006.1.2": "test-defect", "EX-006.1.3": "expected-fail", "EX-006.1.4": "expected-fail"}

GESTURES = """@FEAT-008
Feature: Gestures

  @R-008.1
  Rule: A person can scroll, swipe and go back

    @EX-008.1.1 @ui
    Scenario: A list is scrolled down
      When alice opens the counter page
      And alice scrolls feed with:
        | direction |
        | down      |
      Then alice sees scroll state showing:
        | text     |
        | scrolled |

    @EX-008.1.2 @ui
    Scenario: A card is swiped to the left
      When alice opens the counter page
      And alice swipes deck with:
        | direction |
        | left      |
      Then alice sees swipe state showing:
        | text |
        | left |

    @EX-008.1.3 @ui
    Scenario: Going back returns to the first screen
      When alice opens the counter page
      And alice clicks next button
      And alice goes back
      Then alice sees page title showing:
        | text       |
        | First page |
"""

STATE = """@FEAT-007
Feature: Application state

  @R-007.1
  Rule: The state a scenario starts from is the state the application reports

    @EX-007.1.1 @ui
    Scenario: A setting starts from the state the scenario gave
      Given the application state is:
        | key   | value |
        | theme | dark  |
      When alice opens the counter page
      Then the application state includes:
        | key   | value |
        | theme | dark  |
"""

STATE_SEAMS = """package greenlight.drivers

class ProjectSeams(world: World) : Seams(world) {
    private val state = HashMap<String, Any?>()

    override fun setApplicationState(entries: Map<String, Any?>) {
        state.putAll(entries)
    }

    override fun applicationState(): Map<String, Any?> = state
}
"""


class ScreenStepsTest(unittest.TestCase):
    """What the screen steps are made of, checked without a device."""

    def test_the_ui_profile_is_declared_and_the_device_files_are_bound(self):
        data = adapter.load(KOTLIN)
        self.assertIn("ui", data["profiles"])
        for name in ("src/device-ui/kotlin/greenlight/steps/UiSteps.kt", "src/device-ui/kotlin/greenlight/drivers/UiDriver.kt"):
            self.assertIn(name, data["paths"]["support"])
            self.assertTrue((TEMPLATES / name).is_file(), name)
        self.assertTrue((TEMPLATES / "src/test/kotlin/greenlight/drivers/UiOperations.kt").is_file())

    def test_a_screen_scenario_is_left_out_of_the_jvm_run_and_runs_on_the_device(self):
        by_tag = adapter.load(KOTLIN)["run"]["by_tag"]
        self.assertIn('"@{tag} and not @ui"', by_tag)
        device = re.search(r'(?m)^   by_tag = "(.+)"$', (KOTLIN / "guide.md").read_text(encoding="utf-8"))
        self.assertIsNotNone(device)
        self.assertNotIn("not @ui", device.group(1))              # the device runs every scenario, the screen ones included

    def test_all_seven_screen_instructions_are_bound_and_the_action_with_data_is_a_method_of_its_own(self):
        source = UI_STEPS.read_text(encoding="utf-8")
        bound = set(re.findall(r"// (C\.[A-Z_.]+)", source))
        self.assertEqual(bound, {"C.STATE.GLOBAL", "C.UI.OPEN", "C.UI.ACT", "C.UI.BACK", "C.UI.SEE", "C.UI.NOT_SEE", "C.STATE.VERIFY"})
        patterns = re.findall(r'@(?:Given|When|Then)\("(.+?)"\)', source)
        self.assertEqual(len(patterns), 8)                     # the actions come with data and without
        for pattern in patterns:
            self.assertTrue(pattern.startswith("^") and pattern.endswith("$"), pattern)

    def test_the_screen_driver_waits_for_the_condition_and_never_sleeps(self):
        source = UI_DRIVER.read_text(encoding="utf-8")
        self.assertNotRegex(source, r"Thread\.sleep|delay\(")
        self.assertIn("Until.findObject", source)
        self.assertIn("Until.gone", source)
        self.assertIn("ExpectedMissing", source)

    def test_the_app_under_test_is_never_stopped_by_the_driver(self):
        """In an application module the tests run inside the app's process: stopping it ends the run (found on an emulator)."""
        source = UI_DRIVER.read_text(encoding="utf-8")
        self.assertIn("filter { it != own }", source)


@unittest.skipUnless(jvm.HAVE_DEVICE, "set GREENLIGHT_ANDROID_DEVICE=1 with a JDK, Gradle, the Android SDK and a device in `adb devices`")
class ScreenContractTest(jvm.ScaffoldCase):
    """A Compose application on a device: the scenarios open its screen, tap, type, toggle and read what it shows."""

    fixture = "android-ui"
    adapter_name = "kotlin-android"

    @classmethod
    def prepare(cls) -> None:
        if not (jvm.os.environ.get("ANDROID_HOME") or jvm.os.environ.get("ANDROID_SDK_ROOT")):
            (cls.root / "local.properties").write_text(f"sdk.dir={jvm.android_sdk().as_posix()}\n", encoding="utf-8")
        config = cls.root / ".bdd" / "config.toml"
        config.write_text(config.read_text(encoding="utf-8") + "\n" + jvm.device_block(), encoding="utf-8", newline="\n")
        operations = cls.root / "src/test/kotlin/greenlight/drivers/UiOperations.kt"
        text = operations.read_text(encoding="utf-8")
        text = text.replace('        // "orders" to Screen("com.example.shop", uri = "shop://orders"),', '        "counter" to Screen("sample.ui"),')
        text = text.replace('        // "checkout button" to Target.Id("checkout"),',
                            '        "count" to Target.Id("count"),\n        "add button" to Target.Id("add"),\n        "name field" to Target.Id("name"),\n'
                            '        "agree box" to Target.Id("agree"),\n        "error message" to Target.Id("error"),\n'
                            '        "checkout button" to Target.Id("checkout"),\n        "feed" to Target.Id("feed"),\n'
                            '        "scroll state" to Target.Id("scrolled"),\n        "deck" to Target.Id("deck"),\n        "swipe state" to Target.Id("swiped"),\n'
                            '        "next button" to Target.Id("next"),\n        "page title" to Target.Id("title"),')
        operations.write_text(text, encoding="utf-8", newline="\n")
        jvm.make_gradle_wrapper(cls.root)

    @classmethod
    def tearDownClass(cls):
        wrapper = cls.root / ("gradlew.bat" if jvm.os.name == "nt" else "gradlew")
        subprocess.run([str(wrapper), "--stop"], cwd=cls.root, capture_output=True, timeout=120)    # a daemon holds the folder
        super().tearDownClass()

    def run_on_device(self, feature: str) -> int:
        code, out, err = self.bdd("run", feature, "--adapter", "kotlin-android-device")
        return code

    def test_1_the_screen_scenarios_are_green_on_the_device(self):
        self.add_feature("src/test/resources/features/counter.feature", COUNTER, "FEAT-005")
        self.assertEqual(self.run_on_device("FEAT-005"), 0)
        self.assertEqual(self.results("FEAT-005"), {"EX-005.1.1": "pass", "EX-005.1.2": "pass"})
        self.assertEqual(self.bdd("classify", "FEAT-005", "--expect", "green")[0], 0)

    def test_2_red_looks_like_red_on_a_screen(self):
        self.add_feature("src/test/resources/features/checkout.feature", RED, "FEAT-006")
        self.assertEqual(self.run_on_device("FEAT-006"), 0)
        self.assertEqual(self.results("FEAT-006"), RED_RESULTS)

    def test_3_the_application_state_is_set_and_read_through_the_seams(self):
        seams = self.root / "src/test/kotlin/greenlight/drivers/ProjectSeams.kt"
        original = seams.read_text(encoding="utf-8")
        seams.write_text(STATE_SEAMS, encoding="utf-8", newline="\n")
        try:
            self.add_feature("src/test/resources/features/state.feature", STATE, "FEAT-007")
            self.assertEqual(self.run_on_device("FEAT-007"), 0)
            self.assertEqual(self.results("FEAT-007"), {"EX-007.1.1": "pass"})
        finally:
            seams.write_text(original, encoding="utf-8", newline="\n")

    def test_5_a_list_is_scrolled_a_card_swiped_and_the_back_action_returns_to_the_first_screen(self):
        self.add_feature("src/test/resources/features/gestures.feature", GESTURES, "FEAT-008")
        self.assertEqual(self.run_on_device("FEAT-008"), 0)
        self.assertEqual(self.results("FEAT-008"), {"EX-008.1.1": "pass", "EX-008.1.2": "pass", "EX-008.1.3": "pass"})

    def test_4_the_jvm_side_still_runs_the_other_scenarios_and_leaves_the_screen_ones_out(self):
        code, out, err = self.bdd("run", "FEAT-000", "--adapter", "kotlin-android")
        self.assertEqual(code, 0, out + err)
        self.assertIn("3 passed", out)


if __name__ == "__main__":
    unittest.main()
