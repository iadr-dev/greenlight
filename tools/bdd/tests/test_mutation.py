import contextlib
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

        self.assertEqual(mutation.verdict(counts(8, 2), 80)[:2], (80.0, True))
        self.assertEqual(mutation.verdict(counts(7, 3), 80)[:2], (70.0, False))
        self.assertFalse(mutation.verdict(counts(0, 0), 80)[1])                   # no mutants prove nothing
        self.assertEqual(mutation.verdict(None, 80)[1:2], (True,))                # nothing changed, nothing to mutate


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
        state.update(self.feature_dir, lambda d: d.update(red={"commit": commit, "dirty": False, "source_hash": "", "at": "now"}))

    def implement(self):
        self.write("src/app.py", "def total(x):\n    return x * 0.9 if x >= 1000 else x\n")
        self.write("src/notes.txt", "changed\n")
        self.write("src/new.py", "X = 1\n")

    def mutate(self, *args: str, **env: str) -> tuple[int, str, str]:
        out, err, here = io.StringIO(), io.StringIO(), os.getcwd()
        os.chdir(self.root)
        try:
            with mock.patch.dict(os.environ, env), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = cli.main(["mutate", "FEAT-007", *args])
        finally:
            os.chdir(here)
        return code, out.getvalue(), err.getvalue()



class RunTest(GitProjectCase):
    def test_only_the_changed_production_files_with_the_right_suffix_are_mutated(self):
        self.implement()
        code, out, _ = self.mutate(**mutants(9, 1))
        self.assertEqual(code, 0, out)
        record = json.loads(mutation.result_path(self.root, "FEAT-007").read_text(encoding="utf-8"))
        self.assertEqual(record["files"], ["src/app.py", "src/new.py"])
        self.assertEqual((record["score"], record["passed"]), (90.0, True))
        given = json.loads((runner.runs_dir(self.root, "FEAT-007") / "mutation-report.json.files").read_text(encoding="utf-8"))
        self.assertEqual(given, ["src/app.py", "src/new.py"])
        self.assertIn("passed: 90% killed", out)

    def test_survivors_below_the_threshold_fail_the_check(self):
        self.implement()
        code, out, _ = self.mutate(**mutants(5, 5))
        self.assertEqual(code, 1)
        self.assertIn("FAILED", out)
        self.assertIn("5 of 10 mutants survived", out)

    def test_a_run_that_changed_nothing_has_nothing_to_mutate(self):
        code, out, _ = self.mutate(**mutants(0, 0))
        self.assertEqual(code, 0, out)
        self.assertIn("nothing to mutate", out)

    def test_a_tool_that_writes_no_report_is_a_usage_problem(self):
        self.implement()
        code, _, err = self.mutate(FAKE_NO_REPORT="1", **mutants(1, 0))
        self.assertEqual(code, 2)
        self.assertIn("wrote no report", err)

    def test_it_needs_the_table_and_a_recorded_red(self):
        self.implement()
        state.update(self.feature_dir, lambda d: d.update(red=None))
        code, _, err = self.mutate(**mutants(1, 0))
        self.assertEqual((code, "no red was recorded" in err), (2, True))
        self.config()
        code, _, err = self.mutate(**mutants(1, 0))
        self.assertEqual((code, "not configured" in err), (2, True))

    def test_check_shows_the_record_and_goes_stale_when_the_source_changes(self):
        self.implement()
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
        self.implement()
        self.assertIn("has not been run", self.reasons()[0])
        self.mutate(**mutants(5, 5))
        self.assertIn("mutation check failed", self.reasons()[0])
        self.mutate(**mutants(9, 1))
        self.assertEqual(self.reasons(), [])
        self.write("steps/steps.py", "def then_ok():\n    assert 1 == 1\n")                # a test changed after the check
        self.assertIn("out of date", self.reasons()[0])

    def test_the_gate_function_includes_it(self):
        self.implement()
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
