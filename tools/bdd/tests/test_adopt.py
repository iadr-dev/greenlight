import contextlib
import io
import os
import subprocess
import unittest

from bddlib import adopt, cli, lockfile, redrecord, state
from bddlib import config as cfg
from bddlib.errors import UsageError

from tests.helpers import SPEC, ProjectCase

EXISTING_SPEC = SPEC.replace("  @R-7.1 @EX-7.1.1\n", "  @R-7.1 @EX-7.1.1 @existing\n")


def git(root, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@example.com",
                    "-c", "gc.auto=0", "-c", "maintenance.auto=false", *args], check=True, capture_output=True)


class AdoptCase(ProjectCase):
    def setUp(self):
        super().setUp()
        self.write("app/pricing.py", "RATE = 0.1\n")
        git(self.root, "init", "-q")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "start")
        state.update(self.feature_dir, lambda data: data.__setitem__("kind", "adopt"))

    def bind(self) -> None:
        self.walk_to("refine")
        lockfile.lock(self.root, self.feature_dir, "FEAT-007", "bind", [self.step])
        self.gate("bind", red=redrecord.capture(self.root, cfg.load(self.root).test_dirs))

    def to_tasks(self) -> None:
        self.bind()
        self.gate("tasks")

    def problems(self) -> list[str]:
        return adopt.problems(self.root, self.data())

    def check(self) -> tuple[int, str, str]:
        out, err, here = io.StringIO(), io.StringIO(), os.getcwd()
        os.chdir(self.root)
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                return cli.main(["adopt", "FEAT-007", "--check"]), out.getvalue(), err.getvalue()
        finally:
            os.chdir(here)


class KindTest(ProjectCase):
    def test_a_feature_is_a_normal_feature_unless_it_is_created_as_an_adoption(self):
        self.assertEqual(self.data()["kind"], "feature")
        folder = state.create(self.root, "FEAT-008", "Existing pricing", "standard", "adopt")
        self.assertEqual(state.load(folder)["kind"], "adopt")
        with self.assertRaises(UsageError):
            state.create(self.root, "FEAT-009", "Other", "standard", "rewrite")

    def test_the_state_command_creates_one_and_shows_it(self):
        out, here = io.StringIO(), os.getcwd()
        os.chdir(self.root)
        try:
            with contextlib.redirect_stdout(out):
                self.assertEqual(cli.main(["state", "init", "FEAT-008", "--title", "Existing pricing", "--adopt"]), 0)
                self.assertEqual(cli.main(["state", "show", "FEAT-008"]), 0)
        finally:
            os.chdir(here)
        self.assertIn("kind: adopt", out.getvalue())


class AdoptProblemsTest(AdoptCase):
    def test_scenarios_must_all_be_existing(self):
        self.bind()
        self.assertEqual([p[:2] for p in self.problems()], ["A1"])
        self.spec.write_text(EXISTING_SPEC, encoding="utf-8", newline="\n")
        self.assertEqual(self.problems(), [])

    def test_the_production_source_must_be_pinned_by_the_bind_gate(self):
        self.spec.write_text(EXISTING_SPEC, encoding="utf-8", newline="\n")
        self.walk_to("refine")
        lockfile.lock(self.root, self.feature_dir, "FEAT-007", "bind", [self.step])
        self.gate("bind")
        self.assertEqual([p[:2] for p in self.problems()], ["A2"])

    def test_editing_production_code_afterwards_is_caught(self):
        self.spec.write_text(EXISTING_SPEC, encoding="utf-8", newline="\n")
        self.bind()
        self.write("app/pricing.py", "RATE = 0.2\n")
        self.assertEqual([p[:2] for p in self.problems()], ["A3"])
        self.write("app/pricing.py", "RATE = 0.1\n")
        self.assertEqual(self.problems(), [])

    def test_a_new_production_file_is_caught_too(self):
        self.spec.write_text(EXISTING_SPEC, encoding="utf-8", newline="\n")
        self.bind()
        self.write("app/extra.py", "X = 1\n")
        self.assertEqual([p[:2] for p in self.problems()], ["A3"])


