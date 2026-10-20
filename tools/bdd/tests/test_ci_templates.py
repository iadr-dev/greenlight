"""The ready-made CI workflows of the adapters only use actions pinned to a commit and only call bdd commands and
flags that exist."""
import contextlib
import io
import re
import unittest
from pathlib import Path

from bddlib import cli

REPO = Path(__file__).resolve().parents[3]
ADAPTERS = sorted(p.name for p in (REPO / "adapters").iterdir() if p.is_dir())
PINNED = re.compile(r"^\s*-?\s*uses:\s*(?P<action>[\w./-]+)@(?P<ref>[0-9a-f]{40})\s+#\s*v\d+(\.\d+)*\s*$")
USES = re.compile(r"^\s*-?\s*uses:")
BDD_CALL = re.compile(r'"\$bdd"\s+(?P<command>[a-z][a-z-]*)(?P<rest>[^;&|]*)')
FLAG = re.compile(r"(?<![\w-])--[a-z][a-z-]*")


def workflow(name: str) -> str:
    return (REPO / "adapters" / name / "ci" / "github-actions.yml").read_text(encoding="utf-8")


def help_text(command: str) -> str:
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        try:
            cli.main([command, "--help"])
        except SystemExit:
            pass
    return out.getvalue()


class CiTemplateTest(unittest.TestCase):
    def test_every_adapter_ships_a_workflow(self):
        self.assertTrue(ADAPTERS)
        for name in ADAPTERS:
            with self.subTest(adapter=name):
                self.assertTrue((REPO / "adapters" / name / "ci" / "github-actions.yml").is_file())

    def test_every_action_is_pinned_to_a_commit_with_its_version_in_a_comment(self):
        for name in ADAPTERS:
            used = [line for line in workflow(name).splitlines() if USES.match(line)]
            self.assertTrue(used, name)
            for line in used:
                with self.subTest(adapter=name, line=line.strip()):
                    self.assertRegex(line, PINNED)

    def test_the_workflow_asks_for_the_least_it_needs_and_pins_the_release(self):
        for name in ADAPTERS:
            text = workflow(name)
            with self.subTest(adapter=name):
                self.assertIn("permissions:\n  contents: read", text)
                self.assertRegex(text, r"GREENLIGHT_REF: v\d+\.\d+\.\d+")
                self.assertNotRegex(text, r"(?<!uv )pip install")     # uv, or no install at all
                self.assertIn("persist-credentials: false", text)

    def test_every_bdd_command_and_flag_in_a_workflow_exists(self):
        for name in ADAPTERS:
            calls = [m for line in workflow(name).splitlines() for m in BDD_CALL.finditer(line)]
            self.assertGreaterEqual(len(calls), 8, name)
            for call in calls:
                command = call.group("command")
                with self.subTest(adapter=name, command=command):
                    self.assertIn(command, cli.COMMANDS)
                    helped = help_text(command)
                    for flag in FLAG.findall(call.group("rest")):
                        self.assertIn(flag, helped, f"bdd {command} has no {flag}")

    def test_the_gates_the_documentation_promises_are_all_there(self):
        wanted = ("approve", "lock", "run", "classify", "trace", "stability", "check", "mutate", "status", "lint")
        for name in ADAPTERS:
            used = {m.group("command") for line in workflow(name).splitlines() for m in BDD_CALL.finditer(line)}
            with self.subTest(adapter=name):
                self.assertEqual(set(wanted) - used, set())

    def test_the_loop_only_covers_finished_features(self):
        for name in ADAPTERS:
            with self.subTest(adapter=name):
                self.assertIn('$("$bdd" status --done)', workflow(name))


if __name__ == "__main__":
    unittest.main()
