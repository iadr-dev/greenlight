"""Hard enforcement in Codex: its hook payloads, the guard behind them, the origin check and the hook installer.

The payloads follow Codex's hook documentation (fields ``hook_event_name``, ``session_id``, ``cwd``, ``transcript_path``,
``turn_id``, ``tool_name``, ``tool_input``, ``prompt``) and the rollout file follows what a real Codex 0.142 session file
holds (``session_meta``, ``event_msg`` with ``task_started``, ``user_message`` and ``task_complete``).
"""
import contextlib
import hashlib
import io
import json
import os
import re
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

from bddlib import approvalcommand, approvals, claudepaths, cli, codexguard, codexhook, codexorigin, codexpayload, codexsession
from bddlib import config as cfg
from bddlib import doctor, enforcement, guard, installhooks, lockfile, pr, reportcmd, state, statecmd, tripwire
from bddlib.errors import UsageError

from tests.helpers import ProjectCase

SESSION = "019a0000-aaaa-7bbb-8ccc-000000000001"
TURN = "019a0000-aaaa-7bbb-8ccc-0000000000t1"
APPROVE = "$greenlight-approve FEAT-007 rules"


def tool_call(root: Path, tool: str, tool_input: dict, event: str = "PreToolUse") -> dict:
    return {"hook_event_name": event, "session_id": SESSION, "cwd": str(root), "turn_id": TURN, "tool_name": tool,
            "tool_input": tool_input, "transcript_path": None, "model": "gpt", "permission_mode": "default"}


def patch(*files: str) -> str:
    return "*** Begin Patch\n" + "".join(f"*** Update File: {name}\n@@\n-old\n+new\n" for name in files) + "*** End Patch\n"


def run_hook(payload: dict) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with mock.patch.object(sys, "stdin", io.StringIO(json.dumps(payload))), contextlib.redirect_stdout(out), \
            contextlib.redirect_stderr(err):
        code = codexhook.main([])
    return code, out.getvalue(), err.getvalue()


def assert_denied(case: unittest.TestCase, result: tuple[int, str, str]) -> dict:
    """What Codex acts on (checked in a live session): exit 0 and one JSON object on stdout that denies the call."""
    code, out, err = result
    case.assertEqual(code, 0)
    decision = json.loads(out)                                         # stdout is exactly one JSON object
    body = decision["hookSpecificOutput"]
    case.assertEqual((body["hookEventName"], body["permissionDecision"]), ("PreToolUse", "deny"))
    case.assertTrue(body["permissionDecisionReason"].startswith("greenlight:"))
    case.assertIn(body["permissionDecisionReason"], err)
    return decision


def opt_in(case: "CodexCase") -> None:
    """The person accepts approvals typed in Codex, knowing they are not provenance-verified."""
    case.approval_lines.append("accept_codex = true")
    case.config()


def lock_steps(case: ProjectCase) -> None:
    lockfile.lock(case.root, case.feature_dir, "FEAT-007", "bind", [case.step])


class CodexCase(ProjectCase):
    def setUp(self):
        super().setUp()
        self.home = self.root / "codex-home"
        self.home.mkdir()
        patcher = mock.patch.dict(os.environ, {"CODEX_HOME": str(self.home)})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.approval_lines: list[str] = []
        self.config()

    def config(self, top_level: str = "", tail: str = "") -> None:
        """The project's configuration; it always says where this test's Codex keeps its home, and whatever the test opted in to."""
        lines = "".join(line + "\n" for line in [f"codex_home = {json.dumps(str(self.home))}", *self.approval_lines])
        tail = tail.replace("[approvals]\n", "[approvals]\n" + lines, 1) if "[approvals]\n" in tail else tail + "[approvals]\n" + lines
        super().config(top_level, tail)


class PayloadTest(unittest.TestCase):
    def test_a_shell_command_arrives_as_a_string_or_a_list_of_words(self):
        self.assertEqual(codexpayload.command_of({"command": "ls -la"}), "ls -la")
        self.assertEqual(codexpayload.command_of({"command": ["bash", "-lc", "ls"]}), "bash -lc ls")
        self.assertEqual(codexpayload.command_of({"cmd": "pwd"}), "pwd")
        for nonsense in ({}, {"command": ""}, {"command": [1, 2]}, None, "ls"):
            self.assertIsNone(codexpayload.command_of(nonsense))

    def test_the_files_of_a_patch_are_found_wherever_the_patch_sits(self):
        text = "*** Begin Patch\n*** Add File: a/new.py\n+x\n*** Update File: b.py\n*** Move to: c.py\n*** Delete File: d.py\n*** End Patch"
        self.assertEqual(codexpayload.patch_paths({"input": text}), ["a/new.py", "b.py", "c.py", "d.py"])
        self.assertEqual(codexpayload.patch_paths({"command": ["apply_patch", text]}), ["a/new.py", "b.py", "c.py", "d.py"])
        self.assertEqual(codexpayload.patch_paths({"input": "no patch here"}), [])

    def test_every_line_ending_indentation_and_tab_is_read(self):
        for name, text in {"CRLF": "*** Begin Patch\r\n*** Update File: steps/steps.py\r\n@@\r\n-a\r\n+b\r\n*** End Patch\r\n",
                           "bare CR": "*** Begin Patch\r*** Update File: steps/steps.py\r@@\r-a\r+b\r",
                           "indented": "  *** Begin Patch\n\t  *** Update File: steps/steps.py\n",
                           "tab": "*** Update File:\tsteps/steps.py\n",
                           "no space": "*** Update File:steps/steps.py\n",
                           "space before the colon": "***  Update File :   steps/steps.py   \n",
                           "trailing spaces": "*** Update File: steps/steps.py \t \n"}.items():
            with self.subTest(layout=name):
                self.assertEqual(codexpayload.patch_paths({"input": text}), ["steps/steps.py"])

    def test_a_call_with_more_than_one_command_like_key_is_unreadable(self):
        for tool_input in ({"command": "ls", "cmd": "rm -rf x"}, {"command": ["ls"], "script": "rm x"}, {"cmd": "ls", "argv": ["rm"]}):
            with self.subTest(tool_input=tool_input):
                self.assertIsNone(codexpayload.command_of(tool_input))
                self.assertIsNone(codexpayload.guard_calls({"cwd": "/p", "tool_name": "Bash", "tool_input": tool_input}))
        self.assertEqual(codexpayload.command_of({"argv": ["ls", "-la"]}), "ls -la")

    def test_a_header_that_cannot_be_read_makes_the_whole_patch_unreadable(self):
        for name, text in {"two spaces in the keyword": "*** Update  File: steps/steps.py\n",
                           "lower case": "*** update file: steps/steps.py\n",
                           "no path": "*** Update File:\n",
                           "a good one and a bad one": "*** Update File: a.py\n*** Delete   File: steps/steps.py\n"}.items():
            with self.subTest(layout=name):
                self.assertIsNone(codexpayload.patch_paths({"input": text}))
                self.assertIsNone(codexpayload.guard_calls({"cwd": "/p", "tool_name": "apply_patch", "tool_input": {"input": text}}))
                self.assertIsNone(codexpayload.guard_calls({"cwd": "/p", "tool_name": "Bash", "tool_input": {"command": ["apply_patch", text]}}))

    def test_a_header_path_is_checked_exactly_as_written_and_odd_characters_make_it_unreadable(self):
        for name, text in {"double quotes": '*** Update File: "steps/steps.py"\n', "single quotes": "*** Update File: 'steps/steps.py'\n",
                           "a backtick": "*** Update File: steps/`x`.py\n", "a quote inside": '*** Update File: steps/st"eps.py\n',
                           "a control character": "*** Update File: steps/\x01steps.py\n", "an inner tab": "*** Update File: steps/\tsteps.py\n",
                           "a delete character": "*** Update File: steps/\x7fsteps.py\n"}.items():
            with self.subTest(case=name):
                self.assertIsNone(codexpayload.patch_paths({"input": text}))
                self.assertIsNone(codexpayload.guard_calls({"cwd": "/p", "tool_name": "apply_patch", "tool_input": {"input": text}}))
        self.assertEqual(codexpayload.patch_paths({"input": "*** Update File: steps/my file (1).py\n"}), ["steps/my file (1).py"])

    def test_lines_of_a_hunk_are_content_not_headers(self):
        text = "*** Update File: a.py\n@@\n+print('*** Update File: not a header')\n-x = '*** Delete File: nor this'\n"
        self.assertEqual(codexpayload.patch_paths({"input": text}), ["a.py"])

    def test_every_kind_of_call_becomes_calls_the_guard_understands(self):
        base = {"cwd": "/p", "session_id": "s"}
        shell = codexpayload.guard_calls({**base, "tool_name": "Bash", "tool_input": {"command": "echo hi"}})
        self.assertEqual([c["tool_name"] for c in shell], ["Bash"])
        edit = codexpayload.guard_calls({**base, "tool_name": "apply_patch", "tool_input": {"input": patch("a.py", "b.py")}})
        self.assertEqual([c["tool_input"]["file_path"] for c in edit], ["a.py", "b.py"])
        other = codexpayload.guard_calls({**base, "tool_name": "mcp__x__y", "tool_input": {"a": 1}})
        self.assertEqual([c["tool_name"] for c in other], ["Other"])
        self.assertIsNone(codexpayload.guard_calls({**base, "tool_name": "apply_patch", "tool_input": {"input": "garbage"}}))
        self.assertIsNone(codexpayload.guard_calls({**base, "tool_name": "Bash", "tool_input": {}}))


