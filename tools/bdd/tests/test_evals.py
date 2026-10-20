"""The evaluation collector and the summary table, on canned run directories (no model, no network)."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

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

    def test_cards_read_come_from_the_transcript_when_there_is_one(self):
        transcript = self.project / "session.jsonl"
        transcript.write_text('{"file_path": "C:\\\\plugin\\\\cards\\\\techniques\\\\decision-table.md"}\n'
                              '{"file_path": "/p/cards/practices/python.md"}\n', encoding="utf-8")
        self.assertEqual(collect.cards_read(transcript), ["practices/python.md", "techniques/decision-table.md"])
        self.assertIsNone(collect.cards_read(None))
        self.assertIsNone(collect.cards_read(self.project / "missing.jsonl"))


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

    def test_a_soft_arm_loads_a_plugin_whose_hooks_are_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            copy = run_e2e.plugin_directory(Path(tmp), "off")
            self.assertEqual(json.loads((copy / "hooks" / "hooks.json").read_text(encoding="utf-8")), {"hooks": {}})
            self.assertTrue((copy / "skills" / "feature" / "SKILL.md").is_file())
        self.assertEqual(run_e2e.plugin_directory(Path("unused"), "on"), run_e2e.REPO)


if __name__ == "__main__":
    unittest.main()
