"""An adoption of the legacy-billing reference app, driven by the command line with no model in the loop.

A hand-written adoption (rules, `@existing` scenarios, the operations map) goes through every gate with real test runs,
and the adopt gates are shown to accept it and to refuse the two ways an adoption goes wrong: a scenario that is not
`@existing`, and a production edit after the bind gate.

Needs `pytest` and `pytest-bdd` in the interpreter that runs the tests; skipped without.
"""
import contextlib
import importlib.util
import io
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from bddlib import adapter, cli, state

REPO = Path(__file__).resolve().parents[3]
APP = REPO / "evals" / "apps" / "legacy-billing"
HAVE_RUNNER = all(importlib.util.find_spec(name) for name in ("pytest", "pytest_bdd"))
FEATURE = "FEAT-001"

RULES = """# Rules: pricing and late fees

R-001.1 A line of up to ten units costs quantity times unit price; tax is rounded half up to the cent.
R-001.2 From the eleventh unit the whole line gets 5% off (the code says "ten or more"; asked as a question).
R-001.3 No late fee within 14 days; then 2% per started 30-day period, at most three periods.
R-001.4 More than 90 days overdue, no late fee at all (asked as a question).
"""

SPEC = """@FEAT-001
Feature: Invoice pricing and late fees

  @R-001.1
  Rule: Up to ten units are not discounted and tax is rounded half up

    @existing @EX-001.1.1
    Scenario: Ten units get no discount
      When price invoice is called with:
        | quantity | unit_price_cents | tax_percent |
        | 10       | 1000             | 10          |
      Then the result is:
        \"\"\"
        {"subtotal": 10000, "tax": 1000, "total": 11000}
        \"\"\"

    @existing @EX-001.1.2
    Scenario: Half a cent of tax rounds up
      When price invoice is called with:
        | quantity | unit_price_cents | tax_percent |
        | 1        | 5                | 10          |
      Then the result is:
        \"\"\"
        {"subtotal": 5, "tax": 1, "total": 6}
        \"\"\"

  @R-001.2
  Rule: From the eleventh unit the line gets five percent off

    @existing @EX-001.2.1
    Scenario: Eleven units get the discount
      When price invoice is called with:
        | quantity | unit_price_cents | tax_percent |
        | 11       | 1000             | 10          |
      Then the result is:
        \"\"\"
        {"subtotal": 10450, "tax": 1045, "total": 11495}
        \"\"\"

  @R-001.3
  Rule: Late fees start after the grace period

    @existing @EX-001.3.1
    Scenario: Twenty days overdue costs one period
      When late fee is called with:
        | balance_cents | days_overdue |
        | 10000         | 20           |
      Then the result is:
        \"\"\"
        200
        \"\"\"

  @R-001.4
  Rule: A balance more than ninety days overdue pays nothing

    @existing @EX-001.4.1
    Scenario: Ninety-one days overdue costs nothing
      When late fee is called with:
        | balance_cents | days_overdue |
        | 10000         | 91           |
      Then the result is:
        \"\"\"
        0
        \"\"\"
"""

GIT = ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false",
       "-c", "gc.auto=0", "-c", "maintenance.auto=false"]