class GuardTest(CodexCase):
    def blocked(self, tool: str, tool_input: dict) -> str | None:
        return codexguard.evaluate(tool_call(self.root, tool, tool_input))

    def test_a_patch_of_a_locked_file_is_refused_and_another_is_not(self):
        lock_steps(self)
        self.assertIn("locked", self.blocked("apply_patch", {"input": patch("steps/steps.py")}))
        self.assertIsNone(self.blocked("apply_patch", {"input": patch("src/app.py")}))

    def test_one_locked_file_among_several_in_a_patch_refuses_all(self):
        lock_steps(self)
        self.assertIsNotNone(self.blocked("apply_patch", {"input": patch("src/app.py", "steps/steps.py")}))

    def test_a_shell_command_that_writes_a_locked_file_is_refused(self):
        lock_steps(self)
        self.assertIsNotNone(self.blocked("Bash", {"command": "echo x > steps/steps.py"}))
        self.assertIsNotNone(self.blocked("shell", {"command": ["bash", "-lc", "echo x > steps/steps.py"]}))
        self.assertIsNone(self.blocked("Bash", {"command": "ls steps"}))

    def test_a_powershell_command_that_writes_a_locked_file_is_refused(self):
        """The exact shape a live Codex session produced on Windows: PowerShell started with a quoted script naming the file."""
        lock_steps(self)
        absolute = str(self.root / "steps" / "steps.py")
        shell = '"C:\\WINDOWS\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command '
        for script in (f"Add-Content -LiteralPath '{absolute}' -Value 'x'", "Add-Content -LiteralPath 'steps/steps.py' -Value 'x'"):
            with self.subTest(script=script):
                self.assertIsNotNone(self.blocked("Bash", {"command": shell + '"' + script + '"'}))
        self.assertIsNone(self.blocked("Bash", {"command": shell + '"Get-Content -LiteralPath \'steps/steps.py\'"'}))

    def test_a_patch_given_to_the_shell_is_checked_like_one_given_to_the_patch_tool(self):
        lock_steps(self)
        self.assertIsNotNone(self.blocked("Bash", {"command": ["apply_patch", patch("steps/steps.py")]}))

    def test_a_locked_file_cannot_be_named_in_a_patch_in_a_way_the_guard_does_not_see(self):
        lock_steps(self)
        for name, text in {"CRLF": "*** Begin Patch\r\n*** Update File: steps/steps.py\r\n@@\r\n-a\r\n+b\r\n*** End Patch\r\n",
                           "bare CR": "*** Begin Patch\r*** Update File: steps/steps.py\r",
                           "indented": "*** Begin Patch\n   *** Update File: steps/steps.py\n",
                           "tab": "*** Update File:\tsteps/steps.py\n"}.items():
            with self.subTest(layout=name):
                self.assertIn("locked", self.blocked("apply_patch", {"input": text}))
        for name, text in {"odd spacing": "*** Update  File: steps/steps.py\n", "lower case": "*** update file: steps/steps.py\n"}.items():
            with self.subTest(layout=name):
                self.assertIn("cannot be checked", self.blocked("apply_patch", {"input": text}))
                self.assertIn("cannot be checked", self.blocked("Bash", {"command": ["apply_patch", text]}))

    def test_a_tool_nobody_has_looked_at_is_refused_unless_the_person_allowed_it(self):
        self.assertIn("not one greenlight knows to be harmless", self.blocked("mcp__docs__search", {"query": "x"}))
        self.assertIn("not one greenlight knows to be harmless", self.blocked("brand_new_tool", {}))
        self.assertIsNone(self.blocked("update_plan", {"plan": []}))
        self.assertIsNone(self.blocked("read_file", {"path": "a.py"}))
        self.config(tail='[approvals]\ncodex_allowed_tools = ["mcp__docs__search"]\n')
        self.assertIsNone(self.blocked("mcp__docs__search", {"query": "x"}))

    def test_a_call_runs_in_the_working_directory_it_asks_for(self):
        lock_steps(self)
        self.assertIn("locked", self.blocked("Bash", {"command": "echo x > steps.py", "workdir": "steps"}))
        self.assertIn("locked", self.blocked("Bash", {"command": "echo x > steps/steps.py", "workdir": "."}))
        self.assertIn("locked", self.blocked("shell", {"command": ["bash", "-lc", "echo x > steps.py"], "workdir": str(self.root / "steps")}))
        self.assertIn("keep greenlight's hooks running", self.blocked("Bash", {"command": "echo x > hooks.json", "workdir": ".codex"}))
        self.assertIn("cannot be resolved", self.blocked("Bash", {"command": "ls", "workdir": 5}))
        self.assertIn("cannot be resolved", self.blocked("Bash", {"command": "ls", "workdir": "a\0b"}))
        self.assertIsNone(self.blocked("Bash", {"command": "ls", "workdir": "steps"}))

    def test_a_workdir_outside_the_project_does_not_hide_a_write_into_it(self):
        lock_steps(self)
        outside = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(outside, ignore_errors=True))
        target = (self.root / "steps" / "steps.py").as_posix()
        self.assertIn("locked", self.blocked("Bash", {"command": f"echo x > {target}", "workdir": outside}))

    def test_every_way_a_shell_reads_the_command_is_checked(self):
        for command in ("echo x > .cod\"ex\"/hooks.json", "echo x > .codex$EMPTY/hooks.json", "tee ~/.co''dex/config.toml",
                        "echo x > $HOME/.codex/hooks.json", "sh tools/bdd/bdd cod'ex'-hook < p.json",
                        "echo $'\\x24greenlight-approve FEAT-007 rules'"):
            with self.subTest(command=command):
                self.assertIsNotNone(self.blocked("Bash", {"command": command}), command)

    def test_a_command_that_sets_codex_home_is_refused(self):
        for command in ("CODEX_HOME=/tmp/x bdd status", "export CODEX_HOME=/tmp/x", "env CODEX_HOME=/tmp/x ls", "set CODEX_HOME=C:\\x",
                        "$env:CODEX_HOME = 'C:\\x'", "setx CODEX_HOME C:\\x"):
            with self.subTest(command=command):
                self.assertIn("CODEX_HOME", self.blocked("Bash", {"command": command}))
        self.assertIsNone(self.blocked("Bash", {"command": "echo $CODEX_HOME"}))

    def test_a_codex_session_is_refused_wherever_its_program_word_sits(self):
        for command in ("bash -lc 'codex exec x'", "xargs -I{} codex exec {}", "timeout 5 codex exec x", "echo hi | sh -c \"codex resume\"",
                        "python run.py codex exec", "sh -c 'cd p && codex exec y'", "script -c 'codex' /dev/null", "ls; true && codex",
                        "pwsh -Command \"& codex exec x\"", "x=1 /usr/local/bin/codex.exe exec"):
            with self.subTest(command=command):
                self.assertIn("another Codex session", self.blocked("Bash", {"command": command}))
        for command in ("codex --version", "codex login status", "codex features list", "echo codex-notes", "ls docs"):
            with self.subTest(command=command):
                self.assertIsNone(self.blocked("Bash", {"command": command}))

    def test_the_word_codex_as_text_inside_a_quoted_argument_is_not_a_session(self):
        """Found by the first live Codex run: appending '# edited by codex' to a file was refused as a nested session."""
        for command in ("Add-Content -LiteralPath 'notes.md' -Value '# edited by codex'", 'echo "run codex exec later"',
                        "powershell.exe -Command \"Add-Content -Path notes.md -Value 'ask codex about it'\"",
                        "git commit -m 'document codex hooks'", "Write-Host 'codex'"):
            with self.subTest(command=command):
                self.assertIsNone(self.blocked("Bash", {"command": command}))
        for command in ("powershell.exe -Command \"codex exec x\"", "bash -c \"echo a; codex exec x\"", "cmd /c codex exec x",
                        "sudo -u me codex exec x", "env FOO=1 codex exec x", "find . -exec codex exec x ;", "(codex exec x)"):
            with self.subTest(command=command):
                self.assertIn("another Codex session", self.blocked("Bash", {"command": command}))

    def test_the_rules_of_every_project_a_call_touches_apply(self):
        other = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(lambda: __import__("shutil").rmtree(other, ignore_errors=True))
        (other / ".bdd").mkdir()
        (other / ".bdd" / "config.toml").write_text('[[adapters]]\nname = "x"\nfeatures = "features"\nsteps = "steps"\n', encoding="utf-8")
        feature_dir = state.create(other, "FEAT-007", "Elsewhere", "standard")
        step = other / "steps" / "steps.py"
        step.parent.mkdir()
        step.write_text("def then_ok():\n    assert True\n", encoding="utf-8")
        lockfile.lock(other, feature_dir, "FEAT-007", "bind", [step])
        self.assertIn("locked", self.blocked("apply_patch", {"input": patch(str(step))}))                    # a path in another project
        self.assertIn("locked", self.blocked("Bash", {"command": f"echo x > {step.as_posix()}"}))
        self.assertIn("locked", self.blocked("Bash", {"command": "echo x > steps.py", "workdir": str(other / "steps")}))
        self.assertIsNone(self.blocked("Bash", {"command": "echo x > other.py", "workdir": str(other)}))

    def test_a_call_that_names_two_working_directories_is_refused(self):
        for tool_input in ({"command": "ls", "workdir": "a", "cwd": "b"}, {"command": "ls", "workdir": "a", "cwd": "a"},
                           {"command": "ls", "workdir": "a", "dir": "a"}):
            with self.subTest(tool_input=tool_input):
                self.assertIn("cannot be resolved", self.blocked("Bash", tool_input))
        self.assertIsNone(self.blocked("Bash", {"command": "ls", "cwd": "steps"}))

    def test_the_projects_a_call_reaches_decide_which_rules_apply_to_a_tool_nobody_has_looked_at(self):
        outside = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(lambda: __import__("shutil").rmtree(outside, ignore_errors=True))
        target = (self.root / "steps" / "steps.py").as_posix()
        elsewhere = tool_call(outside, "mcp__docs__write", {"path": target})
        self.assertIn("not one greenlight knows to be harmless", codexguard.evaluate(elsewhere))               # reaches this project
        self.assertIsNone(codexguard.evaluate(tool_call(outside, "mcp__docs__write", {"path": str(outside / "a.txt")})))   # reaches none
        self.assertIsNone(codexguard.evaluate(tool_call(outside, "mcp__docs__write", {"query": "no path here"})))
        self.config(tail='[approvals]\ncodex_allowed_tools = ["mcp__docs__write"]\n')
        self.assertIsNone(codexguard.evaluate(elsewhere))                                                     # this project allows it

    def test_the_hook_entry_points_are_named_however_the_cli_is_reached(self):
        for command in ("python tools/bdd/main.py guard < p.json", "python -m bddlib tripwire --accept", "python -m bddlib.cli guard",
                        "sh \"tools/bdd/bdd\" tripwire", "py main.py tripwire --accept", "/plugin/tools/bdd/bdd guard"):
            with self.subTest(command=command):
                self.assertIn("hook entry points", self.blocked("Bash", {"command": command}))
        self.assertIsNone(self.blocked("Bash", {"command": "tools/bdd/bdd status"}))

    def test_a_path_that_leaves_the_project_with_dots_lands_in_the_project_it_reaches(self):
        lock_steps(self)
        other = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(lambda: __import__("shutil").rmtree(other, ignore_errors=True))
        (other / ".bdd").mkdir()
        (other / ".bdd" / "config.toml").write_text('[[adapters]]\nname = "x"\nfeatures = "features"\nsteps = "steps"\n', encoding="utf-8")
        feature_dir = state.create(other, "FEAT-007", "Elsewhere", "standard")
        step = other / "steps" / "steps.py"
        step.parent.mkdir()
        step.write_text("def then_ok():\n    assert True\n", encoding="utf-8")
        lockfile.lock(other, feature_dir, "FEAT-007", "bind", [step])
        relative = os.path.relpath(step, self.root).replace("\\", "/")
        self.assertIn("locked", self.blocked("Bash", {"command": f"echo x > {relative}"}))
        self.assertIn("locked", self.blocked("Bash", {"command": f"cp a.py {relative}"}))
        self.assertIn("locked", self.blocked("apply_patch", {"input": patch(relative)}))
        self.assertIn("locked", self.blocked("Bash", {"command": f"echo x > {os.path.dirname(relative)}/../steps/steps.py"}))
        self.assertIsNone(self.blocked("Bash", {"command": f"cat {relative}"}))

    def test_a_write_that_names_a_path_nobody_can_resolve_is_refused(self):
        self.assertIn("cannot be resolved", self.blocked("Bash", {"command": "echo x > a\0b/c.txt"}))
        self.assertIsNone(self.blocked("Bash", {"command": "ls a\0b/c.txt"}))               # reading is not a write

    def test_two_command_keys_are_refused_by_the_guard(self):
        self.assertIn("cannot be checked", self.blocked("Bash", {"command": "ls", "cmd": "echo x > steps/steps.py"}))

    def test_a_call_from_outside_every_project_is_still_held_to_the_rules_of_the_project_it_reaches(self):
        lock_steps(self)
        outside = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(outside, ignore_errors=True))
        target = (self.root / "steps" / "steps.py").as_posix()
        for tool, tool_input in (("Bash", {"command": f"echo x > {target}"}), ("Bash", {"command": "echo x > steps.py", "workdir": str(self.root / "steps")}),
                                 ("apply_patch", {"input": patch(target)})):
            with self.subTest(tool=tool, tool_input=tool_input):
                payload = {**tool_call(Path(outside), tool, tool_input)}
                self.assertIn("locked", codexguard.evaluate(payload))
                assert_denied(self, run_hook(payload))
        harmless = tool_call(Path(outside), "Bash", {"command": "echo x > out.txt"})
        self.assertIsNone(codexguard.evaluate(harmless))
        self.assertEqual(run_hook(harmless)[0], 0)

    def test_a_payload_that_cannot_be_parsed_is_refused_when_it_names_a_path_in_a_project(self):
        outside = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(lambda: __import__("shutil").rmtree(outside, ignore_errors=True))
        target = (self.root / "steps" / "steps.py").as_posix()
        for tool_input in ({"input": f"please change {target} somehow"}, {"input": "see ../" + os.path.relpath(target, outside.parent).replace("\\", "/")},
                           {"input": "change a\0b/c.txt"}):
            with self.subTest(tool_input=tool_input):
                payload = tool_call(outside, "apply_patch", tool_input)
                self.assertIsNone(codexpayload.guard_calls(payload))
                self.assertIn("cannot be checked", codexguard.evaluate(payload))
                assert_denied(self, run_hook(payload))
        nothing = tool_call(outside, "apply_patch", {"input": "no path here"})
        self.assertIsNone(codexguard.evaluate(nothing))
        self.assertEqual(run_hook(nothing)[0], 0)

    def test_an_unreadable_payload_that_names_a_working_directory_is_always_refused(self):
        outside = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(lambda: __import__("shutil").rmtree(outside, ignore_errors=True))
        for tool_input in ({"input": "garbage", "workdir": "x"}, {"input": "garbage", "cwd": str(outside)},
                           {"input": f"see steps/steps.py", "workdir": str(self.root)}):
            with self.subTest(tool_input=tool_input):
                payload = tool_call(outside, "apply_patch", tool_input)
                self.assertIsNone(codexpayload.guard_calls(payload))
                self.assertIn("cannot be checked", codexguard.evaluate(payload))
                assert_denied(self, run_hook(payload))
        for workdir in (5, "a\0b"):
            self.assertIn("cannot be resolved", codexguard.evaluate(tool_call(outside, "apply_patch", {"input": "garbage", "workdir": workdir})))

    def test_relative_words_of_an_unreadable_payload_are_resolved_against_the_folder_it_runs_in(self):
        self.assertIn("cannot be checked", codexguard.evaluate(tool_call(self.root, "apply_patch", {"input": "see steps/steps.py"})))
        reach, unresolved = codexguard.raw_reach(tool_call(self.root / "steps", "apply_patch", {"input": "see ../steps/steps.py"}))
        self.assertEqual((reach, unresolved), ([self.root], False))
        self.assertEqual(codexguard.raw_reach(tool_call(self.root, "apply_patch", {"input": "x", "workdir": "a\0b"})), ([], True))

    def test_a_failing_guard_outside_every_project_blocks_only_a_call_that_names_a_path_in_one(self):
        outside = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(lambda: __import__("shutil").rmtree(outside, ignore_errors=True))
        target = (self.root / "steps" / "steps.py").as_posix()
        naming = tool_call(outside, "Bash", {"command": f"echo x > {target}"})
        harmless = tool_call(outside, "Bash", {"command": "echo hi"})
        with mock.patch.object(codexguard, "evaluate", side_effect=RuntimeError("boom")):
            assert_denied(self, run_hook(naming))
            self.assertEqual(run_hook(harmless)[0], 0)

    def test_polling_and_a_few_plain_answers_can_be_sent_to_a_running_command(self):
        for chars in ("", " ", "\n", "\r\n", "y", "n", "yes", "no", "q", "Y\n", "YES\r\n", "No", "Q\n", "7", "42\n", "123", "007"):
            with self.subTest(chars=chars):
                self.assertIsNone(self.blocked("write_stdin", {"session_id": 1, "chars": chars}))

    def test_anything_else_sent_to_a_running_command_is_refused_with_the_reason(self):
        for chars in ("echo x > steps/steps.py\n", "git apply p.diff\n", "sh\n", "bash -c x", "python -c x", "python", "node -e x", "node\n",
                      "cd steps", "cd ..", "pushd x", "popd", "Set-Location x", "ls", "ls -la\n", "cat x", "tee file", "rm a", "mv a b",
                      "echo hi", "ls; rm x", "$(whoami)", "`id`", "a|b", "a&b", "x > y", "x < y", "'y'", '"y"', "y;n", "y y", "y\ny",
                      "1234", "-1", "1.5", "maybe", "yess", "a\tb", "a\x1b[A", "\x03", "\n\n", "y\n\n", " y", "y ", "line one\nline two\n",
                      "$greenlight-approve FEAT-007 rules", "~/x", "*.py", "a[0]", "a\u00e9"):
            with self.subTest(chars=chars):
                self.assertIn("cannot be checked", self.blocked("write_stdin", {"session_id": 1, "chars": chars}) or "")
        self.assertIn("cannot be checked", self.blocked("write_stdin", {"chars": 5}))
        self.assertIn("normal tool call", self.blocked("write_stdin", {"chars": "cd .."}))

    def test_the_strict_rule_applies_only_where_a_call_reaches_a_project(self):
        outside = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(lambda: __import__("shutil").rmtree(outside, ignore_errors=True))
        free = tool_call(outside, "write_stdin", {"session_id": 1, "chars": "echo $(whoami) > out.txt\n"})
        self.assertIsNone(codexguard.evaluate(free))                                           # reaches no project
        reaching = tool_call(outside, "write_stdin", {"session_id": 1, "chars": f"tee {(self.root / 'steps' / 'steps.py').as_posix()}"})
        self.assertIn("cannot be checked", codexguard.evaluate(reaching))
        assert_denied(self, run_hook(reaching))

    def test_nothing_is_held_back_between_chunks_any_more(self):
        self.blocked("write_stdin", {"session_id": 7, "chars": "echo x > steps/ste"})
        self.assertFalse((enforcement.marker_dir(self.root) / "_stdin.json").exists())
        self.assertFalse(hasattr(codexguard, "command_complete"))

    def test_a_call_that_cannot_be_read_is_refused(self):
        self.assertIn("cannot be checked", self.blocked("apply_patch", {"input": "no files named"}))
        self.assertIn("cannot be checked", self.blocked("Bash", {}))

    def test_the_approval_command_cannot_be_run_by_a_tool(self):
        self.assertIn("approvals can only be given", self.blocked("Bash", {"command": "echo '$greenlight-approve FEAT-007 rules'"}))
        self.assertIn("approvals can only be given", self.blocked("Bash", {"command": "echo /greenlight:approve FEAT-007 rules"}))

    def test_a_nested_codex_session_is_refused_but_reading_is_not(self):
        for command in ("codex exec 'hello'", "FOO=1 codex", "npx @openai/codex exec x", "sudo /usr/bin/codex resume",
                        "echo hi && codex exec y", "python -c \"import subprocess; subprocess.run(['codex','exec'])\""):
            with self.subTest(command=command):
                self.assertIn("another Codex session", self.blocked("Bash", {"command": command}))
        for command in ("codex --version", "codex login status", "codex features list", "ls codex-notes"):
            with self.subTest(command=command):
                self.assertIsNone(self.blocked("Bash", {"command": command}))

    def test_a_project_that_takes_codex_approvals_refuses_every_codex_word_but_others_only_where_a_program_starts(self):
        """A nested session is the way to forge a Codex approval, so where those are accepted the check does not trust quoting."""
        text = {"command": "powershell -Command \"Add-Content -LiteralPath notes.txt -Value '# by codex'\""}
        launcher = {"command": "powershell -Command \"codex exec hello\""}
        quote_tricks = ({"command": "bash -c 'x=1; codex exec hello'"}, {"command": "sh -c \"echo ok\" \"; codex exec hi\""},
                        {"command": "echo \"it's\"; echo 'codex' exec hi"})
        self.assertIsNone(self.blocked("Bash", text))                       # not opted in: text that mentions it is fine
        self.assertIn("another Codex session", self.blocked("Bash", launcher))
        opt_in(self)
        self.assertIn("another Codex session", self.blocked("Bash", text))  # opted in: any `codex` word counts
        self.assertIn("another Codex session", self.blocked("Bash", launcher))
        for call in quote_tricks:
            with self.subTest(command=call["command"]):
                self.assertIn("another Codex session", self.blocked("Bash", call))
        self.assertIsNone(self.blocked("Bash", {"command": "codex --version"}))

    def test_a_glob_or_a_change_of_folder_does_not_hide_codexs_state(self):
        moved = self.home.as_posix()
        hidden = moved[:-2] + "*"                                       # the configured home, its last letters a glob
        for command in ("echo '{}' > .co*/hooks.json", "cp forged ~/.c?dex/config.toml", "tee rollout-*.jsonl < forged",
                        f"echo x > {hidden}/sessions/a.jsonl", f"cd {moved} && echo x > config.toml",
                        f"pushd {moved}; Set-Content hooks.json x", "cd .codex && echo x > hooks.json"):
            with self.subTest(command=command):
                self.assertIn("keep greenlight's hooks running", self.blocked("Bash", {"command": command}))
        for command in ("echo x > .cache*/a", "rm build/*.jsonl", f"cd {moved} && cat config.toml", "cd src && echo x > a.txt"):
            with self.subTest(command=command):
                self.assertIsNone(self.blocked("Bash", {"command": command}))

    def test_a_folder_a_command_moves_into_is_one_of_the_places_it_reaches(self):
        other = self.root / "other"
        (other / ".bdd").mkdir(parents=True)
        (other / ".bdd" / "config.toml").write_text('autonomy = "guided"\n', encoding="utf-8")
        calls = codexpayload.guard_calls(tool_call(self.root / "src", "Bash", {"command": "cd ../other && echo x > a.txt"}))
        projects, unresolved = codexguard.reached_projects({"cwd": str(self.root / "src")}, calls)
        self.assertIn(other.resolve(), [p.resolve() for p in projects])
        self.assertFalse(unresolved)
        self.assertEqual(codexguard.directory_operands("git -C repo status; make --directory=build; Set-Location -Path 'x'"),
                         ["x", "repo", "build"])

    def test_codexs_own_hook_and_settings_files_cannot_be_written_by_an_agent(self):
        for path in (".codex/hooks.json", "./.codex/config.toml", ".CODEX/Hooks.JSON", "sub/../.codex/config.toml"):
            with self.subTest(path=path):
                self.assertIn("keep greenlight's hooks running", self.blocked("apply_patch", {"input": patch(path)}))
        for command in ("echo '{}' > .codex/hooks.json", "sed -i s/a/b/ ~/.codex/config.toml", "export CODEX_HOME=/tmp/x && tee y",
                        "echo x >> .CODEX/config.toml"):
            with self.subTest(command=command):
                self.assertIn("keep greenlight's hooks running", self.blocked("Bash", {"command": command}))
        self.assertIsNone(self.blocked("Bash", {"command": "cat .codex/hooks.json"}))

    def test_the_whole_codex_home_including_the_sessions_is_off_limits_for_writes(self):
        rollout_file = self.home / "sessions" / "2026" / "10" / "20" / "rollout-2026-10-20T10-00-00-abc.jsonl"
        for path in (str(rollout_file), str(self.home / "sessions" / "anything.txt"), str(self.home / "auth.json"),
                     str(rollout_file).upper() if os.name == "nt" else str(rollout_file), "rollout-forged.jsonl"):
            with self.subTest(path=path):
                self.assertIn("keep greenlight's hooks running", self.blocked("apply_patch", {"input": patch(path)}))
        for command in (f"cp forged.jsonl '{rollout_file}'", f"echo x > {self.home.as_posix()}/sessions/a.jsonl",
                        "tee rollout-2026-10-20T10-00-00-abc.jsonl < forged", "mv forged.jsonl rollout-x.jsonl"):
            with self.subTest(command=command):
                self.assertIn("keep greenlight's hooks running", self.blocked("Bash", {"command": command}))
        self.assertIsNone(self.blocked("Bash", {"command": f"cat '{rollout_file}'"}))

    def test_a_link_to_codexs_files_does_not_get_around_the_check(self):
        link = self.root / "innocent.json"
        target = self.home / "hooks.json"
        target.write_text("{}", encoding="utf-8")
        try:
            link.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("this account cannot create symbolic links")
        self.assertIn("keep greenlight's hooks running", self.blocked("apply_patch", {"input": patch("innocent.json")}))

    def test_the_hook_entry_points_are_not_for_an_agent_to_run(self):
        for command in ("echo '{}' | sh tools/bdd/bdd codex-hook", "bdd codex-hook < payload.json",
                        "python tools/bdd/main.py approve --from-hook", "sh tools/bdd/bdd guard < p.json",
                        "tools/bdd/bdd tripwire --accept", "sh tools/bdd/bdd install-hooks codex --uninstall",
                        "python -m bddlib.codexhook < p.json"):
            with self.subTest(command=command):
                self.assertIn("hook entry points", self.blocked("Bash", {"command": command}))
        self.assertIsNone(self.blocked("Bash", {"command": "tools/bdd/bdd status"}))

    def test_outside_a_project_nothing_is_ever_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload = tool_call(Path(tmp), "Bash", {"command": "codex exec hi"})
            self.assertIsNone(codexguard.evaluate(payload))


