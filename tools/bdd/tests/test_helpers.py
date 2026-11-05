"""`bdd helpers`: which helper plugins are installed, the line the person types to install the rest, and the rules that keep
an agent from installing anything."""
import contextlib
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from bddlib import doctor, guard, helpers

FIRST = helpers.CATALOG[0]


def listing(*entries: dict) -> object:
    """A stand-in for subprocess.run that answers `claude plugin list --json`."""
    def fake(command, **_):
        return SimpleNamespace(returncode=0, stdout=json.dumps(list(entries)), stderr="")
    return fake


def plugin(plugin_id: str, scope: str = "user", enabled: bool = True, **extra) -> dict:
    return {"id": plugin_id, "version": "1.0.0", "scope": scope, "enabled": enabled, **extra}


class InstalledTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(helpers, "claude_program", return_value="claude")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_plugin_on_for_the_user_or_the_project_counts_and_a_disabled_one_does_not(self):
        found = helpers.installed(listing(
            plugin(FIRST.id), plugin("context7@claude-plugins-official", enabled=False),
            plugin("microsoft-docs@claude-plugins-official", scope="project", projectEnabled=True),
            plugin("feature-dev@claude-plugins-official", scope="project", projectEnabled=False)))
        self.assertEqual(sorted(found), sorted([FIRST.id, "microsoft-docs@claude-plugins-official"]))

    def test_nothing_is_known_when_claude_is_missing_or_its_answer_is_not_the_list(self):
        with mock.patch.object(helpers, "claude_program", return_value=None):
            self.assertIsNone(helpers.installed(listing()))
        self.assertIsNone(helpers.installed(lambda *a, **k: SimpleNamespace(returncode=1, stdout="[]", stderr="boom")))
        self.assertIsNone(helpers.installed(lambda *a, **k: SimpleNamespace(returncode=0, stdout="not json", stderr="")))
        self.assertIsNone(helpers.installed(lambda *a, **k: SimpleNamespace(returncode=0, stdout="{}", stderr="")))

        def hangs(*a, **k):
            raise subprocess.TimeoutExpired("claude", 1)
        self.assertIsNone(helpers.installed(hangs))

    def test_the_catalog_names_only_plugins_of_the_official_directories(self):
        for helper in helpers.CATALOG:
            with self.subTest(helper=helper.name):
                self.assertRegex(helper.id, r"^[a-z0-9-]+@(claude-plugins-official|anthropic-plugin-directory)$")
        self.assertEqual(len({h.name for h in helpers.CATALOG}), len(helpers.CATALOG))


class ReportTest(unittest.TestCase):
    def test_the_report_names_what_is_missing_and_the_line_to_type(self):
        text = helpers.report({FIRST.id: "1"}, None)
        self.assertIn(f"installed  {FIRST.name}", text)
        self.assertIn("missing    context7", text)
        self.assertIn("(optional)", text)
        self.assertIn(helpers.install_line(), text)
        self.assertTrue(helpers.install_line().startswith('! sh "'), "typed after a ! in the person's own shell")
        self.assertIn("bdd helpers --decline", text)
        self.assertNotIn("figma", " ".join(h.name for h in helpers.missing({}, only_recommended=True)))

    def test_with_everything_installed_there_is_nothing_to_type(self):
        everything = {h.id: "1" for h in helpers.CATALOG}
        text = helpers.report(everything, None)
        self.assertIn("Every recommended helper is installed.", text)
        self.assertNotIn("helpers install", text)
        self.assertIsNone(json.loads(helpers.as_json(everything, None))["install"])

    def test_when_the_list_cannot_be_read_nothing_is_claimed(self):
        text = helpers.report(None, None)
        self.assertIn("could not be read", text)
        self.assertNotIn("installed  frontend", text)
        self.assertIsNone(json.loads(helpers.as_json(None, None))["helpers"][0]["installed"])


