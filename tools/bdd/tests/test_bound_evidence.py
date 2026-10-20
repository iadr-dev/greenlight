"""What the test evidence depends on is bound: the adapter's plumbing files, the interpreter, and the kept red run."""
import contextlib
import hashlib
import io
import json
import os
import unittest

from bddlib import config as cfg
from bddlib import cli, gates, guard, lockfile, runner, tripwire

from tests.helpers import ProjectCase

RUN = "[adapters.run]\nby_tag = '{project_python} -m pytest -m {tag}'\nreport = '--out {out}'\n"


class SupportFilesCase(ProjectCase):
    def setUp(self):
        super().setUp()
        self.config(tail='support = ["tests/conftest.py"]\n')
        self.conftest = self.write("tests/conftest.py", "# plumbing\n")

    def write_as(self, agent: str | None, rel: str) -> str | None:
        payload = {"tool_name": "Write", "cwd": str(self.root), "tool_input": {"file_path": str(self.root / rel)}}
        if agent:
            payload["agent_type"] = f"greenlight:{agent}"
        return guard.evaluate(payload)


class SupportFilesTest(SupportFilesCase):
    def test_the_configuration_names_them_and_rejects_nonsense(self):
        self.assertEqual(cfg.load(self.root).support_files, (self.root / "tests/conftest.py",))
        self.config(tail="support = 3\n")
        with self.assertRaises(cfg.ConfigError):
            cfg.load(self.root)

    def test_only_the_step_engineer_may_write_them(self):
        self.assertIsNone(self.write_as("step-engineer", "tests/conftest.py"))
        for agent in ("implementer", "product-analyst", "qa-designer", "spec-auditor"):
            with self.subTest(agent=agent):
                self.assertIsNotNone(self.write_as(agent, "tests/conftest.py"))

    def test_lock_bound_locks_steps_drivers_and_support_files(self):
        out, here = io.StringIO(), os.getcwd()
        os.chdir(self.root)
        try:
            with contextlib.redirect_stdout(out):
                self.assertEqual(cli.main(["lock", "FEAT-007", "--scope", "bind", "--bound"]), 0)
        finally:
            os.chdir(here)
        files = set(lockfile.read_lock(self.feature_dir, "FEAT-007")["scopes"]["bind"]["files"])
        self.assertEqual(files, {"steps/steps.py", "tests/conftest.py"})

    def test_lock_bound_goes_only_with_the_bind_scope_and_no_paths(self):
        for argv in (["lock", "FEAT-007", "--scope", "spec", "--bound"], ["lock", "FEAT-007", "--scope", "bind", "--bound", "steps"]):
            with self.subTest(argv=argv):
                err, here = io.StringIO(), os.getcwd()
                os.chdir(self.root)
                try:
                    with contextlib.redirect_stderr(err):
                        self.assertEqual(cli.main(argv), 2)
                finally:
                    os.chdir(here)
                self.assertIn("--bound goes with", err.getvalue())

    def test_a_changed_plumbing_file_makes_a_recorded_run_stale(self):
        before = runner.inputs_digest(self.root, "FEAT-007")
        self.conftest.write_text("# plumbing that skips tests\n", encoding="utf-8", newline="\n")
        self.assertNotEqual(runner.inputs_digest(self.root, "FEAT-007"), before)


class InterpreterTest(ProjectCase):
    def setUp(self):
        super().setUp()
        self.config(tail=RUN)

    def raw(self, interpreter) -> bytes:
        return json.dumps({"inputs": runner.inputs_digest(self.root, "FEAT-007"), "interpreter": interpreter, "cases": [],
                           "feature": "FEAT-007", "mode": "all", "seed": None, "at": "now", "runs": []}).encode("utf-8")

    def test_a_run_made_with_another_interpreter_is_refused(self):
        problems = gates.run_problems(self.root, "FEAT-007", "verify", self.raw({"path": "/tmp/forged-python", "sha256": None}))
        self.assertEqual(len(problems), 1)
        self.assertIn("another interpreter", problems[0])

    def test_the_interpreter_the_project_resolves_to_is_accepted(self):
        problems = gates.run_problems(self.root, "FEAT-007", "verify", self.raw(runner.interpreter_identity(self.root)))
        self.assertFalse(any("another interpreter" in p for p in problems))

    def test_a_missing_run_is_reported(self):
        self.assertIn("has not been run yet", gates.run_problems(self.root, "FEAT-007", "bind", None)[0])

    def test_a_record_that_is_not_json_is_a_problem_not_a_crash(self):
        self.assertEqual(len(gates.run_problems(self.root, "FEAT-007", "bind", b"{broken")), 1)


class EnvironmentTest(ProjectCase):
    def make_env(self) -> str:
        scripts = self.root / ".venv" / ("Scripts" if os.name == "nt" else "bin")
        scripts.mkdir(parents=True)
        python = scripts / ("python.exe" if os.name == "nt" else "python")
        python.write_text("", encoding="utf-8")
        return str(python)

    def evaluate(self, agent: str | None, rel: str) -> str | None:
        payload = {"tool_name": "Write", "cwd": str(self.root), "tool_input": {"file_path": str(self.root / rel)}}
        if agent:
            payload["agent_type"] = f"greenlight:{agent}"
        return guard.evaluate(payload)

    def test_no_agent_may_write_into_the_projects_environment(self):
        for agent in ("implementer", "step-engineer", "product-analyst"):
            with self.subTest(agent=agent):
                self.assertIsNotNone(self.evaluate(agent, ".venv/Lib/site-packages/pytest/__init__.py"))
                self.assertIsNotNone(self.evaluate(agent, "venv/bin/python"))

    def test_the_interpreter_is_watched_by_the_tripwire(self):
        python = self.make_env()
        with unittest_env({"VIRTUAL_ENV": None, "GREENLIGHT_PYTHON": None}):
            watched = {str(p) for p in tripwire.watched_files(self.root, None)}
        self.assertIn(python, watched)

    def test_the_kept_red_is_exactly_the_bytes_that_were_checked(self):
        runner.runs_dir(self.root, "FEAT-007").mkdir(parents=True)
        raw = b'{"checked": true}\n'
        kept = runner.keep_red(self.root, "FEAT-007", raw)
        self.assertEqual((runner.runs_dir(self.root, "FEAT-007") / "red.json").read_bytes(), raw)
        self.assertEqual(kept["sha256"], hashlib.sha256(raw).hexdigest())


@contextlib.contextmanager
def unittest_env(values: dict):
    """Set (or, for None, remove) environment variables for a block."""
    saved = {k: os.environ.get(k) for k in values}
    for key, value in values.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    try:
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


if __name__ == "__main__":
    unittest.main()
