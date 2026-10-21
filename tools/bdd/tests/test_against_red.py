"""Proving the red again after a feature was reopened past its implementation (``bdd run --against-red``).

The project's tests run in a temporary git worktree of the production source the red was first proven on, with the
current bound files laid over it. The stand-in runner below reads ``src/app.py`` from wherever it runs, so a scenario
passes only where the feature's code is there: the same thing a real runner does.
"""
import contextlib
import io
import json
import os
import shutil
import subprocess
import unittest
from pathlib import Path

from bddlib import againstred, changecmd, classify, lockfile, redrecord, runcmd, runner, state
from bddlib import config as cfg
from bddlib.errors import UsageError

from tests.helpers import ProjectCase

GIT = shutil.which("git")
RUNNER = '''import argparse, re, sys
from pathlib import Path
from xml.sax.saxutils import quoteattr

ap = argparse.ArgumentParser()
ap.add_argument("--root")
ap.add_argument("--out")
args, _ = ap.parse_known_args()
root = Path(args.root)
done = "DISCOUNT = True" in (root / "src" / "app.py").read_text(encoding="utf-8")
names = [m.group(1).strip() for f in sorted((root / "features").glob("*.feature"))
         for m in re.finditer(r"Scenario: (.+)", f.read_text(encoding="utf-8"))]
rows = []
for name in names:
    passed = done or "already" in name
    failure = "" if passed else '<failure message="AssertionError: no discount yet">AssertionError</failure>'
    rows.append(f"<testcase classname=\\"features\\" name={quoteattr(name)}>{failure}</testcase>")
Path(args.out).write_text("<testsuites><testsuite>" + "".join(rows) + "</testsuite></testsuites>", encoding="utf-8")
sys.exit(0 if all("failure" not in r for r in rows) else 1)
'''
FEATURE = """@FEAT-007
Feature: Discounts

  @R-007.1
  Rule: Orders of 1000 or more get 10% off

    @EX-007.1.1
    Scenario: An order of exactly 1000
      Then the request succeeds

    @EX-007.1.2
    Scenario: An order of 999
      Then the request succeeds
"""
NEW_EXAMPLE = """
    @EX-007.1.3
    Scenario: An order of 2000
      Then the request succeeds
"""
RUN_TABLE = """
[adapters.run]
by_tag = '{python} steps/runner.py --root {root}'
report = '--out {out}'

[adapters.classify]
test_defect = ['ImportError']
expected_fail = ['AssertionError']
"""
WITHOUT = "def price(total):\n    return total\n"
WITH = "DISCOUNT = True\n\ndef price(total):\n    return total * 0.9 if total >= 1000 else total\n"


def git(root: Path, *args: str) -> str:
    done = subprocess.run(["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@example.com",
                           "-c", "commit.gpgsign=false", "-c", "gc.auto=0", "-c", "maintenance.auto=false", *args],
                          check=True, capture_output=True, text=True)
    return done.stdout


