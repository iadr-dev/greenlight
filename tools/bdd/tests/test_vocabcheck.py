import tempfile
import textwrap
import unittest
from pathlib import Path

from bddlib import config, vocabcheck, vocabulary


class VocabCheckBase(unittest.TestCase):
    def check(self, toml: str, profiles=config.ALL_PROFILES, threshold: float = 0.85) -> list[str]:
        source = textwrap.dedent(toml).strip() + "\n"
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "vocabulary.toml"
            path.write_text(source, encoding="utf-8")
            vocab = vocabulary.load(path)
            found = vocabcheck.check_vocabulary(vocab, profiles, threshold, path, source)
        return [f"{i.code}:{i.line}:{i.message}" for i in found]


class CompositionTest(VocabCheckBase):
    def test_well_formed_steps_pass(self):
        self.assertEqual(self.check('''
            [[steps]]
            id = "D.CART"
            kind = "given"
            pattern = "{actor} has a cart worth {amount:int}"
            composes = ["C.ACTOR.AUTH", "C.ENTITY.SEED"]

            [[steps]]
            id = "D.QUOTE"
            kind = "when"
            pattern = "{actor} views the order quote"
            composes = ["C.API.CALL"]

            [[steps]]
            id = "D.TOTAL"
            kind = "then"
            pattern = "the total is {amount:int}"
            composes = ["C.API.BODY"]
        '''), [])

    def test_a_step_must_list_what_it_composes(self):
        (msg,) = self.check('''
            [[steps]]
            id = "D.NOTHING"
            kind = "given"
            pattern = "something happens"
        ''')
        self.assertTrue(msg.startswith("L012:2:"))      # the line of `id = "D.NOTHING"`
        self.assertIn("must list the core instructions it composes", msg)

    def test_composed_instructions_must_be_in_an_enabled_profile(self):
        toml = '''
            [[steps]]
            id = "D.HOME"
            kind = "when"
            pattern = "{actor} goes home"
            composes = ["C.UI.OPEN"]
        '''
        self.assertEqual(self.check(toml), [])
        (msg,) = self.check(toml, profiles=("base", "api"))
        self.assertIn("composes C.UI.OPEN, whose profile(s) ui are not enabled", msg)

    def test_then_and_when_steps_must_really_assert_or_act(self):
        for kind, composes in [("then", "C.ENTITY.SEED"), ("when", "C.ENTITY.SEED")]:
            with self.subTest(kind=kind):
                (msg,) = self.check(f'''
                    [[steps]]
                    id = "D.X"
                    kind = "{kind}"
                    pattern = "something"
                    composes = ["{composes}"]
                ''')
                self.assertIn(f"a `{kind}` step must compose at least one `{kind}` core instruction", msg)

    def test_given_steps_may_compose_any_kind(self):
        self.assertEqual(self.check('''
            [[steps]]
            id = "D.PLACED"
            kind = "given"
            pattern = "{actor} has placed an order"
            composes = ["C.API.CALL"]
        '''), [])


class DetailsTest(VocabCheckBase):
    def test_patterns_must_not_mention_implementation_details(self):
        (msg,) = self.check('''
            [[steps]]
            id = "D.POST"
            kind = "when"
            pattern = "{actor} posts to /api/orders/{id}"
            composes = ["C.API.CALL"]
        ''')
        self.assertTrue(msg.startswith("L004:2:"))
        self.assertIn("URL path", msg)


class NearDuplicateTest(VocabCheckBase):
    TWO = '''
        [[steps]]
        id = "D.A"
        kind = "given"
        pattern = "{actor} has a cart worth {amount:int}"
        composes = ["C.ENTITY.SEED"]
        %s
        [[steps]]
        id = "D.B"
        kind = "given"
        pattern = "{actor} has a cart worth {total:int}"
        composes = ["C.ENTITY.SEED"]
        %s
    '''

    def test_near_identical_patterns_are_flagged_on_the_later_unjustified_step(self):
        (msg,) = self.check(self.TWO % ("", ""))
        line_of_b = textwrap.dedent(self.TWO % ("", "")).strip().splitlines().index('id = "D.B"') + 1
        self.assertTrue(msg.startswith(f"L010:{line_of_b}:"), msg)     # reported on the later definition
        self.assertIn("similarity 1.00", msg)
        self.assertIn("give D.B a `justification`", msg)

    def test_justification_clears_the_pair(self):
        reason = 'justification = "different checkout flow"'
        self.assertEqual(self.check(self.TWO % (reason, reason)), [])

    def test_one_justified_step_does_not_excuse_the_other(self):
        (msg,) = self.check(self.TWO % ('justification = "reason"', ""))
        self.assertIn("give D.B a `justification`", msg)

    def test_threshold_is_configurable_and_dissimilar_steps_pass(self):
        toml = '''
            [[steps]]
            id = "D.A"
            kind = "given"
            pattern = "{actor} has a cart worth {amount:int}"
            composes = ["C.ENTITY.SEED"]

            [[steps]]
            id = "D.B"
            kind = "given"
            pattern = "{actor} has a large cart worth {amount:int}"
            composes = ["C.ENTITY.SEED"]
        '''
        self.assertEqual(self.check(toml, threshold=0.9), [])      # 0.83: below the threshold
        (msg,) = self.check(toml, threshold=0.8)
        self.assertIn("L010", msg)

    def test_steps_of_different_kinds_are_never_compared(self):
        self.assertEqual(self.check('''
            [[steps]]
            id = "D.A"
            kind = "given"
            pattern = "the shop is open"
            composes = ["C.ENTITY.SEED"]

            [[steps]]
            id = "D.B"
            kind = "then"
            pattern = "the shop is open"
            composes = ["C.API.BODY"]
        '''), [])

    def test_a_domain_step_that_copies_a_core_pattern_is_flagged(self):
        (msg,) = self.check('''
            [[steps]]
            id = "D.SEED"
            kind = "given"
            pattern = "the following {thing} exist:"
            composes = ["C.ENTITY.SEED"]
        ''')
        self.assertIn("C.ENTITY.SEED", msg)
        self.assertIn("L010", msg)

    def test_core_instructions_are_not_compared_with_each_other(self):
        vocab = vocabulary.Vocabulary(vocabulary.load_core())
        self.assertEqual(vocabcheck.check_near_duplicates(vocab.entries, 0.5, "core.json", ""), [])


class HelperTest(unittest.TestCase):
    def test_similarity_ignores_placeholder_names(self):
        self.assertEqual(vocabcheck.similarity("{a} has {x:int} items", "{b} has {y:int} items"), 1.0)
        self.assertLess(vocabcheck.similarity("Alice pays", "the order ships"), 0.2)

    def test_locate_finds_the_id_line(self):
        source = 'version = 1\n\n[[steps]]\nid = "D.ONE"\n\n[[steps]]\n  id = \'D.TWO\'\n'
        self.assertEqual((vocabcheck.locate(source, "D.ONE"), vocabcheck.locate(source, "D.TWO")), (4, 7))
        self.assertEqual(vocabcheck.locate(source, "D.MISSING"), 1)


if __name__ == "__main__":
    unittest.main()
