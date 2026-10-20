import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from bddlib import cards

REPO = Path(__file__).resolve().parents[3]

GOOD = """---
id: boundary-value
kind: technique
apply_when: a threshold
output: three examples
cost: low
pairs_with: [other-one]
---
## Intent
x
## How to apply
y
## Known pitfalls
- one
"""


class CardCase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.base = Path(self.dir.name)
        self.card("techniques/boundary-value.md", GOOD)
        self.card("techniques/other-one.md", GOOD.replace("boundary-value", "other-one").replace("[other-one]", "[]"))

    def card(self, rel: str, text: str) -> Path:
        path = self.base / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        return path

    def problems(self) -> list[str]:
        return cards.build(self.base)[1]


class RulesTest(CardCase):
    def test_good_cards_build_a_sorted_index(self):
        index, problems = cards.build(self.base)
        self.assertEqual(problems, [])
        self.assertEqual([c["id"] for c in index["cards"]], ["boundary-value", "other-one"])
        first = index["cards"][0]
        self.assertEqual((first["kind"], first["path"], first["pairs_with"]), ("technique", "techniques/boundary-value.md", ["other-one"]))
        self.assertNotIn("body", first)

    def test_every_rule_is_checked(self):
        cases = {
            "no front matter": ("techniques/a.md", "# nothing\n", "missing front matter"),
            "bad kind": ("techniques/a.md", GOOD.replace("kind: technique", "kind: poem"), "kind must be one of"),
            "wrong folder": ("runners/a.md", GOOD.replace("id: boundary-value", "id: a"), "belongs in cards/techniques/"),
            "id differs from file": ("techniques/a.md", GOOD, "id must equal the file name"),
            "missing field": ("techniques/a.md", GOOD.replace("id: boundary-value", "id: a").replace("output: three examples\n", ""), "output is required"),
            "bad cost": ("techniques/a.md", GOOD.replace("id: boundary-value", "id: a").replace("cost: low", "cost: huge"), "cost must be one of"),
            "unknown key": ("techniques/a.md", GOOD.replace("id: boundary-value", "id: a").replace("cost: low", "cost: low\nowner: me"), "unknown front matter key"),
            "pairs_with not a list": ("techniques/a.md", GOOD.replace("id: boundary-value", "id: a").replace("[other-one]", "other-one"), "pairs_with must be a list"),
            "bad phase": ("techniques/a.md", GOOD.replace("id: boundary-value", "id: a").replace("cost: low", "cost: low\nphase: lunch"), "phase must be one of"),
            "missing pitfalls": ("techniques/a.md", GOOD.replace("id: boundary-value", "id: a").replace("## Known pitfalls\n- one\n", ""), "'## Known pitfalls' section is missing"),
            "empty pitfalls": ("techniques/a.md", GOOD.replace("id: boundary-value", "id: a").replace("- one\n", ""), "'## Known pitfalls' section is missing or empty"),
            "unknown pair": ("techniques/a.md", GOOD.replace("id: boundary-value", "id: a").replace("[other-one]", "[ghost]"), "'ghost', which is not a card"),
        }
        for name, (rel, text, message) in cases.items():
            with self.subTest(name):
                path = self.card(rel, text)
                self.assertTrue(any(message in p for p in self.problems()), self.problems())
                path.unlink()

    def test_duplicate_ids(self):
        self.card("practices/boundary-value.md", GOOD.replace("kind: technique", "kind: practice").replace("cost: low\n", ""))
        self.assertTrue(any("used by more than one card" in p for p in self.problems()))

    def test_instruction_and_runner_cards_have_their_own_sections(self):
        self.card("instructions/C.API.CALL.md", "---\nid: C.API.CALL\nkind: instruction\napply_when: calling an API\n---\n## Semantics\nx\n## Known pitfalls\n- y\n")
        self.card("runners/godog.md", "---\nid: godog\nkind: runner\napply_when: Go projects\n---\n## Run\nx\n## Known pitfalls\n- y\n")
        self.assertEqual(self.problems(), [])
        self.card("runners/bad.md", "---\nid: bad\nkind: runner\napply_when: Go projects\n---\n## Known pitfalls\n- y\n")
        self.assertTrue(any("'## Run' section" in p for p in self.problems()))