class HookTest(CodexCase):
    def test_a_blocked_call_is_a_deny_decision_on_stdout_with_exit_0(self):
        """Observed in a live Codex session: exit 2 with the reason on stderr let the call through, a deny decision stopped it."""
        lock_steps(self)
        decision = assert_denied(self, run_hook(tool_call(self.root, "apply_patch", {"input": patch("steps/steps.py")})))
        self.assertIn("locked", decision["hookSpecificOutput"]["permissionDecisionReason"])

    def test_a_hook_that_fails_inside_a_project_denies_the_call_instead_of_letting_it_through(self):
        payload = tool_call(self.root, "Bash", {"command": "ls"})
        with mock.patch.object(codexhook.codexguard, "evaluate", side_effect=RuntimeError("boom")):
            decision = assert_denied(self, run_hook(payload))
        self.assertIn("RuntimeError", decision["hookSpecificOutput"]["permissionDecisionReason"])

    def test_every_refusal_prints_exactly_one_json_object(self):
        lock_steps(self)
        for tool, tool_input in (("apply_patch", {"input": patch("steps/steps.py")}), ("Bash", {"command": "echo x > steps/steps.py"}),
                                 ("Bash", {})):
            with self.subTest(tool=tool):
                _, out, _ = run_hook(tool_call(self.root, tool, tool_input))
                self.assertEqual(len(out.strip().splitlines()), 1)
                self.assertIsInstance(json.loads(out), dict)

    def test_an_allowed_call_exits_0_and_leaves_the_evidence_that_hooks_ran(self):
        code, _, _ = run_hook(tool_call(self.root, "Bash", {"command": "ls"}))
        self.assertEqual(code, 0)
        self.assertTrue(enforcement.active(self.root, SESSION))
        self.assertTrue((enforcement.marker_dir(self.root) / enforcement.CODEX_MARKER).is_file())

    def test_unreadable_input_and_other_projects_are_left_alone(self):
        for raw in ("", "not json", "[]"):
            with mock.patch.object(sys, "stdin", io.StringIO(raw)):
                self.assertEqual(codexhook.main([]), 0)
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(run_hook(tool_call(Path(tmp), "Bash", {"command": "codex exec x"}))[0], 0)

    def test_the_tripwire_reports_a_change_to_a_file_that_keeps_greenlight_running(self):
        prompt = {"hook_event_name": "UserPromptSubmit", "session_id": SESSION, "cwd": str(self.root), "turn_id": TURN,
                  "prompt": "hello", "transcript_path": None}
        self.assertEqual(run_hook(prompt)[0], 0)                                    # takes the baseline
        self.assertEqual(run_hook(tool_call(self.root, "Bash", {"command": "ls"}, "PostToolUse"))[0], 0)
        self.write(".codex/hooks.json", "{}")
        code, out, err = run_hook(tool_call(self.root, "Bash", {"command": "ls"}, "PostToolUse"))
        self.assertEqual(code, 0)
        feedback = json.loads(out)                                      # the documented form for the model: decision block and a reason
        self.assertEqual(set(feedback), {"decision", "reason"})
        self.assertEqual(feedback["decision"], "block")
        self.assertIn(".codex", feedback["reason"])
        self.assertIn(".codex", err)

    def test_the_tripwire_watches_the_hook_files_in_the_project_and_the_home(self):
        self.write(".codex/hooks.json", "{}")
        (self.home / "config.toml").write_text("x = 1\n", encoding="utf-8")
        watched = {p.as_posix() for p in tripwire.watched_files(self.root, None)}
        self.assertIn((self.root / ".codex" / "hooks.json").as_posix(), watched)
        self.assertIn((self.home / "config.toml").resolve().as_posix(), {Path(w).resolve().as_posix() for w in watched})

    def test_an_approval_typed_in_codex_is_recorded_and_told_not_to_be_verified(self):
        opt_in(self)
        self.gate("discover")
        self.rules.write_text("# Rules\n\nR-007.1 Something.\n", encoding="utf-8", newline="\n")
        payload = {"hook_event_name": "UserPromptSubmit", "session_id": SESSION, "cwd": str(self.root), "turn_id": TURN,
                   "prompt": APPROVE, "transcript_path": str(self.home / "sessions" / "rollout-x.jsonl")}
        code, out, _ = run_hook(payload)
        self.assertEqual(code, 0)
        context = json.loads(out)["hookSpecificOutput"]
        self.assertEqual(context["hookEventName"], "UserPromptSubmit")
        self.assertIn("rules approved", context["additionalContext"])
        self.assertIn("not provenance-verified", context["additionalContext"])
        recorded = self.data()["approvals"][-1]
        self.assertEqual((recorded["grade"], recorded["origin"], recorded["prompt_id"]), ("codex", "codex-unverified", f"codex:{TURN}"))

    def test_the_two_spellings_do_not_cross_over(self):
        self.assertIsNone(approvalcommand.parse(APPROVE))
        self.assertIsNone(approvalcommand.parse_codex("/greenlight:approve FEAT-007 rules"))
        self.assertEqual(approvalcommand.parse_codex(APPROVE), ("FEAT-007", "rules", None))
        self.assertEqual(approvalcommand.parse_codex("$greenlight-approve FEAT-007 examples reject too thin"),
                         ("FEAT-007", "examples", "too thin"))
        self.assertIsNone(approvalcommand.parse_codex("please $greenlight-approve FEAT-007 rules"))


