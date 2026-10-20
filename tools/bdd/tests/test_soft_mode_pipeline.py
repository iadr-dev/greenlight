"""A whole feature through the pipeline in soft mode: skills installed for another tool, no hooks, self-reported
approvals. No model is involved: the steps an agent would take are done by hand, with the command line.

It needs `pytest` and `pytest-bdd` in the interpreter that runs the tests (the CI job for the adapter installs them).
"""
import contextlib
import importlib.util
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from bddlib import cli, enforcement, lockfile

HAVE_RUNNER = all(importlib.util.find_spec(name) for name in ("pytest", "pytest_bdd"))
FEATURE = "FEAT-001"

RULES = "# Rules\n\nR-001.1 An order can be placed.\n"
SPEC = """@FEAT-001
Feature: Orders

  @R-001.1
  Rule: An order can be placed

    @EX-001.1.1
    Scenario: An order is placed
      When alice calls place order with:
        | item | qty |
        | tea  | 2   |
      Then the request succeeds
"""
SYSTEM_HTTP = '''        import importlib.util

        if importlib.util.find_spec("app") is None:
            raise ExpectedMissing("an HTTP client for the application")
        from app.orders import client

        return client()
'''
PRODUCTION = '''"""The shop, as far as the scenario needs it."""


class _Response:
    status_code = 200

    def json(self):
        return {"order": 1}


class _Client:
    def request(self, method, url, **options):
        return _Response()


def client():
    return _Client()
'''