@unittest.skipUnless(GIT, "needs git")
class AgainstRedCase(ProjectCase):
    def setUp(self):
        super().setUp()
        self.config(tail=RUN_TABLE)
        self.write("features/discounts.feature", FEATURE)
        self.runner_file = self.write("steps/runner.py", RUNNER)
        self.write("src/app.py", WITHOUT)
        self.write(".gitignore", ".bdd/.runs/\n.bdd/.integrity/\n.bdd/.enforcement/\n__pycache__/\n")
        git(self.root, "init", "-q")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "the application before the feature")

    def cli(self, function, *args: str) -> tuple[int, str, str]:
        out, err, here = io.StringIO(), io.StringIO(), os.getcwd()
        os.chdir(self.root)
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                try:
                    code = function(list(args))
                except SystemExit as exc:
                    code = exc.code
        finally:
            os.chdir(here)
        return code, out.getvalue(), err.getvalue()

    def bdd_run(self, *args: str) -> tuple[int, str, str]:
        return self.cli(runcmd.run_run, "FEAT-007", *args)

    def latest(self) -> dict:
        return runner.load_latest(self.root, "FEAT-007")

    def verdict(self, record: dict | None = None) -> dict:
        record = record or self.latest()
        return classify.classify_run(record, classify.feature_scenarios(self.root, "FEAT-007"), list(cfg.load(self.root).runs))

    def bind(self) -> dict:
        if "bind" not in lockfile.read_lock(self.feature_dir, "FEAT-007")["scopes"]:
            lockfile.lock(self.root, self.feature_dir, "FEAT-007", "bind", [self.runner_file])
        return self.gate("bind", red=redrecord.capture(self.root, cfg.load(self.root).test_dirs, "FEAT-007"))

    def first_red_and_code(self) -> dict:
        """The feature as it stood in the run that deadlocked: red proven, tasks done, the code written and green."""
        self.walk_to("refine")
        self.bdd_run()
        self.assertTrue(self.verdict()["red"]["valid"])
        self.bind()
        self.gate("tasks")
        self.write("src/app.py", WITH)
        self.bdd_run()
        self.assertTrue(self.verdict()["green"]["valid"])
        return self.data()["red"]

    def reopen_and_add_example(self, text: str = NEW_EXAMPLE) -> None:
        changecmd.reopen(self.root, self.feature_dir, "examples", "the audit asked for one more example")
        self.write("features/discounts.feature", FEATURE + text)
        self.approve("examples")
        self.gate("system-map")
        self.gate("refine")


class TheDeadlockTest(AgainstRedCase):
    def test_a_reopen_after_the_code_proves_the_new_red_against_the_original_source(self):
        first = self.first_red_and_code()
        self.reopen_and_add_example()
        self.bdd_run()                                            # in the project the code is there: everything passes
        with self.assertRaises(UsageError) as refused:
            self.bind()
        self.assertIn("passed before implementation", str(refused.exception))
        self.assertIn("--against-red", str(refused.exception))

        code, out, err = self.bdd_run("--against-red")
        self.assertEqual(code, 0, err)
        self.assertIn("ran against the red", out)
        rows = {row["example"]: row["result"] for row in self.verdict()["scenarios"]}
        self.assertEqual(rows, {"EX-007.1.1": "expected-fail", "EX-007.1.2": "expected-fail", "EX-007.1.3": "expected-fail"})

        data = self.bind()
        self.assertEqual(data["gates"]["bind"]["result"], "pass")
        self.assertEqual((data["red"]["commit"], data["red"]["snapshot"]), (first["commit"], first["snapshot"]))
        self.assertIn("reproduced_at", data["red"])
        self.assertEqual((self.root / "src" / "app.py").read_text(encoding="utf-8"), WITH)       # the code was not touched
        self.assertEqual(git(self.root, "worktree", "list").count("\n"), 1)                      # the temporary one is gone

    def test_the_reopen_keeps_the_first_red_on_record(self):
        first = self.first_red_and_code()
        kept = self.data()["red_run"]
        changecmd.reopen(self.root, self.feature_dir, "examples", "one more example")
        data = self.data()
        self.assertIsNone(data["red"])
        self.assertEqual(data["red_history"][0]["red"], first)
        copy = runner.runs_dir(self.root, "FEAT-007") / data["red_history"][0]["red_run"]["file"]
        self.assertEqual(copy.read_bytes(), (runner.runs_dir(self.root, "FEAT-007") / kept["file"]).read_bytes())
        self.assertEqual(againstred.baseline(data), first)

    def test_a_new_example_that_already_passes_without_the_code_is_not_a_red(self):
        self.first_red_and_code()
        self.reopen_and_add_example(NEW_EXAMPLE.replace("An order of 2000", "Totals are already shown"))
        self.bdd_run("--against-red")
        self.assertFalse(self.verdict()["red"]["valid"])
        with self.assertRaises(UsageError):
            self.bind()

    def test_only_test_material_is_laid_over_the_red(self):
        self.first_red_and_code()
        self.reopen_and_add_example()
        self.write("src/extra.py", "DISCOUNT = True\n")           # today's production files never reach the worktree
        config = cfg.load(self.root)
        with againstred.red_worktree(self.root, againstred.baseline(self.data()), config) as (place, _missing):
            self.assertEqual((place / "src" / "app.py").read_text(encoding="utf-8").replace("\r\n", "\n"), WITHOUT)
            self.assertFalse((place / "src" / "extra.py").exists())
            self.assertIn("An order of 2000", (place / "features" / "discounts.feature").read_text(encoding="utf-8"))
            self.assertFalse((place / ".bdd" / ".runs").exists())