class AdoptGateTest(AdoptCase):
    def test_implement_refuses_a_scenario_that_is_not_existing(self):
        self.to_tasks()
        with self.assertRaises(UsageError) as cm:
            self.gate("implement")
        self.assertIn("A1", str(cm.exception))

    def test_implement_passes_and_verify_refuses_after_a_production_edit(self):
        self.spec.write_text(EXISTING_SPEC, encoding="utf-8", newline="\n")
        self.to_tasks()
        self.assertEqual(self.gate("implement", detail={"adopt": "true"})["gates"]["implement"]["result"], "pass")
        self.write("app/pricing.py", "RATE = 0.3\n")
        with self.assertRaises(UsageError) as cm:
            self.gate("verify")
        self.assertIn("A3", str(cm.exception))

    def test_a_normal_feature_is_not_held_to_it(self):
        state.update(self.feature_dir, lambda data: data.__setitem__("kind", "feature"))
        self.to_tasks()
        self.assertEqual(self.gate("implement")["gates"]["implement"]["result"], "pass")


QUALITY_TABLE = "\n[adapters.quality.lint]\ncommand = '{python} -c \"raise SystemExit(1)\"'\n"      # would fail if it were run
MUTATION_TABLE = "\n[adapters.mutation]\ncommand = '{python} fake_mutator.py --report {out} {files}'\nthreshold = 80\n"


class AdoptIsNotHeldToChangeChecksTest(AdoptCase):
    """The code of an adoption already exists, so a quality check on it is not the adoption's business, and there is no
    red to measure a change from, so there is nothing to mutate."""

    def adopt_to_verify(self) -> None:
        self.spec.write_text(EXISTING_SPEC, encoding="utf-8", newline="\n")
        self.to_tasks()
        self.gate("implement", detail={"adopt": "true"})

    def test_quality_checks_do_not_stop_an_adopted_feature(self):
        self.config(tail=QUALITY_TABLE)
        self.adopt_to_verify()
        self.assertEqual(self.gate("verify")["phase"], "done")

    def test_the_same_quality_checks_stop_a_normal_feature(self):
        self.config(tail=QUALITY_TABLE)
        state.update(self.feature_dir, lambda data: data.__setitem__("kind", "feature"))
        self.to_tasks()
        with self.assertRaises(UsageError) as cm:
            self.gate("implement")
        self.assertIn("quality checks are configured but have not been run", str(cm.exception))

    def test_a_mutation_check_does_not_stop_an_adopted_feature(self):
        self.config(tail=MUTATION_TABLE)
        self.adopt_to_verify()
        self.assertEqual(self.gate("verify")["phase"], "done")

    def test_the_same_mutation_check_stops_a_normal_feature_at_verify(self):
        self.config(tail=MUTATION_TABLE)
        state.update(self.feature_dir, lambda data: data.__setitem__("kind", "feature"))
        self.to_tasks()
        self.gate("implement")
        with self.assertRaises(UsageError) as cm:
            self.gate("verify")
        self.assertIn("the mutation check is configured but has not been run", str(cm.exception))


class AdoptCommandTest(AdoptCase):
    def test_the_command_reports_and_sets_the_exit_code(self):
        self.bind()
        code, out, _ = self.check()
        self.assertEqual(code, 1)
        self.assertIn("A1", out)
        self.spec.write_text(EXISTING_SPEC, encoding="utf-8", newline="\n")
        code, out, _ = self.check()
        self.assertEqual((code, "production source unchanged" in out), (0, True))

    def test_a_normal_feature_is_refused(self):
        state.update(self.feature_dir, lambda data: data.__setitem__("kind", "feature"))
        code, _, err = self.check()
        self.assertEqual((code, "not an adoption feature" in err), (2, True))


if __name__ == "__main__":
    unittest.main()