class InstallTest(unittest.TestCase):
    def setUp(self):
        for name, value in (("claude_program", "claude"),):
            patcher = mock.patch.object(helpers, name, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.calls: list[list[str]] = []

    def fake(self, failing: str = ""):
        def run(command, **_):
            self.calls.append(command)
            bad = failing and failing in command[-1]
            return SimpleNamespace(returncode=1 if bad else 0, stdout="" if bad else "Installed ok", stderr="no such plugin" if bad else "")
        return run

    def run_install(self, chosen, failing=""):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = helpers.run_install(chosen, self.fake(failing))
        return code, out.getvalue()

    def test_each_chosen_plugin_is_installed_with_claudes_own_command(self):
        code, out = self.run_install(helpers.choose(["context7", "feature-dev"]))
        self.assertEqual(code, 0)
        self.assertEqual(self.calls, [["claude", "plugin", "install", "context7@claude-plugins-official"],
                                      ["claude", "plugin", "install", "feature-dev@claude-plugins-official"]])
        self.assertIn("installed  context7", out)

    def test_a_failure_is_reported_and_the_rest_still_run(self):
        code, out = self.run_install(helpers.choose(["context7", "feature-dev"]), failing="context7")
        self.assertEqual(code, 1)
        self.assertIn("FAILED     context7: no such plugin", out)
        self.assertEqual(len(self.calls), 2)

    def test_only_names_of_the_catalog_can_be_chosen(self):
        with self.assertRaises(helpers.UsageError):
            helpers.choose(["context7", "evil-plugin@elsewhere"])

    def test_without_yes_nothing_is_installed(self):
        err = io.StringIO()
        with mock.patch.object(helpers, "installed", return_value={}), mock.patch.object(helpers.subprocess, "run") as ran, \
                contextlib.redirect_stderr(err):
            self.assertEqual(helpers.run(["install", "context7"]), 2)
        ran.assert_not_called()
        self.assertIn("add --yes", err.getvalue())

    def test_already_installed_helpers_are_left_alone(self):
        out = io.StringIO()
        with mock.patch.object(helpers, "installed", return_value={"context7@claude-plugins-official": "1"}), \
                mock.patch.object(helpers.subprocess, "run") as ran, contextlib.redirect_stdout(out):
            self.assertEqual(helpers.run(["install", "context7", "--yes"]), 0)
        ran.assert_not_called()
        self.assertIn("already installed", out.getvalue())


class DeclineTest(unittest.TestCase):
    def test_declining_is_remembered_in_the_project_and_needs_a_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / ".bdd").mkdir()
            cwd, out = os.getcwd(), io.StringIO()
            os.chdir(root)
            try:
                self.assertFalse(helpers.declined(root))
                with contextlib.redirect_stdout(out):
                    self.assertEqual(helpers.run(["--decline"]), 0)
                self.assertTrue(helpers.declined(root))
                self.assertEqual(json.loads((root / ".bdd" / "helpers.json").read_text(encoding="utf-8"))["decision"], "declined")
            finally:
                os.chdir(cwd)
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(helpers.cfg, "find_root", return_value=None), \
                contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(helpers.run(["--decline"]), 2)


class DoctorTest(unittest.TestCase):
    def test_the_doctor_reports_the_helpers_and_the_plugins_whose_hooks_react_to_every_edit(self):
        plugins = {FIRST.id: "1", "impeccable@impeccable": "4", "security-guidance@claude-plugins-official": "2"}
        checks = {c.name: c for c in doctor.check_helpers(plugins, declined=False)}
        self.assertEqual(checks["helpers"].status, "ok")
        self.assertIn("1 of 8 helper plugins installed", checks["helpers"].detail)
        self.assertIn("context7", checks["helpers"].detail)
        hooks = checks["plugin hooks"].detail
        self.assertIn("impeccable", hooks)
        self.assertIn("ENABLE_STOP_REVIEW=0", hooks)
        self.assertNotIn("typescript-patterns-enforcer", hooks, "only what is installed is named")

    def test_a_person_who_declined_is_not_told_what_is_missing_and_no_hooks_means_no_second_line(self):
        (only,) = doctor.check_helpers({FIRST.id: "1"}, declined=True)
        self.assertNotIn("missing", only.detail)
        (unknown,) = doctor.check_helpers(None, declined=False)
        self.assertIn("could not be read", unknown.detail)


class GuardTest(unittest.TestCase):
    def test_no_tool_call_installs_helpers_whoever_makes_it(self):
        for command in ('sh "/p/tools/bdd/bdd" helpers install --yes', "bdd helpers install context7 --yes",
                        "./tools/bdd/bdd   helpers   --yes install", 'BDD=1 sh /p/bdd helpers install'):
            with self.subTest(command=command):
                self.assertTrue(guard._HELPERS_INSTALL.search(command))
        for command in ("bdd helpers", "bdd helpers --json", "bdd helpers --decline", "pip install requests", "bdd status"):
            with self.subTest(command=command):
                self.assertFalse(guard._HELPERS_INSTALL.search(command))
