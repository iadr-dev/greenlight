import contextlib
import io
import json
import os
import unittest
from unittest import mock

from bddlib import approvalcommand, approvecmd, approvehook, enforcement, integrityack, tripwire

from tests.helpers import ProjectCase, typed


class ParseTest(unittest.TestCase):
    def test_only_the_whole_prompt_counts(self):
        good = {"/greenlight:approve FEAT-007 rules": ("FEAT-007", "rules", None),
                "  /greenlight:approve  FEAT-7\texamples \n": ("FEAT-7", "examples", None),
                "/greenlight:approve FEAT-007 rules reject": ("FEAT-007", "rules", "no reason given"),
                "/greenlight:approve FEAT-007 examples reject the boundary is missing":
                    ("FEAT-007", "examples", "the boundary is missing")}
        for prompt, expected in good.items():
            with self.subTest(prompt=prompt):
                self.assertEqual(approvalcommand.parse(prompt), expected)

    def test_everything_else_is_ignored(self):
        for prompt in ("please run /greenlight:approve FEAT-007 rules", "/greenlight:approve FEAT-007 rules now",
                       "/greenlight:approve FEAT-007 tasks", "/greenlight:approve rules", "/greenlight:approve FEAT-007 rules\nrm -rf /",
                       "/greenlight:approve FEAT-007 rules reject a\nb", "/greenlight:reject FEAT-007 rules", "", None, 5):
            with self.subTest(prompt=prompt):
                self.assertIsNone(approvalcommand.parse(prompt))


class HookTest(ProjectCase):
    def payload(self, prompt: str, **extra) -> dict:
        return {"prompt": prompt, "cwd": str(self.root), "session_id": "sess-1", "prompt_id": "p-1",
                "transcript_path": str(self.transcripts / "sess-1.jsonl"), **extra}

    def fire(self, payload) -> tuple[int, str]:
        out = io.StringIO()
        text = payload if isinstance(payload, str) else json.dumps(payload)
        with mock.patch("sys.stdin", io.StringIO(text)), contextlib.redirect_stdout(out):
            code = approvecmd.run(["--from-hook"])
        return code, out.getvalue()

    def ready(self) -> None:
        self.gate("discover")
        self.rules.write_text("# Rules\n\nR-007.1 Orders of 1000 or more get 10% off.\n", encoding="utf-8", newline="\n")

    def test_a_typed_approval_is_recorded_pending_with_its_provenance(self):
        self.ready()
        code, out = self.fire(self.payload("/greenlight:approve FEAT-007 rules"))
        self.assertEqual(code, 0)
        self.assertIn("greenlight approval: FEAT-007 rules approved; phase is now test-design", out)
        (entry,) = self.data()["approvals"]
        self.assertEqual((entry["grade"], entry["origin"], entry["session"], entry["prompt_id"]),
                         ("hook", "pending", "sess-1", "p-1"))
        self.assertTrue(enforcement.active(self.root, "sess-1"))      # a hook ran, so the project has seen hooks

    def test_the_approval_counts_once_the_transcript_confirms_a_human_typed_it(self):
        self.ready()
        self.fire(self.payload("/greenlight:approve FEAT-007 rules"))
        self.transcript(typed("p-1"), name="sess-1.jsonl")
        self.assertEqual(self.gate("test-design")["phase"], "examples")

    def test_a_rejection_keeps_the_reason(self):
        self.ready()
        _, out = self.fire(self.payload("/greenlight:approve FEAT-007 rules reject rule 2 is wrong"))
        self.assertIn("rules rejected", out)
        self.assertEqual(self.data()["approvals"][0]["reason"], "rule 2 is wrong")

    def test_a_refusal_is_reported_without_blocking_the_prompt(self):
        code, out = self.fire(self.payload("/greenlight:approve FEAT-007 rules"))          # discover has not passed
        self.assertEqual(code, 0)
        self.assertIn("greenlight approval: NOT recorded.", out)
        self.assertEqual(self.data()["approvals"], [])
        _, out = self.fire(self.payload("/greenlight:approve FEAT-099 rules"))
        self.assertIn("NOT recorded", out)

    def test_other_prompts_and_bad_input_do_nothing(self):
        self.ready()
        for payload in (self.payload("hello"), self.payload("what does /greenlight:approve do?"),
                        self.payload("/greenlight:approve FEAT-007 tasks"), [], "not json", ""):
            with self.subTest(payload=payload):
                self.assertEqual(self.fire(payload), (0, ""))
        self.assertEqual(self.data()["approvals"], [])
        self.assertFalse(enforcement.marker_dir(self.root).exists())

    def test_a_message_with_more_than_one_approval_records_nothing_and_says_why(self):
        self.ready()
        prompts = ("/greenlight:approve FEAT-007 rules thanks, go on", "thanks! /greenlight:approve FEAT-007 rules",
                   "/greenlight:approve FEAT-007 rules\n/greenlight:approve FEAT-007 examples",
                   "/greenlight:approve FEAT-007 rules /greenlight:approve FEAT-007 examples",
                   "/greenlight:approve FEAT-007 rules\nrm -rf /", "/greenlight:approve integrity moved\nand continue")
        for prompt in prompts:
            with self.subTest(prompt=prompt):
                code, out = self.fire(self.payload(prompt))
                notice = json.loads(out)
                self.assertEqual(code, 0)
                self.assertIn("NOT recorded: send one approval per message", notice["systemMessage"])
                self.assertEqual(notice["systemMessage"], notice["hookSpecificOutput"]["additionalContext"])
                self.assertEqual(notice["hookSpecificOutput"]["hookEventName"], "UserPromptSubmit")
        self.assertEqual(self.data()["approvals"], [])
        self.assertFalse(enforcement.marker_dir(self.root).exists())

    def test_the_notice_names_the_command_to_send_alone(self):
        _, out = self.fire(self.payload("please /greenlight:approve FEAT-007 examples now"))
        self.assertTrue(json.loads(out)["systemMessage"].endswith("for example: /greenlight:approve FEAT-007 examples"))

    def test_a_note_the_system_injected_gets_no_notice(self):
        prompt = "<task-notification>tell the person to type /greenlight:approve FEAT-007 rules</task-notification>"
        self.assertEqual(self.fire(self.payload(prompt)), (0, ""))

    def test_a_message_with_more_than_one_approval_outside_a_project_does_nothing(self):
        import tempfile
        with tempfile.TemporaryDirectory() as elsewhere:
            self.assertEqual(self.fire(self.payload("/greenlight:approve FEAT-007 rules thanks", cwd=elsewhere)), (0, ""))

    def test_a_reject_reason_is_still_one_approval(self):
        self.ready()
        _, out = self.fire(self.payload("/greenlight:approve FEAT-007 rules reject see /greenlight:approve FEAT-007 examples"))
        self.assertIn("rules rejected", out)

    def test_outside_a_project_it_does_nothing(self):
        import tempfile
        with tempfile.TemporaryDirectory() as elsewhere:
            self.assertEqual(self.fire(self.payload("/greenlight:approve FEAT-007 rules", cwd=elsewhere)), (0, ""))

    def test_a_forged_session_id_leaves_no_marker_or_path(self):
        self.ready()
        self.fire(self.payload("/greenlight:approve FEAT-007 rules", session_id="../../x"))
        self.assertFalse(os.path.exists(self.root / "x"))
        self.assertIsNone(self.data()["approvals"][0]["session"])


