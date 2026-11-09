"""The edges a rule that uses the boundary card records in test-design.md, and the places that check them."""
import tempfile
import unittest
from pathlib import Path

from bddlib import edgecheck, trace
from bddlib.errors import UsageError

from tests.helpers import ProjectCase

DATE_RULE = "R-007.1 A delivery date is a calendar date no earlier than today.\n"
TEXT_RULE = "R-007.2 A note is at most 200 characters.\n"
PAGE_RULE = "R-007.3 A list comes in pages of 50 and at most 200 per page.\n"
PLAIN_RULE = "R-007.4 Orders of 1000 or more get 10% off.\n"


def section(rule: str, title: str, *bullets: str, techniques: str = "boundary-value, negative-cases") -> str:
    return f"## {rule} {title}\n\nTechniques: {techniques}\nWhy these: boundary-value because the rule has an edge.\n\n" + "".join(
        f"- {b}\n" for b in bullets) + "\n"


class EdgeCase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.folder = Path(self.dir.name)

    def check(self, rules: str, design: str) -> list[str]:
        (self.folder / "rules.md").write_text(rules, encoding="utf-8")
        (self.folder / "test-design.md").write_text("# Test design\n\n" + design, encoding="utf-8")
        return edgecheck.problems(self.folder)


class DatesTest(EdgeCase):
    DESIGN = section("R-007.1", "A delivery date", "EX-007.1.1 Today is accepted (boundary-value: on the edge)")

    def test_a_date_rule_with_no_leap_day_is_named_with_what_to_add(self):
        (problem,) = self.check(DATE_RULE, self.DESIGN)
        self.assertEqual(problem, 'R-007.1 uses the boundary-value card for a date but records no leap day: add an example '
                                  'for it, or a line "- No leap day boundary: <why this rule has none>" in its section of '
                                  "test-design.md")

    def test_an_example_that_names_the_leap_day_records_it(self):
        design = section("R-007.1", "A delivery date", "EX-007.1.2 Delivery on 29 February 2028 is accepted (boundary-value)")
        self.assertEqual(self.check(DATE_RULE, design), [])
        for wording in ("the leap day", "Feb 29 2028", "2028-02-29", "閏年的二月"):
            with self.subTest(wording=wording):
                self.assertEqual(self.check(DATE_RULE, section("R-007.1", "x", f"EX-007.1.2 {wording}")), [])

    def test_a_reason_that_the_rule_has_no_such_boundary_is_accepted(self):
        design = section("R-007.1", "A delivery date", "No leap day boundary: the date is only compared with today")
        self.assertEqual(self.check(DATE_RULE, design), [])

    def test_a_reason_of_one_word_is_not_a_reason(self):
        (problem,) = self.check(DATE_RULE, section("R-007.1", "x", "No leap day boundary: n/a"))
        self.assertIn('the reason after "No leap day boundary:" is too short to be a reason in its section', problem)

    def test_the_prose_of_the_section_is_not_an_example(self):
        design = ("## R-007.1 A delivery date\n\nTechniques: boundary-value\nWhy these: the leap day matters here.\n\n"
                  "- EX-007.1.1 Today is accepted\n")
        self.assertEqual(len(self.check(DATE_RULE, design)), 1)

    def test_a_wrapped_bullet_counts_as_one(self):
        design = ("## R-007.1 A delivery date\n\nTechniques: boundary-value\n\n- EX-007.1.1 Delivery on a day\n"
                  "  that is a leap day is accepted\n")
        self.assertEqual(self.check(DATE_RULE, design), [])


class TextAndPagesTest(EdgeCase):
    def test_a_length_rule_needs_the_empty_value_and_the_maximum(self):
        design = section("R-007.2", "Notes", "EX-007.2.1 A note of 200 characters is kept", "EX-007.2.2 A note of 201 is refused")
        problems = self.check(TEXT_RULE, design)
        self.assertEqual([p.split(" records no ")[1].split(":")[0] for p in problems], ["empty value"])
        full = section("R-007.2", "Notes", "EX-007.2.1 An empty note is refused", "EX-007.2.2 The maximum, 200, is kept")
        self.assertEqual(self.check(TEXT_RULE, full), [])

    def test_a_length_that_is_not_the_rules_limit_is_not_the_maximum(self):
        design = section("R-007.2", "Notes", "EX-007.2.1 A note of 100 characters is kept", "EX-007.2.2 An empty note is refused")
        (problem,) = self.check(TEXT_RULE, design)
        self.assertIn("records no maximum length", problem)
        for found in ("A note of 201 characters is refused", "The longest note is kept", "A note one over the limit is refused"):
            with self.subTest(found=found):
                self.assertEqual(self.check(TEXT_RULE, section("R-007.2", "Notes", f"EX-007.2.1 {found}", "EX-007.2.2 An empty note")), [])

    def test_each_edge_can_be_waived_on_its_own(self):
        design = section("R-007.2", "Notes", "No empty boundary: a note is optional and an empty one is dropped",
                         "No maximum length boundary: the limit is checked by the database column, see R-007.9")
        self.assertEqual(self.check(TEXT_RULE, design), [])

    def test_a_paging_rule_needs_page_size_1(self):
        design = section("R-007.3", "Lists", "EX-007.3.1 A page of 50 is returned")
        (problem,) = self.check(PAGE_RULE, design)
        self.assertIn("for a page of a list but records no page size 1", problem)
        for wording in ("page size 1", "page size of 1", "one item per page", "1 row per page", "a page of one"):
            with self.subTest(wording=wording):
                self.assertEqual(self.check(PAGE_RULE, section("R-007.3", "Lists", f"EX-007.3.2 {wording} returns the total")), [])


