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


class AttributionTest(AgentCostCase):
    """With several features in progress, an agent belongs to the one in progress that its task names."""

    def setUp(self):
        super().setUp()
        state.create(self.root, "FEAT-008", "Another", "standard")

    def agent(self, agent_id: str, task: object) -> None:
        folder = self.project_transcripts / SESSION / "subagents"
        lines = [{"type": "user", "timestamp": "2026-11-08T10:00:00.000Z", "message": {"role": "user", "content": task}},
                 {"type": "assistant", "timestamp": "2026-11-08T10:00:20.000Z",
                  "message": {"id": f"msg_{agent_id}", "role": "assistant", "usage": {"input_tokens": 7, "output_tokens": 3}}}]
        (folder / f"agent-{agent_id}.jsonl").write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")

    def stop_as(self, agent_id: str, task: object, agent_type: str = "greenlight:product-analyst") -> dict:
        self.agent(agent_id, task)
        self.stop(agent_type=agent_type, agent_id=agent_id, duration_ms=None)
        return next(n for n in agentcost.read_entries(self.root) if n["agent_id"] == agent_id)

    def test_the_task_names_the_feature_and_the_note_takes_its_phase(self):
        self.gate("discover")
        note = self.stop_as("bbb", "FEAT-008 discover: run the discover playbook")
        self.assertEqual((note["feature"], note["phase"]), ("FEAT-008", "discover"))
        note = self.stop_as("ccc", [{"type": "text", "text": "FEAT-007 specify: write the rules"}])
        self.assertEqual((note["feature"], note["phase"]), ("FEAT-007", "specify"))

    def test_each_feature_collects_its_own_agents(self):
        self.stop_as("bbb", "FEAT-008 discover: run the discover playbook")
        self.stop_as("ccc", "FEAT-007 discover: run the discover playbook")
        self.assertEqual(agentcost.collect(self.root, "FEAT-008"), ["bbb (greenlight:product-analyst) discover: 10 tokens, 20 s"])
        self.assertEqual(agentcost.collect(self.root, "FEAT-007"), ["ccc (greenlight:product-analyst) discover: 10 tokens, 20 s"])
        self.assertEqual(self.data()["cost_agents"], ["ccc"])

    def test_a_task_that_names_two_features_in_progress_or_none_is_not_guessed(self):
        for agent_id, task in (("bbb", "FEAT-007 and FEAT-008: compare them"), ("ccc", "run the discover playbook")):
            with self.subTest(task=task):
                self.assertIsNone(self.stop_as(agent_id, task)["feature"])

    def test_a_feature_that_is_done_or_unknown_does_not_count_as_named(self):
        self.assertIsNone(self.stop_as("bbb", "FEAT-001 discover: an id from another project")["feature"])
        note = self.stop_as("ccc", "FEAT-008 discover, as FEAT-001 did")
        self.assertEqual(note["feature"], "FEAT-008")

    def test_an_agent_noted_without_an_owner_is_claimed_by_the_feature_its_task_names(self):
        """Notes written before tasks were read (the Fieldly run) have no owner; the task still tells them apart."""
        self.agent("bbb", "FEAT-008 discover: run the discover playbook")
        path = agentcost.agents_path(self.root)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"agent_id": "bbb", "session": SESSION, "agent": "greenlight:product-analyst",
                                    "feature": None, "phase": None, "duration_ms": 0}) + "\n", encoding="utf-8")
        self.assertEqual(agentcost.collect(self.root, "FEAT-007", "discover"), [])
        self.assertIn("no phase known", agentcost.collect(self.root, "FEAT-008")[0])
        self.assertIn("discover: 10 tokens", agentcost.collect(self.root, "FEAT-008", "discover")[0])

    def test_an_agent_without_an_owner_is_recorded_for_one_feature_only(self):
        self.stop_as("bbb", "run the discover playbook")
        self.assertIn("discover: 10 tokens", agentcost.collect(self.root, "FEAT-007", "discover")[0])
        self.assertEqual(agentcost.collect(self.root, "FEAT-008", "discover"), [])

    def test_the_task_is_the_first_user_message_of_the_agent_transcript(self):
        self.assertEqual(agentcost.task_text(self.subagent_file), "Run the test-design playbook for FEAT-001")
        self.assertEqual(agentcost.task_text(None), "")
        self.assertEqual(agentcost.task_text(self.root / "nowhere.jsonl"), "")


