"""The style warnings of `bdd lint` (L015 to L025): each rule fires on its finding, stays quiet on the clean form, and a
project can silence it. A style finding is never an error."""
import contextlib
import io
import os
import tempfile
import textwrap
import unittest
from pathlib import Path

from bddlib import config, gherkin, lint, stylecheck, vocabulary

from tests.helpers import ProjectCase

MOON = """
version = 1
extends = "core"
"""
PREFIX = "@FEAT-1\nFeature: Orders\n"


def feature(body: str) -> str:
    """A well-formed file around ``body`` (two-space levels, as written for the scenarios below)."""
    return PREFIX + textwrap.indent(textwrap.dedent(body).strip("\n"), "  ") + "\n"


CLEAN = feature("""
    @R-1.1 @EX-1.1.1
    Scenario: A big order gets a discount
      Given alice is signed in as member
      When alice calls place order with:
        | total   |
        | 1000.00 |
      Then the response contains:
        | discount |
        | 100      |

    @R-1.1 @EX-1.1.2
    Scenario: A small order gets none
      Given alice is signed in as member
      When alice calls place order with:
        | total |
        | 99.00 |
      Then the response contains:
        | discount |
        | 0        |
""")


class StyleBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vocab = vocabulary.load(None)

    def warnings(self, text: str, path: str = "orders.feature", ignore: tuple[str, ...] = ()) -> list[str]:
        linter = lint.Linter(self.vocab, config.ALL_PROFILES, trace_tags=False, ignore=ignore)
        return [f"{i.code}:{i.line}" for i in linter.lint_text(text, path) if i.code in config.LINT_STYLE_CODES]

    def codes(self, text: str, **kw) -> list[str]:
        return [w.split(":")[0] for w in self.warnings(text, **kw)]


class CleanFileTest(StyleBase):
    def test_a_well_formed_file_has_no_style_warnings(self):
        self.assertEqual(self.warnings(CLEAN), [])

    def test_style_findings_are_warnings_never_errors(self):
        text = feature("""
            Scenario: Stray
              Then the request succeeds
              When alice calls place order
        """)
        linter = lint.Linter(self.vocab, config.ALL_PROFILES, trace_tags=False)
        issues = [i for i in linter.lint_text(text, "orders.feature") if i.code in config.LINT_STYLE_CODES]
        self.assertTrue(issues)
        self.assertEqual({i.severity for i in issues}, {"warning"})


class OrderTest(StyleBase):
    def test_a_given_after_a_when_is_reported_once_at_the_step(self):
        text = feature("""
            Scenario: Out of order
              When alice calls place order
              Given alice is signed in as member
              Then the request succeeds
        """)
        self.assertEqual(self.warnings(text), ["L015:5"])

    def test_a_phase_that_comes_back_is_reported(self):
        text = feature("""
            Scenario: Two behaviours
              Given alice is signed in as member
              When alice calls place order
              Then the request succeeds
              When alice calls place order
              Then the request succeeds
        """)
        self.assertEqual(self.warnings(text), ["L015:7"])

    def test_and_and_but_continue_their_phase_and_a_longer_phase_is_fine(self):
        text = feature("""
            Scenario: In order
              Given alice is signed in as member
              And the current time is 2026-10-21T10:00:00Z
              When alice calls place order
              Then the request succeeds
              And no order records changed
        """)
        self.assertEqual(self.codes(text), [])

    def test_or_as_a_step_keyword_is_still_a_parse_error_not_a_warning(self):
        text = feature("""
            Scenario: Choices
              Given alice is signed in as member
              Or bob is signed in as member
              When alice calls place order
        """)
        linter = lint.Linter(self.vocab, config.ALL_PROFILES, trace_tags=False)
        issues = linter.lint_text(text, "orders.feature")
        self.assertEqual([(i.code, i.severity) for i in issues], [("L001", "error")])


class LengthTest(StyleBase):
    def steps(self, count: int) -> str:
        lines = ["Scenario: Long", "  Given alice is signed in as member", "  When alice calls place order"]
        lines += ["  Then the request succeeds"] + ["  And no order records changed"] * (count - 3)
        return feature("\n".join(lines))

    def test_ten_steps_are_fine_and_eleven_are_reported_at_the_scenario(self):
        self.assertEqual(self.codes(self.steps(10)), [])
        self.assertEqual(self.warnings(self.steps(11)), ["L016:3"])