class HowItIsWrittenTest(EdgeCase):
    PIN_RULE = "R-007.5 A PIN has 4 digits.\n"

    def test_bullets_under_a_subheading_belong_to_the_rule(self):
        design = ("## R-007.2 Notes\n\nTechniques: boundary-value\n\n### Examples\n\n- EX-007.2.1 An empty note is refused\n"
                  "- EX-007.2.2 A note of 200 characters is kept\n\n### Excluded\n\n- none\n\n## Coverage check\n\n- yes\n")
        self.assertEqual(self.check(TEXT_RULE, design), [])

    def test_the_next_rule_starts_its_own_section_even_one_level_down(self):
        design = ("## R-007.1 Date\n\nTechniques: boundary-value\n\n- EX-007.1.1 leap day\n\n"
                  "### R-007.2 Notes\n\nTechniques: boundary-value\n\n- EX-007.2.1 today\n")
        problems = self.check(DATE_RULE + TEXT_RULE, design)
        self.assertEqual([p.split(" ")[0] for p in problems], ["R-007.2", "R-007.2"])

    def test_the_digits_of_an_example_id_are_not_the_limit(self):
        design = section("R-007.5", "PIN", "EX-007.5.4 A PIN of three digits is refused", "EX-007.5.1 An empty PIN is refused")
        (problem,) = self.check(self.PIN_RULE, design)
        self.assertIn("records no maximum length", problem)

    def test_spellings_of_page_size_1(self):
        for wording in ("pageSize=1", "page_size=1", "per_page=1", "limit=1", "Page size: 1", "a page of one"):
            with self.subTest(wording=wording):
                self.assertEqual(self.check(PAGE_RULE, section("R-007.3", "Lists", f"EX-007.3.2 {wording} returns one item")), [])

    def test_other_ways_to_write_the_edge_or_the_waiver(self):
        for line in ("1. No leap day boundary: the date is only compared with today", "**No leap day boundary**: only compared with today",
                     "- No leap-day boundary: the date is only compared with today", "* no Leap Day boundary: only compared, never added"):
            with self.subTest(line=line):
                self.assertEqual(self.check(DATE_RULE, f"## R-007.1 Date\n\nTechniques: boundary-value\n\n{line}\n"), [])
        for wording in ("Delivery on 29.02.2028", "Delivery on 29/02", "A date of 2028-02-29"):
            with self.subTest(wording=wording):
                self.assertEqual(self.check(DATE_RULE, section("R-007.1", "Date", f"EX-007.1.1 {wording}")), [])
        self.assertEqual(self.check(TEXT_RULE, section("R-007.2", "Notes", 'EX-007.2.1 A note of "" is refused', "EX-007.2.2 The maximum")), [])

    def test_a_waiver_with_a_thin_reason_is_never_read_as_the_edge(self):
        for line in ("1. No leap day boundary: n/a", "**No leap day boundary**: none", "- No leap-day boundary: leap"):
            with self.subTest(line=line):
                (problem,) = self.check(DATE_RULE, f"## R-007.1 Date\n\nTechniques: boundary-value\n\n{line}\n")
                self.assertIn("too short to be a reason", problem)

    def test_the_techniques_line_may_be_bold_or_a_bullet(self):
        for line in ("**Techniques:** boundary-value", "- Techniques: boundary-value", "Techniques: **boundary-value**"):
            with self.subTest(line=line):
                self.assertEqual(len(self.check(DATE_RULE, f"## R-007.1 Date\n\n{line}\n\n- EX-007.1.1 today\n")), 1)

    def test_the_message_says_empty_value(self):
        (problem,) = self.check(TEXT_RULE, section("R-007.2", "Notes", "EX-007.2.1 200 characters"))
        self.assertIn("records no empty value: add an example for it, or a line \"- No empty boundary:", problem)


