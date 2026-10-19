import textwrap
import unittest

from bddlib import gherkin, tagcheck


def check(text: str) -> list[str]:
    feature = gherkin.parse(textwrap.dedent(text).strip() + "\n", "f.feature")
    return [f"{i.code}:{i.line}:{i.message}" for i in tagcheck.check_trace_tags(feature, "f.feature")]


GOOD = '''
    @FEAT-7
    Feature: Discounts

      @R-7.1
      Rule: Bulk

        @EX-7.1.1
        Scenario: At the threshold
          Given a thing

        @EX-7.1.2
        Scenario Outline: Around it
          Given <x>

          @partition-low
          Examples:
            | x |
            | 1 |

      @R-7.2
      Rule: Coupons

        @EX-7.2.1
        Scenario: One coupon
          Given a thing
'''


class TraceTagsTest(unittest.TestCase):
    def test_a_fully_tagged_feature_passes(self):
        self.assertEqual(check(GOOD), [])

    def test_features_without_rule_blocks_tag_the_scenario_itself(self):
        self.assertEqual(check('''
            @FEAT-7
            Feature: F
              @R-7.1 @EX-7.1.1
              Scenario: S
                Given a thing
        '''), [])

    def test_a_rule_tag_on_the_feature_is_inherited_by_every_scenario(self):
        self.assertEqual(check('''
            @FEAT-7 @R-7.1
            Feature: F
              @EX-7.1.1
              Scenario: S
                Given a thing
        '''), [])

    def test_missing_and_repeated_feature_tag(self):
        text = "Feature: F\n  @R-7.1 @EX-7.1.1\n  Scenario: S\n    Given x\n"
        self.assertEqual([m.split(":")[0] for m in check(text)], ["L005"])
        self.assertIn("needs exactly one @FEAT-<n> tag: missing", check(text)[0])
        repeated = "@FEAT-7 @FEAT-8\n" + text
        self.assertIn("repeated (@FEAT-7, @FEAT-8)", check(repeated)[0])

    def test_rule_without_a_tag_and_with_the_wrong_feature(self):
        text = '''
            @FEAT-7
            Feature: F
              Rule: Untagged
                @EX-7.1.1
                Scenario: S
                  Given x
        '''
        found = check(text)
        self.assertTrue(any('Rule "Untagged" needs exactly one @R-<feature>.<n> tag: missing' in m for m in found), found)
        wrong = check('''
            @FEAT-7
            Feature: F
              @R-9.1
              Rule: Other feature
                @EX-9.1.1
                Scenario: S
                  Given x
        ''')
        self.assertTrue(any("@R-9.1 belongs to feature 9, not 7" in m for m in wrong), wrong)

    def test_scenario_needs_exactly_one_example_tag(self):
        text = "@FEAT-7\nFeature: F\n  @R-7.1\n  Scenario: S\n    Given x\n"
        self.assertTrue(any('Scenario "S" needs exactly one @EX-<feature>.<rule>.<n> tag: missing' in m for m in check(text)))
        twice = "@FEAT-7\nFeature: F\n  @R-7.1 @EX-7.1.1 @EX-7.1.2\n  Scenario: S\n    Given x\n"
        self.assertTrue(any("repeated (@EX-7.1.1, @EX-7.1.2)" in m for m in check(twice)))

    def test_example_must_belong_to_the_rule_and_the_feature(self):
        found = check('''
            @FEAT-7
            Feature: F
              @R-7.1
              Rule: A
                @EX-7.2.1
                Scenario: wrong rule
                  Given x
                @EX-8.1.1
                Scenario: wrong feature
                  Given x
        ''')
        self.assertTrue(any("@EX-7.2.1 does not belong to @R-7.1" in m for m in found), found)
        self.assertTrue(any("@EX-8.1.1 belongs to feature 8, not 7" in m for m in found), found)

    def test_malformed_tags_are_reported_once_where_they_are_written(self):
        found = check('''
            @FEAT-7 @R-bad
            Feature: F
              @R-7.1
              Rule: A
                @EX-7.1.1
                Scenario: one
                  Given x
                @EX-7.1.2
                Scenario: two
                  Given x
        ''')
        malformed = [m for m in found if "malformed trace tag @R-bad" in m]
        self.assertEqual(len(malformed), 1, found)
        self.assertTrue(malformed[0].startswith("L005:2:"))   # the Feature line, not every scenario

    def test_duplicate_example_ids(self):
        found = check('''
            @FEAT-7
            Feature: F
              @R-7.1
              Rule: A
                @EX-7.1.1
                Scenario: first
                  Given x
                @EX-7.1.1
                Scenario: second
                  Given x
        ''')
        self.assertEqual([m.split(":")[0] for m in found], ["L006"])
        self.assertIn('already used by Scenario "first"', found[0])

    def test_other_tags_are_ignored(self):
        self.assertEqual(check(GOOD.replace("@FEAT-7", "@FEAT-7 @smoke @existing")), [])


if __name__ == "__main__":
    unittest.main()