@unittest.skipUnless(HAVE_RUNNER, "needs pytest and pytest-bdd")
class SoftModePipelineTest(unittest.TestCase):
    """The steps are numbered in the order a person would take them; each assertion is the point of its step."""

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.TemporaryDirectory()
        cls.root = Path(cls.dir.name).resolve()

    @classmethod
    def tearDownClass(cls):
        cls.dir.cleanup()

    def bdd(self, *argv: str) -> tuple[int, str, str]:
        out, err, here = io.StringIO(), io.StringIO(), os.getcwd()
        os.chdir(self.root)
        os.environ.pop(enforcement.SESSION_ENV, None)                      # no Claude Code session, so no hooks
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = cli.main(list(argv))
        finally:
            os.chdir(here)
        return code, out.getvalue(), err.getvalue()

    def write(self, rel: str, text: str) -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        return path

    def edit(self, rel: str, old: str, new: str) -> None:
        path = self.root / rel
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text)
        path.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")

    def commit(self) -> None:
        """The red record names the commit it was proven at, so the project is a git repository."""
        git = ["git", "-c", "gc.auto=0", "-c", "maintenance.auto=false", "-c", "user.name=t", "-c", "user.email=t@example.com"]
        for words in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "tests before code"]):
            subprocess.run([*git, *words], cwd=self.root, check=True, capture_output=True)

    def ok(self, *argv: str) -> str:
        code, out, err = self.bdd(*argv)
        self.assertEqual(code, 0, f"bdd {' '.join(argv)}\n{out}{err}")
        return out

    def feature_dir(self) -> Path:
        return next((self.root / ".bdd" / "features").glob(FEATURE + "-*"))

    def state(self) -> dict:
        return json.loads(self.ok("state", "show", FEATURE, "--json"))

    def test_the_whole_pipeline_in_soft_mode(self):
        self.step_1_setup_and_install()
        self.step_2_specify_and_approve()
        self.step_3_bind_and_prove_the_red()
        self.step_4_a_seeded_edit_of_a_locked_spec_is_detected()
        self.step_5_implement_and_verify()
        self.step_6_the_record_says_soft()
        self.step_7_hard_enforcement_refuses_the_same_approvals()

    def step_1_setup_and_install(self):
        self.ok("init", "--adapter", "python-pytest-bdd", "--autonomy", "standard")
        out = self.ok("install-skills", "codex")
        self.assertIn("soft enforcement", out)
        self.ok("install-skills", "agents-md")
        self.assertTrue((self.root / ".agents/skills/greenlight-feature/SKILL.md").is_file())
        self.assertIn("Enforcement here is soft", (self.root / "AGENTS.md").read_text(encoding="utf-8"))
        self.assertFalse((self.root / ".bdd" / ".enforcement").exists(), "no hook has ever run here")
        self.ok("state", "init", FEATURE, "--title", "Orders")
        self.ok("gate", FEATURE, "discover", "--result", "pass")

    def step_2_specify_and_approve(self):
        self.write(f"{self.feature_dir().relative_to(self.root).as_posix()}/rules.md", RULES)
        out = self.bdd("approve", FEATURE, "rules", "--self-reported")
        self.assertEqual(out[0], 0, out)
        self.assertIn("self-reported", out[2])
        self.ok("gate", FEATURE, "test-design", "--result", "pass")
        self.write("tests/features/orders.feature", SPEC)
        self.ok("lint", "tests/features")
        self.ok("approve", FEATURE, "examples", "--self-reported")
        self.assertIn("spec", lockfile.read_lock(self.feature_dir(), FEATURE)["scopes"])      # approving locked the examples
        self.ok("gate", FEATURE, "system-map", "--result", "pass")
        self.ok("gate", FEATURE, "refine", "--result", "pass")

    def step_3_bind_and_prove_the_red(self):
        self.edit("tests/drivers/operations.py", '    # "place order": Api("POST", "/orders"),',
                  '    "place order": Api("POST", "/orders"),')
        self.edit("tests/drivers/system.py", '        raise ExpectedMissing("an HTTP client for the application")\n', SYSTEM_HTTP)
        self.ok("run", FEATURE)
        self.ok("classify", FEATURE, "--expect", "red")
        self.ok("lock", FEATURE, "--scope", "bind", "--bound")
        self.commit()
        self.ok("gate", FEATURE, "bind", "--result", "pass", "--record-red")
        self.ok("gate", FEATURE, "tasks", "--result", "pass")

    def step_4_a_seeded_edit_of_a_locked_spec_is_detected(self):
        spec = self.root / "tests/features/orders.feature"
        original = spec.read_text(encoding="utf-8")
        spec.write_text(original.replace("qty |\n        | tea  | 2 ", "qty |\n        | tea  | 3 "), encoding="utf-8", newline="\n")
        code, out, _ = self.bdd("lock", FEATURE, "--check", "--require")
        self.assertEqual(code, 1, out)
        self.assertIn("changed since it was locked", out)
        code, _, err = self.bdd("gate", FEATURE, "implement", "--result", "pass")
        self.assertNotEqual(code, 0)
        self.assertIn("changed since it was locked", err)
        spec.write_text(original, encoding="utf-8", newline="\n")
        self.ok("lock", FEATURE, "--check", "--require")

    def step_5_implement_and_verify(self):
        self.write("app/__init__.py", "")
        self.write("app/orders.py", PRODUCTION)
        self.ok("run", FEATURE)
        self.ok("classify", FEATURE, "--expect", "green")
        self.ok("gate", FEATURE, "implement", "--result", "pass")
        self.ok("gate", FEATURE, "verify", "--result", "pass")
        self.assertEqual(self.state()["phase"], "done")

    def step_6_the_record_says_soft(self):
        data = self.state()
        self.assertEqual(data["enforcement"]["level"], "soft")
        self.assertTrue(any("self-reported" in reason for reason in data["enforcement"]["reasons"]))
        grades = {a["gate"]: a["grade"] for a in data["approvals"]}
        self.assertEqual(grades, {"rules": "self-reported", "examples": "self-reported"})
        row = next(line for line in self.ok("status").splitlines() if line.startswith(FEATURE))
        self.assertRegex(row, r"approved\s+soft\s")                      # the ENFORCEMENT column

    def step_7_hard_enforcement_refuses_the_same_approvals(self):
        self.edit(".bdd/config.toml", 'enforcement = "auto"', 'enforcement = "hard"')
        self.ok("state", "init", "FEAT-002", "--title", "Refunds")
        feature2 = next((self.root / ".bdd" / "features").glob("FEAT-002-*"))
        (feature2 / "rules.md").write_text("# Rules\n\nR-002.1 A refund can be made.\n", encoding="utf-8", newline="\n")
        code, _, err = self.bdd("approve", "FEAT-002", "rules", "--self-reported")
        self.assertNotEqual(code, 0)
        self.assertIn("hard enforcement", err)
        data = json.loads(self.ok("state", "show", "FEAT-002", "--json"))
        self.assertEqual(data["approvals"], [])


if __name__ == "__main__":
    unittest.main()