@unittest.skipUnless(HAVE_RUNNER, "needs pytest and pytest-bdd")
class AdoptBillingTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name).resolve()
        shutil.copytree(APP, self.root, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        (self.root / ".bdd").mkdir()
        subprocess.run([*GIT, "init", "-q"], cwd=self.root, check=True, capture_output=True)
        subprocess.run([*GIT, "add", "-A"], cwd=self.root, check=True, capture_output=True)
        subprocess.run([*GIT, "commit", "-q", "-m", "legacy"], cwd=self.root, check=True, capture_output=True)
        adapter.apply(self.root, "python-pytest-bdd")
        (self.root / "tests" / "features" / "sample.feature").unlink()
        operations = self.root / "tests" / "drivers" / "operations.py"
        operations.write_text(operations.read_text(encoding="utf-8").replace(
            '    "add": "tests.sample_domain:add",        # sample; "module:function"\n',
            '    "price invoice": "billing.pricing:invoice",\n    "late fee": "billing.fees:late_fee",\n'),
            encoding="utf-8", newline="\n")
        state.create(self.root, FEATURE, "Pricing and late fees", "standard", "adopt")
        self.feature_dir = next((self.root / ".bdd" / "features").glob(f"{FEATURE}-*"))
        (self.feature_dir / "rules.md").write_text(RULES, encoding="utf-8", newline="\n")
        self.spec = self.root / "tests" / "features" / "billing.feature"
        self.write_spec(SPEC)

    def write_spec(self, text: str) -> None:
        self.spec.write_text(text, encoding="utf-8", newline="\n")

    def bdd(self, *argv: str) -> tuple[int, str]:
        out, here = io.StringIO(), os.getcwd()
        os.chdir(self.root)
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
                return cli.main(list(argv)), out.getvalue()
        finally:
            os.chdir(here)

    def ok(self, *argv: str) -> str:
        code, out = self.bdd(*argv)
        self.assertEqual(code, 0, f"bdd {' '.join(argv)}\n{out}")
        return out

    def gate(self, name: str, *more: str) -> tuple[int, str]:
        return self.bdd("gate", FEATURE, name, "--result", "pass", *more)

    def walk_to_bind(self) -> None:
        for name in ("discover",):
            self.ok("gate", FEATURE, name, "--result", "pass")
        self.ok("approve", FEATURE, "rules", "--self-reported")
        self.ok("gate", FEATURE, "test-design", "--result", "pass")
        self.ok("approve", FEATURE, "examples", "--self-reported")              # approving the examples locks the specs
        for name in ("system-map", "refine"):
            self.ok("gate", FEATURE, name, "--result", "pass")
        self.ok("run", FEATURE)
        self.ok("lock", FEATURE, "--scope", "bind", "--bound")

    def walk_to_tasks(self) -> None:
        self.walk_to_bind()
        self.ok("classify", FEATURE, "--expect", "red")                    # valid: every scenario is @existing and passes
        self.ok("gate", FEATURE, "bind", "--result", "pass", "--record-red")
        self.ok("gate", FEATURE, "tasks", "--result", "pass", "--detail", "adopt=true")

    def test_the_scenarios_describe_the_unchanged_code_and_lint_is_clean(self):
        self.ok("lint", "tests/features")
        self.ok("run", FEATURE)
        self.ok("classify", FEATURE, "--expect", "green")

    def test_a_correct_adoption_passes_every_gate_and_leaves_the_code_alone(self):
        self.walk_to_tasks()
        self.assertIn("production source unchanged", self.ok("adopt", FEATURE, "--check"))
        self.ok("run", FEATURE)
        self.ok("classify", FEATURE, "--expect", "green")
        self.ok("gate", FEATURE, "implement", "--result", "pass", "--detail", "adopt=true")
        self.ok("gate", FEATURE, "verify", "--result", "pass")
        self.assertIn('"phase": "done"', self.ok("state", "show", FEATURE, "--json"))
        changed = subprocess.run([*GIT, "diff", "--stat", "HEAD", "--", "billing", "smoke.py"], cwd=self.root,
                                 check=True, capture_output=True, text=True).stdout
        self.assertEqual(changed, "")

    def test_a_scenario_that_is_not_existing_is_refused(self):
        self.write_spec(SPEC.replace("@existing @EX-001.4.1", "@EX-001.4.1"))
        self.walk_to_bind()
        code, out = self.bdd("classify", FEATURE, "--expect", "red")
        self.assertEqual(code, 1, out)                                       # it passed before any change: not a valid red
        code, out = self.bdd("gate", FEATURE, "bind", "--result", "pass", "--record-red")
        self.assertNotEqual(code, 0, out)
        code, out = self.bdd("adopt", FEATURE, "--check")
        self.assertEqual(code, 1, out)
        self.assertIn("A1", out)
        self.assertIn("EX-001.4.1", out)

    def test_a_production_edit_after_the_bind_gate_is_refused(self):
        self.walk_to_tasks()
        pricing = self.root / "billing" / "pricing.py"
        original = pricing.read_text(encoding="utf-8")
        pricing.write_text(original.replace("if quantity > 10:", "if quantity >= 10:"), encoding="utf-8", newline="\n")
        code, out = self.bdd("adopt", FEATURE, "--check")
        self.assertEqual(code, 1, out)
        self.assertIn("A3", out)
        code, out = self.gate("implement", "--detail", "adopt=true")
        self.assertNotEqual(code, 0, out)
        self.assertIn("A3", out)
        pricing.write_text(original, encoding="utf-8", newline="\n")
        self.ok("adopt", FEATURE, "--check")
        self.ok("run", FEATURE)
        self.ok("gate", FEATURE, "implement", "--result", "pass", "--detail", "adopt=true")


if __name__ == "__main__":
    unittest.main()
