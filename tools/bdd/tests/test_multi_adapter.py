"""A repository with two adapters (a backend and a web front end): one feature can have scenarios in both."""
import contextlib
import io
import json
import os
import unittest
from collections import Counter
from pathlib import Path

from bddlib import adapter, classify, cli, runner, state
from bddlib import config as cfg
from bddlib.errors import UsageError

from tests.helpers import ProjectCase

RUNNER = '''"""A stand-in runner for one adapter: reports the scenarios in CASES and notes where it ran."""
import os
import sys
from xml.sax.saxutils import quoteattr

CASES = {cases!r}
options = dict(zip(sys.argv[1::2], sys.argv[2::2]))
wanted = options.get("--only", "").lower()
with open("ran-here.txt", "a", encoding="utf-8") as handle:
    handle.write(os.getcwd() + "\\n")
rows = "".join("<testcase classname=\\"s\\" name=%s>%s</testcase>" % (quoteattr(name), body)
               for name, body in CASES if wanted in name.lower())
with open(options["--out"], "w", encoding="utf-8") as handle:
    handle.write("<testsuites><testsuite name=\\"s\\">" + rows + "</testsuite></testsuites>")
'''
PASSED, FAILED = "", '<failure message="AssertionError: not built yet">AssertionError</failure>'

API_FEATURE = """@FEAT-007
Feature: Discounts

  @R-007.1
  Rule: Big orders get 10% off

    @EX-007.1.1
    Scenario: The API applies the discount
      Then the request succeeds

    @EX-007.1.2
    Scenario: The API refuses a negative total
      Then the request succeeds
"""
WEB_FEATURE = """@FEAT-007
Feature: Discounts on the cart page

  @R-007.1
  Rule: Big orders get 10% off

    @EX-007.1.3
    Scenario: The cart page shows the discount
      Then the request succeeds
"""
ADAPTER_TABLE = """
[[adapters]]
name = "{name}"
root = "{name}"
features = "features"
steps = "steps"
drivers = "drivers"
support = ["tests.config"]

[adapters.run]
by_tag = '{{python}} runner.py --tag {{tag}} --base {{base}}'
report = '--out {{out}}'
isolated = '--only {{scenario}}'

[adapters.classify]
test_defect = ['ImportError']
expected_fail = ['AssertionError']
"""


class TwoAdaptersCase(ProjectCase):
    def setUp(self):
        super().setUp()
        self.write(".bdd/config.toml", "".join(ADAPTER_TABLE.format(name=name) for name in ("api", "web")))
        self.write("api/features/discounts.feature", API_FEATURE)
        self.write("web/features/cart.feature", WEB_FEATURE)
        (self.root / "features" / "discounts.feature").unlink()
        self.runner("api", [("The API applies the discount", PASSED), ("The API refuses a negative total", PASSED)])
        self.runner("web", [("The cart page shows the discount", PASSED)])

    def runner(self, name: str, cases: list) -> None:
        self.write(f"{name}/runner.py", RUNNER.format(cases=cases))

    def bdd(self, *argv: str) -> tuple[int, str, str]:
        out, err, here = io.StringIO(), io.StringIO(), os.getcwd()
        os.chdir(self.root)
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = cli.main(list(argv))
        finally:
            os.chdir(here)
        return code, out.getvalue(), err.getvalue()

    def ran_in(self, name: str) -> list[str]:
        marker = self.root / name / "ran-here.txt"
        return marker.read_text(encoding="utf-8").split() if marker.is_file() else []


class ConfigTest(TwoAdaptersCase):
    def test_every_path_of_an_adapter_is_under_its_folder(self):
        config = cfg.load(self.root)
        self.assertEqual(config.feature_dirs, (self.root / "api/features", self.root / "web/features"))
        self.assertEqual(config.step_dirs[:2], (self.root / "api/steps", self.root / "api/drivers"))
        self.assertEqual({r.adapter: (r.base, r.features) for r in config.runs},
                         {"api": ("api", "api/features"), "web": ("web", "web/features")})
        self.assertIn(self.root / "api/tests.config", config.support_files)

    def test_a_folder_outside_the_project_is_refused(self):
        for value in ("../elsewhere", "/etc", "C:/elsewhere", "a/../../b"):
            with self.subTest(root=value):
                self.write(".bdd/config.toml", f'[[adapters]]\nname = "x"\nroot = "{value}"\nfeatures = "f"\n')
                with self.assertRaises(cfg.ConfigError):
                    cfg.load(self.root)

    def test_without_a_root_nothing_changes(self):
        self.config()
        config = cfg.load(self.root)
        self.assertEqual(config.feature_dirs, (self.root / "features",))


