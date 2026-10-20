"""What the test evidence depends on is bound: the adapter's plumbing files, the interpreter, and the kept red run."""
import contextlib
import hashlib
import io
import json
import os
import tempfile
import unittest

from pathlib import Path

from bddlib import config as cfg
from bddlib import cli, gates, guard, lockfile, redrecord, runner, tripwire

from tests.helpers import ProjectCase

RUN = "[adapters.run]\nby_tag = '{project_python} -m pytest -m {tag}'\nreport = '--out {out}'\n"


class SupportFilesCase(ProjectCase):
    def setUp(self):
        super().setUp()
        self.config(tail='support = ["tests/conftest.py", "tests/*/conftest.py"]\n')
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


class SupportPatternTest(SupportFilesCase):
    def test_a_plumbing_file_made_later_is_covered_by_its_pattern(self):
        self.assertIsNone(self.write_as("step-engineer", "tests/extra/conftest.py"))
        for agent in ("implementer", "product-analyst"):
            with self.subTest(agent=agent):
                self.assertIsNotNone(self.write_as(agent, "tests/extra/conftest.py"))

    def test_existing_matches_are_part_of_the_lock_and_the_digest(self):
        nested = self.write("tests/extra/conftest.py", "# nested\n")
        config = cfg.load(self.root)
        self.assertIn(nested, config.support_files)
        self.assertEqual(config.support_patterns, ("tests/*/conftest.py",))
        before = runner.inputs_digest(self.root, "FEAT-007")
        nested.write_text("# nested, now skipping\n", encoding="utf-8", newline="\n")
        self.assertNotEqual(runner.inputs_digest(self.root, "FEAT-007"), before)


class ProductionNamesTest(unittest.TestCase):
    def test_a_file_entry_matches_only_that_file_and_a_folder_entry_its_contents(self):
        excluded = [".bdd/", "tests/steps/", "tests/conftest.py"]
        for name, production in {"src/app.py": True, "tests/conftest.py": False, "tests/conftest.py.bak": True,
                                 "tests/conftest.pyx": True, "tests/steps/a.py": False, "tests/steps2/a.py": True,
                                 ".bdd/config.toml": False}.items():
            with self.subTest(name=name):
                self.assertEqual(redrecord.is_production(name, excluded), production)


