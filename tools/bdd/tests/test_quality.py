import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from bddlib import cli, doctor, gates, guard, initcmd, quality, redrecord, runner, state, tripwire
from bddlib import config as cfg
from bddlib.errors import UsageError

from tests.helpers import ProjectCase
from tests.test_redrecord import run_git

PASSING = "import sys; sys.exit(0)"
FAILING = "import sys; print('E501 line too long'); sys.exit(3)"


def command(code: str) -> str:
    """A TOML line that runs a bit of Python as a check (single quotes only inside the code)."""
    return 'command = "{python} -c \\"' + code + '\\""'


TABLE = f"""
[adapters.quality.format]
{command(PASSING)}

[adapters.quality.lint]
{command(PASSING)}
timeout = 60
"""


def table(lint: str = PASSING) -> str:
    return f"""
[adapters.quality.format]
{command(PASSING)}

[adapters.quality.lint]
{command(lint)}
"""


class RulesTest(ProjectCase):
    def test_the_table_is_optional_and_read_in_order_when_present(self):
        self.assertIsNone(cfg.load(self.root).quality)
        self.config(tail=TABLE)
        rules = cfg.load(self.root).quality
        self.assertEqual([(c.name, c.timeout) for c in rules.checks], [("format", 600), ("lint", 60)])
        self.assertEqual(rules.adapter, "x")

    def test_bad_tables_are_config_errors(self):
        for body, message in (("[adapters.quality]\n", "at least one named check"),
                              ("[adapters.quality.Lint]\ncommand = 'x'\n", "named in lower case"),
                              ("[adapters.quality.lint]\ncommand = ''\n", "needs command"),
                              ("[adapters.quality.lint]\ncommand = 3\n", "needs command"),
                              ("[adapters.quality.lint]\ncommand = 'x'\ntimeout = 0\n", "timeout"),
                              ("[adapters.quality]\nlint = 'x'\n", "named in lower case")):
            with self.subTest(body=body):
                self.config(tail=body)
                with self.assertRaises(cfg.ConfigError) as cm:
                    cfg.load(self.root)
                self.assertIn(message, str(cm.exception))


class CommandTest(ProjectCase):
    def test_placeholders_fill_words_and_cannot_add_words(self):
        check = cfg.QualityCheck("lint", "{python} tool --root={root} {project_python}")
        words = quality.build_command(check, self.root)
        self.assertEqual(len(words), 4)
        self.assertEqual(words[2], f"--root={self.root}")

    def test_a_root_with_spaces_and_shell_characters_stays_one_word(self):
        check = cfg.QualityCheck("lint", "tool {root}")
        odd = Path("C:/a b; rm -rf") / "project"
        with mock.patch.object(quality.runner, "project_python", return_value="python"):
            self.assertEqual(quality.build_command(check, odd), ["tool", str(odd)])


class GitProjectCase(ProjectCase):
    """A project under git with the quality table configured."""

    def setUp(self):
        super().setUp()
        self.write(".gitignore", ".bdd/.runs/\n")
        self.write("src/app.py", "def total(x):\n    return x\n")
        self.config(tail=TABLE)
        run_git(self.root, "init", "-q")
        run_git(self.root, "add", "-A")
        run_git(self.root, "commit", "-q", "-m", "initial")

    def check(self, *args: str) -> tuple[int, str, str]:
        out, err, here = io.StringIO(), io.StringIO(), os.getcwd()
        os.chdir(self.root)
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = cli.main(["check", "FEAT-007", *args])
        finally:
            os.chdir(here)
        return code, out.getvalue(), err.getvalue()

    def record(self) -> dict:
        return json.loads(quality.result_path(self.root, "FEAT-007").read_text(encoding="utf-8"))