class CommandTest(CardCase):
    def cmd(self, *argv: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, {"CLAUDE_PLUGIN_ROOT": str(self.base.parent / "x")}), \
                mock.patch.object(cards, "cards_dir", return_value=self.base), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            return cards.run(list(argv)), out.getvalue(), err.getvalue()

    def test_build_check_and_list(self):
        self.assertEqual(self.cmd("build", "--check")[0], 1)                  # nothing written yet
        code, out, _ = self.cmd("build")
        self.assertEqual((code, out.strip()), (0, "2 card(s) indexed"))
        self.assertEqual(self.cmd("build")[1].strip(), "2 card(s) indexed (unchanged)")
        self.assertEqual(self.cmd("build", "--check")[0], 0)
        self.card("techniques/third.md", GOOD.replace("boundary-value", "third").replace("[other-one]", "[]"))
        code, _, err = self.cmd("build", "--check")
        self.assertEqual((code, "out of date" in err), (1, True))              # a new card drifts the index
        self.cmd("build")
        lines = self.cmd("list", "--kind", "technique")[1].splitlines()
        self.assertEqual(len(lines), 3)
        self.assertEqual(lines[0], "boundary-value\ttechnique\ta threshold")
        self.assertEqual(self.cmd("list", "--kind", "runner")[1], "")

    def test_a_broken_card_stops_the_build_with_every_problem(self):
        self.card("techniques/bad.md", "# no front matter\n")
        code, _, err = self.cmd("build")
        self.assertEqual((code, "bad.md" in err), (1, True))
        self.assertFalse((self.base / "index.json").exists())

    def test_list_needs_an_index(self):
        code, _, err = self.cmd("list")
        self.assertEqual((code, "bdd cards build" in err), (2, True))


class RepositoryCardsTest(unittest.TestCase):
    def test_the_shipped_cards_are_valid_and_their_index_is_in_sync(self):
        base = REPO / "cards"
        index, problems = cards.build(base)
        self.assertEqual(problems, [])
        shipped = json.loads((base / "index.json").read_text(encoding="utf-8"))
        self.assertEqual(shipped, index, "cards/index.json is out of date; run `bdd cards build`")
        self.assertTrue({"boundary-value", "decision-table", "state-transition"} <= {c["id"] for c in index["cards"]})


class InstructionCardsTest(unittest.TestCase):
    """The instruction cards describe the vocabulary: none missing for the profiles that have an adapter, none invented."""

    ADAPTED_PROFILES = {"base", "api", "cli", "lib"}

    @classmethod
    def setUpClass(cls):
        cls.core = {i["id"]: i for i in json.loads((REPO / "vocabulary" / "core.json").read_text(encoding="utf-8"))["instructions"]}
        cls.found = {p.stem: p for p in (REPO / "cards" / "instructions").glob("C.*.md")}

    def test_every_instruction_of_an_adapted_profile_has_a_card(self):
        wanted = {i for i, spec in self.core.items() if set(spec["profiles"]) <= self.ADAPTED_PROFILES}
        self.assertEqual(wanted - set(self.found), set())

    def test_no_card_is_for_an_instruction_that_does_not_exist(self):
        self.assertEqual(set(self.found) - set(self.core), set())

    def test_each_card_lists_exactly_the_patterns_of_its_instruction(self):
        for iid, path in self.found.items():
            with self.subTest(card=iid):
                _, body = cards.frontmatter.parse(path.read_text(encoding="utf-8"))
                listed = [line[3:-1] for line in cards.sections(body)["Patterns"].splitlines() if line.startswith("- `")]
                self.assertEqual(listed, self.core[iid]["patterns"])


if __name__ == "__main__":
    unittest.main()
