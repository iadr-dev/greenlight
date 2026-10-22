"""The evaluation collector and the summary table, on canned run directories (no model, no network)."""
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from bddlib import doctor

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "evals"))
import collect  # noqa: E402
import run_e2e  # noqa: E402

FEATURE_TEXT = """@FEAT-001
Feature: Discounts
  @R-001.1
  Rule: Big orders get 10% off
    @EX-001.1.1
    Scenario: Exactly 1000
      Given alice is signed in as member
      When alice calls place order with:
        | total |
        | 1000  |
      Then the request succeeds
"""
GOOD_STATE = {
    "phase": "done", "autonomy": {"level": "autopilot"}, "enforcement": {"level": "hard"},
    "gates": {"bind": {"result": "pass"}, "implement": {"result": "pass"}, "verify": {"result": "pass"}},
    "red": {"commit": "abc"}, "cost": {"bind": {"tokens": 1200, "seconds": 30.5}, "implement": {"tokens": 800, "seconds": 20}},
    "assumptions": [{"text": "The 1000 threshold is measured on the total before discount", "rationale": "as asked"},
                    {"text": "Amounts are rounded to 2 decimal places, half up", "rationale": ""}],
}
TRACE = {"rules": [{"id": "R-001.1", "examples": [{"id": "EX-001.1.1"}]}, {"id": "R-001.2", "examples": []}],
         "gaps": [{"code": "T001"}]}


def canned(outputs: dict):
    def read(*args):
        return outputs.get(args, (0, "{}"))
    return read


def outputs_for(overrides=None, feature="FEAT-001"):
    table = {
        ("status", "--json"): (0, json.dumps({"features": [{"feature": feature, "dir": "FEAT-001-discounts"}], "open_violations": 0})),
        ("state", "show", feature, "--json"): (0, json.dumps(GOOD_STATE)),
        ("trace", feature, "--json"): (0, json.dumps(TRACE)),
        ("classify", feature, "--json"): (0, json.dumps({"green": {"valid": True}})),
        ("classify", feature, "--run", "red", "--json"): (0, json.dumps({"red": {"valid": True}})),
        ("lock", feature, "--check", "--require"): (0, ""),
        ("lint", "--json"): (0, json.dumps({"issues": []})),
        ("approve", feature, "--verify"): (0, "rules: valid\nexamples: valid\n"),
    }
    table.update(overrides or {})
    return table


class CollectRowTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.project = Path(self.dir.name)
        (self.project / "tests" / "features").mkdir(parents=True)
        (self.project / "tests" / "features" / "a.feature").write_text(FEATURE_TEXT, encoding="utf-8")
        report = self.project / ".bdd" / "features" / "FEAT-001-discounts"
        report.mkdir(parents=True)
        (report / "report.md").write_text("# Report\n\nVerdict: PASS\n", encoding="utf-8")

    def row(self, overrides=None):
        answers = [{"id": "threshold", "about": ["1000"], "expect": ["before"]},
                   {"id": "rounding", "about": ["round"], "expect": ["2", "half"]},
                   {"id": "coupons", "about": ["coupon"], "expect": ["one"]}]
        return collect.collect_row(canned(outputs_for(overrides)), self.project, answers)

    def test_a_clean_run_is_measured_against_the_records(self):
        row = self.row()
        self.assertEqual((row["feature"], row["phase"], row["enforcement"]), ("FEAT-001", "done", "hard"))
        self.assertEqual(row["rules_with_examples_pct"], 50.0)
        self.assertEqual((row["valid_red_pct"], row["green_pct"]), (100.0, 100.0))
        self.assertEqual((row["locked_spec_violations"], row["forged_approvals"]), (0, 0))
        self.assertEqual(row["vocabulary_resolution_pct"], 100.0)
        self.assertEqual((row["tokens"], row["cost_recorded"], row["auditor_verdict"]), (2000, True, "PASS"))
        self.assertEqual(row["seconds_per_phase"], {"bind": 30.5, "implement": 20})
        self.assertEqual(row["trace_gaps"], ["T001"])

    def test_assumptions_are_scored_against_the_scripted_answers(self):
        agreement = self.row()["assumption_agreement"]
        self.assertEqual((agreement["agreed"], agreement["disagreed"], agreement["unanswered"]), (2, 0, 1))
        self.assertAlmostEqual(agreement["agreement_pct"], 66.7, places=1)

    def test_a_wrong_assumption_is_a_disagreement(self):
        state = dict(GOOD_STATE, assumptions=[{"text": "The 1000 threshold is measured on the total after discount"}])
        agreement = self.row({("state", "show", "FEAT-001", "--json"): (0, json.dumps(state))})["assumption_agreement"]
        self.assertEqual((agreement["agreed"], agreement["disagreed"]), (0, 1))

    def test_violations_forged_approvals_and_unresolved_steps_are_counted(self):
        lint = {"issues": [{"code": "L002"}, {"code": "L005"}]}
        row = self.row({
            ("lock", "FEAT-001", "--check", "--require"): (1, "FEAT-001: [spec] a.feature changed since it was locked\n"),
            ("status", "--json"): (0, json.dumps({"features": [{"feature": "FEAT-001", "dir": "FEAT-001-discounts"}], "open_violations": 2})),
            ("approve", "FEAT-001", "--verify"): (0, "rules: valid\nexamples: INVALID (not typed)\n"),
            ("lint", "--json"): (0, json.dumps(lint)),
        })
        self.assertEqual((row["locked_spec_violations"], row["forged_approvals"]), (3, 1))
        self.assertEqual(row["vocabulary_resolution_pct"], 66.7)         # 3 steps, 1 unresolved

    def test_a_red_or_green_that_never_happened_is_not_scored_as_a_failure(self):
        state = dict(GOOD_STATE, gates={}, red=None, phase="discover")
        row = self.row({("state", "show", "FEAT-001", "--json"): (0, json.dumps(state)),
                          ("classify", "FEAT-001", "--json"): (0, "{}"),
                          ("classify", "FEAT-001", "--run", "red", "--json"): (2, "")})
        self.assertIsNone(row["valid_red_pct"])
        self.assertIsNone(row["green_pct"])

    def test_a_project_without_a_feature_gives_a_short_row(self):
        row = collect.collect_row(canned({("status", "--json"): (0, json.dumps({"features": [], "open_violations": 0}))}), self.project)
        self.assertEqual(row, {"features": 0, "open_violations": 0})

    def test_cards_read_are_the_cards_the_agents_opened_with_a_reading_tool(self):
        """The shapes are those of a real run: the orchestrator's transcript, and one transcript per subagent beside it, where the
        cards are read (with ``cat`` in a Bash call or with Read). A prompt that names a card, or a Write of a file called like a
        card, is not a read."""
        shutil.copytree(Path(__file__).parent / "fixtures" / "transcript", self.project / "claude")
        transcript = self.project / "claude" / "session.jsonl"
        self.assertEqual(collect.cards_read(transcript), ["practices/python.md", "techniques/decision-table.md"])
        self.assertEqual(collect.cards_read(transcript.parent / "session" / "subagents" / "agent-aaa111.jsonl"),
                         ["practices/python.md", "techniques/decision-table.md"])
        self.assertIsNone(collect.cards_read(None))
        self.assertIsNone(collect.cards_read(self.project / "missing.jsonl"))

    def test_a_session_without_subagents_reads_no_cards_instead_of_failing(self):
        lone = self.project / "lone.jsonl"
        lone.write_text('{"type":"assistant","message":{"content":[{"type":"tool_use","name":"Bash","input":{"command":"ls"}}]}}\n'
                        "not json\n", encoding="utf-8")
        self.assertEqual(collect.cards_read(lone), [])


class TargetsAndTableTest(unittest.TestCase):
    def test_targets_compare_in_the_right_direction(self):
        self.assertEqual(collect.meets("valid_red_pct", 90.0), "ok")
        self.assertEqual(collect.meets("valid_red_pct", 89.9), "MISS")
        self.assertEqual(collect.meets("forged_approvals", 0), "ok")
        self.assertEqual(collect.meets("forged_approvals", 1), "MISS")
        self.assertEqual(collect.meets("green_pct", None), "-")
        self.assertEqual(collect.meets("tokens", 5), "-")

    def test_the_summary_groups_runs_and_marks_misses(self):
        rows = [
            {"arm": "plugin", "autonomy_requested": "autopilot", "hooks": "on", "model": "m", "valid_red_pct": 100.0,
             "green_pct": 100.0, "tokens": 10, "claude": {"total_cost_usd": 0.5}},
            {"arm": "plugin", "autonomy_requested": "autopilot", "hooks": "on", "model": "m", "valid_red_pct": 50.0,
             "green_pct": None, "tokens": 5, "claude": {"total_cost_usd": 0.25}},
            {"arm": "baseline", "hooks": "n/a", "model": "m", "claude": {}},
        ]
        lines = collect.summary_table(rows).splitlines()
        self.assertEqual(len(lines), 3)                                  # header and two groups
        plugin = next(line for line in lines if line.startswith("plugin"))
        self.assertIn("75 MISS", plugin)
        self.assertIn("100 ok", plugin)
        self.assertTrue(plugin.rstrip().endswith("0.75"))

    def test_rows_round_trip_through_json_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rows.jsonl"
            path.write_text(json.dumps({"arm": "plugin"}) + "\n\n" + json.dumps({"arm": "baseline"}) + "\n", encoding="utf-8")
            self.assertEqual([r["arm"] for r in collect.read_rows([path])], ["plugin", "baseline"])