def rollout(path: Path, message: str = APPROVE, source: str = "cli", thread: str = "user", turn: str = TURN,
            session: str = SESSION) -> Path:
    rows = [{"type": "session_meta", "payload": {"id": session, "source": source, "thread_source": thread,
                                                  "originator": "codex-tui", "cli_version": "0.142.3"}},
            {"type": "event_msg", "payload": {"type": "task_started", "turn_id": turn}},
            {"type": "response_item", "payload": {"type": "message", "role": "user", "content": []}},
            {"type": "event_msg", "payload": {"type": "user_message", "message": message, "images": []}},
            {"type": "event_msg", "payload": {"type": "task_complete", "turn_id": turn}}]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(("\n".join(json.dumps(r) for r in rows) + "\n").encode("utf-8"))
    return path


def append_turn(path: Path, message: str = APPROVE, turn: str = TURN) -> None:
    """What Codex does when a prompt arrives: it only ever adds to the end of the session file."""
    rows = [{"type": "event_msg", "payload": {"type": "task_started", "turn_id": turn}},
            {"type": "event_msg", "payload": {"type": "user_message", "message": message, "images": []}},
            {"type": "event_msg", "payload": {"type": "task_complete", "turn_id": turn}}]
    with path.open("ab") as handle:
        handle.write(("\n".join(json.dumps(r) for r in rows) + "\n").encode("utf-8"))