class AgentCommandsTest(ProjectCase):
    def bash(self, command: str, agent: str | None) -> str | None:
        payload = {"tool_name": "Bash", "cwd": str(self.root), "tool_input": {"command": command}}
        if agent:
            payload["agent_type"] = f"greenlight:{agent}"
        return guard.evaluate(payload)

    def test_an_agent_may_not_install_packages_but_the_orchestrator_may(self):
        for command in ("pip install requests", "python -m pip install -r requirements.txt", "uv pip install pytest",
                        "poetry add httpx", "npm install left-pad", "uv add fastapi"):
            with self.subTest(command=command):
                self.assertIn("may not install packages", self.bash(command, "implementer"))
                self.assertIsNone(self.bash(command, None))

    def test_node_package_tools_are_refused_unless_a_safe_subcommand_is_clear(self):
        refused = (
            "npm install", "npm -w x i y", "npm --workspace=x install", "npm --prefix test install", "npm --prefix tests install",
            "npm --loglevel verbose install", "npm -g i left-pad", "npm --silent ci", "npm clean-install", "npm uninstall x",
            "npm update", "npm rebuild", "npm link ../x", "npm init", "npm exec some-tool", "npm config set registry http://x",
            "npm pack", "npm --prefix tests run typecheck",          # a flag that might take a value in front: place unclear
            "npm run build install", "npm test add", "npm ls -- remove x",   # a package-changing word anywhere later
            "yarn", "yarn --frozen-lockfile", "yarn add zod", "yarn global add zod", "yarn build", "yarnpkg add zod",
            "pnpm dlx create-thing", "pnpm --filter app add zod", "pnpm i", "bun add zod", "bun x tool",
            "npx playwright install", "pnpx thing", "bunx create-thing", "./node_modules/.bin/npx tsc", "corepack enable",
            "./tools/npm install", "tools/yarn add x", "/usr/local/bin/npm i", "C:\\Tools\\npm.cmd install",
            "sudo npm i", "FOO=1 npm install", "env npm install", "cd tests && npm ci", "echo done; npm remove x", "(npm install)",
            "echo npm install", "echo npm install | sh", "xargs npm install", "find . -exec npm install ;",
            "bash -c 'npm install'", 'sh -c "cd tests && npm ci"', "npm \\\n install",
            '"npm" install', 'n""pm install', "'npm' 'i'", "$'np\\x6d' install",
            "node node_modules/npm/bin/npm-cli.js install", "node /usr/lib/node_modules/pnpm/bin/pnpm.cjs add x",
            "node .yarn/releases/yarn-3.6.1.cjs install", "node tools/yarn.js add x", "node tools/npx-cli.js thing",
            "npm audit fix", "npm audit --fix", "npm audit --fix --force", "npm audit signatures", "npm audit --json fix")
        for command in refused:
            with self.subTest(command=command):
                self.assertIn("may not install packages", self.bash(command, "step-engineer"))
                self.assertIsNone(self.bash(command, None))            # the orchestrator is not restricted

    def test_node_commands_that_run_scripts_or_only_read_are_allowed(self):
        allowed = ("npm test", "npm t", "npm run build", "npm run-script lint", "npm run install-docs", "npm test -- --update",
                   "npm --silent run lint", "npm -s test", "npm --no-color ls", "npm run typecheck --prefix tests",
                   "npm run build -- --mode production", "npm ls", "npm list --depth 0", "npm why left-pad",
                   "npm view left-pad version", "npm info left-pad", "npm outdated", "npm audit", "npm audit --json --production",
                   "npm audit --omit=dev", "npm audit --audit-level=high", "npm --version", "npm -v", "yarn run build",
                   "yarn test", "yarn why left-pad", "pnpm test", "pnpm run build", "bun run build", "bun test",
                   "node tests/run.mjs --tag FEAT-1 --out r.xml", "ls node_modules/npm", "ls ./tools/npm", "cd node_modules/npm",
                   "cat tools/yarn.js", "cat package.json", "git status")
        for command in allowed:
            with self.subTest(command=command):
                self.assertIsNone(self.bash(command, "implementer"))

    def test_an_environment_folder_is_a_whole_path_segment_with_or_without_a_separator(self):
        for command in ("rm -rf node_modules", "rm -rf tests/node_modules", "cp evil.js tests/node_modules/pkg/index.js",
                        "cd tests/node_modules && cp evil.js x.js", "cd .venv && rm -rf lib", "mv thing venv",
                        "echo x > node_modules", "Remove-Item -Recurse tests\\node_modules"):
            with self.subTest(command=command):
                self.assertIn("may not install packages", self.bash(command, "implementer"))
                self.assertIsNone(self.bash(command, None))
        for command in ("rm -rf node_modules_old", "cp a.md venv_notes.md", "ls node_modules", "cat .venv/pyvenv.cfg"):
            with self.subTest(command=command):
                self.assertIsNone(self.bash(command, "implementer"))

    def test_an_agent_may_not_write_into_the_environment_from_a_shell(self):
        reason = self.bash("cp evil.py .venv/Lib/site-packages/sitecustomize.py", "step-engineer")
        self.assertIn("may not install packages", reason)
        self.assertIn("may not install packages", self.bash("cp evil.js tests/node_modules/playwright-bdd/dist/x.js", "implementer"))
        self.assertIsNone(self.bash("ls tests/node_modules", "step-engineer"))
        self.assertIsNone(self.bash("ls .venv", "step-engineer"))                      # reading is fine
        self.assertIsNone(self.bash("cp evil.py .venv/Lib/x.py", None))


class EnvironmentWatchTest(ProjectCase):
    def test_the_interpreter_its_startup_files_and_the_test_runner_are_watched(self):
        scripts = "Scripts" if os.name == "nt" else "bin"
        site = self.root / ".venv" / ("Lib" if os.name == "nt" else "lib/python3.12") / "site-packages"
        for rel in (f".venv/{scripts}/python" + (".exe" if os.name == "nt" else ""), ".venv/pyvenv.cfg"):
            self.write(rel, "x")
        for rel in ("a.pth", "sitecustomize.py", "_pytest/main.py", "pytest_bdd/plugin.py", "pytest/__init__.py", "requests/api.py"):
            target = site / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("x", encoding="utf-8")
        watched = {p.name for p in tripwire.environment_files(self.root)}
        self.assertEqual(watched, {"python.exe" if os.name == "nt" else "python", "pyvenv.cfg", "a.pth", "sitecustomize.py",
                                   "main.py", "plugin.py", "__init__.py"})                  # not the other packages

    def test_an_environment_outside_the_project_is_not_watched(self):
        self.assertEqual(tripwire.environment_files(self.root), [])


