import unittest

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
        ]:
            with self.subTest(bad=bad):
                with self.assertRaises(FrontmatterError) as cm:
                    parse(bad)
                self.assertIn(msg, str(cm.exception))


if __name__ == "__main__":
    unittest.main()