NAME = "rollout-2026-10-20T10-00-00-abc.jsonl"


class SupportingEvidenceTest(CodexCase):
    """What Codex's session file shows about an approval: a sentence for a reviewer, never a verdict."""

    def approval(self, path: Path | None = None, **extra) -> dict:
        path = path or self.home / "sessions" / "2026" / "10" / "20" / NAME
        return {"transcript_path": str(path), "prompt_id": f"codex:{TURN}", "session": SESSION, "gate": "rules",
                "decision": "approve", "at": "2026-10-20T10:00:00+00:00", "source": self.fingerprint(path), **extra}

    def fingerprint(self, path: Path) -> dict:
        """What the hook records: the file as it is, or nothing yet if Codex has not written it."""
        return codexorigin.fingerprint(self.root, str(path)) or {
            "size": 0, "sha256": hashlib.sha256(b"").hexdigest(), "sessions": codexorigin.pinned_sessions(self.root)}

    def put(self, **kwargs) -> dict:
        path = self.home / "sessions" / "2026" / "10" / "20" / NAME
        path.unlink(missing_ok=True)                             # a new session each time
        approval_before = self.approval(path)                    # the hook runs before Codex writes the prompt
        rollout(path, **kwargs)
        return {**approval_before}

    def evidence(self, approval: dict) -> str:
        return codexorigin.supporting_evidence(self.root, approval, "FEAT-007")

    def allow(self, *sources: str) -> None:
        values = ", ".join(json.dumps(s) for s in sources)
        self.config(tail=f"[approvals]\ncodex_interactive_sources = [{values}]\n")

    def test_it_is_always_labelled_as_supporting_evidence_only(self):
        self.allow("cli")
        for approval in (self.put(), self.approval(), {**self.put(), "source": None}):
            self.assertIn("supporting evidence only", self.evidence(approval))

    def test_a_session_file_that_shows_exactly_the_approval_says_so_and_names_the_source(self):
        self.allow("cli")
        text = self.evidence(self.put())
        self.assertIn("shows exactly this approval", text)
        self.assertIn("an interactive session as named in codex_interactive_sources", text)

    def test_a_source_nobody_named_is_not_guessed_and_exec_is_called_headless(self):
        self.assertIn("add 'tui' to [approvals] codex_interactive_sources", self.evidence(self.put(source="tui")))
        self.assertIn("headless `codex exec` session", self.evidence(self.put(source="exec")))
        self.assertIn("not a user session", self.evidence(self.put(thread="subagent")))

    def test_the_wrong_text_a_missing_turn_and_another_session_are_reported(self):
        self.allow("cli")
        self.assertIn("is not the rules approve", self.evidence(self.put(message="$greenlight-approve FEAT-007 examples")))
        self.assertIn("is not the rules approve", self.evidence(self.put(message="please " + APPROVE)))
        self.assertIn("does not appear", self.evidence(self.put(turn="another-turn")))
        self.assertIn("belongs to session", self.evidence(self.put(session="019a0000-aaaa-7bbb-8ccc-00000000ffff")))

    def test_a_session_file_rewritten_after_the_approval_is_reported(self):
        self.allow("cli")
        path = self.home / "sessions" / "2026" / "10" / "20" / NAME
        rollout(path, message="hello")                               # what the file held when the hook ran
        approval = self.approval(path)
        rollout(path, message=APPROVE)                               # then someone rewrote it to say the approval
        self.assertIn("changed after", self.evidence(approval))

    def test_an_approval_without_a_fingerprint_is_reported(self):
        self.assertIn("did not record what the session file looked like", self.evidence({**self.put(), "source": None}))

    def test_only_the_recorded_file_inside_codexs_sessions_folder_is_ever_looked_at(self):
        self.assertIn("not a rollout file inside", self.evidence({**self.approval(), "transcript_path": "/etc/passwd"}))
        elsewhere = rollout(self.root / "elsewhere" / NAME)
        self.assertIn("not a rollout file inside", self.evidence(self.approval(elsewhere)))
        other_folder = self.home / "sessions" / "2026" / "10" / "21" / NAME
        rollout(self.home / "sessions" / "2026" / "10" / "20" / NAME)
        self.assertIn("not a rollout file inside", self.evidence(self.approval(other_folder)))                # never found by name

    def test_nothing_but_a_rollout_file_in_the_sessions_folder_is_ever_read_for_a_fingerprint(self):
        outside = self.root / "secrets" / NAME
        outside.parent.mkdir()
        outside.write_text("not for greenlight", encoding="utf-8")
        for path in (str(outside), "/etc/passwd", "", None, str(self.home / "sessions" / "2026" / ".." / ".." / ".." / "x" / NAME)):
            with self.subTest(path=path):
                self.assertIsNone(codexorigin.fingerprint(self.root, path))
        inside = rollout(self.home / "sessions" / "2026" / "10" / "20" / NAME)
        self.assertEqual(codexorigin.fingerprint(self.root, str(inside))["size"], inside.stat().st_size)

    def test_a_link_out_of_the_sessions_folder_is_not_followed(self):
        outside = rollout(self.root / "outside" / NAME)
        inside = self.home / "sessions" / "2026" / "10" / "20" / NAME
        inside.parent.mkdir(parents=True, exist_ok=True)
        try:
            inside.symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest("this account cannot create symbolic links")
        self.assertIn("not a rollout file inside", self.evidence(self.approval(inside)))

    def test_the_sessions_folder_is_the_configured_one_never_the_one_in_the_environment(self):
        self.allow("cli")
        approval = self.put()
        with mock.patch.dict(os.environ, {"CODEX_HOME": str(self.root / "other-home")}):
            self.assertEqual(codexorigin.codex_sessions_dir(self.root), self.home / "sessions")
            self.assertIn("shows exactly this approval", self.evidence(approval))
        moved = {**approval, "source": {**approval["source"], "sessions": str(self.root / "somewhere-else")}}
        self.assertIn("codex_home", self.evidence(moved))

    def test_the_config_options_are_read_and_checked(self):
        self.allow("cli", "vscode")
        self.assertEqual(cfg.load(self.root).codex_interactive_sources, ("cli", "vscode"))
        self.write(".bdd/config.toml", '[approvals]\ncodex_home = "~/elsewhere"\ncodex_allowed_tools = ["mcp__docs__search"]\n')
        self.assertEqual(cfg.load(self.root).codex_home, "~/elsewhere")
        self.assertEqual(cfg.load(self.root).codex_allowed_tools, ("mcp__docs__search",))
        for bad in ("codex_interactive_sources = 3", "codex_home = 3", "codex_allowed_tools = 3"):
            with self.subTest(bad=bad):
                self.config(tail=f"[approvals]\n{bad}\n")
                with self.assertRaises(cfg.ConfigError):
                    cfg.load(self.root)