class OrchestratorTest(AgentCostCase):
    """Claude Code's own count of the session that started the agents is shown, never recorded (D37)."""

    def test_the_session_of_the_recorded_agents_is_counted_from_its_main_transcript(self):
        self.stop()
        agentcost.collect(self.root, "FEAT-007")
        figure = agentcost.orchestrator_tokens(self.root, self.data())
        self.assertEqual(figure, {"sessions": 1, "found": 1, "tokens": 5 + 300 + 9000 + 2 + 90 + 400})
        self.assertEqual(self.data()["cost"]["discover"]["tokens"], 1282)            # the record holds the agents only
        text = agentcost.describe_orchestrator(figure)
        self.assertIn("Orchestrator session: 9,797 tokens, Claude Code's own count", text)
        self.assertIn("not part of the recorded cost", text)

    def test_a_subagent_reply_in_the_session_transcript_is_not_the_sessions_own(self):
        session = self.project_transcripts / "session.jsonl"
        sidechain = {"type": "assistant", "isSidechain": True,
                     "message": {"id": "msg_side", "usage": {"input_tokens": 100000}}}
        session.write_text(session.read_text(encoding="utf-8") + json.dumps(sidechain) + "\n", encoding="utf-8")
        self.assertEqual(agentcost.transcript_tokens(session, main_thread=True), 9797)
        self.assertEqual(agentcost.transcript_tokens(session), 109797)

    def test_without_noted_agents_or_transcripts_the_figure_is_not_known(self):
        self.assertIsNone(agentcost.orchestrator_tokens(self.root, self.data()))
        self.assertIn("not known", agentcost.describe_orchestrator(None))
        self.stop()
        agentcost.collect(self.root, "FEAT-007")
        (self.project_transcripts / "session.jsonl").unlink()
        figure = agentcost.orchestrator_tokens(self.root, self.data())
        self.assertEqual(figure, {"sessions": 1, "found": 0, "tokens": 0})
        self.assertIn("could not be found", agentcost.describe_orchestrator(figure))

    def test_status_and_the_report_show_it_next_to_the_record(self):
        self.stop()
        agentcost.collect(self.root, "FEAT-007")
        status = self.cli("status")[1]
        self.assertIn("cost: FEAT-007 1,282 tokens, 41.4 s recorded; orchestrator session 9,797 tokens, "
                      "Claude Code's own count, not recorded", status)
        page = self.cli("report", "FEAT-007")[1]
        self.assertIn("Orchestrator session: 9,797 tokens", page)
        self.assertIn("Orchestrator session: 9,797 tokens", self.cli("pr", "FEAT-007")[1])


class AmendTest(AgentCostCase):
    """A wrong figure is corrected with a reason; the figure it replaces stays on record."""

    def test_a_correction_replaces_the_figure_and_keeps_the_original(self):
        state.add_cost(self.feature_dir, "test-design", 150000, 12.0)
        code, out, _ = self.cli("cost", "FEAT-007", "--amend", "test-design", "--tokens", "30000", "--reason", "typed by hand")
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "FEAT-007 test-design: 150,000 tokens, 12.0 s corrected to 30,000 tokens, 12.0 s")
        data = self.data()
        self.assertEqual(data["cost"]["test-design"], {"tokens": 30000, "seconds": 12.0, "runs": 1})
        (amendment,) = data["cost_amendments"]
        self.assertEqual((amendment["was"], amendment["now"], amendment["reason"]),
                         ({"tokens": 150000, "seconds": 12.0}, {"tokens": 30000, "seconds": 12.0}, "typed by hand"))
        self.assertIn("1 correction(s)", self.cli("status")[1])
        self.assertIn("1 correction(s)", self.cli("state", "show", "FEAT-007")[1])
        self.assertIn("test-design corrected from 150,000 tokens, 12.0 s: typed by hand (now 30,000 tokens, 12.0 s)", self.cli("report", "FEAT-007")[1])

    def test_a_second_correction_keeps_both(self):
        state.add_cost(self.feature_dir, "bind", 100, 10.0)
        state.amend_cost(self.feature_dir, "bind", None, 4.5, "the hook gave no time")
        state.amend_cost(self.feature_dir, "bind", 90, None, "a reply was counted twice")
        data = self.data()
        self.assertEqual(data["cost"]["bind"]["tokens"], 90)
        self.assertEqual(data["cost"]["bind"]["seconds"], 4.5)
        self.assertEqual([a["was"] for a in data["cost_amendments"]], [{"tokens": 100, "seconds": 10.0}, {"tokens": 100, "seconds": 4.5}])

    def test_a_correction_needs_a_reason_figures_and_a_recorded_phase(self):
        state.add_cost(self.feature_dir, "bind", 100, 10.0)
        cases = ((["--amend", "bind", "--tokens", "5"], "a correction needs --reason"),
                 (["--amend", "bind", "--tokens", "5", "--reason", "   "], "a correction needs --reason"),
                 (["--amend", "bind", "--reason", "why"], "needs --tokens, --seconds or both"),
                 (["--amend", "bind", "--tokens", "-1", "--reason", "why"], "cannot be negative"),
                 (["--amend", "verify", "--tokens", "5", "--reason", "why"], "no cost recorded for verify; phases with a cost: bind"))
        for argv, message in cases:
            with self.subTest(argv=argv):
                code, _, err = self.cli("cost", "FEAT-007", *argv)
                self.assertEqual(code, 2)
                self.assertIn(message, err)
        self.assertEqual(self.data()["cost"]["bind"]["tokens"], 100)
        self.assertNotIn("cost_amendments", self.data())

    def test_amend_does_not_mix_with_the_other_ways_of_recording(self):
        for argv in (["--amend", "bind", "--collect", "--reason", "x"], ["--amend", "bind", "--phase", "bind", "--reason", "x"],
                     ["--phase", "bind", "--tokens", "5", "--reason", "x"]):
            with self.subTest(argv=argv):
                self.assertEqual(self.cli("cost", "FEAT-007", *argv)[0], 2)


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