class RunTest(GitProjectCase):
    def test_every_check_runs_and_the_result_is_recorded(self):
        code, out, _ = self.check()
        self.assertEqual(code, 0, out)
        self.assertIn("quality checks passed", out)
        record = self.record()
        self.assertTrue(record["passed"])
        self.assertEqual([(c["name"], c["exit"]) for c in record["checks"]], [("format", 0), ("lint", 0)])
        for key in ("source_hash", "inputs", "standards", "interpreter"):
            self.assertIn(key, record)

    def test_the_exit_status_is_the_verdict_and_the_tool_output_is_shown(self):
        self.config(tail=table(FAILING))
        code, out, _ = self.check()
        self.assertEqual(code, 1)
        self.assertIn("FAIL lint: exit 3", out)
        self.assertIn("E501 line too long", out)
        self.assertIn("ok   format", out)
        self.assertFalse(self.record()["passed"])

    def test_a_tool_that_is_not_installed_is_a_failed_check_with_the_reason(self):
        self.config(tail="[adapters.quality.lint]\ncommand = 'no-such-linter-xyz {root}'\n")
        code, out, _ = self.check()
        self.assertEqual(code, 1)
        self.assertIn("not on PATH", out)
        self.assertFalse(self.record()["checks"][0]["passed"])

    def test_a_tool_that_is_a_script_shim_on_the_path_starts_without_a_shell(self):
        shim = Path(self.root) / ("shimtool.cmd" if os.name == "nt" else "shimtool")
        shim.write_text("@exit /b 0\r\n" if os.name == "nt" else "#!/bin/sh\nexit 0\n", encoding="utf-8", newline="")
        shim.chmod(0o755)
        self.config(tail="[adapters.quality.lint]\ncommand = 'shimtool'\n")
        with mock.patch.dict(os.environ, {"PATH": str(self.root) + os.pathsep + os.environ["PATH"]}):
            self.assertEqual(self.check()[0], 0)

    def test_a_check_that_takes_too_long_fails(self):
        self.config(tail="[adapters.quality.lint]\n" + command("import time; time.sleep(30)") + "\ntimeout = 1\n")
        code, out, _ = self.check()
        self.assertEqual(code, 1)
        self.assertIn("took longer than 1 s", out)

    def test_variables_that_steer_a_program_do_not_reach_the_tools(self):
        probe = "import os, sys; sys.exit(7 if 'PYTHONPATH' in os.environ else 0)"
        self.config(tail=table(probe))
        with mock.patch.dict(os.environ, {"PYTHONPATH": "/elsewhere"}):
            self.assertEqual(self.check()[0], 0)

    def test_it_needs_the_table_and_a_feature(self):
        self.config()
        code, _, err = self.check()
        self.assertEqual((code, "no [adapters.quality.NAME] table" in err), (2, True))
        self.config(tail=TABLE)
        out, here = io.StringIO(), os.getcwd()
        os.chdir(self.root)
        try:
            with contextlib.redirect_stderr(out):
                self.assertEqual(cli.main(["check", "FEAT-999"]), 2)
        finally:
            os.chdir(here)

    def test_check_shows_the_record_and_goes_stale_when_the_source_changes(self):
        self.check()
        self.assertEqual(self.check("--check")[0], 0)
        self.write("src/app.py", "def total(x):\n    return x * 2\n")
        code, _, err = self.check("--check")
        self.assertEqual(code, 1)
        self.assertIn("out of date", err)


class GateProblemsTest(GitProjectCase):
    def reasons(self) -> list[str]:
        return quality.problems(self.root, "FEAT-007")

    def test_without_the_table_nothing_is_asked(self):
        self.config()
        self.assertEqual(self.reasons(), [])

    def test_a_current_passing_result_is_needed(self):
        self.assertIn("have not been run", self.reasons()[0])
        self.config(tail=table(FAILING))
        self.check()
        self.assertIn("quality check(s) failed: lint", self.reasons()[0])
        self.config(tail=table(PASSING))
        self.check()
        self.assertEqual(self.reasons(), [])

    def test_a_change_to_the_source_the_tests_or_the_standards_makes_it_stale(self):
        self.check()
        self.write("src/app.py", "def total(x):\n    return x + 1\n")
        self.assertIn("out of date", self.reasons()[0])
        self.check()
        self.write("steps/steps.py", "def then_ok():\n    assert 1 == 1\n")
        self.assertIn("out of date", self.reasons()[0])
        self.check()
        self.write(".bdd/standards.md", "# Engineering standards\n")
        self.assertIn("out of date", self.reasons()[0])

    def test_changing_which_checks_are_configured_needs_a_new_run(self):
        self.check()
        self.config(tail=TABLE + "\n[adapters.quality.typecheck]\ncommand = 'x'\n")
        self.assertIn("checks changed", self.reasons()[0])

    def test_a_damaged_record_is_a_problem_not_a_crash(self):
        self.check()
        quality.result_path(self.root, "FEAT-007").write_text("[]", encoding="utf-8")
        self.assertIn("quality result", self.reasons()[0])


