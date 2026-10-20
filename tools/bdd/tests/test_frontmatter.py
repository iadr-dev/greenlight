import unittest
from pathlib import Path

from bddlib.frontmatter import FrontmatterError, parse


class FrontmatterTest(unittest.TestCase):
    def test_scalars_lists_and_body(self):
        meta, body = parse("---\nname: init\ntitle: \"Quoted: yes\"\nuses: [a, 'b', c]\nempty: []\n---\n# Body\n")
        self.assertEqual(meta, {"name": "init", "title": "Quoted: yes", "uses": ["a", "b", "c"], "empty": []})
        self.assertEqual(body, "# Body")

    def test_value_may_contain_colons(self):
        meta, _ = parse("---\ndescription: Use when the user runs /greenlight:init now\n---\n")
        self.assertEqual(meta["description"], "Use when the user runs /greenlight:init now")

    def test_comments_blank_lines_and_bom_and_crlf(self):
        meta, body = parse("\ufeff---\r\n# note\r\n\r\nname: x\r\n---\r\nbody\r\n")
        self.assertEqual(meta, {"name": "x"})
        self.assertEqual(body, "body")

    def test_errors(self):
        for bad, msg in [
            ("no front matter", "must start"),
            ("---\nname: a\n", "not closed"),
            ("---\nname: a\nname: b\n---\n", "duplicate"),
            ("---\nnested:\n  child: 1\n---\n", "no value"),
            ("---\nlist: [a, b\n---\n", "unterminated"),
            ("---\njust text\n---\n", "expected 'key: value'"),
            ("---\ndescription: Read-only: it writes nothing\n---\n", "put it in double quotes"),
            ("---\ndescription: fine # not a comment here\n---\n", "put it in double quotes"),
            ("---\ndescription: {braces}\n---\n", "put it in double quotes"),
            ("---\ndescription: ends with a colon:\n---\n", "put it in double quotes"),
        ]:
            with self.subTest(bad=bad):
                with self.assertRaises(FrontmatterError) as cm:
                    parse(bad)
                self.assertIn(msg, str(cm.exception))


class RealYamlTest(unittest.TestCase):
    """Everything that Claude Code or Codex reads must also be plain, valid YAML where a real parser looks at it."""

    ROOT = Path(__file__).resolve().parents[3]

    def test_every_agent_skill_and_card_parses_with_the_strict_parser(self):
        files = [*self.ROOT.glob("agents/*.md"), *self.ROOT.glob("skills/*/SKILL.md"), *self.ROOT.glob("cards/**/*.md")]
        self.assertGreater(len(files), 40)
        for path in files:
            with self.subTest(file=path.relative_to(self.ROOT).as_posix()):
                meta, _ = parse(path.read_text(encoding="utf-8"))
                self.assertTrue(meta)

    def test_a_quoted_value_may_hold_a_colon_and_a_space(self):
        meta, _ = parse('---\ndescription: "Read-only: it writes nothing"\n---\n')
        self.assertEqual(meta["description"], "Read-only: it writes nothing")


if __name__ == "__main__":
    unittest.main()