class WhichRulesTest(EdgeCase):
    def test_a_rule_that_does_not_use_the_boundary_card_is_not_asked(self):
        design = section("R-007.1", "A delivery date", techniques="equivalence-partitioning, negative-cases")
        self.assertEqual(self.check(DATE_RULE, design), [])

    def test_a_boundary_rule_that_speaks_of_no_date_text_or_page_is_not_asked(self):
        design = section("R-007.4", "Discount", "EX-007.4.1 999 gets none", "EX-007.4.2 1000 gets 10%")
        self.assertEqual(self.check(PLAIN_RULE, design), [])

    def test_the_rule_text_comes_from_rules_md_and_the_heading(self):
        self.assertEqual(len(self.check(PLAIN_RULE, section("R-007.4", "Delivery date", "EX-007.4.1 today"))), 1)

    def test_a_section_for_several_rules_is_judged_on_all_their_words(self):
        design = section("R-007.1 and R-007.2", "Date and note", "EX-007.1.1 A leap day is accepted")
        problems = self.check(DATE_RULE + TEXT_RULE, design)
        self.assertEqual(len(problems), 2)
        self.assertTrue(all(p.startswith("R-007.1 and R-007.2 uses") for p in problems))

    def test_sections_are_judged_one_by_one(self):
        design = (section("R-007.1", "Date", "EX-007.1.1 today") + section("R-007.2", "Notes", "EX-007.2.1 empty, maximum"))
        problems = self.check(DATE_RULE + TEXT_RULE, design)
        self.assertEqual([p.split(" ")[0] for p in problems], ["R-007.1"])

    def test_no_test_design_means_nothing_to_check(self):
        self.assertEqual(edgecheck.problems(self.folder), [])


class WhereItIsCheckedTest(ProjectCase):
    def setUp(self):
        super().setUp()
        self.rules.write_text("# Rules\n\n" + DATE_RULE, encoding="utf-8")
        self.test_design = self.feature_dir / "test-design.md"
        self.test_design.write_text("# Test design\n\n" + section("R-007.1", "Delivery date", "EX-007.1.1 Today"),
                                    encoding="utf-8")
        self.gate("discover")
        self.approve("rules")

    def test_the_test_design_gate_refuses_a_boundary_rule_with_no_leap_day(self):
        with self.assertRaises(UsageError) as refused:
            self.gate("test-design")
        self.assertIn("R-007.1 uses the boundary-value card for a date but records no leap day", str(refused.exception))
        self.assertEqual(self.data()["phase"], "test-design")

    def test_the_gate_passes_once_the_edge_is_recorded(self):
        self.test_design.write_text("# Test design\n\n" + section("R-007.1", "Delivery date", "EX-007.1.1 Today",
                                    "No leap day boundary: the date is only compared with today"), encoding="utf-8")
        self.assertEqual(self.gate("test-design")["phase"], "examples")

    def test_a_failing_result_is_recorded_without_the_check(self):
        self.assertEqual(self.gate("test-design", "fail")["gates"]["test-design"]["result"], "fail")

    def test_trace_shows_it_as_a_gap_until_the_gate_has_passed(self):
        codes = lambda: [g["code"] for g in trace.build(self.root, self.feature_dir, "FEAT-007")["gaps"]]
        self.assertIn("T009", codes())
        self.test_design.write_text("# Test design\n\n" + section("R-007.1", "Delivery date", "EX-007.1.1 leap day"),
                                    encoding="utf-8")
        self.assertNotIn("T009", codes())
        self.test_design.write_text("# Test design\n\n" + section("R-007.1", "Delivery date", "EX-007.1.1 Today"),
                                    encoding="utf-8")
        self.assertIn("T009", codes())

    def test_a_feature_whose_test_design_gate_passed_before_is_not_reopened_by_it(self):
        self.test_design.write_text("# Test design\n\n" + section("R-007.1", "Delivery date", "EX-007.1.1 leap day"),
                                    encoding="utf-8")
        self.gate("test-design")
        self.test_design.write_text("# Test design\n\n" + section("R-007.1", "Delivery date", "EX-007.1.1 Today"),
                                    encoding="utf-8")
        report = trace.build(self.root, self.feature_dir, "FEAT-007")
        self.assertNotIn("T009", [g["code"] for g in report["gaps"]])


class TaskAreasTest(unittest.TestCase):
    def test_a_task_keeps_its_areas_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tasks.md"
            path.write_text("## T-007.1 Banner\n\nCovers: EX-007.1.1\nAreas: api/src/, web/app.ts\nDepends on: none\n\n"
                            "## T-007.2 Other\n\nCovers: EX-007.2.1\nAreas:\n", encoding="utf-8")
            tasks = trace.read_tasks(path)
        self.assertEqual((tasks["T-007.1"]["areas"], tasks["T-007.2"]["areas"]), ("api/src/, web/app.ts", ""))
        self.assertEqual(tasks["T-007.1"]["examples"], ["EX-007.1.1"])


if __name__ == "__main__":
    unittest.main()