class GateTest(GitProjectCase):
    def test_the_implement_and_verify_gates_refuse_without_a_current_result(self):
        self.walk_to("tasks")
        with self.assertRaises(UsageError) as cm:
            self.gate("implement")
        self.assertIn("have not been run", str(cm.exception))
        self.check()
        self.assertEqual(self.gate("implement")["gates"]["implement"]["result"], "pass")
        self.write("src/app.py", "def total(x):\n    return x * 3\n")
        with self.assertRaises(UsageError) as cm:
            self.gate("verify")
        self.assertIn("quality result is out of date", str(cm.exception))

    def test_an_adopted_feature_is_not_held_to_it(self):
        data = state.load(self.feature_dir)
        data["kind"] = "adopt"
        reasons = gates.gate_problems(self.root, self.feature_dir, data, "implement")
        self.assertFalse(any("quality" in r for r in reasons))
        data["kind"] = "feature"
        reasons = gates.gate_problems(self.root, self.feature_dir, data, "implement")
        self.assertTrue(any("quality" in r for r in reasons))


class StandardsFileTest(ProjectCase):
    def write_as(self, agent: str | None, tool: str = "Write") -> str | None:
        payload = {"tool_name": tool, "cwd": str(self.root),
                   "tool_input": {"file_path": str(self.root / ".bdd" / "standards.md")}}
        if agent:
            payload["agent_type"] = f"greenlight:{agent}"
        return guard.evaluate(payload)

    def test_no_agent_and_not_the_orchestrator_may_write_it(self):
        for agent in (None, "implementer", "step-engineer", "system-analyst", "spec-auditor"):
            with self.subTest(agent=agent):
                self.assertIn("managed by the bdd command line", self.write_as(agent))

    def test_a_shell_command_naming_it_is_refused(self):
        reason = guard.evaluate({"tool_name": "Bash", "cwd": str(self.root),
                                 "tool_input": {"command": "echo 'Status: APPROVED' > .bdd/standards.md"}})
        self.assertIn("managed by", reason)

    def test_a_shell_command_that_changes_directory_first_is_refused(self):
        for name in ("standards.md", "config.toml"):
            with self.subTest(name=name):
                reason = guard.evaluate({"tool_name": "Bash", "cwd": str(self.root),
                                         "tool_input": {"command": f"cd .bdd && echo x > {name}"}})
                self.assertIn("managed by", reason)

    def bash(self, command: str, cwd: Path | None = None) -> str | None:
        return guard.evaluate({"tool_name": "Bash", "cwd": str(cwd or self.root), "tool_input": {"command": command}})

    def test_a_call_that_already_runs_inside_bdd_names_the_files_by_their_bare_name(self):
        inside = self.root / ".bdd"
        for name in ("standards.md", "config.toml"):
            with self.subTest(name=name):
                self.assertIn("managed by", self.bash(f"echo x > {name}", inside))
        self.assertIsNone(self.bash("ls", inside))                                       # reading is fine
        self.assertIn("managed by", self.bash("echo x > standards.md", self.root / "src"))     # a bare name fails closed
        self.assertIn("managed by", self.bash("echo x > ./standards.md", self.root / "src"))
        self.assertIn("managed by", self.bash("echo x > ../standards.md", self.root / "src"))

    def test_a_standards_file_in_a_folder_that_is_not_bdd_is_a_different_file(self):
        for command in ("echo x > docs/standards.md", "echo x > src/*/standards.md", "echo x > ../docs/standards.md",
                        "echo x > .git*/standards.md"):
            with self.subTest(command=command):
                self.assertIsNone(self.bash(command))
        for command in ("echo x > .bdd/standards.md", "echo x > docs/../.bdd/standards.md", "echo x > .b*/standards.md"):
            with self.subTest(command=command):
                self.assertIn("managed by", self.bash(command))

    def test_a_glob_that_can_expand_to_bdd_is_treated_as_naming_it(self):
        for command in ("echo x > .b*/standards.md", "echo x > .?dd/config.toml", "echo x > .*/standards.md",
                        "cp evil .bd[d]/standards.md"):
            with self.subTest(command=command):
                self.assertIsNotNone(self.bash(command))               # `.*` also reaches .claude: either message blocks
        self.assertIn("managed by", self.bash("echo x > .b*/standards.md"))

    def test_redirections_assignments_and_character_classes_do_not_hide_a_glob(self):
        for command in ("echo x>.b*/standards.md", "echo x 2>.?dd/config.toml", "F=.b*/config.toml; echo x > $F",
                        "echo x > .[^a]dd/config.toml", "echo x > .[!a]dd/standards.md"):
            with self.subTest(command=command):
                self.assertIn("managed by", self.bash(command))

    def test_a_glob_without_a_dot_reaches_bdd_only_when_it_has_a_literal_character(self):
        self.assertIn("managed by", self.bash("echo x > b*/config.toml"))            # dotglob
        self.assertIn("managed by", self.bash("echo x > .bdd/.ru?s/latest.json"))
        self.assertIsNone(self.bash("rm -rf *"))                                      # a bare * is everywhere: not a target
        self.assertIsNone(self.bash("cp -r * ../backup"))

    def test_the_managed_folders_are_matched_as_whole_segments_wherever_the_command_starts(self):
        data = self.root / ".bdd"
        for command, cwd in (("cd .bdd/.runs && echo {} > latest.json", None), ("echo {} > latest.json", data / ".runs"),
                             ("echo {} > .bdd/.ru*/latest.json", None), ("echo {} > .bdd/.integrity", None),
                             ("cd .integrity && echo {} > violations.json", data), ("echo x > .enforcement", data)):
            with self.subTest(command=command):
                self.assertIn("managed by", self.bash(command, cwd))
        self.assertIsNone(self.bash("cd src && echo {} > latest.json"))
        self.assertIsNone(self.bash("echo {} > not.runs/latest.json"))

    def test_the_tripwire_reports_a_change_by_any_route_and_the_gates_see_it(self):
        self.write(".bdd/standards.md", "# Engineering standards\n")
        with tempfile.TemporaryDirectory() as claude_dir, mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": claude_dir}):
            tripwire.accept(self.root, None)
            self.assertEqual(tripwire.check(self.root, None), [])
            (self.root / ".bdd" / "standards.md").write_text("# Changed\n", encoding="utf-8", newline="\n")
            found = tripwire.check(self.root, None, "Bash")
        self.assertEqual([(f["kind"], Path(f["path"]).name) for f in found], [("changed", "standards.md")])
        self.assertEqual([Path(v["path"]).name for v in tripwire.open_violations(self.root)], ["standards.md"])

    def test_a_config_file_of_another_folder_is_not_mistaken_for_it(self):
        reason = guard.evaluate({"tool_name": "Bash", "cwd": str(self.root),
                                 "tool_input": {"command": "cd src && echo x > config.toml"}})
        self.assertIsNone(reason)

    def test_the_tripwire_watches_it(self):
        self.write(".bdd/standards.md", "# Engineering standards\n")
        watched = {p.name for p in tripwire.watched_files(self.root, None)}
        self.assertIn("standards.md", watched)


