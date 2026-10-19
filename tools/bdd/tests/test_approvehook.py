import contextlib
import io
import json
import os
import unittest
from unittest import mock

from bddlib import approvalcommand, approvecmd, approvehook, enforcement

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
        for payload in (self.payload("hello"), self.payload("/greenlight:approve FEAT-007 rules please"), [], "not json", ""):
            with self.subTest(payload=payload):
                self.assertEqual(self.fire(payload), (0, ""))
        self.assertEqual(self.data()["approvals"], [])
        self.assertFalse(enforcement.marker_dir(self.root).exists())

    def test_outside_a_project_it_does_nothing(self):
        import tempfile
        with tempfile.TemporaryDirectory() as elsewhere:
            self.assertEqual(self.fire(self.payload("/greenlight:approve FEAT-007 rules", cwd=elsewhere)), (0, ""))

    def test_a_forged_session_id_leaves_no_marker_or_path(self):
        self.ready()
        self.fire(self.payload("/greenlight:approve FEAT-007 rules", session_id="../../x"))
        self.assertFalse(os.path.exists(self.root / "x"))
        self.assertIsNone(self.data()["approvals"][0]["session"])


if __name__ == "__main__":
    unittest.main()
