import contextlib
import hashlib
import io
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from bddlib import cli, gates, guard, mutation, redrecord, runner, state
from bddlib import config as cfg
from bddlib.errors import UsageError

from tests.helpers import ProjectCase
from tests.test_redrecord import GIT, run_git

FIXTURES = Path(__file__).parent / "fixtures"
TABLE = """
[adapters.mutation]
command = '{python} fake_mutator.py --report {out} {files}'
threshold = 80
extensions = [".py"]
"""


def mutants(killed: int, survived: int, **more: int) -> dict:
    return {"FAKE_MUTANTS": json.dumps({"killed": killed, "survived": survived, **more})}


class RulesTest(ProjectCase):
    def test_the_table_is_optional_and_read_when_present(self):
        self.assertIsNone(cfg.load(self.root).mutation)
        self.config(tail=TABLE)
        rules = cfg.load(self.root).mutation
        self.assertEqual((rules.adapter, rules.threshold, rules.timeout, rules.extensions), ("x", 80.0, 1800, (".py",)))

    def test_bad_tables_are_config_errors(self):
        for table, message in (("command = ''\n", "needs command"),
                               ("command = 'tool {out}'\n", "{files} as a word of its own"),
                               ("command = 'tool {files}'\n", "{out}"),
                               ("command = 'tool x{files} {out}'\n", "{files} as a word of its own"),
                               ("command = 'tool {files} {out}'\nthreshold = 0\n", "threshold"),
                               ("command = 'tool {files} {out}'\nthreshold = 101\n", "threshold"),
                               ("command = 'tool {files} {out}'\ntimeout = 0\n", "timeout"),
                               ("command = 'tool {files} {out}'\nextensions = ['py']\n", "extensions")):
            with self.subTest(table=table):
                self.config(tail="[adapters.mutation]\n" + table)
                with self.assertRaises(cfg.ConfigError) as cm:
                    cfg.load(self.root)
                self.assertIn(message, str(cm.exception))


class CommandTest(ProjectCase):
    def test_files_become_words_and_nothing_else_can_add_words(self):
        rules = cfg.MutationRules("x", "{python} tool {files} --report {out} --root={root}")
        words = mutation.build_command(rules, self.root, Path("o.json"), ["src/a b.py", "src/c;rm.py"])
        self.assertEqual(words[2:4], ["src/a b.py", "src/c;rm.py"])
        self.assertEqual(words[4:], ["--report", "o.json", f"--root={self.root}"])


class ReportTest(unittest.TestCase):
    def parse(self, text: str):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "r.json"
            path.write_text(text, encoding="utf-8")
            return mutation.parse_report(path)

    def test_counts_are_read(self):
        self.assertEqual(self.parse('{"killed": 8, "survived": 2, "timeout": 1}'),
                         {"killed": 8, "survived": 2, "timeout": 1, "suspicious": 0, "skipped": 0})

    def test_anything_else_is_refused(self):
        for text in ("not json", "[]", '{"killed": 1}', '{"killed": true, "survived": 0}', '{"killed": -1, "survived": 0}',
                     '{"killed": 1, "survived": 0, "timeout": "x"}'):
            with self.subTest(text=text), self.assertRaises(UsageError):
                self.parse(text)

    def test_the_verdict(self):
        def counts(killed: int, survived: int) -> dict:
            return {"killed": killed, "survived": survived}

        rules = cfg.MutationRules("x", "t {files} {out}", 80.0, 1800, (".py",))
        self.assertEqual(mutation.verdict(rules, counts(8, 2), 2, 2, 0)[:2], (80.0, True))
        self.assertEqual(mutation.verdict(rules, counts(7, 3), 2, 2, 0)[:2], (70.0, False))
        self.assertFalse(mutation.verdict(rules, counts(0, 0), 2, 2, 0)[1])       # no mutants prove nothing
        self.assertFalse(mutation.verdict(rules, counts(10, 0), 2, 2, 1)[1])      # a tool that did not finish cleanly
        self.assertEqual(mutation.verdict(rules, None, 0, 0, None)[1], True)      # nothing changed, nothing to mutate
        score, passed, note = mutation.verdict(rules, None, 3, 0, None)           # changed, but nothing was selected
        self.assertEqual((score, passed), (None, False))
        self.assertIn("covered nothing", note)


