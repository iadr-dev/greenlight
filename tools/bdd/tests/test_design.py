import contextlib
import io
import os
import unittest

from bddlib import cli, design, gates
from bddlib.errors import UsageError

from tests.helpers import ProjectCase

SYSTEM = "## Interfaces\n\n| Logical name | Kind | Where |\n|---|---|---|\n| place order | API operation | POST /orders |\n"
GOOD = "# Design\n\n```mermaid\nflowchart LR\n  %% interface: Place Order\n  a[Client] -->|POST /orders| b[(Orders)]\n```\n"


def block(body: str) -> str:
    return f"```mermaid\n{body}\n```\n"


class DesignLintTest(ProjectCase):
    def setUp(self):
        super().setUp()
        self.write_system()

    def write_system(self):
        (self.feature_dir / "system.md").write_text(SYSTEM, encoding="utf-8", newline="\n")

    def lint(self, text: str | None) -> list[str]:
        path = self.feature_dir / design.DESIGN_FILE
        if text is not None:
            path.write_text(text, encoding="utf-8", newline="\n")
        return [i.code for i in design.lint(self.feature_dir)]

    def test_a_good_view_is_clean_and_interface_names_ignore_case(self):
        self.assertEqual(self.lint(GOOD), [])

    def test_no_file_and_no_block(self):
        self.assertEqual(self.lint(None), ["D1"])
        self.assertEqual(self.lint("# Design\n\nnothing here\n"), ["D1"])

    def test_an_unclosed_fence(self):
        self.assertEqual(self.lint("```mermaid\nflowchart LR\n  a --> b\n"), ["D2"])

    def test_the_diagram_type_must_be_known(self):
        self.assertEqual(self.lint(block("pie title Pets\n  \"Dogs\": 3")), ["D3"])
        self.assertEqual(self.lint(block("%% only a comment")), ["D3"])

    def test_brackets_must_balance_but_quoted_text_is_ignored(self):
        self.assertEqual(self.lint(block("flowchart LR\n  a[Client --> b")), ["D4"])
        self.assertEqual(self.lint(block('flowchart LR\n  a["Client ("] --> b')), [])

    def test_nothing_active_is_allowed(self):
        for line in ("click a href \"http://x\"", "click a callback", "link a: http://x", "a --> b\n  href", "%%{init: {}}%%",
                     "a[<script>x</script>]"):
            with self.subTest(line=line):
                self.assertIn("D5", self.lint(block("flowchart LR\n  " + line)))

    def test_a_named_interface_must_be_in_system_md(self):
        self.assertEqual(self.lint(block("flowchart LR\n  %% interface: cancel order\n  a --> b")), ["D6"])
        (self.feature_dir / "system.md").unlink()
        self.assertEqual(self.lint(GOOD), ["D6"])


class DesignCommandTest(ProjectCase):
    def run_cli(self, *argv: str) -> tuple[int, str]:
        out, here = io.StringIO(), os.getcwd()
        os.chdir(self.root)
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                return cli.main(list(argv)), out.getvalue()
        finally:
            os.chdir(here)

    def test_the_command_reports_and_sets_the_exit_code(self):
        code, out = self.run_cli("design", "FEAT-007")
        self.assertEqual(code, 1)
        self.assertIn("D1", out)
        (self.feature_dir / "design.md").write_text(block("flowchart LR\n  a --> b"), encoding="utf-8", newline="\n")
        self.assertEqual(self.run_cli("design", "FEAT-007")[0], 0)
        self.assertEqual(self.run_cli("design", "FEAT-999")[0], 2)


class DesignGateTest(ProjectCase):
    def test_the_system_map_gate_refuses_a_broken_view_but_not_a_missing_one(self):
        self.walk_to("examples")
        (self.feature_dir / "design.md").write_text(block("flowchart LR\n  a[x --> b"), encoding="utf-8", newline="\n")
        with self.assertRaises(UsageError) as cm:
            self.gate("system-map")
        self.assertIn("D4", str(cm.exception))
        (self.feature_dir / "design.md").write_text(block("flowchart LR\n  a --> b"), encoding="utf-8", newline="\n")
        self.assertEqual(self.gate("system-map")["gates"]["system-map"]["result"], "pass")


if __name__ == "__main__":
    unittest.main()
