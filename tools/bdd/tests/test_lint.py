import contextlib
import io
import json
import tempfile
import textwrap
import unittest
from pathlib import Path

from bddlib import config, lint, vocabulary

DOMAIN = '''
version = 1

[[steps]]
id = "D.CART.WORTH"
kind = "given"
pattern = "{actor} has a cart worth {amount:int}"
composes = ["C.ACTOR.AUTH"]

[[steps]]
id = "D.DUP.A"
kind = "when"
pattern = "the shopper pays"

[[steps]]
id = "D.DUP.B"
kind = "when"
pattern = "the shopper {verb}"
'''


MOON = '''
[[steps]]
id = "D.MOON"
kind = "given"
pattern = "the moon is full"
composes = ["C.ENTITY.SEED"]
'''


def feature(body: str, header: str = "Feature: F") -> str:
    return textwrap.dedent(header).strip() + "\n" + textwrap.indent(textwrap.dedent(body).strip("\n"), "  ") + "\n"


class LintBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        vocab_file = Path(cls.tmp.name) / "vocabulary.toml"
        vocab_file.write_text(DOMAIN, encoding="utf-8")
        cls.vocab = vocabulary.load(vocab_file)

    def issues(self, text: str, profiles=config.ALL_PROFILES):
        """The errors and vocabulary findings of a file; its style warnings have their own tests (test_stylecheck.py)."""
        linter = lint.Linter(self.vocab, profiles, trace_tags=False, ignore=config.LINT_STYLE_CODES)
        return linter.lint_text(text, "f.feature")

    def codes(self, text: str, **kw) -> list[str]:
        return [f"{i.code}:{i.line}" for i in self.issues(text, **kw)]


class StepResolutionTest(LintBase):
    def test_clean_feature_has_no_issues(self):
        text = feature('''
            Scenario: Checkout
              Given Alice has a cart worth 999
              And the following products exist:
                | sku |
                | A1  |
              When Alice calls quote.create with:
                | qty |
                | 1   |
              Then the request succeeds
        ''')
        self.assertEqual(self.issues(text), [])

    def test_unresolved_step_is_an_error_with_the_closest_pattern(self):
        (issue,) = self.issues(feature('''
            Scenario: S
              Then the request is rejected
        '''))
        self.assertEqual((issue.code, issue.severity, issue.line), ("L002", "error", 3))
        self.assertIn('Closest: C.API.STATUS "the request is rejected with {error}"', issue.message)

    def test_unrelated_text_gets_no_misleading_suggestion(self):
        (issue,) = self.issues(feature("Scenario: S\n  Given the moon is full\n"))
        self.assertEqual(issue.code, "L002")
        self.assertNotIn("Closest", issue.message)

    def test_proposed_step_is_only_a_warning(self):
        issues = self.issues(feature('''
            Scenario: S
              # proposed-step
              Given the moon is full
        '''))
        self.assertEqual([(i.code, i.severity) for i in issues], [("L011", "warning")])

    def test_a_comment_that_is_not_the_marker_does_not_excuse_a_step(self):
        issues = self.issues(feature("Scenario: S\n  # TODO later\n  Given the moon is full\n"))
        self.assertEqual([i.code for i in issues], ["L002"])

    def test_ambiguous_steps_name_every_candidate(self):
        (issue,) = self.issues(feature("Scenario: S\n  When the shopper pays\n"))
        self.assertEqual(issue.code, "L003")
        self.assertIn("D.DUP.A", issue.message)
        self.assertIn("D.DUP.B", issue.message)

    def test_kind_is_inherited_by_and_but(self):
        text = feature("Scenario: S\n  Given Alice has a cart worth 5\n  And Bob has a cart worth 6\n  When the shopper pays\n")
        self.assertEqual(self.codes(text), ["L003:5"])  # only the ambiguous step

    def test_background_and_rule_background_steps_are_checked(self):
        text = feature('''
            Background:
              Given the moon is full

            Rule: R
              Background:
                Given the sun is hot

              Scenario: S
                Given Alice has a cart worth 1
        ''')
        self.assertEqual(self.codes(text), ["L002:3", "L002:7"])

    def test_parse_errors_become_L001_with_the_line(self):
        (issue,) = self.issues("Feature: F\nScenario: S\n  And x\n")
        self.assertEqual((issue.code, issue.line), ("L001", 3))

    def test_localized_features_resolve_core_and_english_steps(self):
        text = "# language: zh-TW\n功能: 折扣\n  場景: S\n    假設 以下商品已存在:\n      | sku |\n      | A1 |\n    而且 the current time is 2026-01-01\n"
        self.assertEqual(self.issues(text), [])


