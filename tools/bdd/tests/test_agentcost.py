"""What the agents cost: noted by the SubagentStop hook, collected into the feature's cost per phase, never estimated."""
import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from bddlib import agentcost, cli, reportcmd, state

from tests.helpers import ProjectCase

FIXTURES = Path(__file__).parent / "fixtures" / "transcript"
SESSION = "session"
AGENT = "aaa111"
DURATION_MS = 41384


class AgentCostCase(ProjectCase):
    def setUp(self):
        super().setUp()
        self.project_transcripts = self.transcripts / "some-project"        # inside the folders the tools search
        shutil.copytree(FIXTURES, self.project_transcripts)                  # session.jsonl and session/subagents/agent-aaa111.jsonl
        self.subagent_file = self.project_transcripts / SESSION / "subagents" / f"agent-{AGENT}.jsonl"

    def stop(self, agent_type: str = "greenlight:qa-designer", **extra) -> int:
        payload = {"hook_event_name": "SubagentStop", "session_id": SESSION, "cwd": str(self.root), "agent_id": AGENT,
                   "agent_type": agent_type, "transcript_path": str(self.project_transcripts / "session.jsonl"),
                   "duration_ms": DURATION_MS, **extra}
        with mock.patch("sys.stdin", io.StringIO(json.dumps(payload))):
            return agentcost.subagent_stop([])

    def cli(self, *argv: str) -> tuple[int, str, str]:
        out, err, here = io.StringIO(), io.StringIO(), os.getcwd()
        os.chdir(self.root)
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                try:
                    code = cli.main(list(argv))
                except SystemExit as exc:
                    code = exc.code
        finally:
            os.chdir(here)
        return code, out.getvalue(), err.getvalue()


class TokensTest(AgentCostCase):
    def test_each_model_reply_counts_once_and_cache_reads_do_not_count(self):
        # 8+20+1000 (one reply written as two lines) + 3+40+200 + 1+10
        self.assertEqual(agentcost.transcript_tokens(self.subagent_file), 1282)

    def test_a_transcript_that_cannot_be_read_is_unknown_and_not_zero(self):
        self.assertIsNone(agentcost.transcript_tokens(self.root / "nowhere.jsonl"))
        self.assertIsNone(agentcost.transcript_tokens(None))

    def test_the_subagent_transcript_is_looked_up_by_plain_ids_inside_the_transcript_folders(self):
        self.assertEqual(agentcost.find_subagent_transcript(SESSION, AGENT), self.subagent_file)
        for session, agent in ((SESSION, "../../escape"), ("../session", AGENT), (SESSION, "a/b"), ("", AGENT), (None, AGENT),
                               (SESSION, 7), (SESSION, "does-not-exist")):
            with self.subTest(session=session, agent=agent):
                self.assertIsNone(agentcost.find_subagent_transcript(session, agent))