class RunTest(TwoAdaptersCase):
    def test_a_run_covers_every_adapter_and_each_runs_in_its_own_folder(self):
        code, out, err = self.bdd("run", "FEAT-007")
        self.assertEqual(code, 0, out + err)
        record = runner.load_latest(self.root, "FEAT-007")
        self.assertEqual(record["adapter"], "api, web")
        self.assertEqual([r["adapter"] for r in record["runs"]], ["api", "web"])
        self.assertEqual(len(record["cases"]), 3)
        self.assertEqual([Path(p) for p in self.ran_in("api")], [self.root / "api"])
        self.assertEqual([Path(p) for p in self.ran_in("web")], [self.root / "web"])
        command = record["runs"][1]["command"]
        self.assertEqual(Path(command[command.index("--base") + 1]), self.root / "web")      # {base}

    def test_one_adapter_can_be_chosen(self):
        self.assertEqual(self.bdd("run", "FEAT-007", "--adapter", "web")[0], 0)
        record = runner.load_latest(self.root, "FEAT-007")
        self.assertEqual([r["adapter"] for r in record["runs"]], ["web"])
        self.assertEqual(self.ran_in("api"), [])

    def test_an_adapter_with_no_scenario_of_the_feature_is_skipped(self):
        (self.root / "web/features/cart.feature").unlink()
        code, out, err = self.bdd("run", "FEAT-007")
        self.assertEqual(code, 0, out + err)
        self.assertEqual([r["adapter"] for r in runner.load_latest(self.root, "FEAT-007")["runs"]], ["api"])

    def test_isolated_runs_give_each_adapter_only_its_own_scenarios(self):
        self.assertEqual(self.bdd("run", "FEAT-007", "--isolated")[0], 0)
        record = runner.load_latest(self.root, "FEAT-007")
        self.assertEqual(Counter(r["adapter"] for r in record["runs"]), {"api": 2, "web": 1})
        self.assertEqual(len(record["cases"]), 3)


class ClassifyTest(TwoAdaptersCase):
    def verdicts(self) -> dict:
        code, out, err = self.bdd("classify", "FEAT-007", "--json")
        self.assertIn(code, (0, 1), err)
        return json.loads(out)

    def test_the_scenarios_of_both_adapters_are_judged_together(self):
        self.bdd("run", "FEAT-007")
        report = self.verdicts()
        self.assertEqual([r["example"] for r in report["scenarios"]], ["EX-007.1.1", "EX-007.1.2", "EX-007.1.3"])
        self.assertTrue(report["green"]["valid"])
        self.assertFalse(report["red"]["valid"])

    def test_a_red_in_one_adapter_and_a_pass_in_the_other_is_not_a_valid_red(self):
        self.runner("api", [("The API applies the discount", FAILED), ("The API refuses a negative total", FAILED)])
        self.runner("web", [("The cart page shows the discount", FAILED)])
        self.bdd("run", "FEAT-007")
        self.assertTrue(self.verdicts()["red"]["valid"])
        self.runner("web", [("The cart page shows the discount", PASSED)])
        self.bdd("run", "FEAT-007")
        self.assertFalse(self.verdicts()["red"]["valid"])

    def test_the_trace_spans_both_folders(self):
        self.write(".bdd/features/FEAT-007-order-discounts/rules.md", "# Rules\n\nR-007.1 Big orders get 10% off.\n")
        code, out, err = self.bdd("trace", "FEAT-007", "--json")
        self.assertIn(code, (0, 1), err)
        self.assertEqual(json.loads(out)["totals"]["scenarios"], 3)


class ApplyIntoTest(ProjectCase):
    def test_an_adapter_can_be_placed_in_a_folder_and_two_can_coexist(self):
        created, _ = adapter.apply(self.root, "python-pytest-bdd", "api")
        self.assertIn("api/tests/drivers/system.py", created)
        created, _ = adapter.apply(self.root, "generic-junit", "tools")
        self.assertTrue(all(p.startswith("tools/") for p in created))
        config = cfg.load(self.root)
        self.assertEqual({r.adapter: r.base for r in config.runs}, {"python-pytest-bdd": "api", "generic-junit": "tools"})
        self.assertIn(self.root / "api/tests/features", config.feature_dirs)
        self.assertIn(self.root / "api/tests/conftest.py", config.support_files)
        self.assertEqual(classify.feature_scenarios(self.root, "FEAT-000")[0]["path"], "api/tests/features/sample.feature")

    def test_the_same_adapter_twice_in_one_folder_is_refused_but_not_in_two(self):
        adapter.apply(self.root, "generic-junit", "one")
        with self.assertRaises(UsageError):
            adapter.apply(self.root, "generic-junit", "one")
        adapter.apply(self.root, "generic-junit", "two")

    def test_a_folder_outside_the_project_is_refused(self):
        for value in ("..", "../x", "/tmp/x"):
            with self.subTest(into=value), self.assertRaises((UsageError, cfg.ConfigError)):
                adapter.apply(self.root, "generic-junit", value)

    def test_the_command_takes_into(self):
        out, here = io.StringIO(), os.getcwd()
        os.chdir(self.root)
        try:
            with contextlib.redirect_stdout(out):
                self.assertEqual(adapter.run(["apply", "generic-junit", "--into", "svc"]), 0)
        finally:
            os.chdir(here)
        self.assertTrue((self.root / "svc" / "tests").is_dir())


class SingleAdapterTest(unittest.TestCase):
    def test_the_selection_helpers(self):
        two = cfg.Config(runs=(cfg.RunRules("a", "x", "y"), cfg.RunRules("b", "x", "y")))
        self.assertEqual([r.adapter for r in runner.pick_all(two, None)], ["a", "b"])
        self.assertEqual([r.adapter for r in runner.pick_all(two, "b")], ["b"])
        with self.assertRaises(UsageError):
            runner.pick_all(cfg.Config(), None)
        rules = cfg.RunRules("a", "x", "y", features="web/features")
        rows = [{"name": "inside", "path": "web/features/a.feature"}, {"name": "elsewhere", "path": "api/features/b.feature"}]
        self.assertEqual(runner.scenarios_of(rules, rows, True), ["inside"])
        self.assertEqual(runner.scenarios_of(rules, rows, False), ["inside", "elsewhere"])


if __name__ == "__main__":
    unittest.main()