class PlaceholderTest(StyleBase):
    def test_placeholder_values_in_a_table_a_quote_and_a_word_are_reported(self):
        for step in ('Given the following products exist:\n        | name |\n        | foo  |',
                     'Given the following products exist:\n        | name |\n        | test |',
                     'Given alice is signed in as "bar"',
                     'Given alice is signed in as lorem'):
            with self.subTest(step=step):
                text = feature(f"Scenario: S\n  {step}\n  When alice calls place order\n  Then the request succeeds")
                self.assertEqual(self.codes(text), ["L017"])

    def test_placeholder_examples_are_reported_at_the_examples(self):
        text = feature("""
            Scenario Outline: S
              Given alice is signed in as <role>
              When alice calls place order
              Then the request succeeds

              Examples:
                | role |
                | foo  |
                | baz  |
        """)
        self.assertEqual(self.warnings(text), ["L017:8"])

    def test_realistic_values_and_ordinary_words_are_fine(self):
        text = feature("""
            Scenario: Real
              Given the following products exist:
                | name          |
                | Green tea 50g |
                | Test kitchen  |
              When alice calls place order
              Then the request succeeds
        """)
        self.assertEqual(self.codes(text), [])

    def test_a_scenario_about_invalid_input_may_use_nonsense(self):
        for header in ("Scenario: Invalid role is refused", "@invalid-input\nScenario: S"):
            with self.subTest(header=header):
                text = feature(f"{header}\n  Given alice is signed in as foo\n  When alice calls place order\n"
                               "  Then the request succeeds")
                self.assertEqual(self.codes(text), [])


class BackgroundAndOutlineTest(StyleBase):
    def test_a_background_for_one_scenario_is_reported_and_for_two_is_not(self):
        one = feature("""
            Background:
              Given alice is signed in as member

            Scenario: Only
              When alice calls place order
              Then the request succeeds
        """)
        two = one + "\n  Scenario: Second\n    When alice calls place order\n    Then the request succeeds\n"
        self.assertEqual(self.warnings(one), ["L018:3"])
        self.assertEqual(self.codes(two), [])

    def test_a_rule_background_counts_the_scenarios_of_its_rule(self):
        text = feature("""
            Rule: R

              Background:
                Given alice is signed in as member

              Scenario: Only
                When alice calls place order
                Then the request succeeds
        """)
        self.assertEqual(self.codes(text), ["L018"])

    def outline(self, rows: str) -> str:
        return feature(f"""
            Scenario Outline: Sized
              Given alice is signed in as member
              When alice calls place order with "<total>"
              Then the request succeeds

              Examples:
                | total |
{rows}
        """)

    def test_an_outline_needs_two_distinct_rows(self):
        self.assertEqual(self.codes(self.outline("                | 10 |")), ["L019"])
        self.assertEqual(self.codes(self.outline("                | 10 |\n                | 20 |")), [])
        self.assertEqual(self.codes(self.outline("                | Big |\n                | big |")), ["L019"])


class TitleTest(StyleBase):
    def test_an_empty_title_and_text_under_a_title_are_reported(self):
        empty = feature("Scenario:\n  When alice calls place order\n  Then the request succeeds")
        carried = feature("Scenario: A long title that\n  continues here\n  When alice calls place order\n"
                          "  Then the request succeeds")
        self.assertEqual(self.codes(empty), ["L020"])
        self.assertEqual(self.codes(carried), ["L020"])


class LayoutTest(StyleBase):
    def test_wrong_indentation_names_the_line_and_the_expected_width(self):
        text = PREFIX + "    Scenario: Deep\n        When alice calls place order\n        Then the request succeeds\n"
        found = [i for i in lint.Linter(self.vocab, trace_tags=False).lint_text(text, "orders.feature") if i.code == "L021"]
        self.assertEqual([i.line for i in found], [3, 4, 5])
        self.assertIn("expected 2", found[0].message)
        self.assertIn("expected 4", found[1].message)

    def test_a_rule_pushes_its_scenarios_one_level_deeper(self):
        text = PREFIX + ("  Rule: R\n\n    Scenario: S\n      When alice calls place order\n"
                         "      Then the request succeeds\n")
        self.assertEqual(self.codes(text), [])

    def test_a_tab_is_reported_as_a_tab(self):
        text = PREFIX + "\tScenario: Tabbed\n    When alice calls place order\n    Then the request succeeds\n"
        found = [i for i in lint.Linter(self.vocab, trace_tags=False).lint_text(text, "orders.feature") if i.code == "L021"]
        self.assertIn("tab", found[0].message)

    def test_a_long_line_is_reported_but_a_long_line_in_a_doc_string_is_not(self):
        long_title = "Scenario: " + "word " * 30
        text = feature(f"{long_title}\n  When alice calls place order\n  Then the request succeeds")
        self.assertEqual(self.warnings(text), ["L022:3"])
        payload = ('Scenario: Payload\n  Given the input file in.txt contains:\n    """\n    ' + "x" * 150 + '\n    """\n'
                   "  When alice calls place order\n  Then the request succeeds")
        self.assertEqual(self.codes(feature(payload)), [])

    def test_a_blank_line_between_steps_is_reported_but_not_inside_a_doc_string(self):
        gap = feature("Scenario: S\n  Given alice is signed in as member\n\n  When alice calls place order\n"
                      "  Then the request succeeds")
        self.assertEqual(self.warnings(gap), ["L023:5"])
        doc = feature('Scenario: S\n  Given the input file in.txt contains:\n    """\n    a\n\n    b\n    """\n'
                      "  When alice calls place order\n  Then the request succeeds")
        self.assertEqual(self.codes(doc), [])

    def test_scenarios_need_a_blank_line_between_them_tags_travel_with_their_scenario(self):
        tight = feature("""
            @EX-1.1.1
            Scenario: One
              When alice calls place order
              Then the request succeeds
            @EX-1.1.2
            Scenario: Two
              When alice calls place order
              Then the request succeeds
        """)
        self.assertEqual(self.warnings(tight), ["L024:8"])
        spaced = tight.replace("    Then the request succeeds\n  @EX", "    Then the request succeeds\n\n  @EX")
        self.assertEqual(self.codes(spaced), [])

    def test_the_first_scenario_may_follow_its_header_directly(self):
        self.assertEqual(self.codes(feature("Rule: R\n  Scenario: S\n    When alice calls place order\n"
                                            "    Then the request succeeds")), [])

    def test_file_names_must_be_kebab_case(self):
        for name, expected in (("order-discounts.feature", []), ("orders2.feature", []), ("OrderDiscounts.feature", ["L025"]),
                               ("order_discounts.feature", ["L025"]), ("Order-1.feature", ["L025"]),
                               ("<string>", [])):
            with self.subTest(name=name):
                self.assertEqual(self.codes(CLEAN, path=name), expected)