class CodexGradeTest(CodexCase):
    """An approval typed in Codex is accepted but never graded hard and never called verified."""

    def type_approval(self) -> None:
        opt_in(self)
        self.gate("discover")
        self.rules.write_text("# Rules\n\nR-007.1 Something.\n", encoding="utf-8", newline="\n")
        path = self.home / "sessions" / "2026" / "10" / "20" / NAME
        payload = {"hook_event_name": "UserPromptSubmit", "session_id": SESSION, "cwd": str(self.root), "turn_id": TURN,
                   "prompt": APPROVE, "transcript_path": str(path)}
        rollout(path, message="an earlier prompt", turn="earlier-turn")
        self.assertEqual(run_hook(payload)[0], 0)
        append_turn(path)

    def test_a_project_where_claude_code_hooks_have_run_does_not_take_one_without_the_opt_in(self):
        self.gate("discover")
        self.rules.write_text("# Rules\n\nR-007.1 Something.\n", encoding="utf-8", newline="\n")
        enforcement.touch(self.root, "a-claude-code-session")                         # what the Claude Code guard leaves behind
        self.assertFalse(enforcement.codex_seen(self.root))
        with self.assertRaises(UsageError) as refused:
            approvals.record(self.root, self.feature_dir, "rules", "approve", "codex")
        self.assertIn("accept_codex = true", str(refused.exception))
        opt_in(self)
        self.assertEqual(approvals.record(self.root, self.feature_dir, "rules", "approve", "codex")["grade"], "codex")

    def test_by_default_it_is_refused_once_hooks_have_run_and_says_how_to_opt_in(self):
        self.gate("discover")
        self.rules.write_text("# Rules\n\nR-007.1 Something.\n", encoding="utf-8", newline="\n")
        payload = {"hook_event_name": "UserPromptSubmit", "session_id": SESSION, "cwd": str(self.root), "turn_id": TURN,
                   "prompt": APPROVE, "transcript_path": None}
        code, out, _ = run_hook(payload)
        self.assertEqual(code, 0)                                                     # the prompt itself is never blocked
        self.assertIn("NOT recorded", out)
        self.assertIn("accept_codex = true", out)
        self.assertEqual(self.data()["approvals"], [])

    def test_no_mode_takes_it_without_the_opt_in_and_a_hard_project_never_does(self):
        self.gate("discover")
        self.rules.write_text("# Rules\n\nR-007.1 Something.\n", encoding="utf-8", newline="\n")
        for mode in ("soft", "auto"):
            with self.subTest(mode=mode):
                self.approval_lines = []
                self.config(f'enforcement = "{mode}"\n')
                with self.assertRaises(UsageError) as refused:
                    approvals.record(self.root, self.feature_dir, "rules", "approve", "codex")
                self.assertIn("accept_codex = true", str(refused.exception))
        self.approval_lines = ["accept_codex = true"]
        self.config('enforcement = "soft"\n')
        approvals.record(self.root, self.feature_dir, "rules", "approve", "codex")
        self.assertEqual(approvals.effective_problems(self.root, self.data(), "rules"), [])
        self.config('enforcement = "hard"\n')
        self.assertTrue(approvals.effective_problems(self.root, self.data(), "rules"))

    def test_the_ci_check_fails_on_a_codex_approval_until_the_project_commits_its_acceptance(self):
        opt_in(self)
        self.gate("discover")
        self.rules.write_text("# Rules\n\nR-007.1 Something.\n", encoding="utf-8", newline="\n")
        approvals.record(self.root, self.feature_dir, "rules", "approve", "codex")
        self.approval_lines = []
        self.config()                                                         # the acceptance is not in the committed config
        found = approvals.recorded_problems(self.root, self.data())["rules"]
        self.assertIn(approvals.CI_CODEX_MESSAGE, found)
        out, here = io.StringIO(), os.getcwd()
        os.chdir(self.root)
        try:
            with contextlib.redirect_stdout(out):
                code = cli.main(["approve", "FEAT-007", "--check"])
        finally:
            os.chdir(here)
        self.assertEqual(code, 1)
        self.assertIn("a reviewer has to accept it", out.getvalue())
        opt_in(self)
        self.assertNotIn(approvals.CI_CODEX_MESSAGE, approvals.recorded_problems(self.root, self.data())["rules"])

    def test_with_the_opt_in_it_is_accepted_and_labelled_everywhere(self):
        self.type_approval()
        label = approvals.CODEX_LABEL
        self.assertIn(label, statecmd.describe_approvals(self.data()["approvals"]))
        self.assertIn(label, reportcmd.approval_text(self.root, self.data()))
        self.assertEqual([row["origin"] for row in pr.approvals_of(self.root, self.data())], [label])
        self.assertIn(label, pr.approval_line({**pr.approvals_of(self.root, self.data())[0]}))

    def test_the_approval_is_recorded_with_the_codex_grade_and_an_unverified_origin(self):
        self.type_approval()
        recorded = self.data()["approvals"][-1]
        self.assertEqual((recorded["grade"], recorded["origin"], recorded["prompt_id"]), ("codex", "codex-unverified", f"codex:{TURN}"))
        self.assertEqual(self.data()["phase"], "test-design")

    def test_verifying_adds_supporting_evidence_and_leaves_the_origin_unverified(self):
        self.config(tail='[approvals]\ncodex_interactive_sources = ["cli"]\n')
        self.type_approval()
        approvals.verify_origins(self.feature_dir)
        recorded = self.data()["approvals"][-1]
        self.assertEqual(recorded["origin"], "codex-unverified")
        self.assertIn("supporting evidence only", recorded["evidence"])
        self.assertIn("shows exactly this approval", recorded["evidence"])

    def test_the_gate_accepts_it_by_default_and_a_hard_project_does_not(self):
        self.type_approval()
        self.assertEqual(approvals.effective_problems(self.root, self.data(), "rules"), [])
        self.config("enforcement = \"hard\"\n")
        problems = approvals.effective_problems(self.root, self.data(), "rules")
        self.assertTrue(any("requires hard enforcement" in p for p in problems), problems)
        with self.assertRaises(UsageError):
            approvals.record(self.root, self.feature_dir, "rules", "approve", "codex")

    def test_a_feature_with_such_an_approval_is_soft_and_says_why(self):
        self.type_approval()
        level, reasons = enforcement.classify(self.root, self.data())
        self.assertEqual(level, "soft")
        self.assertTrue(any("typed in Codex and is not provenance-verified" in reason for reason in reasons))

    def test_the_ci_check_names_it_for_the_reviewer(self):
        self.type_approval()
        out, here = io.StringIO(), os.getcwd()
        os.chdir(self.root)
        try:
            with contextlib.redirect_stdout(out):
                cli.main(["approve", "FEAT-007", "--check"])
        finally:
            os.chdir(here)
        self.assertIn("typed in Codex", out.getvalue())
        self.assertIn("a reviewer has to confirm", out.getvalue())

    def test_work_done_where_codex_hooks_run_is_never_graded_hard(self):
        self.gate("discover")
        self.assertEqual(enforcement.classify(self.root, self.data())[0], "soft")
        enforcement.touch_codex(self.root, SESSION)
        level, reasons = enforcement.classify(self.root, self.data())
        self.assertEqual(level, "soft")
        self.assertTrue(any("Codex hooks were used here" in reason for reason in reasons))

    def test_nothing_a_hook_command_writes_can_make_a_gate_hard(self):
        """The hook is a command anything could call with a made-up payload, so whatever it logs proves nothing."""
        self.gate("discover")
        call = {**tool_call(self.root, "Bash", {"command": "sh /p/bdd gate FEAT-007 discover"}), "tool_use_id": "call-5"}
        run_hook(call)
        run_hook({**call, "hook_event_name": "PostToolUse"})
        self.assertEqual(enforcement.classify(self.root, self.data())[0], "soft")

    def test_the_marker_is_a_hint_that_is_not_pruned_or_mistaken_for_a_session(self):
        enforcement.touch_codex(self.root, SESSION)
        marker = enforcement.marker_dir(self.root) / enforcement.CODEX_MARKER
        self.assertTrue(enforcement.codex_seen(self.root))
        os.utime(marker, (0, 0))
        enforcement.prune(enforcement.marker_dir(self.root))
        self.assertTrue(marker.is_file())


