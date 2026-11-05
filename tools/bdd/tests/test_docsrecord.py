"""`bdd docs`: the documentation a task was written from is on record, and the implement gate waits for it."""
import contextlib
import io
import json
import os
import unittest

from bddlib import docsrecord, gates, guard
from bddlib.errors import UsageError

from tests.helpers import ProjectCase

SPEC = """@FEAT-007
Feature: Discounts
  @R-007.1
  Rule: A banner
    @EX-007.1.1
    Scenario: S
      When alice opens the orders page
      Then alice sees the banner showing:
        | text |
        | hi   |
"""


class DocsCase(ProjectCase):
    def setUp(self):
        super().setUp()
        self.write("features/discounts.feature", SPEC)
        self.write(".bdd/features/FEAT-007-order-discounts/tasks.md", "## T-007.1 Banner\nCovers: EX-007.1.1\n")
        self.local_doc = self.write("docs/lib.md", "# lib 2.1\n")

    def add(self, **fields):
        base = {"task": "T-007.1", "library": "react", "version": "19.3.1", "source": "https://react.dev/reference"}
        base.update(fields)
        if base.get("none") is not None:                       # "no library" stands alone
            base.update(library=None, version=None, source=None)
        return docsrecord.add(self.root, self.feature_dir, "FEAT-007", base["task"], base.get("library"), base.get("version"),
                              base.get("source"), base.get("none"))


class AddTest(DocsCase):
    def test_a_record_keeps_the_task_the_library_its_version_and_the_source(self):
        entry = self.add()
        self.assertEqual((entry["task"], entry["kind"], entry["library"], entry["version"]), ("T-007.1", "doc", "react", "19.3.1"))
        self.assertEqual(docsrecord.entries(self.feature_dir)[0]["source"], "https://react.dev/reference")

    def test_a_file_that_exists_is_a_source_and_so_is_one_given_from_the_project_folder(self):
        self.add(source=str(self.local_doc))
        self.add(source="docs/lib.md")
        self.assertEqual(len(docsrecord.entries(self.feature_dir)), 2)

    def test_a_source_that_cannot_be_opened_is_refused(self):
        for source in ("from memory", "docs/missing.md", "http://react.dev", "https://", "ftp://react.dev/x", "recalled"):
            with self.subTest(source=source), self.assertRaises(UsageError) as refused:
                self.add(source=source)
            self.assertIn("the source must be an https address or a file that exists", str(refused.exception))
        self.assertEqual(docsrecord.entries(self.feature_dir), [])

    def test_a_record_needs_all_three_and_a_task_of_the_feature(self):
        for missing in ("library", "version", "source"):
            with self.subTest(missing=missing), self.assertRaises(UsageError):
                self.add(**{missing: None})
        with self.assertRaises(UsageError) as unknown:
            self.add(task="T-007.9")
        self.assertIn("is not a task of FEAT-007", str(unknown.exception))

    def test_none_stands_alone_and_needs_a_reason(self):
        self.assertEqual(self.add(none="arithmetic on the total only")["kind"], "none")
        with self.assertRaises(UsageError):
            self.add(none="no")
        with self.assertRaises(UsageError):                    # a library next to --none
            docsrecord.add(self.root, self.feature_dir, "FEAT-007", "T-007.1", "react", None, None, "but it cites a library")


class GateTest(DocsCase):
    def setUp(self):
        super().setUp()
        self.walk_to("tasks")

    def test_the_implement_gate_waits_for_a_record_of_every_task(self):
        self.assertEqual(len(docsrecord.problems(self.root, self.feature_dir, "FEAT-007")), 1)
        self.write_reviews()
        with self.assertRaises(UsageError) as refused:
            self.gate("implement", reviews=False)
        self.assertIn("T-007.1 has no documentation record", str(refused.exception))
        self.add(none="no library is called by the banner")
        self.assertEqual(docsrecord.problems(self.root, self.feature_dir, "FEAT-007"), [])
        self.gate("implement", reviews=False)
        self.assertEqual(self.data()["phase"], "verify")

    def test_examples_that_no_task_claims_need_a_record_for_the_whole_feature_task(self):
        self.write(".bdd/features/FEAT-007-order-discounts/tasks.md", "# Tasks\n")
        (problem,) = docsrecord.problems(self.root, self.feature_dir, "FEAT-007")
        self.assertIn("T-007.0", problem)

    def test_a_record_for_the_wrong_task_does_not_count(self):
        self.write(".bdd/features/FEAT-007-order-discounts/tasks.md",
                   "## T-007.1 A\nCovers: EX-007.1.1\n\n## T-007.2 B\nCovers: EX-007.1.2\n")
        self.write("features/discounts.feature", SPEC + "    @EX-007.1.2\n    Scenario: T\n      When alice runs export\n")
        self.add(none="task one calls no library")
        (problem,) = docsrecord.problems(self.root, self.feature_dir, "FEAT-007")
        self.assertIn("T-007.2", problem)


class GuardAndCommandTest(DocsCase):
    def test_only_the_cli_writes_the_record(self):
        path = str(self.feature_dir / docsrecord.RECORD)
        for agent in (None, "greenlight:implementer", "greenlight:ui-engineer", "Explore"):
            with self.subTest(agent=agent):
                payload = {"tool_name": "Write", "cwd": str(self.root), "tool_input": {"file_path": path, "content": "{}"}}
                if agent:
                    payload["agent_type"] = agent
                self.assertIn("managed by the bdd command line", guard.evaluate(payload) or "")
        shell = {"tool_name": "Bash", "cwd": str(self.root), "agent_type": "greenlight:implementer",
                 "tool_input": {"command": "echo '{}' > docs-consulted.json"}}
        self.assertIn("managed by the bdd command line", guard.evaluate(shell) or "")

    def test_the_command_records_and_lists(self):
        from bddlib import cli
        cwd = os.getcwd()
        os.chdir(self.root)
        try:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(cli.main(["docs", "FEAT-007", "--task", "T-007.1", "--library", "react", "--version", "19.3.1",
                                           "--source", "https://react.dev/reference"]), 0)
                self.assertEqual(cli.main(["docs", "FEAT-007", "--list"]), 0)
            self.assertIn("recorded: T-007.1 react 19.3.1", out.getvalue())
            self.assertIn("T-007.1  react 19.3.1  https://react.dev/reference", out.getvalue())
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                self.assertEqual(cli.main(["docs", "FEAT-007", "--task", "T-007.1", "--library", "react"]), 2)
            self.assertIn("needs --library, --version and --source", err.getvalue())
        finally:
            os.chdir(cwd)
        self.assertEqual(json.loads((self.feature_dir / docsrecord.RECORD).read_text(encoding="utf-8"))["entries"][0]["kind"], "doc")
