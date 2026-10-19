import unittest
from pathlib import Path

from bddlib import gherkin
from bddlib.gherkin import ParseError, Rule, Scenario, parse, parse_file

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "gherkin"


def load(name: str):
    return parse_file(FIXTURES / name)


def kinds(scenario: Scenario) -> list[str]:
    return [s.kind for s in scenario.steps]


class FixtureFilesTest(unittest.TestCase):
    def test_there_are_at_least_fifteen_fixtures_and_all_parse(self):
        files = sorted(FIXTURES.glob("*.feature"))
        self.assertGreaterEqual(len(files), 15)
        for f in files:
            with self.subTest(fixture=f.name):
                feature = parse_file(f)
                self.assertTrue(feature.name)
                self.assertTrue(list(feature.scenarios()), "fixture should contain a scenario")

    def test_minimal(self):
        f = load("01_minimal.feature")
        (sc, rule), = f.scenarios()
        self.assertIsNone(rule)
        self.assertEqual((f.name, sc.name), ("Minimal", "Smallest useful scenario"))
        self.assertEqual(kinds(sc), ["given", "when", "then"])
        self.assertEqual(f.language, "en")

    def test_rules_background_and_tag_inheritance(self):
        f = load("02_rules_and_background.feature")
        self.assertEqual(f.tags, ["@FEAT-007"])
        self.assertIn("so that I pay less.", f.description)
        self.assertEqual(f.background.steps[0].table, [["sku", "price"], ["A1", "100"]])
        rules = [c for c in f.children if isinstance(c, Rule)]
        self.assertEqual([r.name for r in rules], ["Bulk orders get ten percent off", "Coupons cannot be stacked"])
        self.assertEqual(rules[0].background.steps[0].text, "a registered shopper")
        sc, rule = next(iter(f.scenarios()))
        self.assertEqual(f.effective_tags(sc, rule), ["@FEAT-007", "@R-007.1", "@EX-007.1.1"])
        self.assertEqual(len(list(f.scenarios())), 3)

    def test_outline_with_tagged_examples(self):
        f = load("03_outline_examples.feature")
        (sc, _), = f.scenarios()
        self.assertTrue(sc.outline)
        self.assertEqual([e.name for e in sc.examples], ["light parcels", "heavy parcels"])
        self.assertEqual(sc.examples[1].header, ["kg", "fee"])
        self.assertEqual(sc.examples[1].rows, [["20", "15"], ["21", "30"]])
        self.assertEqual(f.effective_tags(sc), ["@R-1.1", "@partition-light", "@partition-heavy"])

    def test_tables_and_doc_strings(self):
        f = load("04_tables_and_docstrings.feature")
        (sc, _), = f.scenarios()
        table, posted, response = sc.steps
        self.assertEqual(table.table, [["name", "role"], ["alice", "admin"], ["bob", "user"]])
        self.assertEqual(posted.docstring_type, "json")
        self.assertIn('"text": "hello"', posted.docstring)
        self.assertEqual(posted.docstring.splitlines()[0], "{")        # indentation of the opener is removed
        self.assertEqual(response.docstring, "done\n  indented line")  # relative indentation is kept
        self.assertIsNone(response.docstring_type)

    def test_traditional_chinese(self):
        f = load("05_zh_tw.feature")
        self.assertEqual((f.language, f.name), ("zh-TW", "訂單折扣"))
        self.assertEqual(f.tags, ["@FEAT-010"])
        self.assertEqual(f.background.steps[0].text, "商店已有商品")
        first, outline = [sc for sc, _ in f.scenarios()]
        self.assertEqual(first.name, "滿千折一成")
        self.assertEqual(kinds(first), ["given", "given", "when", "then", "then"])  # 而且 / 但是 inherit
        self.assertEqual(first.steps[1].keyword, "而且")
        self.assertTrue(outline.outline)
        self.assertEqual(outline.examples[0].rows, [["1", "5"], ["21", "30"]])

    def test_other_languages(self):
        for name, language, expected in [
            ("06_zh_cn.feature", "zh-CN", ["given", "when", "then", "then"]),
            ("07_ja.feature", "ja", ["given", "when", "then"]),
            ("08_de.feature", "de", ["given", "when", "then", "then"]),
        ]:
            with self.subTest(fixture=name):
                f = load(name)
                self.assertEqual(f.language, language)
                (sc, _), = f.scenarios()
                self.assertEqual(kinds(sc), expected)

    def test_comments_and_blank_lines_are_ignored(self):
        f = load("09_comments_and_blank_lines.feature")
        self.assertEqual(f.description, "Description text.")
        (sc, _), = f.scenarios()
        self.assertEqual([s.text for s in sc.steps], ["a thing", "it happens", "it works"])

    def test_tags_accumulate_across_lines(self):
        f = load("10_multiple_tags.feature")
        self.assertEqual(f.tags, ["@FEAT-1", "@smoke", "@slow"])
        (sc, _), = f.scenarios()
        self.assertEqual(sc.tags, ["@R-1.1", "@EX-1.1.1", "@wip"])

    def test_step_words_in_descriptions_are_prose(self):
        f = load("11_prose_with_step_words.feature")
        self.assertIn("Given that customers differ", f.description)
        self.assertIn("Then everything below is real.", f.description)
        rule = f.children[0]
        self.assertEqual(rule.description, "Then this is rule description, not a step.")
        self.assertEqual(kinds(rule.scenarios[0]), ["given", "when", "then"])

    def test_and_but_star_inherit_the_previous_kind(self):
        (sc, _), = load("12_and_but_star.feature").scenarios()
        self.assertEqual(kinds(sc), ["given"] * 3 + ["when"] * 2 + ["then"] * 3)
        self.assertEqual([s.keyword for s in sc.steps][:3], ["Given", "And", "*"])

    def test_cell_escapes(self):
        (sc, _), = load("13_escaped_cells.feature").scenarios()
        rows = sc.steps[0].table
        self.assertEqual(rows[1], ["a | b", "pipe"])
        self.assertEqual(rows[2], ["c " + chr(92) + " d", "backslash"])
        self.assertEqual(rows[3][0], "line1" + chr(10) + "line2")
        self.assertEqual(rows[4], ["", "empty first cell"])

    def test_keyword_aliases(self):
        f = load("14_example_alias_and_template.feature")
        plain, outline = [sc for sc, _ in f.scenarios()]
        self.assertFalse(plain.outline)
        self.assertTrue(outline.outline)
        self.assertEqual(outline.examples[0].rows, [["1"]])

    def test_scenario_description(self):
        (sc, _), = load("15_scenario_descriptions.feature").scenarios()
        self.assertEqual(sc.description, "This explains the scenario in prose,\nover two lines.")
        self.assertEqual(kinds(sc), ["given", "then"])

    def test_everything_together(self):
        f = load("16_mixed_everything.feature")
        outline, plain = [sc for sc, _ in f.scenarios()]
        self.assertEqual(outline.steps[-1].table, [["key", "value"], ["a", "b"]])
        self.assertEqual(outline.examples[0].rows[1], ["2026-01-01", "accepted"])
        self.assertEqual(plain.steps[0].docstring, '{"coupon": "X"}')