class ProfileAndShapeTest(LintBase):
    def test_instruction_from_a_disabled_profile(self):
        text = feature("Scenario: S\n  When Alice opens the Home page\n")
        self.assertEqual(self.codes(text), [])
        (issue,) = self.issues(text, profiles=("base", "api"))
        self.assertEqual(issue.code, "L007")
        self.assertIn("C.UI.OPEN", issue.message)

    def test_the_query_count_step_needs_the_data_profile(self):
        text = feature("Scenario: S\n  Then list orders ran at most 2 queries\n")
        self.assertEqual(self.codes(text), [])
        (issue,) = self.issues(text, profiles=("base", "api"))
        self.assertEqual(issue.code, "L007")
        self.assertIn("C.QUERY.COUNT", issue.message)
        self.assertEqual(self.codes(feature("Scenario: S\n  Then list orders ran at most many queries\n")), ["L002:3"])

    def test_domain_steps_are_not_profile_checked(self):
        text = feature("Scenario: S\n  Given Alice has a cart worth 5\n")
        self.assertEqual(self.codes(text, profiles=("cli",)), [])

    def test_table_and_doc_string_requirements(self):
        cases = [
            ("Given the following products exist:\n", "L008"),                                  # table required
            ('Given the following products exist:\n  """\n  x\n  """\n', "L008"),               # doc string is not a table
            ("Then the request succeeds\n  | a |\n", "L008"),                                  # takes no data
            ("Given the input file in.txt contains:\n", "L008"),                                # table or doc string
            ('Given the input file in.txt contains:\n  """\n  text\n  """\n', None),
            ("Given the input file in.txt contains:\n  | a |\n", None),
            ("When Alice calls quote.create\n", None),                                          # optional data
            ("When Alice calls quote.create with:\n  | a |\n", None),
            ('When Alice calls quote.create with:\n  """\n  {}\n  """\n', None),
        ]
        for step, code in cases:
            with self.subTest(step=step.splitlines()[0], expect=code):
                text = "Feature: F\nScenario: S\n" + textwrap.indent(step, "  ")
                found = [i.code for i in self.issues(text)]
                self.assertEqual(found, [code] if code else [])


class OutlineTest(LintBase):
    def test_parameters_must_exist_as_columns(self):
        text = feature('''
            Scenario Outline: O
              Given Alice has a cart worth <amount>
              Then the request is rejected with <error>

              Examples:
                | amount |
                | 1      |
        ''')
        issues = self.issues(text)
        self.assertEqual([(i.code, i.severity) for i in issues], [("L009", "error")])
        self.assertIn("<error>", issues[0].message)

    def test_unused_columns_warn(self):
        text = feature('''
            Scenario Outline: O
              Given Alice has a cart worth <amount>

              Examples:
                | amount | spare |
                | 1      | x     |
        ''')
        issues = self.issues(text)
        self.assertEqual([(i.code, i.severity) for i in issues], [("L009", "warning")])
        self.assertIn('"spare"', issues[0].message)

    def test_parameters_inside_tables_and_doc_strings_count_as_used(self):
        text = feature('''
            Scenario Outline: O
              Given the following products exist:
                | sku   |
                | <sku> |
              When Alice calls quote.create with:
                """
                {"qty": <qty>}
                """

              Examples:
                | sku | qty |
                | A1  | 2   |
        ''')
        self.assertEqual(self.issues(text), [])

    def test_outline_without_examples(self):
        (issue,) = self.issues(feature("Scenario Outline: O\n  Given Alice has a cart worth 1\n"))
        self.assertEqual((issue.code, issue.severity), ("L009", "error"))


class CliTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name)
        (self.root / ".bdd").mkdir()
        (self.root / "features").mkdir()

    def write(self, rel: str, text: str) -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def run_lint(self, *args: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        import os
        cwd = os.getcwd()
        os.chdir(self.root)
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = lint.run(list(args))
        finally:
            os.chdir(cwd)
        return code, out.getvalue(), err.getvalue()

    HEAD = "@FEAT-1\nFeature: F\n  @R-1.1 @EX-1.1.1\n  Scenario: S\n"
    GOOD = HEAD + "    Then the request succeeds\n"
    BAD = HEAD + "    Then the request is rejected\n"

    def test_exit_codes_and_text_output(self):
        good = self.write("features/good.feature", self.GOOD)
        bad = self.write("features/sub/bad.feature", self.BAD)
        code, out, _ = self.run_lint(str(good))
        self.assertEqual((code, out.strip()), (0, "1 file(s), 0 error(s), 0 warning(s)"))
        code, out, _ = self.run_lint(str(self.root / "features"))     # directory, recursive
        self.assertEqual(code, 1)
        self.assertIn("bad.feature:5: error L002:", out)
        self.assertIn("2 file(s), 1 error(s)", out)
        self.assertEqual(self.run_lint(str(bad))[0], 1)

    def test_warnings_alone_do_not_fail(self):
        f = self.write("features/w.feature", self.HEAD + "    # proposed-step\n    Then something new\n")
        code, out, _ = self.run_lint(str(f))
        self.assertEqual(code, 0)
        self.assertIn("warning L011", out)

    def test_options_may_come_after_the_paths(self):
        f = self.write("features/bad.feature", self.BAD)
        code, out, _ = self.run_lint(str(f), "--json", "--no-trace-tags")
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out)["summary"]["errors"], 1)

    def test_json_output(self):
        f = self.write("features/bad.feature", self.BAD)
        code, out, _ = self.run_lint("--json", str(f))
        data = json.loads(out)
        self.assertEqual(code, 1)
        self.assertEqual(data["summary"], {"files": 1, "errors": 1, "warnings": 0})
        self.assertEqual(data["issues"][0]["code"], "L002")
        self.assertEqual(data["issues"][0]["line"], 5)

    def test_defaults_come_from_the_project_config(self):
        self.write(".bdd/config.toml", 'profiles = ["base"]\n[[adapters]]\nname = "x"\nfeatures = "features"\n')
        self.write("features/ui.feature", self.HEAD + "    When Alice opens the Home page\n")
        code, out, _ = self.run_lint()                        # no paths: uses the configured feature dir
        self.assertEqual(code, 1)
        self.assertIn("L007", out)
        self.assertEqual(self.run_lint("--profiles", "base,ui")[0], 0)

    def test_project_vocabulary_is_picked_up(self):
        self.write(".bdd/vocabulary.toml", MOON)
        f = self.write("features/m.feature", self.HEAD + "    Given the moon is full\n")
        self.assertEqual(self.run_lint(str(f))[0], 0)

    def test_trace_tags_are_required_unless_switched_off(self):
        f = self.write("features/untagged.feature", "Feature: F\n  Scenario: S\n    Then the request succeeds\n")
        code, out, _ = self.run_lint(str(f))
        self.assertEqual(code, 1)
        for expected in ("needs exactly one @FEAT-<n> tag", "needs exactly one @R-<feature>.<n> tag",
                         "needs exactly one @EX-<feature>.<rule>.<n> tag"):
            self.assertIn(expected, out)
        self.assertEqual(self.run_lint("--no-trace-tags", str(f))[0], 0)

    def test_implementation_details_in_steps_are_errors(self):
        f = self.write("features/detail.feature", self.HEAD + "    Then the response is HTTP 404\n")
        code, out, _ = self.run_lint(str(f))
        self.assertEqual(code, 1)
        self.assertIn("L004", out)
        self.assertIn("HTTP status code", out)

    def test_problems_in_the_project_vocabulary_are_reported_against_its_file(self):
        self.write(".bdd/vocabulary.toml", '[[steps]]\nid = "D.LAZY"\nkind = "given"\npattern = "the moon is full"\n')
        good = self.write("features/g.feature", self.GOOD)
        code, out, _ = self.run_lint(str(good))
        self.assertEqual(code, 1)
        self.assertIn("vocabulary.toml:2: error L012: D.LAZY: a domain step must list the core instructions", out)

    def test_similarity_threshold_comes_from_the_config(self):
        steps = ('[[steps]]\nid = "D.A"\nkind = "given"\npattern = "{{actor}} has a cart worth {{n:int}}"\n'
                 'composes = ["C.ENTITY.SEED"]\n\n[[steps]]\nid = "D.B"\nkind = "given"\n'
                 'pattern = "{{actor}} has a large cart worth {{n:int}}"\ncomposes = ["C.ENTITY.SEED"]\n')
        self.write(".bdd/vocabulary.toml", steps.format())
        good = self.write("features/g.feature", self.GOOD)
        self.assertEqual(self.run_lint(str(good))[0], 0)                       # 0.83 < the default 0.85
        self.write(".bdd/config.toml", "[gates]\nnear_duplicate_step_similarity = 0.7\n")
        code, out, _ = self.run_lint(str(good))
        self.assertEqual(code, 1)
        self.assertIn("L010", out)

    def test_lint_refuses_to_read_files_that_are_not_feature_files(self):
        secret = self.write("secret.txt", "Feature: F\nTOP-SECRET-TOKEN-123\n")
        code, out, err = self.run_lint(str(secret))
        self.assertEqual(code, 2)
        self.assertIn("not a .feature file", err)
        self.assertNotIn("TOP-SECRET", out + err)      # nothing from the file is echoed back

    def test_vocabulary_option_is_limited_to_toml_files_inside_the_project(self):
        good = self.write("features/g.feature", self.GOOD)
        outside = tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False, encoding="utf-8")
        outside.write("TOP-SECRET-TOKEN-123 = oops\n")
        outside.close()
        self.addCleanup(lambda: Path(outside.name).unlink())
        for arg in (outside.name, str(self.write("notes.txt", "x"))):
            with self.subTest(arg=Path(arg).name):
                code, out, err = self.run_lint("--vocabulary", arg, str(good))
                self.assertEqual(code, 2)
                self.assertIn("--vocabulary must be a .toml file inside", err)
                self.assertNotIn("TOP-SECRET", out + err)
        inside = self.write("custom.toml", MOON)
        self.assertEqual(self.run_lint("--vocabulary", str(inside), str(good))[0], 0)

    def test_hidden_and_node_modules_directories_are_skipped(self):
        self.write("features/.cache/x.feature", self.BAD)
        self.write("features/node_modules/y.feature", self.BAD)
        self.write("features/ok.feature", self.GOOD)
        code, out, _ = self.run_lint(str(self.root / "features"))
        self.assertEqual((code, out.strip()), (0, "1 file(s), 0 error(s), 0 warning(s)"))

    def test_usage_problems_exit_2(self):
        self.assertEqual(self.run_lint()[0], 2)                                        # nothing to lint
        self.assertEqual(self.run_lint("nope.feature")[0], 2)                          # missing path
        self.assertEqual(self.run_lint("--profiles", "web", "x")[0], 2)                # unknown profile
        self.write(".bdd/config.toml", 'profiles = ["web"]\n')
        code, _, err = self.run_lint(str(self.write("features/g.feature", self.GOOD)))
        self.assertEqual(code, 2)
        self.assertIn("unknown profile", err)


class ConfigTest(unittest.TestCase):
    def test_find_root_walks_up(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d).resolve()
            (root / ".bdd").mkdir()
            deep = root / "a" / "b"
            deep.mkdir(parents=True)
            self.assertEqual(config.find_root(deep), root)

    def test_defaults_without_a_project(self):
        c = config.load(None)
        self.assertEqual(c.profiles, config.ALL_PROFILES)
        self.assertEqual(c.near_duplicate_similarity, 0.85)
        self.assertIsNone(c.vocabulary_file)


if __name__ == "__main__":
    unittest.main()
