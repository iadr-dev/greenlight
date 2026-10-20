"""Features that span several repositories: the home, and members with their own scenarios, locks and recorded runs."""
import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from bddlib import approvals, cli, guard, lockfile, state, store, tripwire, workspace
from bddlib import config as cfg
from bddlib.errors import UsageError

from tests.helpers import ProjectCase

FIXTURES = Path(__file__).parent / "fixtures"
SPEC = "@FEAT-007\nFeature: {title}\n\n  @R-007.1\n  Rule: Big orders get 10% off\n\n    @EX-007.1.{n}\n    Scenario: {scenario}\n      Then the request succeeds\n"
RUN_TABLE = """
[adapters.run]
by_tag = '{python} fake_runner.py --tag {marker}'
report = '--out {out}'

[adapters.classify]
test_defect = ['ImportError']
expected_fail = ['AssertionError']
"""


def case(name: str, outcome: str, text: str = "") -> dict:
    return {"name": name, "outcome": outcome, "text": text}


RED = [case("test_web_shows_discount", "failed", "AssertionError: 404"), case("test_api_applies_discount", "failed", "AssertionError: 404")]
GREEN = [case("test_web_shows_discount", "passed"), case("test_api_applies_discount", "passed")]


def write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


class WorkspaceCase(ProjectCase):
    """FEAT-007 at home (the rules, the state, the report) and two member repositories that test their share of it."""

    def setUp(self):
        super().setUp()
        self.others = tempfile.TemporaryDirectory()
        self.addCleanup(self.others.cleanup)
        base = Path(self.others.name).resolve()
        self.web = self.make_member(base / "web", "Web shows discount", "Web", 1)
        self.api = self.make_member(base / "api", "Api applies discount", "Api", 2)
        self.config(tail=f'\n[workspace]\nweb = {json.dumps(str(self.web))}\napi = {json.dumps(str(self.api))}\n')

    def make_member(self, root: Path, scenario: str, title: str, n: int) -> Path:
        write(root, ".bdd/config.toml", '[[adapters]]\nname = "x"\nfeatures = "features"\nsteps = "steps"\n' + RUN_TABLE)
        write(root, "features/spec.feature", SPEC.format(title=title, scenario=scenario, n=n))
        write(root, "steps/steps.py", "def then_ok():\n    assert True\n")
        shutil.copy(FIXTURES / "fake_runner.py", root / "fake_runner.py")
        state.create(root, "FEAT-007", f"{title} part of discounts", "standard")
        return root

    def bdd(self, *argv: str, cases=None, cwd: Path | None = None) -> tuple[int, str, str]:
        out, err, here = io.StringIO(), io.StringIO(), os.getcwd()
        os.chdir(cwd or self.root)
        try:
            with mock.patch.dict(os.environ, {"FAKE_CASES": json.dumps(cases or RED)}), \
                    contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = cli.main(list(argv))
        finally:
            os.chdir(here)
        return code, out.getvalue(), err.getvalue()

    def lock_member(self, member: Path) -> None:
        feature_dir = store.find_feature_dir(member, "FEAT-007")
        lockfile.lock(member, feature_dir, "FEAT-007", "spec", [member / "features/spec.feature"])
        lockfile.lock(member, feature_dir, "FEAT-007", "bind", [member / "steps/steps.py"])

    def red_members(self) -> None:
        for name in ("web", "api"):
            self.assertEqual(self.bdd("--in", name, "run", "FEAT-007", cases=RED)[0], 0)
        for member in (self.web, self.api):
            self.lock_member(member)

    def refused(self, gate: str) -> str:
        with self.assertRaises(UsageError) as cm:
            self.gate(gate)
        return str(cm.exception)


class ConfigTest(WorkspaceCase):
    def test_members_are_read_and_resolved(self):
        names = {m.name: m.path for m in cfg.load(self.root).workspace}
        self.assertEqual(names, {"web": self.web, "api": self.api})

    def test_a_member_must_be_a_repository_of_its_own(self):
        for table in (f'web = {json.dumps(str(self.root))}', f'web = {json.dumps(str(self.root / "inside"))}',
                      f'web = {json.dumps(str(self.web))}\napi = {json.dumps(str(self.web / "sub"))}',
                      'Web = "../x"', 'web = ""', 'web = 3'):
            with self.subTest(table=table):
                self.config(tail="\n[workspace]\n" + table + "\n")
                with self.assertRaises(cfg.ConfigError):
                    cfg.load(self.root)

    def test_a_project_without_a_workspace_is_unchanged(self):
        self.config()
        self.assertEqual(cfg.load(self.root).workspace, ())
        self.assertEqual(self.bdd("workspace", "list")[1].strip(), "no workspace: this feature lives in one repository")