class IgnoreTest(StyleBase):
    def test_the_ignore_list_silences_only_the_codes_it_names(self):
        text = PREFIX + "    Scenario: Deep\n        When alice calls place order\n        Then the request succeeds\n"
        self.assertEqual(self.codes(text), ["L021", "L021", "L021"])
        self.assertEqual(self.codes(text, ignore=("L021",)), [])
        self.assertEqual(self.codes(text, ignore=("L022",)), ["L021", "L021", "L021"])


class ConfigTest(ProjectCase):
    def set_lint(self, body: str) -> None:
        self.write(".bdd/config.toml", '[[adapters]]\nname = "x"\nfeatures = "features"\nsteps = "steps"\n' + body)

    def run_lint(self, *args: str) -> tuple[int, str]:
        out, here = io.StringIO(), os.getcwd()
        os.chdir(self.root)
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                return lint.run(list(args)), out.getvalue()
        finally:
            os.chdir(here)

    def test_the_ignore_list_is_read_and_checked(self):
        self.set_lint('\n[lint]\nignore = ["L021", "L021", "L017"]\n')
        self.assertEqual(config.load(self.root).lint_ignore, ("L021", "L017"))
        for bad in ('ignore = ["L002"]', 'ignore = ["style"]', 'ignore = "L021"', "ignore = [21]", "ignore = [\"L014\"]"):
            with self.subTest(bad=bad):
                self.set_lint(f"\n[lint]\n{bad}\n")
                with self.assertRaises(config.ConfigError):
                    config.load(self.root)

    def test_errors_cannot_be_silenced_and_the_exit_code_ignores_warnings(self):
        self.write("features/ugly.feature", PREFIX + "    Scenario: Deep\n        Then the request succeeds\n")
        self.set_lint("")
        code, out = self.run_lint("features/ugly.feature", "--no-trace-tags")
        self.assertEqual(code, 0)
        self.assertIn("L021", out)
        self.set_lint('\n[lint]\nignore = ["L021"]\n')
        code, out = self.run_lint("features/ugly.feature", "--no-trace-tags")
        self.assertEqual((code, "L021" in out), (0, False))
        self.assertIn("0 warning(s)", out)


class RepositoryFeaturesTest(unittest.TestCase):
    """The features this repository ships (examples, the adapters' samples and its own specs) follow its own style rules."""

    def test_no_shipped_feature_has_a_style_warning(self):
        repo = Path(__file__).resolve().parents[3]
        files = sorted(p for folder in ("docs/examples", "adapters", "specs") for p in (repo / folder).rglob("*.feature")
                       if "node_modules" not in p.parts)
        self.assertTrue(files)
        found = []
        for path in files:
            text = path.read_text(encoding="utf-8-sig")
            try:
                parsed = gherkin.parse(text, str(path))
            except gherkin.ParseError:
                continue
            found += [f"{path.relative_to(repo).as_posix()}:{i.line}: {i.code} {i.message}"
                      for i in stylecheck.check_feature(parsed, text, str(path))]
        self.assertEqual(found, [])


if __name__ == "__main__":
    unittest.main()
