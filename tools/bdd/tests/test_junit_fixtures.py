"""Reports of real runners, classified with the generic-junit defaults.

Each folder under tests/fixtures/junit holds the same two-scenario feature in four states. All five runners (cucumber-js,
behave, godog, cucumber-jvm, reqnroll) are real runs (see the README there for the versions)."""
import tempfile
import unittest
from pathlib import Path

from bddlib import adapter, classify, junit, state
from bddlib import config as cfg

REPO = Path(__file__).resolve().parents[3]
FIXTURES = Path(__file__).parent / "fixtures" / "junit"
RUNNERS = ("cucumber-js", "behave", "godog", "cucumber-jvm", "reqnroll")
SCENARIOS = ("Two numbers are added", "A negative number is refused")
EXPECTED = {"red": classify.EXPECTED, "assert": classify.EXPECTED, "defect": classify.DEFECT, "green": classify.PASS}


class FixtureCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.TemporaryDirectory()
        cls.root = Path(cls.dir.name).resolve()
        (cls.root / ".bdd").mkdir()
        adapter.apply(cls.root, "generic-junit")
        state.create(cls.root, "FEAT-000", "Sample", "standard")
        cls.rules = list(cfg.load(cls.root).runs)
        cls.scenarios = classify.feature_scenarios(cls.root, "FEAT-000")

    @classmethod
    def tearDownClass(cls):
        cls.dir.cleanup()

    def report(self, runner: str, name: str) -> dict:
        cases = junit.parse_file(FIXTURES / runner / f"{name}.xml")
        record = {"feature": "FEAT-000", "mode": "all", "seed": None, "at": "now",
                  "cases": [{"name": c.name, "classname": c.classname, "outcome": c.outcome, "text": c.text} for c in cases]}
        return classify.classify_run(record, self.scenarios, self.rules)


class RunnerFixtureTest(FixtureCase):
    def test_the_sample_feature_has_the_scenarios_the_fixtures_name(self):
        self.assertEqual(tuple(s["name"] for s in self.scenarios), SCENARIOS)

    def test_every_runner_has_all_four_states(self):
        for runner in RUNNERS:
            for state_name in EXPECTED:
                with self.subTest(runner=runner, state=state_name):
                    self.assertTrue((FIXTURES / runner / f"{state_name}.xml").is_file())

    def test_each_state_is_classified_the_same_way_for_every_runner(self):
        for runner in RUNNERS:
            for state_name, wanted in EXPECTED.items():
                with self.subTest(runner=runner, state=state_name):
                    results = [row["result"] for row in self.report(runner, state_name)["scenarios"]]
                    self.assertEqual(results, [wanted, wanted])

    def test_a_red_is_valid_for_the_red_and_the_assertion_states_only(self):
        for runner in RUNNERS:
            with self.subTest(runner=runner):
                self.assertTrue(self.report(runner, "red")["red"]["valid"])
                self.assertTrue(self.report(runner, "assert")["red"]["valid"])
                self.assertFalse(self.report(runner, "defect")["red"]["valid"])
                self.assertFalse(self.report(runner, "green")["red"]["valid"])

    def test_a_green_is_valid_only_for_the_green_state(self):
        for runner in RUNNERS:
            with self.subTest(runner=runner):
                self.assertTrue(self.report(runner, "green")["green"]["valid"])
                for state_name in ("red", "assert", "defect"):
                    self.assertFalse(self.report(runner, state_name)["green"]["valid"], state_name)

    def test_a_defect_names_what_is_wrong(self):
        for runner in RUNNERS:
            with self.subTest(runner=runner):
                problems = self.report(runner, "defect")["red"]["problems"]
                self.assertTrue(problems and all("test defect" in p for p in problems), problems)


class EmptyFailureTest(unittest.TestCase):
    """cucumber-js writes `<failure/>` for an undefined step and says what happened only in system-out."""

    def test_the_output_stands_in_for_a_failure_without_text(self):
        xml = (b'<testsuite><testcase classname="f" name="s"><failure/>'
               b'<system-out><![CDATA[When I fly...undefined]]></system-out></testcase></testsuite>')
        (case,) = junit.parse(xml)
        self.assertEqual((case.outcome, case.text), (junit.FAILED, "When I fly...undefined"))

    def test_a_failure_with_text_keeps_its_own_text_and_a_pass_has_none(self):
        xml = (b'<testsuite><testcase name="a"><failure message="boom"/><system-out>noise</system-out></testcase>'
               b'<testcase name="b"><system-out>noise</system-out></testcase></testsuite>')
        first, second = junit.parse(xml)
        self.assertEqual(first.text, "boom")
        self.assertEqual((second.outcome, second.text), (junit.PASSED, ""))


if __name__ == "__main__":
    unittest.main()