@unittest.skipUnless(GIT, "needs git")
class GitProjectCase(ProjectCase):
    """A project under git whose red was recorded at the first commit, with the mutation table configured."""

    def setUp(self):
        super().setUp()
        shutil.copy(FIXTURES / "fake_mutator.py", self.root / "fake_mutator.py")
        self.write(".gitignore", ".bdd/.runs/\n")
        self.write("src/app.py", "def total(x):\n    return x\n")
        self.write("src/notes.txt", "n\n")
        self.config(tail=TABLE)
        run_git(self.root, "init", "-q")
        run_git(self.root, "add", "-A")
        run_git(self.root, "commit", "-q", "-m", "initial")
        commit = redrecord.git(self.root, "rev-parse", "HEAD").strip()
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.files_given = Path(self.scratch.name) / "files-given.json"
        state.update(self.feature_dir, lambda d: d.update(red={"commit": commit, "dirty": False, "source_hash": "", "at": "now"}))

    def write_implementation(self):
        self.write("src/app.py", "def total(x):\n    return x * 0.9 if x >= 1000 else x\n")
        self.write("src/notes.txt", "changed\n")
        self.write("src/new.py", "X = 1\n")

    def mutate(self, *args: str, **env: str) -> tuple[int, str, str]:
        out, err, here = io.StringIO(), io.StringIO(), os.getcwd()
        os.chdir(self.root)
        try:
            variables = {"FAKE_FILES_OUT": str(self.files_given), **env}
            with mock.patch.dict(os.environ, variables), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = cli.main(["mutate", "FEAT-007", *args])
        finally:
            os.chdir(here)
        return code, out.getvalue(), err.getvalue()

