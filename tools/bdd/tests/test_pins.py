"""tools/pins/check.py: pinned versions that are out of date or near end of life, with the network and gh replaced."""
import datetime
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("pins_check", REPO / "tools" / "pins" / "check.py")
pins = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = pins              # a dataclass looks its module up here
spec.loader.exec_module(pins)

TODAY = datetime.date(2026, 11, 5)
SHA = "a" * 40
NODE = [{"cycle": "26", "eol": "2029-04-30"}, {"cycle": "24", "eol": "2028-04-30"}, {"cycle": "22", "eol": "2026-12-01"},
        {"cycle": "20", "eol": "2026-04-30"}]
DOTNET = [{"cycle": "10", "eol": "2028-11-14"}, {"cycle": "8", "eol": True}]


def fetcher(answers):
    return lambda url: answers.get(url)


class PinsCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def write(self, rel, text):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


class RuntimeTest(PinsCase):
    def findings(self, workflow, table=None):
        self.write(".github/workflows/ci.yml", workflow)
        tables = {"nodejs": NODE, "dotnet": DOTNET} if table is None else table
        answers = {f"https://endoflife.date/api/{product}.json": rows for product, rows in tables.items()}
        return pins.runtime_findings(self.root, fetcher(answers), TODAY)

    def test_a_runtime_past_its_end_of_life_or_close_to_it_is_reported(self):
        found = self.findings('with:\n  node-version: "20"\n')
        self.assertEqual([(f.what, f.level) for f in found], [("nodejs 20", "eol")])
        found = self.findings("with:\n  node-version: 22\n")
        self.assertEqual(found[0].detail, "reaches end of life on 2026-12-01")

    def test_a_supported_runtime_is_not_reported(self):
        self.assertEqual(self.findings('with:\n  node-version: "24"\n'), [])

    def test_a_dotted_version_matches_its_major_cycle(self):
        self.assertEqual(self.findings('with:\n  dotnet-version: "10.0.x"\n'), [])
        self.assertEqual(self.findings('with:\n  dotnet-version: "8.0.x"\n')[0].level, "eol")

    def test_what_cannot_be_checked_is_said_not_passed(self):
        self.assertEqual(self.findings('with:\n  node-version: "99"\n')[0].level, "unchecked")
        self.assertEqual(self.findings('with:\n  node-version: "24"\n', table={})[0].level, "unchecked")


class ActionAndPackageTest(PinsCase):
    def test_an_action_of_a_template_behind_its_latest_release_is_reported(self):
        self.write("adapters/x/ci/github-actions.yml",
                   f"- uses: actions/setup-java@{SHA}  # v6.1.0\n- uses: actions/checkout@{SHA}  # v7.0.1\n")
        answers = {"https://api.github.com/repos/actions/setup-java/releases/latest": {"tag_name": "v6.2.0"},
                   "https://api.github.com/repos/actions/checkout/releases/latest": {"tag_name": "v7.0.1"}}
        (found,) = pins.action_findings(self.root, fetcher(answers))
        self.assertEqual((found.what, found.pinned, found.level), ("actions/setup-java", "6.1.0", "behind"))

    def test_the_repositorys_own_workflows_are_left_to_dependabot(self):
        self.write(".github/workflows/ci.yml", f"- uses: actions/setup-java@{SHA}  # v1.0.0\n")
        self.assertEqual(pins.action_findings(self.root, fetcher({})), [])

    def test_a_nuget_package_behind_the_latest_stable_release_is_reported(self):
        self.write("adapters/dotnet-reqnroll/templates/tests/G.csproj", '<PackageReference Include="Foo.Bar" Version="1.2.0" />\n')
        listing = {"https://api.nuget.org/v3-flatcontainer/foo.bar/index.json": {"versions": ["1.2.0", "1.10.0", "2.0.0-beta.1"]}}
        (found,) = pins.package_findings(self.root, fetcher(listing))
        self.assertEqual((found.pinned, found.detail), ("1.2.0", "latest release is 1.10.0"))


class AcceptedTest(PinsCase):
    PROJECT = "adapters/dotnet-reqnroll/templates/tests/G.csproj"

    def test_a_pin_held_back_on_purpose_is_not_reported_until_the_pin_changes(self):
        self.write(self.PROJECT, '<PackageReference Include="Foo" Version="3.1.5" />\n')
        listing = {"https://api.nuget.org/v3-flatcontainer/foo/index.json": {"versions": ["3.1.5", "4.0.1"]}}
        holds = {("Foo", "3.1.5"): "built on xunit v2"}
        self.assertEqual(pins.check(self.root, fetcher(listing), TODAY, holds), [])
        self.write(self.PROJECT, '<PackageReference Include="Foo" Version="3.2.0" />\n')
        self.assertEqual(len(pins.check(self.root, fetcher(listing), TODAY, holds)), 1)

    def test_the_shipped_accepted_file_gives_every_entry_a_reason(self):
        holds = pins.accepted()
        self.assertTrue(holds)
        self.assertTrue(all(len(reason) > 20 for reason in holds.values()))


class IssueTest(unittest.TestCase):
    FOUND = [pins.Finding("runtime", "nodejs 20", "ci.yml", "20", "has reached end of life", "eol")]

    def run_with(self, findings, listing):
        calls = []

        class Done:
            def __init__(self, stdout):
                self.stdout = stdout

        def run(cmd, **kwargs):
            calls.append(cmd[1:3])
            return Done(json.dumps(listing) if cmd[1:3] == ["issue", "list"] else "")
        return pins.keep_issue(findings, run), calls

    def test_findings_open_one_issue_and_then_update_it(self):
        said, calls = self.run_with(self.FOUND, [])
        self.assertEqual((said, ["issue", "create"] in calls), ("opened an issue", True))
        said, calls = self.run_with(self.FOUND, [{"number": 7}])
        self.assertEqual((said, ["issue", "edit"] in calls), ("updated issue #7", True))

    def test_nothing_to_report_closes_the_open_issue(self):
        self.assertEqual(self.run_with([], [{"number": 7}])[0], "closed issue #7")
        self.assertEqual(self.run_with([], [])[0], "nothing to report")


class ReportTest(unittest.TestCase):
    def test_the_report_groups_by_level_and_says_when_all_is_current(self):
        self.assertIn("current", pins.report([]))
        text = pins.report([pins.Finding("action", "a/b", "x.yml", "1.0", "latest release is v2", "behind")])
        self.assertIn("### A newer release exists", text)


if __name__ == "__main__":
    unittest.main()
