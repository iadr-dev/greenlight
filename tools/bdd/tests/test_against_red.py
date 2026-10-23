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
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from bddlib import againstred, changecmd, classify, folderlinks, lockfile, redrecord, runcmd, runner, state
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


class DependencyLinksTest(AgainstRedCase):
    """The installed folders (``node_modules`` and the like) reach the temporary worktree through links, and the links
    go away without touching the folders: on Windows a junction, because a symbolic link needs a privilege."""

    def setUp(self):
        super().setUp()
        self.first_red_and_code()
        self.reopen_and_add_example()
        self.marker = self.write("node_modules/pkg/marker.txt", "the real package\n")
        self.write(".venv/pyvenv.cfg", "home = elsewhere\n")

    def worktree(self):
        return againstred.red_worktree(self.root, againstred.baseline(self.data()), cfg.load(self.root))

    def refuse_links(self):
        """Neither a junction nor a symbolic link can be made, as on a Windows machine without the right."""
        denied = OSError("A required privilege is not held by the client")
        return _patched((folderlinks, "_junction", denied), (os, "symlink", denied))

    def test_the_folders_are_reachable_in_the_worktree_and_survive_its_removal(self):
        with self.worktree() as (place, linked):
            self.assertEqual(linked, ["node_modules", ".venv"])
            self.assertEqual((place / "node_modules" / "pkg" / "marker.txt").read_text(encoding="utf-8"),
                             "the real package\n")
            self.assertTrue(folderlinks.is_link(place / "node_modules"))
            holder = place.parent
        self.assertFalse(holder.exists())
        self.assertEqual(self.marker.read_text(encoding="utf-8"), "the real package\n")
        self.assertTrue((self.root / ".venv" / "pyvenv.cfg").is_file())

    @unittest.skipUnless(os.name == "nt", "a junction exists on Windows only")
    def test_on_windows_the_link_is_a_junction_which_needs_no_privilege(self):
        with self.worktree() as (place, _linked):
            link = place / "node_modules"
            self.assertFalse(link.is_symlink())          # a junction is not a symbolic link
            self.assertTrue(folderlinks.is_link(link))
            self.assertEqual(os.lstat(link).st_reparse_tag, stat.IO_REPARSE_TAG_MOUNT_POINT)
            self.assertTrue((link / "pkg" / "marker.txt").is_file())

    @unittest.skipUnless(os.name == "nt", "mklink exists on Windows only")
    def test_on_windows_mklink_makes_the_same_junction_without_a_shell_string(self):
        target = Path(self.enterContext(tempfile.TemporaryDirectory())) / "linked"
        folderlinks._mklink_junction((self.root / "node_modules").resolve(), target)
        self.assertTrue(folderlinks.is_link(target))
        self.assertTrue((target / "pkg" / "marker.txt").is_file())
        folderlinks.remove_link(target)
        self.assertTrue(self.marker.is_file())

    def test_a_path_cmd_would_read_as_syntax_is_not_passed_to_mklink(self):
        with self.assertRaises(UsageError):
            folderlinks._mklink_junction(Path("C:/a&b"), Path("C:/target"))

    def test_a_relative_path_is_refused(self):
        with self.assertRaises(UsageError):
            folderlinks.link_directory(Path("node_modules"), Path("elsewhere"))

    def test_a_folder_that_cannot_be_linked_stops_the_run_before_any_test_runs(self):
        before = self.latest()
        with self.refuse_links():
            code, _out, err = self.bdd_run("--against-red")
        self.assertEqual(code, 2)
        self.assertIn("cannot link the installed folder node_modules", err)
        self.assertIn("Nothing was run", err)
        self.assertIn("privilege", err)
        self.assertIn("Developer Mode" if os.name == "nt" else "TMPDIR", err)
        self.assertEqual(self.latest(), before)           # no run was recorded
        self.assertTrue(self.marker.is_file())
        self.assertEqual(git(self.root, "worktree", "list").count("greenlight-red-"), 0)

    def test_links_made_before_the_one_that_failed_are_removed_and_leave_their_folders(self):
        real = folderlinks.link_directory
        made = []

        def second_fails(source, target):
            if made:
                raise UsageError("cannot link the installed folder .venv: refused")
            made.append(real(source, target))
            return made[0]

        with mock.patch.object(folderlinks, "link_directory", second_fails), self.assertRaises(UsageError):
            with self.worktree():
                self.fail("the worktree must not be handed out")
        self.assertEqual(len(made), 1)
        self.assertTrue(self.marker.is_file())

    def test_the_folders_survive_when_removing_the_worktree_fails_half_way(self):
        real = redrecord.git

        def refuse_removal(root, *args, **kwargs):
            if args[:2] == ("worktree", "remove"):
                raise UsageError("the worktree could not be removed")
            return real(root, *args, **kwargs)

        with mock.patch.object(redrecord, "git", refuse_removal):
            with self.worktree() as (place, _linked):
                holder = place.parent
        self.assertFalse(holder.exists())
        self.assertEqual(self.marker.read_text(encoding="utf-8"), "the real package\n")

    def test_a_link_that_cannot_be_removed_keeps_the_worktree_and_the_folder(self):
        err = io.StringIO()
        with mock.patch.object(folderlinks, "remove_link", side_effect=OSError("in use")):
            with contextlib.redirect_stderr(err), self.worktree() as (place, _linked):
                holder = place.parent
        try:
            self.assertTrue(holder.exists())
            self.assertIn(str(place / "node_modules"), err.getvalue())
            self.assertEqual(self.marker.read_text(encoding="utf-8"), "the real package\n")
        finally:                                          # the test's own cleanup, link by link, then the folder
            for name in againstred.DEPENDENCY_DIRS:
                if folderlinks.is_link(place / name):
                    folderlinks.remove_link(place / name)
            redrecord.git(self.root, "worktree", "remove", "--force", str(place))
            shutil.rmtree(holder, ignore_errors=True)
        self.assertTrue(self.marker.is_file())

    def test_removing_a_link_leaves_what_it_points_at(self):
        target = Path(self.enterContext(tempfile.TemporaryDirectory())) / "linked"
        folderlinks.link_directory((self.root / "node_modules").resolve(), target)
        folderlinks.remove_link(target)
        self.assertFalse(target.exists())
        self.assertTrue(self.marker.is_file())

    def test_a_real_folder_is_never_removed_as_a_link(self):
        with self.assertRaises(OSError):
            folderlinks.remove_link(self.root / "node_modules")
        self.assertTrue(self.marker.is_file())

    def test_an_empty_result_says_which_folders_were_linked(self):
        self.assertIn("linked into the temporary worktree: node_modules, .venv", runcmd.links_note(["node_modules", ".venv"]))

    def test_an_empty_result_says_when_the_project_has_nothing_to_link(self):
        note = runcmd.links_note([])
        self.assertIn("none of node_modules", note)
        self.assertIn("install the project's dependencies", note)


def _patched(*changes):
    """Replace several attributes with functions that raise; an ExitStack of the patches."""
    stack = contextlib.ExitStack()
    for owner, name, error in changes:
        stack.enter_context(mock.patch.object(owner, name, side_effect=error))
    return stack


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