class RunTest(GitProjectCase):
    def test_only_the_changed_production_files_with_the_right_suffix_are_mutated(self):
        self.write_implementation()
        code, out, _ = self.mutate(**mutants(9, 1))
        self.assertEqual(code, 0, out)
        record = json.loads(mutation.result_path(self.root, "FEAT-007").read_text(encoding="utf-8"))
        self.assertEqual(record["files"], ["src/app.py", "src/new.py"])
        self.assertEqual((record["score"], record["passed"]), (90.0, True))
        self.assertEqual(record["changed"], ["src/app.py", "src/new.py", "src/notes.txt"])
        self.assertEqual(json.loads(self.files_given.read_text(encoding="utf-8")), ["src/app.py", "src/new.py"])
        self.assertIn("passed: 90% killed", out)

    def test_the_report_is_written_in_a_fresh_private_folder_outside_the_project(self):
        self.write_implementation()
        seen = Path(self.scratch.name) / "seen.json"
        self.mutate(FAKE_SEE_REPORT_FIRST=str(seen), **mutants(9, 1))
        fact = json.loads(seen.read_text(encoding="utf-8"))
        self.assertFalse(fact["existed"])
        self.assertNotIn(self.root, Path(fact["path"]).parents)
        self.assertFalse(Path(fact["path"]).parent.exists())                      # removed afterwards

    def test_the_record_names_the_command_the_exit_status_and_the_hash_of_the_report(self):
        self.write_implementation()
        self.mutate(**mutants(9, 1))
        record = json.loads(mutation.result_path(self.root, "FEAT-007").read_text(encoding="utf-8"))
        self.assertEqual(record["command"][1], "fake_mutator.py")
        self.assertEqual(record["exit"], 0)
        self.assertEqual(record["report_sha256"], hashlib.sha256(mutants(9, 1)["FAKE_MUTANTS"].encode("utf-8")).hexdigest())

    def test_a_tool_that_exits_non_zero_fails_whatever_its_report_says(self):
        self.write_implementation()
        code, out, _ = self.mutate(FAKE_EXIT="1", **mutants(10, 0))
        self.assertEqual(code, 1)
        self.assertIn("exited with status 1", out)

    def test_changed_files_that_match_no_extension_are_a_failure_not_a_pass(self):
        self.config(tail=TABLE.replace('[".py"]', '[".go"]'))
        self.write_implementation()
        code, out, _ = self.mutate(**mutants(10, 0))
        self.assertEqual(code, 1)
        self.assertIn("covered nothing", out)
        self.assertFalse(self.files_given.exists())                               # the tool was never started
        self.assertEqual(self.mutate("--check")[0], 1)

    def test_survivors_below_the_threshold_fail_the_check(self):
        self.write_implementation()
        code, out, _ = self.mutate(**mutants(5, 5))
        self.assertEqual(code, 1)
        self.assertIn("FAILED", out)
        self.assertIn("5 of 10 mutants survived", out)

    def test_a_run_that_changed_nothing_has_nothing_to_mutate(self):
        code, out, _ = self.mutate(**mutants(0, 0))
        self.assertEqual(code, 0, out)
        self.assertIn("nothing to mutate", out)
        self.assertFalse(self.files_given.exists())

    def test_a_recorded_commit_that_is_not_a_commit_id_is_refused(self):
        state.update(self.feature_dir, lambda d: d.update(red={"commit": "--output=x", "dirty": False}))
        code, _, err = self.mutate(**mutants(1, 0))
        self.assertEqual((code, "not a commit id" in err), (2, True))

    def test_a_tool_that_writes_no_report_is_a_usage_problem(self):
        self.write_implementation()
        code, _, err = self.mutate(FAKE_NO_REPORT="1", **mutants(1, 0))
        self.assertEqual(code, 2)
        self.assertIn("wrote no report", err)

    def test_it_needs_the_table_and_a_recorded_red(self):
        self.write_implementation()
        state.update(self.feature_dir, lambda d: d.update(red=None))
        code, _, err = self.mutate(**mutants(1, 0))
        self.assertEqual((code, "no red was recorded" in err), (2, True))
        self.config()
        code, _, err = self.mutate(**mutants(1, 0))
        self.assertEqual((code, "not configured" in err), (2, True))

    def test_check_shows_the_record_and_goes_stale_when_the_source_changes(self):
        self.write_implementation()
        self.mutate(**mutants(9, 1))
        self.assertEqual(self.mutate("--check")[0], 0)
        self.write("src/app.py", "def total(x):\n    return 0\n")
        code, _, err = self.mutate("--check")
        self.assertEqual((code, "out of date" in err), (1, True))


class VerifyGateTest(GitProjectCase):
    def reasons(self) -> list[str]:
        return mutation.problems(self.root, "FEAT-007")

    def test_without_the_table_the_gate_asks_for_nothing(self):
        self.config()
        self.assertEqual(self.reasons(), [])

    def test_with_the_table_the_gate_needs_a_current_passing_result(self):
        self.write_implementation()
        self.assertIn("has not been run", self.reasons()[0])
        self.mutate(**mutants(5, 5))
        self.assertIn("mutation check failed", self.reasons()[0])
        self.mutate(**mutants(9, 1))
        self.assertEqual(self.reasons(), [])
        self.write("steps/steps.py", "def then_ok():\n    assert 1 == 1\n")                # a test changed after the check
        self.assertIn("out of date", self.reasons()[0])

    def test_the_gate_function_includes_it(self):
        self.write_implementation()
        self.walk_to("implement")
        with self.assertRaises(UsageError) as cm:
            self.gate("verify")
        self.assertIn("mutation check", str(cm.exception))


class GuardTest(ProjectCase):
    def test_an_agent_cannot_write_the_result(self):
        path = self.root / ".bdd" / ".runs" / "FEAT-007" / "mutation.json"
        reason = guard.evaluate({"tool_name": "Write", "cwd": str(self.root), "tool_input": {"file_path": str(path)}})
        self.assertIn("managed by the bdd command line", reason)


if __name__ == "__main__":
    unittest.main()