class ClaudeCodeGuardTest(ProjectCase):
    """The Claude Code guard also keeps an agent away from the Codex side: the cheap, sure refusals."""

    def evaluate(self, tool: str, **tool_input) -> str | None:
        return guard.evaluate({"tool_name": tool, "cwd": str(self.root), "tool_input": tool_input})

    def test_the_codex_spelling_of_the_approval_is_refused_like_the_claude_code_one(self):
        for command in ("echo '$greenlight-approve FEAT-007 rules'", "printf '$greenlight-reject FEAT-007 examples'"):
            with self.subTest(command=command):
                self.assertIn("approvals can only be given", self.evaluate("Bash", command=command))
        self.assertIn("approvals can only be given", self.evaluate("SendMessage", message="$greenlight-approve FEAT-007 rules"))

    def test_starting_a_codex_session_is_refused_the_same_way_as_in_the_codex_guard(self):
        for command in ("codex exec 'hello'", "bash -lc 'codex resume'", "xargs -I{} codex exec {}", "timeout 5 codex exec x",
                        "npx @openai/codex exec x", "co''dex exec x"):
            with self.subTest(command=command):
                self.assertIn("another Codex session", self.evaluate("Bash", command=command))
        for command in ("codex --version", "codex login status", "echo codex-notes"):
            with self.subTest(command=command):
                self.assertIsNone(self.evaluate("Bash", command=command))
        self.assertEqual(codexguard.starts_codex_session("codex exec x"), codexsession.starts_codex_session("codex exec x"))

    def test_the_hook_entry_points_are_refused(self):
        for command in ("sh tools/bdd/bdd codex-hook < payload.json", "bdd install-hooks codex --apply", "bdd approve --from-hook"):
            with self.subTest(command=command):
                self.assertIn("hook entry points", self.evaluate("Bash", command=command))
        self.assertIsNone(self.evaluate("Bash", command="bdd approve FEAT-007 --check"))

    def test_the_cli_reached_in_any_way_is_named(self):
        for command in ("python tools/bdd/main.py guard < p.json", "python -m bddlib tripwire --accept", "sh tools/bdd/bdd guard"):
            with self.subTest(command=command):
                self.assertIn("hook entry points", self.evaluate("Bash", command=command))

    def test_interpreters_importing_the_approval_code_are_refused(self):
        for command in ("python -c \"from bddlib import approvals; approvals.record(1)\"", "python -c 'import bddlib.approvals as a'",
                        "python -c \"from bddlib.approvals import record\"", "py -c \"import bddlib.approvehook\"",
                        "node -e \"require('child_process').execSync('python -m bddlib.codexhook')\""):
            with self.subTest(command=command):
                self.assertIn("hook entry points", self.evaluate("Bash", command=command))

    def test_every_reading_of_the_command_is_checked(self):
        for command in ("sh tools/bdd/bdd cod''ex-hook < p.json", "echo x > ~/.co''dex/config.toml", "echo x > .co\"dex\"/hooks.json",
                        "python -m bddlib.codex''hook < p.json"):
            with self.subTest(command=command):
                self.assertIsNotNone(self.evaluate("Bash", command=command))

    def test_writes_to_codex_state_are_refused_and_reading_it_is_not(self):
        for command in ("echo x > ~/.codex/config.toml", "tee ~/.codex/sessions/2026/a/rollout-x.jsonl < forged", "export CODEX_HOME=/tmp/x && cp a b"):
            with self.subTest(command=command):
                self.assertIn("Codex's home folder", self.evaluate("Bash", command=command))
        for path in (".codex/hooks.json", "home/.codex/sessions/rollout-abc.jsonl", "rollout-2026-10-20T10-00-00-abc.jsonl"):
            with self.subTest(path=path):
                self.assertIn("Codex's home folder", self.evaluate("Write", file_path=str(self.root / path)))
        self.assertIsNone(self.evaluate("Bash", command="cat ~/.codex/config.toml"))
        self.assertIsNone(self.evaluate("Write", file_path=str(self.root / "src" / "app.py")))

    def test_a_glob_that_reaches_codex_state_is_refused_like_the_name(self):
        for command in ("echo x > ~/.co*/config.toml", "cp forged ~/.c?dex/hooks.json", "rm ~/.[c]odex/hooks.json",
                        "tee ~/x/sessions/rollout-*.jsonl < forged", "cp forged ro?lout-*.jsonl"):
            with self.subTest(command=command):
                self.assertIn("Codex's home folder", self.evaluate("Bash", command=command))
        for command in ("echo x > ~/.cache*/a", "rm build/*.jsonl", "cp a ~/.config/*.toml"):
            with self.subTest(command=command):
                self.assertIsNone(self.evaluate("Bash", command=command))

    def test_a_link_into_codex_state_is_refused_for_a_write(self):
        home = self.root / "home" / ".codex"
        home.mkdir(parents=True)
        (home / "hooks.json").write_text("{}", encoding="utf-8")
        link = self.root / "innocent.json"
        try:
            link.symlink_to(home / "hooks.json")
        except (OSError, NotImplementedError):
            self.skipTest("this account cannot create symbolic links")
        self.assertIn("Codex's home folder", self.evaluate("Write", file_path=str(link)))


class InstallTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.home = Path(self.dir.name).resolve() / "home"
        patcher = mock.patch.dict(os.environ, {"CODEX_HOME": str(self.home)})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.file = self.home / "hooks.json"

    def install(self, *argv: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            return installhooks.run(["codex", *argv]), out.getvalue(), err.getvalue()

    def test_by_default_it_only_shows_what_it_would_write(self):
        code, out, _ = self.install()
        self.assertEqual(code, 0)
        self.assertIn("codex-hook", out)
        self.assertIn("--apply", out)
        self.assertFalse(self.file.exists())

    def test_apply_writes_the_three_events_and_keeps_what_was_there(self):
        self.home.mkdir()
        foreign = {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "mine.sh"}]}]},
                   "other": 1}
        self.file.write_text(json.dumps(foreign), encoding="utf-8")
        self.assertEqual(self.install("--apply")[0], 0)
        data = json.loads(self.file.read_text(encoding="utf-8"))
        self.assertEqual(data["other"], 1)
        self.assertEqual(set(data["hooks"]), {"PreToolUse", "PostToolUse", "UserPromptSubmit"})
        self.assertEqual(data["hooks"]["PreToolUse"][0], foreign["hooks"]["PreToolUse"][0])
        self.assertEqual(len(data["hooks"]["PreToolUse"]), 2)
        self.assertNotIn("matcher", data["hooks"]["UserPromptSubmit"][0])
        self.assertTrue(installhooks.installed(self.file))

    def test_applying_twice_changes_nothing_and_a_changed_wrapper_path_is_replaced_not_added(self):
        self.install("--apply")
        before = self.file.read_text(encoding="utf-8")
        self.assertIn("already in place", self.install("--apply")[1])
        self.assertEqual(self.file.read_text(encoding="utf-8"), before)
        with mock.patch.object(installhooks, "wrapper_path", return_value=Path("/new/place/tools/bdd/bdd")):
            self.install("--apply")
        data = json.loads(self.file.read_text(encoding="utf-8"))
        self.assertEqual([len(groups) for groups in data["hooks"].values()], [1, 1, 1])
        self.assertIn("/new/place", json.dumps(data))

    def test_uninstall_removes_only_greenlights_entries_and_the_file_if_that_leaves_nothing(self):
        self.home.mkdir()
        self.file.write_text(json.dumps({"hooks": {"PreToolUse": [{"hooks": [{"type": "command", "command": "mine.sh"}]}]}}),
                             encoding="utf-8")
        self.install("--apply")
        self.assertEqual(self.install("--uninstall")[0], 0)
        data = json.loads(self.file.read_text(encoding="utf-8"))
        self.assertEqual(data, {"hooks": {"PreToolUse": [{"hooks": [{"type": "command", "command": "mine.sh"}]}]}})
        self.file.unlink()
        self.install("--apply")
        self.install("--uninstall")
        self.assertFalse(self.file.exists())
        self.assertIn("nothing of greenlight's", self.install("--uninstall")[1])

    def test_a_file_that_is_not_json_is_refused_and_left_alone(self):
        self.home.mkdir()
        self.file.write_text("{broken", encoding="utf-8")
        code, _, err = self.install("--apply")
        self.assertEqual(code, 2)
        self.assertIn("not valid JSON", err)
        self.assertEqual(self.file.read_text(encoding="utf-8"), "{broken")

    def test_apply_and_uninstall_together_are_refused(self):
        self.assertEqual(self.install("--apply", "--uninstall")[0], 2)

    def test_the_project_file_can_be_chosen(self):
        project = Path(self.dir.name).resolve() / "proj"
        (project / ".bdd").mkdir(parents=True)
        here = os.getcwd()
        os.chdir(project)
        try:
            self.assertEqual(self.install("--apply", "--project")[0], 0)
        finally:
            os.chdir(here)
        self.assertTrue(installhooks.installed(project / ".codex" / "hooks.json"))
        self.assertFalse(self.file.exists())

    def test_the_command_is_registered_and_the_hook_command_exists(self):
        self.assertIn("install-hooks", cli.COMMANDS)
        self.assertIn("codex-hook", cli.COMMANDS)
        self.assertTrue(installhooks.command().endswith('bdd" codex-hook'))


class DoctorTest(unittest.TestCase):
    def test_no_codex_no_check(self):
        self.assertIsNone(doctor.check_codex_hooks(False, False, False))

    def test_installed_and_seen_is_ok_and_the_rest_says_soft(self):
        self.assertEqual(doctor.check_codex_hooks(True, True, True).status, "ok")
        waiting = doctor.check_codex_hooks(True, True, False)
        self.assertEqual(waiting.status, "warn")
        self.assertIn("soft", waiting.fix)
        missing = doctor.check_codex_hooks(True, False, False)
        self.assertEqual(missing.status, "warn")
        self.assertIn("bdd install-hooks codex", missing.fix)


if __name__ == "__main__":
    unittest.main()
