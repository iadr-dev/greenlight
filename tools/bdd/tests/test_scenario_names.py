"""Which scenario a test belongs to, when the title is not plain ASCII or the runner rewrites it."""
import unittest
from pathlib import Path

from bddlib import classify, runner
from bddlib import config as cfg

SCENARIOS = [
    {"name": "Café au lait is ordered", "example": "EX-004.1.1"},
    {"name": "訂單可以建立", "example": "EX-004.1.2"},
    {"name": "Order of 1000", "example": "EX-004.1.10"},
    {"name": "Order of 1000 with a coupon", "example": "EX-004.1.11"},
]


def example_of(test_name: str) -> str | None:
    found = classify.scenario_for(test_name, SCENARIOS)
    return found["example"] if found else None


class UnicodeTitleTest(unittest.TestCase):
    def test_a_title_in_chinese_is_found_in_the_test_name(self):
        self.assertEqual(example_of("訂單可以建立"), "EX-004.1.2")
        self.assertEqual(example_of("Scenario: 訂單可以建立 [row 2]"), "EX-004.1.2")

    def test_an_accented_title_matches_with_or_without_the_accents(self):
        for name in ("Café au lait is ordered", "Cafe_au_lait_is_ordered", "test_cafe_au_lait_is_ordered", "CAFÉ AU LAIT IS ORDERED"):
            with self.subTest(name=name):
                self.assertEqual(example_of(name), "EX-004.1.1")

    def test_the_longest_scenario_name_still_wins(self):
        self.assertEqual(example_of("test_order_of_1000_with_a_coupon"), "EX-004.1.11")
        self.assertEqual(example_of("test_order_of_1000"), "EX-004.1.10")

    def test_two_scenarios_with_empty_ascii_names_are_not_confused(self):
        other = [{"name": "訂單", "example": "EX-005.1.1"}, {"name": "付款", "example": "EX-005.1.2"}]
        self.assertEqual(classify.scenario_for("付款成功", other)["example"], "EX-005.1.2")
        self.assertIsNone(classify.scenario_for("退款", other))


class ReportedNamesTest(unittest.TestCase):
    """The test names a real Reqnroll 3 run (xUnit, JUnit logger) wrote for these three titles: it drops the accent and the
    punctuation, keeps Chinese as it is, and glues the ASCII part of a mixed title on after it."""

    TITLES = [
        {"name": "Café: two numbers are added", "example": "EX-004.1.1"},
        {"name": "兩個數字相加", "example": "EX-004.1.2"},
        {"name": "負數會被拒絕 (a negative number is refused)", "example": "EX-004.1.3"},
    ]
    REPORTED = {
        "CafeTwoNumbersAreAdded": "EX-004.1.1",
        "兩個數字相加": "EX-004.1.2",
        "負數會被拒絕ANegativeNumberIsRefused(a negative number is refused)": "EX-004.1.3",
    }

    def test_every_reported_name_maps_to_its_scenario(self):
        for reported, example in self.REPORTED.items():
            with self.subTest(reported=reported):
                self.assertEqual(classify.scenario_for(reported, self.TITLES)["example"], example)


class RegexFilterTest(unittest.TestCase):
    """The name filter handed to a runner that reads it as a regular expression must survive a command line that is
    converted to the Windows code page on its way to ``mvn.cmd`` or ``gradlew.bat``: plain ASCII, whatever the title."""

    def test_the_filter_is_ascii_even_for_a_title_in_another_script(self):
        for title in ("Café: a product is stored", "商品可以儲存並讀回", "茶 and 咖啡 (tea and coffee)", "naïve 😀 emoji"):
            with self.subTest(title=title):
                self.assertTrue(runner.regex_escape(title).isascii())

    def test_non_ascii_characters_become_code_point_escapes_and_metacharacters_stay_escaped(self):
        self.assertEqual(runner.regex_escape("Café"), "Caf\\x{E9}")
        self.assertEqual(runner.regex_escape("茶 (a)"), "\\x{8336}\\ \\(a\\)")
        self.assertEqual(runner.regex_escape("😀"), "\\x{1F600}")
        self.assertEqual(runner.regex_escape("a.b*c"), "a\\.b\\*c")
        self.assertEqual(runner.regex_escape("x\\Ey"), "x\\\\Ey")

    def test_the_command_carries_the_escaped_name_as_one_word(self):
        rules = cfg.RunRules("x", "{python} run", "--out {out}", isolated="-Dname='\\A{scenario:regex}\\z'")
        words = runner.build_command(rules, Path("."), "FEAT-004", Path("o.xml"), scenario="商品 (a)")
        self.assertEqual(words[-1], "-Dname=\\A\\x{5546}\\x{54C1}\\ \\(a\\)\\z")


class ExampleIdTest(unittest.TestCase):
    def test_a_test_name_that_carries_the_example_id_maps_when_the_title_is_lost(self):
        for name in ("Scenario_EX_004_1_2", "EX-004.1.2 x", "test ex-004.1.2", "EX004_1_2"):
            with self.subTest(name=name):
                self.assertEqual(example_of(name), "EX-004.1.2")

    def test_an_id_is_not_found_inside_a_longer_id(self):
        self.assertEqual(example_of("EX-004.1.10"), "EX-004.1.10")
        self.assertEqual(example_of("EX-004.1.11"), "EX-004.1.11")
        self.assertIsNone(example_of("XEX-004.1.2"))
        self.assertIsNone(example_of("EX-004.1.3"))

    def test_the_id_is_only_a_fallback_for_a_title_that_matched_nothing(self):
        self.assertEqual(example_of("Order of 1000 EX-004.1.2"), "EX-004.1.10")

    def test_a_scenario_without_an_id_is_never_matched_by_id(self):
        self.assertIsNone(classify.scenario_for("EX-004.1.2", [{"name": "zzz", "example": None}]))


if __name__ == "__main__":
    unittest.main()