class DoctorTest(ProjectCase):
    def test_a_missing_file_is_reported_and_an_existing_one_is_in_force_without_approval(self):
        self.assertEqual(doctor.check_standards(self.root).status, "warn")
        self.assertIn("does not exist", doctor.check_standards(self.root).detail)
        self.write(".bdd/standards.md", "# Engineering standards\n")
        check = doctor.check_standards(self.root)
        self.assertEqual((check.status, check.detail), ("ok", ".bdd/standards.md is in force"))

    def test_a_placeholder_left_means_what_the_project_already_uses(self):
        self.write(".bdd/standards.md", "- Formatter: <ruff format, prettier or gofmt>\n")
        check = doctor.check_standards(self.root)
        self.assertEqual(check.status, "ok")
        self.assertIn("<ruff format, prettier or gofmt>", check.detail)
        self.assertIn("already uses", check.detail)

    def test_comments_code_blocks_and_generic_types_are_not_placeholders(self):
        text = ("<!-- fill in <the tool> here -->\n- Return `List<Order>` or `Map<K,V>`, never `<br>`.\n"
                "```\nsrc/<feature>/api/   # one folder per feature\n```\n")
        self.write(".bdd/standards.md", text)
        self.assertEqual(doctor.check_standards(self.root).detail, ".bdd/standards.md is in force")

    def test_the_template_has_no_status_line_and_leaves_the_project_specific_parts_open(self):
        template = (Path(__file__).resolve().parents[3] / "templates" / "standards.md").read_text(encoding="utf-8")
        self.assertFalse([line for line in template.splitlines() if line.startswith("Status:")])
        self.assertTrue(doctor.unfilled_placeholders(template))
        self.assertTrue(template.endswith("\n"))


class InitTest(unittest.TestCase):
    def test_a_new_project_gets_the_template_and_an_existing_one_can_add_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            created = initcmd.write_project(root, "guided", None)
            self.assertIn(".bdd/standards.md", created)
            text = (root / ".bdd" / "standards.md").read_text(encoding="utf-8")
            self.assertEqual(text, (Path(__file__).resolve().parents[3] / "templates" / "standards.md").read_text(encoding="utf-8"))
            (root / ".bdd" / "standards.md").write_text("mine\n", encoding="utf-8")
            self.assertIsNone(initcmd.add_standards(root))                              # never overwritten
            self.assertEqual((root / ".bdd" / "standards.md").read_text(encoding="utf-8"), "mine\n")
            (root / ".bdd" / "standards.md").unlink()
            self.assertEqual(initcmd.add_standards(root), ".bdd/standards.md")

    def test_the_flag_needs_a_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            here = os.getcwd()
            os.chdir(tmp)
            try:
                with contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(cli.main(["init", "--standards"]), 2)
            finally:
                os.chdir(here)