class TheSnapshotTest(AgainstRedCase):
    def test_uncommitted_production_source_at_the_red_is_kept_in_a_snapshot(self):
        self.write("src/app.py", WITHOUT + "VERSION = 2\n")           # changed, not committed, before the red
        self.walk_to("refine")
        self.bdd_run()
        red = self.bind()["red"]
        self.assertTrue(red["dirty"])
        self.assertTrue(redrecord.is_commit(red["snapshot"]))
        self.assertIn(red["snapshot"][:12], git(self.root, "for-each-ref", "refs/greenlight/red/"))
        self.gate("tasks")
        self.write("src/app.py", WITH)
        self.reopen_and_add_example()
        self.assertEqual(self.bdd_run("--against-red")[0], 0)
        self.assertTrue(self.verdict()["red"]["valid"])
        with againstred.red_worktree(self.root, againstred.baseline(self.data()), cfg.load(self.root)) as (place, _):
            self.assertIn("VERSION = 2", (place / "src" / "app.py").read_text(encoding="utf-8"))

    def test_making_the_snapshot_leaves_the_index_and_the_working_tree_alone(self):
        self.write("src/app.py", WITHOUT + "VERSION = 2\n")
        self.write("src/new.py", "x = 1\n")
        before = git(self.root, "status", "--porcelain")
        redrecord.capture(self.root, cfg.load(self.root).test_dirs, "FEAT-007")
        self.assertEqual(git(self.root, "status", "--porcelain"), before)
        self.assertEqual(git(self.root, "diff", "--cached", "--name-only"), "")

    def test_the_snapshot_holds_only_production_files(self):
        commit = redrecord.capture(self.root, cfg.load(self.root).test_dirs, "FEAT-007")["snapshot"]
        names = set(git(self.root, "ls-tree", "-r", "--name-only", commit).split())
        self.assertEqual(names, {".gitignore", "src/app.py"})


class RefusalTest(AgainstRedCase):
    def test_a_feature_without_a_red_has_nothing_to_run_against(self):
        self.walk_to("refine")
        code, _out, err = self.bdd_run("--against-red")
        self.assertEqual(code, 2)
        self.assertIn("has no recorded red", err)

    def test_an_adoption_has_no_red_to_reproduce(self):
        self.assertIn("adoption", againstred.problem({"feature": "FEAT-007", "kind": "adopt", "red": {"commit": "a"}}))

    def test_an_old_dirty_red_without_a_snapshot_cannot_be_checked_out(self):
        with self.assertRaises(UsageError) as refused:
            againstred.source_commit({"commit": "a" * 40, "dirty": True})
        self.assertIn("not committed", str(refused.exception))

    def test_a_source_that_is_not_the_one_of_the_red_is_refused(self):
        self.first_red_and_code()
        self.reopen_and_add_example()
        def tamper(data: dict) -> None:
            data["red_history"][-1]["red"]["source_hash"] = "0" * 64
        state.update(self.feature_dir, tamper)
        code, _out, err = self.bdd_run("--against-red")
        self.assertEqual(code, 2)
        self.assertIn("digest differs", err)
        self.assertEqual(git(self.root, "worktree", "list").count("\n"), 1)

    def test_a_run_against_another_red_does_not_back_the_bind_gate(self):
        self.first_red_and_code()
        self.reopen_and_add_example()
        self.bdd_run("--against-red")
        path = runner.latest_path(self.root, "FEAT-007")
        record = json.loads(path.read_text(encoding="utf-8"))
        record["against_red"]["commit"] = "b" * 40
        path.write_text(json.dumps(record), encoding="utf-8")
        with self.assertRaises(UsageError) as refused:
            self.bind()
        self.assertIn("another red", str(refused.exception))

    def test_against_red_is_one_plain_run(self):
        self.assertEqual(self.bdd_run("--against-red", "--shuffle")[0], 2)


if __name__ == "__main__":
    unittest.main()
