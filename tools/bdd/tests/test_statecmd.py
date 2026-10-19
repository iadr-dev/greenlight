import contextlib
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from bddlib import approvals, lockcmd, state, statecmd, store

SPEC = "@FEAT-007\nFeature: Discounts\n  @R-7.1 @EX-7.1.1\n  Scenario: S\n    Then the request succeeds\n"


class StateCommandTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name).resolve()
        self.write(".bdd/config.toml", 'autonomy = "guided"\n[[adapters]]\nname = "x"\nfeatures = "features"\nsteps = "steps"\n')
        self.spec = self.write("features/discounts.feature", SPEC)
        self.step = self.write("steps/steps.py", "def then_ok():\n    assert True\n")

    def write(self, rel: str, text: str) -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        return path

    def run_cmd(self, runner, *args: str, cwd: Path | None = None) -> tuple[int, str, str]:
        out, err, here = io.StringIO(), io.StringIO(), os.getcwd()
        os.chdir(cwd or self.root)
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = runner(list(args))
        finally:
            os.chdir(here)
        return code, out.getvalue(), err.getvalue()

    def init(self, *extra: str):
        return self.run_cmd(statecmd.run_state, "init", "FEAT-007", "--title", "Order discounts", *extra)

    def gate(self, *args: str):
        return self.run_cmd(statecmd.run_gate, "FEAT-007", *args)

    def lock_both(self):
        self.run_cmd(lockcmd.run_lock, "FEAT-007", "--scope", "spec")
        self.run_cmd(lockcmd.run_lock, "FEAT-007", "--scope", "bind", "steps")

    # -- init and show -------------------------------------------------------------------
    def test_init_uses_the_configured_autonomy_unless_told_otherwise(self):
        code, out, _ = self.init()
        self.assertEqual((code, out.strip()), (0, "created FEAT-007 in .bdd/features/FEAT-007-order-discounts"))
        feature_dir = store.find_feature_dir(self.root, "FEAT-007")
        self.assertEqual(state.load(feature_dir)["autonomy"]["level"], "guided")
        self.write(".bdd/config.toml", "")
        self.run_cmd(statecmd.run_state, "init", "FEAT-008", "--title", "Other", "--autonomy", "autopilot")
        self.assertEqual(state.load(store.find_feature_dir(self.root, "FEAT-008"))["autonomy"]["level"], "autopilot")

    def test_show_summarises_everything_in_one_place(self):
        self.init()
        self.lock_both()
        self.gate("discover", "--result", "pass")
        self.run_cmd(statecmd.run_assume, "FEAT-007", "--text", "t", "--rationale", "r")
        self.run_cmd(statecmd.run_cost, "FEAT-007", "--phase", "discover", "--tokens", "12000", "--seconds", "30")
        code, out, _ = self.run_cmd(statecmd.run_state, "show", "FEAT-007")
        self.assertEqual(code, 0)
        for expected in ("FEAT-007 Order discounts", "phase: specify    autonomy: guided", "gates: discover pass",
                         "approvals: none", "assumptions: 1", "locks: bind: 1 file(s), spec: 1 file(s)",
                         "red: not recorded", "cost: 12,000 tokens, 30.0 s"):
            self.assertIn(expected, out)

    def test_show_as_json_includes_the_lock_summary(self):
        self.init()
        self.lock_both()
        code, out, _ = self.run_cmd(statecmd.run_state, "show", "FEAT-007", "--json")
        data = json.loads(out)
        self.assertEqual((code, data["locks"], data["phase"]), (0, {"bind": 1, "spec": 1}, "discover"))

    # -- gates ---------------------------------------------------------------------------
    def test_gate_records_and_reports_the_new_phase(self):
        self.init()
        code, out, _ = self.gate("discover", "--result", "pass", "--detail", "questions=0", "--detail", "note=a=b")
        self.assertEqual((code, out.strip()), (0, "FEAT-007: discover pass; phase is now specify"))
        recorded = state.load(store.find_feature_dir(self.root, "FEAT-007"))["gates"]["discover"]["detail"]
        self.assertEqual(recorded, {"questions": "0", "note": "a=b"})

    def test_human_gates_are_refused_with_instructions(self):
        self.init()
        code, _, err = self.gate("rules", "--result", "pass")
        self.assertEqual(code, 2)
        self.assertIn("only the person can approve it", err)

    def approve_through(self, *gates_to_pass: str) -> None:
        """Pass the given machine gates and approve both human gates, in pipeline order, without hooks."""
        feature_dir = store.find_feature_dir(self.root, "FEAT-007")
        rules = feature_dir / "rules.md"
        rules.write_text("# Rules\n\nR-007.1 Orders of 1000 or more get 10% off.\n", encoding="utf-8", newline="\n")
        self.gate("discover", "--result", "pass")
        approvals.record(self.root, feature_dir, "rules", "approve", "self-reported")
        self.gate("test-design", "--result", "pass")
        approvals.record(self.root, feature_dir, "examples", "approve", "self-reported")
        for name in gates_to_pass:
            self.assertEqual(self.gate(name, "--result", "pass")[0], 0, name)

    def test_implement_gate_is_refused_until_locks_are_intact(self):
        self.init()
        code, _, err = self.gate("implement", "--result", "pass")
        self.assertEqual(code, 2)
        self.assertIn("cannot record implement=pass", err)
        self.approve_through("system-map", "refine")
        self.run_cmd(lockcmd.run_lock, "FEAT-007", "--scope", "bind", "steps")
        self.gate("bind", "--result", "pass")
        self.gate("tasks", "--result", "pass")
        self.step.write_text("def then_ok():\n    pass\n", encoding="utf-8", newline="\n")
        self.assertEqual(self.gate("implement", "--result", "pass")[0], 2)
        self.step.write_text("def then_ok():\n    assert True\n", encoding="utf-8", newline="\n")
        self.assertEqual(self.gate("implement", "--result", "pass")[0], 0)

    def test_usage_errors(self):
        self.init()
        cases = [(("discover", "--result", "pass", "--detail", "oops"), "expects key=value"),
                 (("deploy", "--result", "pass"), "unknown gate"),
                 (("discover", "--result", "pass", "--record-red"), "belongs to the bind gate")]
        for args, message in cases:
            with self.subTest(args=args):
                code, _, err = self.gate(*args)
                self.assertEqual(code, 2)
                self.assertIn(message, err)

    @unittest.skipUnless(shutil.which("git"), "needs git")
    def test_record_red_captures_the_git_position(self):
        self.init()
        self.write("src/app.py", "x = 1\n")
        git = ["git", "-C", str(self.root), "-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false"]
        subprocess.run([*git, "init", "-q"], check=True, capture_output=True)
        subprocess.run([*git, "add", "-A"], check=True, capture_output=True)
        subprocess.run([*git, "commit", "-q", "-m", "init"], check=True, capture_output=True)
        self.approve_through("system-map", "refine")
        self.run_cmd(lockcmd.run_lock, "FEAT-007", "--scope", "bind", "steps")
        code, _, _ = self.gate("bind", "--result", "pass", "--record-red")
        self.assertEqual(code, 0)
        red = state.load(store.find_feature_dir(self.root, "FEAT-007"))["red"]
        self.assertRegex(red["commit"], r"^[0-9a-f]{40}$")
        self.assertFalse(red["dirty"])      # `bdd state init` wrote under .bdd/, which is not production source
        self.assertRegex(red["source_hash"], r"^[0-9a-f]{64}$")
        code, out, _ = self.run_cmd(statecmd.run_state, "show", "FEAT-007")
        self.assertIn(f"red: commit {red['commit'][:8]}", out)

    def test_record_red_outside_git_is_a_clear_error(self):
        self.init()
        code, _, err = self.gate("bind", "--result", "pass", "--record-red")
        self.assertEqual(code, 2)
        self.assertIn("git rev-parse failed", err)

    # -- assume, cost, mode --------------------------------------------------------------
    def test_assume_prints_the_new_id(self):
        self.init()
        code, out, _ = self.run_cmd(statecmd.run_assume, "FEAT-007", "--text", "Tax is excluded", "--rationale",
                                    "prices are net", "--alt", "tax included", "--alt", "ask later")
        self.assertEqual((code, out.strip()), (0, "A-007.1"))
        stored = state.load(store.find_feature_dir(self.root, "FEAT-007"))["assumptions"][0]
        self.assertEqual(stored["alternatives"], ["tax included", "ask later"])

    def test_cost_reports_totals_for_the_phase(self):
        self.init()
        self.run_cmd(statecmd.run_cost, "FEAT-007", "--phase", "bind", "--tokens", "1000", "--seconds", "5")
        code, out, _ = self.run_cmd(statecmd.run_cost, "FEAT-007", "--phase", "bind", "--tokens", "500", "--seconds", "2.5")
        self.assertEqual((code, out.strip()), (0, "FEAT-007 bind: 1,500 tokens, 7.5 s in 2 run(s)"))

    def test_mode_switch(self):
        self.init()
        code, out, _ = self.run_cmd(statecmd.run_mode, "FEAT-007", "--switch", "autopilot", "--reason", "user: you decide")
        self.assertEqual((code, out.strip()), (0, "FEAT-007: autonomy is now autopilot"))
        code, _, err = self.run_cmd(statecmd.run_mode, "FEAT-007", "--switch", "autopilot", "--reason", "again")
        self.assertEqual(code, 2)
        self.assertIn("already autopilot", err)

    # -- plumbing ------------------------------------------------------------------------
    def test_commands_report_problems_instead_of_tracebacks(self):
        self.init()
        for runner, args in [(statecmd.run_state, ("show", "FEAT-404")), (statecmd.run_gate, ("FEAT-404", "discover", "--result", "pass")),
                             (statecmd.run_assume, ("FEAT-404", "--text", "a", "--rationale", "b")),
                             (statecmd.run_cost, ("FEAT-404", "--phase", "bind")),
                             (statecmd.run_mode, ("FEAT-404", "--switch", "auto", "--reason", "r")),
                             (statecmd.run_state, ("init", "FEAT-007", "--title", "dup"))]:
            with self.subTest(args=args):
                code, _, err = self.run_cmd(runner, *args)
                self.assertEqual(code, 2)
                self.assertTrue(err.startswith("bdd "), err)

    def test_outside_a_project(self):
        with tempfile.TemporaryDirectory() as elsewhere:
            code, _, err = self.run_cmd(statecmd.run_state, "show", "FEAT-007", cwd=Path(elsewhere))
        self.assertEqual(code, 2)
        self.assertIn("not inside a greenlight project", err)

    def test_the_real_cli_dispatches_every_command(self):
        from bddlib import cli
        for command in ("state", "gate", "assume", "cost", "mode", "lock", "unlock", "lint", "doctor"):
            self.assertIn(command, cli.COMMANDS)
        os.chdir(self.root)
        try:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(cli.main(["nonsense"]), 2)
                self.assertEqual(cli.main([]), 2)
        finally:
            os.chdir(Path(__file__).parent)


if __name__ == "__main__":
    unittest.main()