class InputVariantsTest(unittest.TestCase):
    def test_bom_and_crlf_are_accepted(self):
        text = chr(0xFEFF) + "Feature: F\r\n  Scenario: S\r\n    Given a thing\r\n    Then ok\r\n"
        f = parse(text)
        (sc, _), = f.scenarios()
        self.assertEqual([s.text for s in sc.steps], ["a thing", "ok"])

    def test_parse_file_reads_utf8_with_bom(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.feature"
            p.write_bytes(b"\xef\xbb\xbfFeature: F\nScenario: S\nGiven a\n")
            self.assertEqual(parse_file(p).name, "F")

    def test_every_bundled_language_loads_its_keywords(self):
        self.assertGreaterEqual(len(gherkin.languages()), 70)
        for code in ("en", "zh-TW", "zh-CN", "ja", "ko", "de", "fr", "es"):
            self.assertIn(code, gherkin.languages())

    def test_effective_tags_are_deduplicated(self):
        f = parse("@a\nFeature: F\n  @a @b\n  Scenario: S\n    Given x\n")
        (sc, _), = f.scenarios()
        self.assertEqual(f.effective_tags(sc), ["@a", "@b"])


class ErrorTest(unittest.TestCase):
    def assertError(self, text: str, message: str, line: int):
        with self.assertRaises(ParseError) as cm:
            parse(text, "f.feature")
        self.assertIn(message, cm.exception.message)
        self.assertEqual(cm.exception.line, line, cm.exception.message)
        self.assertTrue(str(cm.exception).startswith(f"f.feature:{line}:"))

    def test_errors_name_the_line(self):
        cases = [
            ("", "no Feature found", 1),
            ("Scenario: s\n", "before Feature", 1),
            ("Feature: a\nFeature: b\n", "only one Feature", 2),
            ("# language: xx-YY\nFeature: f\n", "unknown language", 1),
            ("Feature: f\nScenario: s\n  And x\n", "no preceding", 3),
            ("Feature: f\nScenario: s\n  Given x\n  Examples:\n    | a |\n", "inside a Scenario Outline", 4),
            ("Feature: f\nScenario Outline: o\n  Given <a>\n  Examples:\n    | a | b |\n    | 1 |\n", "row has 1 cells", 6),
            ("Feature: f\nScenario: s\n  Given x\n    | a | b\n", "start and end with", 4),
            ("Feature: f\nScenario: s\n  Given x\n    | a |\n    | a | b |\n", "table row has 2 cells", 5),
            ("Feature: f\nScenario: s\n  Given x\n    \"\"\"\n    open\n", "never closed", 4),
            ("Feature: f\nScenario: s\n  Given x\n    | a |\n    \"\"\"\n    x\n    \"\"\"\n", "doc string is only allowed", 5),
            ("Feature: f\nScenario: s\n  Given x\n  some stray words\n", "unexpected text", 4),
            ("Feature: f\nScenario: s\n  Given x\n  @tag\n  Then y\n", "tags must be followed", 5),
            ("Feature: f\nScenario: s\n  Given x\n@dangling\n", "tags at end of file", 4),
            ("Feature: f\n  Scenario: s\n    Given x\n  Background:\n    Given y\n", "Background must come first", 4),
            ("Feature: f\n  @t\n  Background:\n    Given y\n", "not allowed on Background", 3),
            ("| a |\n", "no Feature found", 1),
        ]
        for text, message, line in cases:
            with self.subTest(message=message, line=line):
                if message == "no Feature found" and text.startswith("|"):
                    with self.assertRaises(ParseError):
                        parse(text, "f.feature")
                else:
                    self.assertError(text, message, line)


if __name__ == "__main__":
    unittest.main()