class InitPythonTest(ProjectCase):
    def run_init(self, folder: Path, *argv: str) -> int:
        here = os.getcwd()
        os.chdir(folder)
        try:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                return cli.main(["init", *argv])
        finally:
            os.chdir(here)

    def test_python_is_recorded_in_the_configuration(self):
        with tempfile.TemporaryDirectory() as tmp:
            fresh = Path(tmp).resolve()
            interpreter = fresh / "chosen-python"
            interpreter.write_text("", encoding="utf-8")
            self.assertEqual(self.run_init(fresh, "--python", str(interpreter)), 0)
            self.assertEqual(Path(cfg.load(fresh).python), interpreter)

    def test_a_python_that_is_not_a_file_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            fresh = Path(tmp).resolve()
            self.assertEqual(self.run_init(fresh, "--python", str(fresh / "nope")), 2)
            self.assertFalse((fresh / ".bdd").exists())

    def test_the_run_table_can_scrub_variables_and_must_say_it_properly(self):
        self.config(tail="[adapters.run]\nby_tag = 'x'\nreport = 'y'\nscrub_env = ['PYTEST_']\n")
        self.assertEqual(cfg.load(self.root).runs[0].scrub_env, ("PYTEST_",))
        self.config(tail="[adapters.run]\nby_tag = 'x'\nreport = 'y'\nscrub_env = 3\n")
        with self.assertRaises(cfg.ConfigError):
            cfg.load(self.root)
        self.config("python = 3\n")
        with self.assertRaises(cfg.ConfigError):
            cfg.load(self.root)


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

    def test_no_agent_may_write_into_installed_node_packages_at_any_depth(self):
        for agent in ("implementer", "step-engineer"):
            for rel in ("node_modules/left-pad/index.js", "tests/node_modules/@playwright/test/cli.js"):
                with self.subTest(agent=agent, path=rel):
                    self.assertIn("environment", self.evaluate(agent, rel))
        self.assertIsNone(self.evaluate("implementer", "src/node_modules_notes.md"))              # only the folder itself

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


class RunnerEnvironmentTest(unittest.TestCase):
    def test_variables_that_steer_a_program_never_reach_the_runner(self):
        steering = {"PYTHONPATH": "/x", "PYTHONSTARTUP": "/x", "LD_PRELOAD": "/x", "DYLD_INSERT_LIBRARIES": "/x",
                    "BASH_ENV": "/x", "NODE_OPTIONS": "--require x", "PYTEST_PLUGINS": "evil", "KEEP_ME": "1",
                    "PYTHONUTF8": "1"}
        with unittest_env(steering):
            environment = runner.runner_environment(("PYTEST_",))
        self.assertEqual({k for k in steering if k in environment}, {"KEEP_ME", "PYTHONUTF8"})


class PatternTest(unittest.TestCase):
    def test_a_star_never_crosses_a_slash_and_double_stars_are_refused(self):
        self.assertTrue(cfg.pattern_matches("tests/*/conftest.py", "tests/extra/conftest.py"))
        self.assertTrue(cfg.pattern_matches("tests/*/conftest.py", "Tests/Extra/Conftest.py"))
        self.assertFalse(cfg.pattern_matches("tests/*/conftest.py", "tests/a/b/conftest.py"))
        self.assertFalse(cfg.pattern_matches("tests/*/conftest.py", "tests/conftest.py"))

    def test_expansion_and_matching_agree(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            for rel in ("tests/a/conftest.py", "tests/a/b/conftest.py", "tests/conftest.py"):
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / rel).write_text("x", encoding="utf-8")
            found = [p.relative_to(root).as_posix() for p in cfg.expand_pattern(root, "tests/*/conftest.py")]
            self.assertEqual(found, ["tests/a/conftest.py"])


class UnlockedBoundFileTest(SupportFilesCase):
    def test_a_matching_file_made_after_the_lock_is_a_violation(self):
        lockfile.lock(self.root, self.feature_dir, "FEAT-007", "bind", [self.root / rel for rel in lockfile.bound_files(self.root)])
        later = self.write("tests/extra/conftest.py", "# added after the lock\n")
        violations = lockfile.check(self.root, self.feature_dir, "FEAT-007", ("bind",), None, lockfile.bound_files(self.root))
        self.assertEqual([(v.kind, v.path) for v in violations], [("added", later.relative_to(self.root).as_posix())])
        self.assertIn("never locked", str(violations[0]))


class WatchedPackagesTest(ProjectCase):
    def test_entry_points_and_the_runners_dependencies_are_watched(self):
        scripts = "Scripts" if os.name == "nt" else "bin"
        site = self.root / ".venv" / ("Lib" if os.name == "nt" else "lib/python3.12") / "site-packages"
        self.write(f".venv/{scripts}/python" + (".exe" if os.name == "nt" else ""), "x")
        for rel in ("pytest-8.dist-info/entry_points.txt", "pluggy/_manager.py", "gherkin/parser.py", "requests/api.py"):
            target = site / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("x", encoding="utf-8")
        watched = {p.name for p in tripwire.environment_files(self.root)}
        self.assertTrue({"entry_points.txt", "_manager.py", "parser.py"} <= watched)
        self.assertNotIn("api.py", watched)


if __name__ == "__main__":
    unittest.main()