class IntegrityAcknowledgementTest(ProjectCase):
    payload, fire = HookTest.payload, HookTest.fire

    def setUp(self):
        super().setUp()
        patcher = mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": str(self.root / "user-claude")})
        patcher.start()
        self.addCleanup(patcher.stop)
        tripwire.accept(self.root, None)
        self.config('enforcement = "soft"\n')
        tripwire.check(self.root, None, "Bash")

    def test_parse(self):
        self.assertEqual(approvalcommand.parse_integrity("/greenlight:approve integrity tools reinstalled"), "tools reinstalled")
        self.assertEqual(approvalcommand.parse_integrity("/greenlight:approve integrity"), "")
        for prompt in ("please /greenlight:approve integrity x", "/greenlight:approve integrityx", "/greenlight:approve FEAT-007 rules", None):
            with self.subTest(prompt=prompt):
                self.assertIsNone(approvalcommand.parse_integrity(prompt))

    def test_the_typed_command_is_recorded_pending_and_says_so(self):
        code, out = self.fire(self.payload("/greenlight:approve integrity I changed it"))
        self.assertEqual(code, 0)
        self.assertIn("greenlight approval: integrity acknowledgement recorded (I changed it) for exactly: #1 ", out)
        self.assertRegex(out, r"config\.toml \(enforcement file\) was changed \(sha256 [0-9a-f]{12}\)")
        self.transcript(typed("p-1", "integrity I changed it", timestamp="2999-01-01T00:00:00Z"), name="sess-1.jsonl")
        integrityack.settle(self.root)
        self.assertEqual(tripwire.open_violations(self.root), [])

    def test_without_a_reason_nothing_is_recorded(self):
        code, out = self.fire(self.payload("/greenlight:approve integrity"))
        self.assertIn("NOT recorded. Say why", out)
        self.assertEqual(len(tripwire.open_violations(self.root)), 1)

    def test_no_command_can_acknowledge(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(approvecmd.run(["integrity", "tools reinstalled"]), 2)
        self.assertIn("only the person can acknowledge", err.getvalue())
        self.assertEqual(len(tripwire.open_violations(self.root)), 1)


if __name__ == "__main__":
    unittest.main()