class CommandLineTest(unittest.TestCase):
    def test_only_names_of_result_files_are_accepted(self):
        for argument in ("../secret.jsonl", "C:\\x\\rows.jsonl", "rows.txt", "a/b.jsonl"):
            with self.subTest(argument=argument):
                self.assertEqual(collect.main([argument]), 2)
        self.assertEqual(collect.main(["no-such-rows.jsonl"]), 2)

    def test_stored_rows_are_summarised_by_name(self):
        collect.RESULTS.mkdir(exist_ok=True)
        path = collect.RESULTS / "unit-test-rows.jsonl"
        path.write_text(json.dumps({"arm": "plugin", "model": "m"}) + "\n", encoding="utf-8")
        self.addCleanup(path.unlink)
        self.assertEqual(collect.main(["unit-test-rows.jsonl"]), 0)


class HarnessHelpersTest(unittest.TestCase):
    def test_usage_of_follow_up_prompts_is_added_up(self):
        total = {"total_cost_usd": 0.5, "num_turns": 3, "seconds": 10, "usage": {"input_tokens": 100}, "session_id": "s1"}
        merged = run_e2e.merge_usage(total, {"total_cost_usd": 0.25, "num_turns": 2, "seconds": 5, "exit": 0,
                                             "usage": {"input_tokens": 50, "service_tier": "standard"}, "result": "ok"})
        self.assertEqual((merged["total_cost_usd"], merged["num_turns"], merged["seconds"]), (0.75, 5, 15))
        self.assertEqual(merged["usage"], {"input_tokens": 150})
        self.assertEqual((merged["session_id"], merged["result"], merged["exit"]), ("s1", "ok", 0))
        self.assertEqual(run_e2e.tokens_reported(merged), 150)

    def test_the_waiting_command_is_found_in_the_status_text(self):
        self.assertEqual(run_e2e.WAITING.search("the person: /greenlight:approve FEAT-002 examples").groups(), ("FEAT-002", "examples"))
        self.assertIsNone(run_e2e.WAITING.search("the bind phase"))

    def test_lists_are_validated(self):
        self.assertEqual(run_e2e.parse_list("standard, autopilot", run_e2e.LEVELS, "autonomy"), ["standard", "autopilot"])
        with self.assertRaises(Exception):
            run_e2e.parse_list("turbo", run_e2e.LEVELS, "autonomy")

    def test_output_that_is_not_json_is_kept_as_raw_text(self):
        self.assertEqual(run_e2e.parse_output("not json")["raw"], "not json")
        self.assertEqual(run_e2e.parse_output('{"a": 1}'), {"a": 1})

    def test_the_plugin_a_run_loads_is_the_committed_tree_and_a_soft_arm_has_no_hooks(self):
        with tempfile.TemporaryDirectory() as tmp:
            hard = run_e2e.plugin_snapshot(Path(tmp) / "a", "on")
            soft = run_e2e.plugin_snapshot(Path(tmp) / "b", "off")
            committed = run_e2e.run([*run_e2e.GIT, "show", "HEAD:hooks/hooks.json"], run_e2e.REPO, dict(os.environ)).stdout
            self.assertEqual(json.loads((hard / "hooks" / "hooks.json").read_text(encoding="utf-8")), json.loads(committed))
            self.assertEqual(json.loads((soft / "hooks" / "hooks.json").read_text(encoding="utf-8")), {"hooks": {}})
            self.assertTrue((hard / "tools" / "bdd" / "bdd").is_file())
            self.assertFalse((hard / ".git").exists())
            self.assertFalse((Path(tmp) / "a" / "plugin.index").exists())          # the private index is gone again

    def test_an_uncommitted_change_in_the_checkout_does_not_reach_the_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            checkout = Path(tmp) / "checkout"
            checkout.mkdir()
            run_e2e.run([*run_e2e.GIT, "init", "-q"], checkout, dict(os.environ))
            (checkout / "hooks").mkdir()
            (checkout / "hooks" / "hooks.json").write_text('{"hooks": {"a": 1}}', encoding="utf-8")
            run_e2e.commit_all(checkout, dict(os.environ), "committed")
            (checkout / "hooks" / "hooks.json").write_text('{"hooks": {"edited": 1}}', encoding="utf-8")
            with mock.patch.object(run_e2e, "REPO", checkout):
                snapshot = run_e2e.plugin_snapshot(Path(tmp) / "run", "on")
                self.assertEqual(run_e2e.checkout_changes(), ["hooks/hooks.json"])
            self.assertEqual(json.loads((snapshot / "hooks" / "hooks.json").read_text(encoding="utf-8")), {"hooks": {"a": 1}})

    def test_the_run_has_its_own_codex_home_and_its_own_claude_folder_only_when_the_login_allows(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_folder = Path(tmp)
            with mock.patch.dict("os.environ", {"CLAUDE_CODE_USE_BEDROCK": "1"}):
                env = run_e2e.base_environment(run_folder)
            self.assertEqual(Path(env["CODEX_HOME"]), run_folder / "codex-home")
            self.assertEqual(Path(env["CLAUDE_CONFIG_DIR"]), run_folder / "claude-config")
            login_in_folder = {k: v for k, v in os.environ.items() if k not in run_e2e.ENVIRONMENT_AUTH + ("CLAUDE_CONFIG_DIR",)}
            with mock.patch.dict("os.environ", login_in_folder, clear=True):
                env = run_e2e.base_environment(run_folder)
            self.assertNotIn("CLAUDE_CONFIG_DIR", env)                             # the person's folder, with its login
        self.assertFalse(run_e2e.authenticates_through_environment({"CLAUDE_CODE_USE_BEDROCK": "0", "ANTHROPIC_API_KEY": ""}))

    def test_host_files_the_run_could_not_make_its_own_are_watched_for_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_folder = Path(tmp) / "run"
            env = {"CODEX_HOME": str(run_folder / "codex-home"), "CLAUDE_CONFIG_DIR": str(run_folder / "claude-config")}
            watched = {p.as_posix() for p in run_e2e.host_watched_files(env, run_folder)}
            self.assertEqual(watched, {(Path.home() / ".codex" / n).as_posix() for n in ("hooks.json", "config.toml")})
            env.pop("CLAUDE_CONFIG_DIR")
            self.assertIn((Path.home() / ".claude" / "settings.json").as_posix(),
                          {p.as_posix() for p in run_e2e.host_watched_files(env, run_folder)})
            host = Path(tmp) / "settings.json"
            host.write_text("{}", encoding="utf-8")
            before = run_e2e.digests([host, Path(tmp) / "absent.toml"])
            host.write_text('{"env": {}}', encoding="utf-8")
            self.assertEqual(run_e2e.changed_between(before, run_e2e.digests([host, Path(tmp) / "absent.toml"])), [host.as_posix()])


class ContaminationTest(unittest.TestCase):
    def violations(self, project: Path, items: list[dict]) -> None:
        folder = project / ".bdd" / ".integrity"
        folder.mkdir(parents=True)
        (folder / "violations.json").write_text(json.dumps({"schema": 1, "items": items}), encoding="utf-8")

    def test_a_violation_outside_the_run_is_foreign_and_one_inside_is_not(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_folder = Path(tmp).resolve()
            project = run_folder / "project"
            host = Path.home() / ".codex" / "config.toml"
            self.violations(project, [
                {"open": True, "path": host.as_posix(), "what": "enforcement file"},
                {"open": True, "path": (run_folder / "plugin" / "tools" / "bdd" / "bddlib" / "doctor.py").as_posix()},
                {"open": True, "path": "tests/features/a.feature", "what": "FEAT-001 spec lock"},
                {"open": False, "path": (Path.home() / ".claude" / "settings.json").as_posix()},
            ])
            self.assertEqual(collect.foreign_violations(project, [run_folder]), [host.as_posix()])

    def test_the_end_of_a_run_is_kept_in_the_row_cut_to_a_readable_length(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            folder = project / ".bdd" / "features" / "FEAT-001-x"
            folder.mkdir(parents=True)
            (folder / "report.md").write_text("Verdict: FINDINGS\n" + "x" * 9000, encoding="utf-8")
            notes = run_e2e.run_notes(project, {"result": "I stopped at verify. " + "y" * 9000})
            self.assertTrue(notes["final_message"].startswith("I stopped at verify."))
            self.assertTrue(notes["report"].startswith("Verdict: FINDINGS"))
            self.assertEqual((len(notes["final_message"]), len(notes["report"])), (run_e2e.NOTE_LIMIT, run_e2e.NOTE_LIMIT))

    def test_a_run_with_no_report_and_no_final_message_has_empty_notes(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(run_e2e.run_notes(Path(tmp), {}), {"final_message": ""})

    def test_a_project_without_violations_is_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(collect.foreign_violations(Path(tmp), []), [])

    def test_a_contaminated_run_is_left_out_of_the_targets_and_listed_apart(self):
        clean = {"arm": "plugin", "autonomy_requested": "autopilot", "hooks": "on", "model": "m", "run": 1,
                 "valid_red_pct": 100.0, "locked_spec_violations": 0, "tokens": 10, "claude": {"total_cost_usd": 1.0}}
        dirty = {**clean, "run": 2, "locked_spec_violations": 2, "contaminated": True,
                 "foreign_violations": ["C:/Users/x/.codex/config.toml"]}
        table = collect.summary_table([clean, dirty])
        plugin = next(line for line in table.splitlines() if line.startswith("plugin"))
        self.assertIn(" 1 ", plugin)                                             # one run counted
        self.assertIn("0 ok", plugin)
        self.assertIn("not counted: 1 run(s)", table)
        self.assertIn("run 2 (plugin, autopilot): C:/Users/x/.codex/config.toml", table)


class ApprovedStandardsTest(unittest.TestCase):
    """Each reference app brings standards its person approved; the product template stays a draft."""

    APPS = sorted({kind["app"] for kind in run_e2e.REQUEST_KINDS.values()})

    def test_every_app_has_approved_standards_with_nothing_left_to_fill_in(self):
        for app in self.APPS:
            with self.subTest(app=app):
                text = (run_e2e.APPS / app / run_e2e.STANDARDS).read_text(encoding="utf-8")
                self.assertIn("\nStatus: APPROVED\n", text)
                self.assertEqual(doctor.unfilled_placeholders(text), [])

    def test_doctor_calls_each_one_approved(self):
        for app in self.APPS:
            with self.subTest(app=app), tempfile.TemporaryDirectory() as tmp:
                project = Path(tmp)
                (project / ".bdd").mkdir()
                run_e2e.approve_standards(project, {"app": app})
                self.assertEqual(doctor.check_standards(project).status, "ok")

    def test_the_harness_puts_the_approved_file_in_place_of_the_draft(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / ".bdd").mkdir()
            draft = project / ".bdd" / run_e2e.STANDARDS
            draft.write_text((REPO / "templates" / "standards.md").read_text(encoding="utf-8"), encoding="utf-8")
            run_e2e.approve_standards(project, {"app": "shop-api"})
            self.assertEqual(draft.read_text(encoding="utf-8"),
                             (run_e2e.APPS / "shop-api" / run_e2e.STANDARDS).read_text(encoding="utf-8"))

    def test_an_app_without_one_keeps_the_draft(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / ".bdd").mkdir()
            draft = project / ".bdd" / run_e2e.STANDARDS
            draft.write_text("Status: DRAFT\n", encoding="utf-8")
            with mock.patch.object(run_e2e, "APPS", project / "no-apps"):
                run_e2e.approve_standards(project, {"app": "shop-api"})
            self.assertEqual(draft.read_text(encoding="utf-8"), "Status: DRAFT\n")

    def test_the_file_is_not_copied_into_the_project_root_with_the_app(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            run_e2e.copy_app("csv-tool", project)
            self.assertTrue((project / "go.mod").is_file())
            self.assertFalse((project / run_e2e.STANDARDS).exists())

    def test_the_product_template_is_still_a_draft(self):
        text = (REPO / "templates" / "standards.md").read_text(encoding="utf-8")
        status = [line for line in text.splitlines() if line.startswith("Status:")]
        self.assertEqual(status, ["Status: DRAFT"])
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / ".bdd").mkdir()
            (project / ".bdd" / run_e2e.STANDARDS).write_text(text, encoding="utf-8")
            self.assertIn("still a draft", doctor.check_standards(project).detail)


if __name__ == "__main__":
    unittest.main()