class ObservedTest(WorkspaceCase):
    def test_a_member_that_is_not_here_is_not_observed(self):
        shutil.rmtree(self.api)
        self.assertIn("does not exist", workspace.unobserved(workspace.find(self.root, "api")))
        code, out, _ = self.bdd("workspace", "list")
        self.assertEqual(code, 0)
        self.assertIn("NOT OBSERVED", out)

    def test_a_directory_that_is_not_a_project_is_not_observed(self):
        (self.web / ".bdd" / "config.toml").unlink()
        self.assertIn("not a greenlight project", workspace.unobserved(workspace.find(self.root, "web")))

    def test_a_data_folder_that_leads_out_of_the_repository_is_not_observed(self):
        elsewhere = Path(self.others.name) / "elsewhere"
        (elsewhere / "features").mkdir(parents=True)
        shutil.rmtree(self.api / ".bdd" / "features", ignore_errors=True)
        try:
            os.symlink(elsewhere / "features", self.api / ".bdd" / "features", target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("this platform does not allow creating symbolic links here")
        self.assertIn("leads out of the repository", workspace.unobserved(workspace.find(self.root, "api")))

    def test_an_unknown_member_and_a_repeated_flag_are_refused(self):
        code, _, err = self.bdd("--in", "nope", "status")
        self.assertEqual((code, "not a member" in err), (2, True))
        code, _, err = self.bdd("--in", "web", "--in", "api", "status")
        self.assertEqual((code, "cannot be repeated" in err), (2, True))


class AcrossRepositoriesTest(WorkspaceCase):
    def test_a_command_can_be_run_inside_a_member(self):
        code, out, _ = self.bdd("--in", "web", "run", "FEAT-007", cases=RED)
        self.assertEqual(code, 0)
        self.assertIn("FEAT-007: 1 run(s)", out)
        self.assertTrue((self.web / ".bdd" / ".runs" / "FEAT-007" / "latest.json").is_file())
        self.assertFalse((self.root / ".bdd" / ".runs").exists())

    def test_trace_can_include_the_scenarios_of_every_member(self):
        report = json.loads(self.bdd("trace", "FEAT-007", "--json", "--workspace")[1])
        paths = {s["path"] for rule in report["rules"] for e in rule["examples"] for s in e["scenarios"]}
        self.assertEqual(paths, {"features/discounts.feature", "web:features/spec.feature", "api:features/spec.feature"})

    def test_trace_says_when_a_member_is_not_observed(self):
        shutil.rmtree(self.api)
        report = json.loads(self.bdd("trace", "FEAT-007", "--json", "--workspace")[1])
        self.assertIn("T008", [g["code"] for g in report["gaps"]])

    def test_a_lock_check_can_cover_every_member(self):
        self.red_members()
        code, out, _ = self.bdd("lock", "FEAT-007", "--check", "--workspace")
        self.assertIn("== web ==", out)
        self.assertIn("== api ==", out)
        self.assertEqual(self.bdd("lock", "FEAT-007", "--check", "--workspace", "--require")[0], 1)    # home itself is not locked yet
        self.assertEqual(self.bdd("--in", "api", "lock", "FEAT-007", "--check", "--require")[0], 0)
        (self.api / "steps" / "steps.py").write_text("def then_ok():\n    assert 1\n", encoding="utf-8")
        self.assertEqual(self.bdd("--in", "api", "lock", "FEAT-007", "--check", "--require")[0], 1)

    def test_run_and_classify_cover_every_member(self):
        code, out, _ = self.bdd("run", "FEAT-007", "--workspace", cases=RED)
        self.assertEqual(code, 0, out)
        self.assertIn("== web ==", out)
        code, out, _ = self.bdd("classify", "FEAT-007", "--workspace", "--expect", "red", cases=RED)
        self.assertEqual(code, 0, out)

    def test_status_names_every_member(self):
        out = self.bdd("status", "--workspace")[1]
        self.assertIn("== web ==", out)
        self.assertIn("== api ==", out)


class GatesTest(WorkspaceCase):
    def test_the_bind_gate_waits_for_every_member_to_prove_its_red(self):
        self.walk_to("refine")
        self.lock_for_bind()
        self.assertIn("[web] FEAT-007 has not been run yet", self.refused("bind"))
        self.bdd("--in", "web", "run", "FEAT-007", cases=RED)
        message = self.refused("bind")
        self.assertNotIn("[web]", message)
        self.assertIn("[api]", message)
        self.bdd("--in", "api", "run", "FEAT-007", cases=GREEN)
        self.assertIn("[api] the recorded run is not a valid red", self.refused("bind"))

    def lock_for_bind(self) -> None:
        lockfile.lock(self.root, self.feature_dir, "FEAT-007", "bind", [self.step])

    def test_a_member_that_is_not_here_blocks_the_gate(self):
        self.walk_to("refine")
        self.lock_for_bind()
        self.red_members()
        shutil.rmtree(self.web)
        self.assertIn("[web] not observed here", self.refused("bind"))

    def test_the_whole_feature_goes_green_across_three_repositories(self):
        self.walk_to("refine")
        self.lock_for_bind()
        self.red_members()
        data = self.gate("bind")
        self.assertEqual(set(data["members_red"]), {"web", "api"})
        for name in ("web", "api"):
            self.assertTrue((Path(self.others.name) / name / ".bdd" / ".runs" / "FEAT-007" / "red.json").is_file())
        self.gate("tasks")
        self.gate("implement")
        self.assertIn("is not a valid green", self.refused("verify"))
        for name in ("web", "api"):
            self.bdd("--in", name, "run", "FEAT-007", cases=GREEN)
        self.assertEqual(self.gate("verify")["phase"], "done")
        self.assertEqual(self.bdd("workspace", "check", "FEAT-007")[0], 0)

    def test_a_broken_lock_in_a_member_blocks_the_implement_gate(self):
        self.walk_to("refine")
        self.lock_for_bind()
        self.red_members()
        self.gate("bind")
        self.gate("tasks")
        (self.web / "steps" / "steps.py").write_text("def then_ok():\n    assert 1 == 1\n", encoding="utf-8")
        self.assertIn("[web] [bind] steps/steps.py changed since it was locked", self.refused("implement"))

    def test_an_open_integrity_violation_in_a_member_blocks_the_gate(self):
        self.walk_to("refine")
        self.lock_for_bind()
        self.red_members()
        self.gate("bind")
        self.gate("tasks")
        item = {"id": 1, "kind": "changed", "path": "x", "what": "enforcement file", "open": True}
        store.write_json(self.api / ".bdd" / ".integrity" / "violations.json", {"schema": 1, "items": [item]})
        self.assertIn("[api] integrity violation #1 is open", self.refused("implement"))

    def test_the_red_kept_in_a_member_cannot_be_replaced(self):
        self.walk_to("refine")
        self.lock_for_bind()
        self.red_members()
        self.gate("bind")
        self.gate("tasks")
        kept = self.web / ".bdd" / ".runs" / "FEAT-007" / "red.json"
        kept.write_text(kept.read_text(encoding="utf-8").replace('"mode": "all"', '"mode": "forged"'), encoding="utf-8")
        self.assertIn("[web] the kept red run of FEAT-007 does not match", self.refused("implement"))


class ProtectionTest(WorkspaceCase):
    def write_payload(self, path: Path, agent: str | None = None) -> dict:
        payload = {"tool_name": "Write", "cwd": str(self.root), "tool_input": {"file_path": str(path)}}
        if agent:
            payload["agent_type"] = f"greenlight:{agent}"
        return payload

    def test_the_guard_protects_what_a_member_has_locked(self):
        self.lock_member(self.web)
        reason = guard.evaluate(self.write_payload(self.web / "features" / "spec.feature"))
        self.assertIn("locked", reason)
        self.assertIsNone(guard.evaluate(self.write_payload(self.root / "notes.txt")))

    def test_the_guard_keeps_a_members_data_to_the_command_line(self):
        reason = guard.evaluate(self.write_payload(self.api / ".bdd" / "features" / "FEAT-007-x" / "state.json"))
        self.assertIn("managed", reason)

    def test_the_guard_applies_the_agents_limits_in_a_member(self):
        self.assertIsNotNone(guard.evaluate(self.write_payload(self.api / "src" / "app.py", "step-engineer")))
        self.assertIsNone(guard.evaluate(self.write_payload(self.api / "src" / "app.py", "implementer")))

    def test_the_tripwire_sees_a_locked_file_changed_in_a_member(self):
        self.lock_member(self.api)
        self.assertEqual(tripwire.lock_findings(self.root), [])
        (self.api / "steps" / "steps.py").write_text("def then_ok():\n    assert 2\n", encoding="utf-8")
        found = tripwire.lock_findings(self.root)
        self.assertEqual([(f["kind"], f["what"]) for f in found], [("changed", "api: FEAT-007 bind lock")])


class ApprovalBindingTest(WorkspaceCase):
    """The examples approved at home cover what the members contribute, so their specs cannot be swapped quietly."""

    def approved(self) -> dict:
        self.walk_to("examples")
        return self.data()

    def problems(self) -> list[str]:
        return approvals.effective_problems(self.root, self.data(), "examples")

    def test_the_approval_covers_each_members_feature_files_and_configuration(self):
        last = self.approved()["approvals"][-1]
        self.assertEqual(sorted(k for k in last["artifacts"] if k.startswith("@")),
                         ["@api/.bdd/config.toml", "@api/features/spec.feature",
                          "@web/.bdd/config.toml", "@web/features/spec.feature"])
        self.assertEqual(self.problems(), [])

    def test_a_member_spec_that_is_unlocked_edited_and_locked_again_needs_a_new_approval(self):
        self.approved()
        feature_dir = store.find_feature_dir(self.web, "FEAT-007")
        self.lock_member(self.web)
        lockfile.unlock(feature_dir, "FEAT-007", "spec", "swap the scenario")
        (self.web / "features" / "spec.feature").write_text(SPEC.format(title="Web", scenario="Something else", n=1),
                                                            encoding="utf-8", newline="\n")
        lockfile.lock(self.web, feature_dir, "FEAT-007", "spec", [self.web / "features" / "spec.feature"])
        self.assertEqual(self.problems(), ["@web/features/spec.feature changed after the examples approval; "
                                           "it has to be approved again"])

    def test_a_changed_member_configuration_needs_a_new_approval(self):
        self.approved()
        with (self.api / ".bdd" / "config.toml").open("a", encoding="utf-8") as handle:
            handle.write("\n# quietly loosened\n")
        self.assertIn("@api/.bdd/config.toml changed after the examples approval", self.problems()[0])

    def test_a_member_dropped_from_the_workspace_invalidates_the_approval(self):
        self.approved()
        self.config(tail=f'\n[workspace]\nweb = {json.dumps(str(self.web))}\n')
        self.assertTrue(any("@api/" in p for p in self.problems()))

    def test_examples_cannot_be_approved_while_a_member_is_not_observed(self):
        shutil.rmtree(self.api)
        with self.assertRaises(UsageError) as cm:
            self.walk_to("examples")
        self.assertIn("api is not observed here", str(cm.exception))


class FailClosedTest(WorkspaceCase):
    def payload(self, path: Path, agent: str | None = None) -> dict:
        payload = {"tool_name": "Write", "cwd": str(self.root), "tool_input": {"file_path": str(path)}}
        if agent:
            payload["agent_type"] = f"greenlight:{agent}"
        return payload

    def test_a_member_that_does_not_exist_yet_is_protected_all_the_same(self):
        shutil.rmtree(self.web)
        for name in ("config.toml", "standards.md", "features/FEAT-007-x/state.json"):
            with self.subTest(name=name):
                self.assertIn("greenlight", guard.evaluate(self.payload(self.web / ".bdd" / name)))
        self.assertIsNotNone(guard.evaluate(self.payload(self.web / "src" / "app.py", "product-analyst")))

    def test_a_member_without_a_data_folder_is_protected_the_same_way(self):
        shutil.rmtree(self.api / ".bdd")
        self.assertIn("greenlight", guard.evaluate(self.payload(self.api / ".bdd" / "config.toml")))

    def test_a_member_whose_feature_has_no_state_backs_no_gate(self):
        self.walk_to("refine")
        lockfile.lock(self.root, self.feature_dir, "FEAT-007", "bind", [self.step])
        self.red_members()
        state.path_of(store.find_feature_dir(self.web, "FEAT-007")).unlink()
        self.assertIn("[web]", self.refused("bind"))

    def test_the_tripwire_watches_every_members_configuration(self):
        baseline = tripwire.snapshot(self.root, None)
        configs = {(m / ".bdd" / "config.toml").resolve().as_posix() for m in (self.web, self.api)}
        self.assertTrue(configs <= set(baseline))
        with (self.web / ".bdd" / "config.toml").open("a", encoding="utf-8") as handle:
            handle.write("\n# changed\n")
        found = tripwire.baseline_findings(self.root, None, baseline)
        self.assertEqual([(f["kind"], Path(f["path"]).name) for f in found], [("changed", "config.toml")])


if __name__ == "__main__":
    unittest.main()
