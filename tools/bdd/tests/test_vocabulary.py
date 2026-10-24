import re
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from bddlib import vocabulary as v

FULLWIDTH_COLON = "："
SAMPLES = {"int": "3", "decimal": "1.5", "string": '"abc"', "name": "Alice", "datetime": "2026-01-01",
           "duration": "5 minutes", "bool": "true"}
PLACEHOLDER = re.compile(r"\{([A-Za-z_]\w*)(?::(enum\([^)]*\)|[A-Za-z]+))?\}")


def sample_text(pattern_text: str) -> str:
    """Fill every placeholder with a value of its type."""
    def fill(m):
        name, ptype = m.group(1), m.group(2) or (m.group(1) if m.group(1) in SAMPLES else "name")
        if ptype.startswith("enum("):
            return ptype[5:-1].split(",")[0].strip()
        return SAMPLES[ptype]
    return PLACEHOLDER.sub(fill, pattern_text)


class PatternTest(unittest.TestCase):
    def match(self, pattern, text):
        return v.compile_pattern(pattern).match(text)

    def test_typed_placeholders(self):
        cases = [
            ("{amount:int} items", "12 items", {"amount": "12"}),
            ("{amount:int} items", "-3 items", {"amount": "-3"}),
            ("costs {price:decimal}", "costs 9.99", {"price": "9.99"}),
            ("says {text:string}", 'says "hello world"', {"text": "hello world"}),
            ("at {when:datetime}", "at 2026-03-01T10:30:00Z", {"when": "2026-03-01T10:30:00Z"}),
            ("after {duration}", "after 90 minutes", {"duration": "90 minutes"}),
            ("flag {on:bool}", "flag yes", {"on": "yes"}),
            ("sets {state:enum(on,off)}", "sets off", {"state": "off"}),
        ]
        for pattern, text, expected in cases:
            with self.subTest(pattern=pattern, text=text):
                self.assertEqual(self.match(pattern, text), expected)

    def test_values_that_do_not_fit_the_type_do_not_match(self):
        for pattern, text in [("{n:int} items", "x items"), ("{n:int} items", "1.5 items"),
                              ("sets {s:enum(on,off)}", "sets maybe"), ("says {t:string}", "says hello"),
                              ("at {d:datetime}", "at tomorrow"), ("after {duration}", "after soon")]:
            with self.subTest(text=text):
                self.assertIsNone(self.match(pattern, text))

    def test_names_can_be_multiword_or_quoted_and_stop_at_literals(self):
        self.assertEqual(self.match("the following {entity} exist:", "the following order items exist:"),
                         {"entity": "order items"})
        self.assertEqual(self.match("{actor} opens the {page} page", 'Alice opens the "My Orders" page'),
                         {"actor": "Alice", "page": '"My Orders"'})

    def test_scenario_outline_placeholders_are_accepted_for_any_type(self):
        self.assertEqual(self.match("a cart worth {amount:int}", "a cart worth <amount>"), {"amount": "<amount>"})
        self.assertIsNotNone(self.match("sets {s:enum(on,off)}", "sets <state>"))

    def test_case_whitespace_and_fullwidth_punctuation(self):
        self.assertIsNotNone(self.match("the following {entity} exist:", "The   Following products EXIST:"))
        self.assertIsNotNone(self.match("the following {entity} exist:", "the following products exist" + FULLWIDTH_COLON))
        zh = v.compile_pattern("以下{entity}已存在" + FULLWIDTH_COLON)  # pattern may use the full-width colon too
        self.assertEqual(zh.match("以下商品已存在:"), {"entity": "商品"})

    def test_regex_metacharacters_in_literals_are_literal(self):
        self.assertIsNotNone(self.match("costs $5 (approx.)", "costs $5 (approx.)"))
        self.assertIsNone(self.match("costs $5 (approx.)", "costs $5 (approxX)"))

    def test_invalid_patterns(self):
        for bad, message in [("{a:nope}", "unknown parameter type"), ("{a} and {a}", "appears twice"),
                             ("{a:enum()}", "no values"), ("stray } brace", "malformed")]:
            with self.subTest(bad=bad):
                with self.assertRaises(v.VocabularyError) as cm:
                    v.compile_pattern(bad)
                self.assertIn(message, str(cm.exception))


class CoreVocabularyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entries = v.load_core()
        cls.vocab = v.Vocabulary(cls.entries)

    def test_there_are_30_instructions_with_the_documented_split(self):
        self.assertEqual(len(self.entries), 30)
        self.assertEqual(Counter(e.kind for e in self.entries), {"given": 7, "when": 9, "then": 14})
        profiles = Counter(p for e in self.entries for p in e.profiles)
        self.assertEqual(dict(profiles), {"base": 12, "api": 3, "ui": 7, "cli": 5, "lib": 4, "data": 1})
        self.assertTrue(all(e.id.startswith("C.") for e in self.entries))
        self.assertTrue(all(e.source == "core" for e in self.entries))

    def test_every_pattern_of_every_language_resolves_to_exactly_its_own_instruction(self):
        checked = 0
        for entry in self.entries:
            for lang, patterns in entry.patterns.items():
                for pattern in patterns:
                    text = sample_text(pattern.text)
                    with self.subTest(entry=entry.id, lang=lang, text=text):
                        found = self.vocab.resolve(entry.kind, text, lang)
                        self.assertEqual([m.entry.id for m in found], [entry.id], "ambiguous or unmatched")
                        checked += 1
        self.assertGreater(checked, 60)

    def test_traditional_chinese_alternates_exist_for_instructions_without_enums(self):
        with_zh = [e for e in self.entries if "zh-TW" in e.patterns]
        self.assertGreaterEqual(len(with_zh), 24)
        found = self.vocab.resolve("given", "以下商品已存在" + FULLWIDTH_COLON, "zh-TW")
        self.assertEqual([m.entry.id for m in found], ["C.ENTITY.SEED"])

    def test_english_steps_still_resolve_in_a_zh_tw_feature(self):
        found = self.vocab.resolve("given", "the following products exist:", "zh-TW")
        self.assertEqual([m.entry.id for m in found], ["C.ENTITY.SEED"])

    def test_kind_must_match(self):
        self.assertEqual(self.vocab.resolve("when", "the following products exist:"), [])

    def test_first_matching_pattern_wins_within_an_instruction(self):
        (m,) = self.vocab.resolve("when", "Alice calls quote.create with:")
        self.assertEqual(m.params, {"actor": "Alice", "operation": "quote.create"})
        (m,) = self.vocab.resolve("when", "Alice calls quote.create")
        self.assertEqual(m.params["operation"], "quote.create")


class ProjectVocabularyTest(unittest.TestCase):
    def write(self, text: str) -> Path:
        d = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: [f.unlink() for f in d.iterdir()] or d.rmdir())
        f = d / "vocabulary.toml"
        f.write_text(text, encoding="utf-8")
        return f

    VALID = '''
version = 1
extends = "core"

[[steps]]
id = "D.CART.WORTH"
kind = "given"
pattern = "{actor} has a cart worth {amount:int}"
composes = ["C.ACTOR.AUTH", "C.ENTITY.SEED"]
owner = "FEAT-007"

[[steps]]
id = "D.QUOTE.VIEW"
kind = "when"
patterns = ["{actor} views the order quote", "{actor} asks for a quote"]
composes = ["C.API.CALL"]
maps_to = { operation = "quote.create" }
'''

    def test_loads_and_resolves_domain_steps(self):
        vocab = v.load(self.write(self.VALID))
        self.assertEqual(len(vocab.entries), 32)
        (m,) = vocab.resolve("given", "Alice has a cart worth 999")
        self.assertEqual((m.entry.id, m.params), ("D.CART.WORTH", {"actor": "Alice", "amount": "999"}))
        self.assertEqual(m.entry.owner, "FEAT-007")
        (m,) = vocab.resolve("when", "Bob asks for a quote", "zh-TW")   # project patterns apply to every language
        self.assertEqual(m.entry.maps_to, {"operation": "quote.create"})

    def test_missing_file_means_core_only(self):
        self.assertEqual(len(v.load(Path(tempfile.gettempdir()) / "no-such-vocabulary.toml").entries), 30)

    def test_validation_errors(self):
        step = '[[steps]]\nid = "{id}"\nkind = "{kind}"\npattern = "x {{a:int}}"\ncomposes = {composes}\n'
        cases = [
            (dict(id="C.MINE", kind="given", composes="[]"), "must start with 'D.'"),
            (dict(id="D.X", kind="maybe", composes="[]"), "kind must be one of"),
            (dict(id="D.X", kind="given", composes='["C.NOPE"]'), "unknown core instruction"),
        ]
        for fields, message in cases:
            with self.subTest(message=message):
                with self.assertRaises(v.VocabularyError) as cm:
                    v.load(self.write("version = 1\n" + step.format(**fields)))
                self.assertIn(message, str(cm.exception))

    def test_duplicate_ids_are_rejected(self):
        with self.assertRaises(v.VocabularyError) as cm:
            v.load(self.write(self.VALID + self.VALID.split("extends")[1].split("\n", 1)[1]))
        self.assertIn("duplicate", str(cm.exception))

    def test_ambiguous_domain_steps_are_reported_not_hidden(self):
        text = ('[[steps]]\nid = "D.A"\nkind = "given"\npattern = "a thing named {n}"\n'
                '[[steps]]\nid = "D.B"\nkind = "given"\npattern = "a thing named {n:string}"\n')
        vocab = v.load(self.write(text))
        self.assertEqual(sorted(m.entry.id for m in vocab.resolve("given", 'a thing named "x"')), ["D.A", "D.B"])


if __name__ == "__main__":
    unittest.main()