class ProgramResolutionTest(unittest.TestCase):
    """A bare tool name is found on PATH only; a file planted in the project cannot stand in for the tool."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name).resolve() / "project"
        self.tools = Path(self.dir.name).resolve() / "tools"
        self.root.mkdir()
        self.tools.mkdir()
        self.suffixes = runner.executable_suffixes()

    def make(self, folder: Path, name: str) -> Path:
        path = folder / (name + (".exe" if self.suffixes else ""))
        path.write_text("x", encoding="utf-8")
        path.chmod(0o755)
        return path

    def test_a_bare_name_is_found_on_the_search_path(self):
        tool = self.make(self.tools, "mytool")
        self.assertEqual(runner.resolve_program("mytool", self.root, str(self.tools), self.suffixes), str(tool))

    def test_a_file_planted_in_the_project_is_not_found_by_its_bare_name(self):
        self.make(self.root, "ruff")
        self.assertIsNone(runner.resolve_program("ruff", self.root, str(self.tools), self.suffixes))
        here = os.getcwd()
        os.chdir(self.root)
        try:
            with mock.patch.dict(os.environ, {"PATH": str(self.tools)}), self.assertRaises(UsageError) as cm:
                runner.execute(["ruff", "check"], self.root, 30)
        finally:
            os.chdir(here)
        self.assertIn("not on PATH", str(cm.exception))

    def test_relative_and_empty_search_path_entries_are_ignored(self):
        self.make(self.root, "ruff")
        search = os.pathsep.join(["", ".", "project", str(self.root.parent / "nothing")])
        here = os.getcwd()
        os.chdir(self.root.parent)
        try:
            self.assertIsNone(runner.resolve_program("ruff", self.root, search, self.suffixes))
        finally:
            os.chdir(here)

    def test_a_word_with_a_separator_is_a_path_relative_to_the_project(self):
        tool = self.make(self.root, "gradlew")
        found = runner.resolve_program("./gradlew", self.root, "", self.suffixes)
        self.assertEqual(Path(found), tool)
        self.assertIsNone(runner.resolve_program("./missing", self.root, "", self.suffixes))

    def test_pathext_decides_what_runs_on_windows(self):
        self.assertEqual(runner.executable_suffixes({"PATHEXT": ".EXE;.BAT;nonsense"}) if os.name == "nt" else (),
                         (".exe", ".bat") if os.name == "nt" else ())


class BatchFileTest(unittest.TestCase):
    def test_arguments_with_shell_syntax_are_refused_for_a_batch_file(self):
        for argument in ('a"b', "a&b", "a|b", "a<b", "a>b", "a^b", "%PATH%", "a!b", "a\nb", "a\rb"):
            with self.subTest(argument=argument):
                self.assertIn("batch file", runner.batch_problem("C:\\tools\\npm.cmd", ["install", argument]))

    def test_plain_arguments_and_real_executables_are_fine(self):
        self.assertIsNone(runner.batch_problem("C:\\tools\\gradlew.bat", ["build", "--info", "-Pname=value"]))
        self.assertIsNone(runner.batch_problem("C:\\tools\\ruff.exe", ['a"b', "a&b"]))
        self.assertIsNone(runner.batch_problem("/usr/bin/ruff", ["a&b"]))

    def test_the_check_applies_before_anything_is_started(self):
        with tempfile.TemporaryDirectory() as tmp:
            shim = Path(tmp) / "tool.cmd"
            shim.write_text("@exit /b 0\r\n", encoding="utf-8")
            with mock.patch.object(runner, "resolve_program", return_value=str(shim)), \
                    self.assertRaises(UsageError) as cm:
                runner.execute(["tool", "a&b"], Path(tmp), 30)
            self.assertIn("batch file", str(cm.exception))


class GuardResultTest(ProjectCase):
    def test_an_agent_cannot_write_the_result(self):
        path = self.root / ".bdd" / ".runs" / "FEAT-007" / "quality.json"
        reason = guard.evaluate({"tool_name": "Write", "cwd": str(self.root), "tool_input": {"file_path": str(path)}})
        self.assertIn("managed by the bdd command line", reason)


if __name__ == "__main__":
    unittest.main()