class HookTest(AgentCostCase):
    def test_an_agent_of_the_plugin_is_noted_with_the_feature_and_phase_in_progress(self):
        self.assertEqual(self.stop(), 0)
        (note,) = agentcost.read_entries(self.root)
        self.assertEqual((note["agent_id"], note["session"], note["feature"], note["phase"], note["duration_ms"]),
                         (AGENT, SESSION, "FEAT-007", "discover", DURATION_MS))
        self.assertNotIn("transcript", note)                      # no path is kept: it is looked up again when it is read

    def test_other_agents_and_projects_without_greenlight_are_ignored(self):
        self.assertEqual(self.stop(agent_type="Explore"), 0)
        self.assertEqual(agentcost.read_entries(self.root), [])
        with tempfile.TemporaryDirectory() as outside:                   # not under the project, which would find its .bdd
            self.assertEqual(self.stop(cwd=outside), 0)
        self.assertEqual(agentcost.read_entries(self.root), [])

    def test_with_two_features_in_progress_the_owner_is_not_guessed(self):
        state.create(self.root, "FEAT-008", "Another", "standard")
        self.stop()
        (note,) = agentcost.read_entries(self.root)
        self.assertIsNone(note["feature"])

    def test_a_payload_that_is_not_a_note_does_not_stop_the_session(self):
        with mock.patch("sys.stdin", io.StringIO("[1, 2]")):
            self.assertEqual(agentcost.subagent_stop([]), 0)
        self.assertEqual(agentcost.read_entries(self.root), [])

    def test_a_note_that_cannot_be_written_is_reported_without_blocking(self):
        with mock.patch("sys.stdin", io.StringIO("not json")), contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(agentcost.subagent_stop([]), 1)       # 1 is shown and ignored; 2 would block
        self.assertIn("could not be noted", err.getvalue())

    def test_the_hook_is_registered_and_its_command_exists(self):
        hooks = json.loads((Path(__file__).resolve().parents[3] / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]
        commands = [h["command"] for group in hooks["SubagentStop"] for h in group["hooks"]]
        self.assertEqual(len(commands), 1)
        self.assertTrue(commands[0].endswith(" subagent-stop"))
        self.assertIn("subagent-stop", cli.COMMANDS)


class CollectTest(AgentCostCase):
    def test_the_cost_of_a_finished_agent_is_recorded_once_from_its_transcript(self):
        self.stop()
        lines = agentcost.collect(self.root, "FEAT-007")
        self.assertEqual(len(lines), 1)
        entry = self.data()["cost"]["discover"]
        self.assertEqual((entry["tokens"], entry["seconds"], entry["runs"]), (1282, 41.384, 1))
        self.assertEqual(agentcost.collect(self.root, "FEAT-007"), [])
        self.assertEqual(self.data()["cost"]["discover"]["runs"], 1)

    def test_without_a_duration_from_the_hook_the_time_comes_from_the_transcript(self):
        """Claude Code's SubagentStop payload carried no duration in real runs; the transcript's time stamps still do."""
        self.stop(duration_ms=None)
        agentcost.collect(self.root, "FEAT-007")
        self.assertEqual(self.data()["cost"]["discover"]["seconds"], 34.302)       # 02:02:45.698 to 02:03:20.000

    def test_the_duration_of_a_real_subagent_transcript(self):
        """An anonymised excerpt of a real one: user, attachment and assistant lines, every one with a time stamp."""
        excerpt = FIXTURES / "real-subagent-excerpt.jsonl"
        self.assertEqual(agentcost.transcript_seconds(excerpt), 60.816)            # 05:28:41.156 to 05:29:41.972
        self.assertEqual(agentcost.transcript_tokens(excerpt), 6351 * 2 + 2 * 2 + 16 + 294)

    def test_a_transcript_without_time_stamps_has_no_duration(self):
        empty = self.root / "no-stamps.jsonl"
        empty.write_text('{"type": "user"}\nnot json\n', encoding="utf-8")
        self.assertIsNone(agentcost.transcript_seconds(empty))
        self.assertIsNone(agentcost.transcript_seconds(None))

    def test_an_unreadable_transcript_records_the_time_and_says_so(self):
        self.subagent_file.unlink()
        self.stop()
        lines = agentcost.collect(self.root, "FEAT-007")
        self.assertIn("only the time is recorded", lines[0])
        self.assertEqual(self.data()["cost"]["discover"]["tokens"], 0)

    def test_a_forged_note_cannot_make_the_collector_read_another_file(self):
        self.stop()
        path = agentcost.agents_path(self.root)
        note = json.loads(path.read_text(encoding="utf-8"))
        note.update(transcript=str(self.root / "steps" / "steps.py"), session="../../steps", agent_id="x")
        path.write_text(json.dumps(note) + "\n", encoding="utf-8")
        self.assertIn("only the time is recorded", agentcost.collect(self.root, "FEAT-007")[0])

    def test_an_agent_without_an_owner_is_recorded_only_when_the_phase_is_given(self):
        state.create(self.root, "FEAT-008", "Another", "standard")
        self.stop()
        self.assertEqual(agentcost.collect(self.root, "FEAT-007"), [])
        self.assertEqual(self.data()["cost"], {})
        agentcost.collect(self.root, "FEAT-007", "test-design")
        self.assertEqual(self.data()["cost"]["test-design"]["tokens"], 1282)

    def test_an_agent_noted_for_another_feature_is_left_alone(self):
        self.stop()
        state.create(self.root, "FEAT-008", "Another", "standard")
        self.assertEqual(agentcost.collect(self.root, "FEAT-008"), [])

    def test_the_command_collects_and_refuses_figures_given_with_it(self):
        self.stop()
        code, out, _ = self.cli("cost", "FEAT-007", "--collect")
        self.assertEqual(code, 0)
        self.assertIn("1282 tokens", out)
        self.assertEqual(self.cli("cost", "FEAT-007", "--collect")[1].strip(), "FEAT-007: no finished agent is waiting to be recorded")
        self.assertEqual(self.cli("cost", "FEAT-007", "--collect", "--tokens", "5")[0], 2)
        self.assertEqual(self.cli("cost", "FEAT-007")[0], 2)                   # a phase is needed without --collect
        self.assertEqual(self.cli("cost", "FEAT-007", "--phase", "bind", "--tokens", "10", "--seconds", "2")[0], 0)


class MissingCostTest(AgentCostCase):
    def test_a_passed_phase_without_a_cost_record_is_named(self):
        self.gate("discover")
        self.assertEqual(agentcost.missing_cost(self.data()), ["discover"])
        row = reportcmd.feature_row(self.root, self.feature_dir)
        self.assertEqual(row["missing_cost"], ["discover"])
        self.assertIn("cost: FEAT-007 passed discover with no cost recorded", self.cli("status")[1])
        state.add_cost(self.feature_dir, "discover", 100, 1.0)
        self.assertEqual(agentcost.missing_cost(self.data()), [])
        self.assertNotIn("no cost recorded", self.cli("status")[1])

    def test_phases_the_orchestrator_does_itself_need_no_record(self):
        self.walk_to("tasks")
        self.assertNotIn("tasks", agentcost.missing_cost(self.data()))


if __name__ == "__main__":
    unittest.main()
