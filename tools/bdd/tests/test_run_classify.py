import contextlib
import io
import json
import os
import re
import shutil
import sys
import unittest
from pathlib import Path
from unittest import mock

from bddlib import classify, guard, junit, lockfile, runcmd, runner
from bddlib import config as cfg
from bddlib.errors import UsageError

from tests.helpers import ProjectCase

FIXTURES = Path(__file__).parent / "fixtures"
SPEC = """@FEAT-007
Feature: Discounts

  @R-007.1
  Rule: Big orders get 10% off

    @EX-007.1.1
    Scenario: Order of exactly 1000
      Then the request succeeds

    @EX-007.1.2
    Scenario: Order of 999
      Then the request succeeds

    @existing @EX-007.1.3
    Scenario: Order of zero
      Then the request succeeds
"""
RUN_TABLE = """
[adapters.run]
by_tag = '{python} fake_runner.py --tag {marker}'
report = '--out {out}'
shuffle = '--seed {seed}'
isolated = '--only "{scenario}"'

[adapters.classify]
test_defect = ['ImportError', 'StepDefinitionNotFound']
expected_fail = ['AssertionError', 'BDD_EXPECTED_MISSING']
"""


def case(name: str, outcome: str, text: str = "", body: str = "") -> dict:
    return {"name": name, "outcome": outcome, "text": text, "body": body}


ALL_RED = [case("test_order_of_exactly_1000", "failed", "AssertionError: 404 != 200"),
           case("test_order_of_999", "failed", "BDD_EXPECTED_MISSING"),
           case("test_order_of_zero", "passed")]
ALL_GREEN = [case(n, "passed") for n in ("test_order_of_exactly_1000", "test_order_of_999", "test_order_of_zero")]


class RunCase(ProjectCase):
    def setUp(self):
        super().setUp()
        self.write("features/discounts.feature", SPEC)
        shutil.copy(FIXTURES / "fake_runner.py", self.root / "fake_runner.py")
        self.config(tail=RUN_TABLE)

    def cli(self, runner_function, *args: str, cases=None, env=None) -> tuple[int, str, str]:
        out, err, here = io.StringIO(), io.StringIO(), os.getcwd()
        os.chdir(self.root)
        variables = {"FAKE_CASES": json.dumps(cases if cases is not None else ALL_RED), **(env or {})}
        try:
            with mock.patch.dict(os.environ, variables), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                try:
                    code = runner_function(list(args))
                except SystemExit as exc:
                    code = exc.code
        finally:
            os.chdir(here)
        return code, out.getvalue(), err.getvalue()

    def run_feature(self, *args: str, cases=None, env=None):
        return self.cli(runcmd.run_run, "FEAT-007", *args, cases=cases, env=env)

    def classify(self, *args: str):
        return self.cli(runcmd.run_classify, "FEAT-007", *args)

    def report(self, *args: str) -> dict:
        code, out, err = self.classify("--json", *args)
        self.assertIn(code, (0, 1), err)
        return json.loads(out)


class RunTest(RunCase):
    def test_the_run_is_recorded_and_summarised(self):
        code, out, _ = self.run_feature()
        self.assertEqual((code, out.strip()), (0, "FEAT-007: 1 run(s) (all): 2 failed, 1 passed"))
        record = json.loads((self.root / ".bdd" / ".runs" / "FEAT-007" / "latest.json").read_text(encoding="utf-8"))
        self.assertEqual((record["mode"], record["seed"], len(record["cases"])), ("all", None, 3))
        self.assertEqual(record["runs"][0]["command"][1:4], ["fake_runner.py", "--tag", "FEAT_007"])

    def test_shuffle_passes_a_repeatable_seed(self):
        code, out, _ = self.run_feature("--shuffle", "--seed", "42")
        self.assertEqual(code, 0)
        self.assertIn("(shuffle, seed 42)", out)
        record = runner.load_latest(self.root, "FEAT-007")
        self.assertEqual(record["runs"][0]["command"][-2:], ["--seed", "42"])
        code, out, _ = self.run_feature("--shuffle")
        self.assertRegex(out, r"shuffle, seed \d+")

    def test_isolated_runs_one_process_per_scenario(self):
        code, out, _ = self.run_feature("--isolated")
        self.assertEqual(code, 0)
        self.assertIn("3 run(s) (isolated)", out)
        record = runner.load_latest(self.root, "FEAT-007")
        self.assertEqual([r["scenario"] for r in record["runs"]], ["Order of exactly 1000", "Order of 999", "Order of zero"])
        self.assertEqual(len(record["cases"]), 3)                           # each process ran only its own scenario

    def test_option_combinations_are_refused(self):
        self.assertEqual(self.run_feature("--seed", "3")[0], 2)
        self.assertEqual(self.run_feature("--shuffle", "--isolated")[0], 2)

    def test_a_runner_that_writes_no_report_is_reported_with_its_output(self):
        self.config(tail="[adapters.run]\nby_tag = '{python} -c \"print(1)\"'\nreport = '--out {out}'\n")
        code, _, err = self.run_feature()
        self.assertEqual(code, 1)
        self.assertIn("no test report was written", err)

    def test_a_report_without_test_cases_fails_and_shows_what_the_runner_said(self):
        code, out, err = self.run_feature(cases=[], env={"FAKE_NOTE": "no scenario matched the filter"})
        self.assertEqual(code, 1)
        self.assertIn("no test cases", out)
        self.assertIn("the test report holds no test cases (the runner exited with status 0)", err)
        self.assertIn("no scenario matched the filter", err)                         # the runner's own words are shown
        record = runner.load_latest(self.root, "FEAT-007")
        self.assertEqual((record["runs"][0]["report"], record["runs"][0]["cases"]), (True, 0))

    def test_an_empty_result_is_never_a_success_in_any_mode(self):
        """Plain, shuffled and one-process-per-scenario runs: no test case anywhere, or none in one of the runs, exits 1."""
        for mode in ((), ("--shuffle",), ("--shuffle", "--seed", "5"), ("--isolated",)):
            with self.subTest(mode=mode, cases="none"):
                code, out, err = self.run_feature(*mode, cases=[], env={"FAKE_NOTE": "nothing matched"})
                self.assertEqual(code, 1, out + err)
                self.assertIn("no test cases", out)
                self.assertIn("nothing matched", err)
        two_of_three = [ALL_GREEN[0], ALL_GREEN[1]]                  # the third scenario's own run finds no test
        code, out, err = self.run_feature("--isolated", cases=two_of_three)
        self.assertEqual(code, 1, out + err)
        self.assertIn("2 passed", out)                                # what did run is still counted and shown
        self.assertIn("the test report holds no test cases", err)

    def test_a_feature_with_no_scenario_cannot_be_isolated_into_success(self):
        self.write("features/discounts.feature", "@FEAT-007\nFeature: Discounts\n")
        code, out, err = self.run_feature("--isolated")
        self.assertEqual(code, 1, out + err)
        self.assertIn("0 run(s) (isolated): no test cases", out)

    def test_shuffle_or_isolated_words_the_runner_refuses_are_a_failure_with_its_message(self):
        self.write("refuse.py", "import sys\nprint('error: unrecognized arguments', file=sys.stderr)\nsys.exit(2)\n")
        for flag, words in (("--shuffle", "shuffle = '--seed {seed}'"), ("--isolated", "isolated = '--only {scenario}'")):
            with self.subTest(flag=flag):
                self.config(tail=f"[adapters.run]\nby_tag = '{{python}} refuse.py'\nreport = '--out {{out}}'\n{words}\n")
                code, out, err = self.run_feature(flag)
                self.assertEqual(code, 1, out + err)
                self.assertIn("no test report was written", err)
                self.assertIn("unrecognized arguments", err)

    def test_every_run_records_how_many_test_cases_it_found(self):
        self.run_feature()
        self.assertEqual([r["cases"] for r in runner.load_latest(self.root, "FEAT-007")["runs"]], [3])

    def test_missing_commands_timeouts_and_missing_tables_are_usage_problems(self):
        self.config(tail="[adapters.run]\nby_tag = 'no-such-runner-xyz {tag}'\nreport = '--out {out}'\n")
        code, _, err = self.run_feature()
        self.assertEqual((code, "not on PATH" in err), (2, True))
        self.config(tail=RUN_TABLE.replace("[adapters.run]", "[adapters.run]\ntimeout = 1"))
        code, _, err = self.run_feature(env={"FAKE_SLEEP": "5"})
        self.assertEqual((code, "took longer than 1 s" in err), (2, True))
        self.config()
        code, _, err = self.run_feature()
        self.assertEqual((code, "[adapters.run]" in err), (2, True))

    def test_shuffle_needs_the_adapter_to_say_how(self):
        self.config(tail="[adapters.run]\nby_tag = '{python} fake_runner.py'\nreport = '--out {out}'\n")
        code, _, err = self.run_feature("--shuffle")
        self.assertEqual((code, "no shuffle words" in err), (2, True))

    def test_placeholders_fill_words_and_cannot_add_words(self):
        rules = cfg.RunRules("x", "{python} run {root} -m {tag}", "--out {out}", isolated="-k {scenario}")
        words = runner.build_command(rules, self.root, "FEAT-007", Path("o.xml"), scenario="a b; rm -rf /")
        self.assertEqual(words[-2:], ["-k", "a b; rm -rf /"])             # one word, whatever it contains
        self.assertEqual(len(words), 9)

    def test_the_alnum_placeholder_keeps_only_letters_and_digits_of_any_script(self):
        rules = cfg.RunRules("x", "run", "", isolated="-run={marker}_{scenario:alnum}")
        for name, expected in {"Counts the rows of a file": "Countstherowsofafile",
                               "Order of 999 (rounded), 2.5%": "Orderof999rounded25", "café 訂單 #1": "café訂單1",
                               "(?i).*|^$ [x]": "ix", "": ""}.items():
            with self.subTest(name=name):
                words = runner.build_command(rules, self.root, "FEAT-007", Path("o.xml"), scenario=name)
                self.assertEqual(words, ["run", f"-run=FEAT_007_{expected}"])

    def test_the_js_placeholder_writes_the_name_for_javascripts_engine_in_plain_ascii(self):
        """Checked against cucumber-js 11.2.0 (`--name "^...$"` selected exactly one scenario for each of these names)."""
        rules = cfg.RunRules("x", "run", "", isolated='--name "^{scenario:js}$"')
        for name in ("Counts the rows (really)", "Café menu", "Third one [a|b] $5 ^x", "訂單 😀 ok", "a\\b"):
            with self.subTest(name=name):
                # JSON writes a character beyond ASCII as \uXXXX (and one beyond the first plane as two halves), as JavaScript reads it
                expected = "^" + "".join(re.escape(c) if c.isascii() else json.dumps(c)[1:-1] for c in name) + "$"
                words = runner.build_command(rules, self.root, "FEAT-007", Path("o.xml"), scenario=name)
                self.assertEqual([word.lower() for word in words], ["run", "--name", expected.lower()])    # hex digits: any case
                self.assertTrue(words[2].isascii())

    def test_the_regex_placeholder_makes_a_name_match_only_itself(self):
        names = ["Order \\E of (999)", "a\\Qb", 'say "hi" [now] {x} $1 ^ | ? * + . # & ~', "café 訂單", "{tag} {out} {scenario}",
                 "ends with a backslash \\"]
        rules = cfg.RunRules("x", "{python} run", "--out {out}", isolated="-Dname='\\A{scenario:regex}\\z'")
        for name in names:
            with self.subTest(name=name):
                words = runner.build_command(rules, self.root, "FEAT-007", Path("o.xml"), scenario=name)
                prefix = "-Dname=\\A"
                self.assertTrue(words[-1].startswith(prefix) and words[-1].endswith("\\z"), words[-1])
                pattern = words[-1][len(prefix):-2]
                self.assertTrue(pattern.isascii(), "plain ASCII, so a Windows code page cannot change it")
                # Java's and Go's engines read \x{HEX} as a code point; Python's does not, so stand it in for the check
                code_point = re.compile(r"\\x\{([0-9A-F]+)\}")
                python_pattern = code_point.sub(lambda found: re.escape(chr(int(found.group(1), 16))), pattern)
                self.assertTrue(re.fullmatch(python_pattern, name), "the escaped name must match the name")
                self.assertFalse(re.fullmatch(python_pattern, name + "x"), "and nothing longer")
                # the same text is also a valid literal in Java's regular expressions: a backslash is only ever put in
                # front of punctuation or as \x{HEX}, never in front of a letter or a digit that would mean something else
                bare = code_point.sub("", pattern)
                self.assertTrue(all(not escaped.isalnum() for escaped in re.findall(r"\\(.)", bare, re.DOTALL)), pattern)

    def test_a_placeholder_in_a_value_is_not_filled_in_again(self):
        rules = cfg.RunRules("x", "{python} run", "--out {out}", isolated="-k {scenario}")
        words = runner.build_command(rules, self.root, "FEAT-007", Path("o.xml"), scenario="{tag} {out}")
        self.assertEqual(words[-2:], ["-k", "{tag} {out}"])

    def test_several_adapters_need_a_choice(self):
        two = [cfg.RunRules("a", "x", "y"), cfg.RunRules("b", "x", "y")]
        with self.assertRaises(UsageError):
            runner.pick_rules(cfg.Config(runs=tuple(two)), None)
        self.assertEqual(runner.pick_rules(cfg.Config(runs=tuple(two)), "b").adapter, "b")
        with self.assertRaises(UsageError):
            runner.pick_rules(cfg.Config(runs=tuple(two)), "c")


class ClassifyTest(RunCase):
    def test_a_valid_red(self):
        self.run_feature()
        report = self.report("--expect", "red")
        self.assertEqual([r["result"] for r in report["scenarios"]], ["expected-fail", "expected-fail", "pass"])
        self.assertTrue(report["red"]["valid"])                              # the passing one is tagged @existing
        self.assertFalse(report["green"]["valid"])
        self.assertEqual(self.classify("--expect", "red")[0], 0)
        self.assertEqual(self.classify("--expect", "green")[0], 1)

    def test_defects_unknown_failures_and_tautologies_block_the_red(self):
        cases = [case("test_order_of_exactly_1000", "error", "ImportError: no module"),
                 case("test_order_of_999", "failed", "something odd happened"),
                 case("test_order_of_zero", "passed")]
        self.run_feature(cases=cases)
        self.assertEqual(self.classify("--expect", "red")[0], 1)
        problems = self.report()["red"]["problems"]
        self.assertTrue(any("is a test defect: ImportError" in p for p in problems))
        self.assertTrue(any("no classifier recognises" in p for p in problems))

    def test_a_scenario_that_passes_without_being_existing_is_flagged(self):
        self.run_feature(cases=ALL_GREEN)
        problems = self.report()["red"]["problems"]
        self.assertEqual(len(problems), 2)
        self.assertIn("passed before implementation", problems[0])
        self.assertIn("@existing", problems[0])

    def test_defect_patterns_win_over_expected_ones(self):
        cases = [case("test_order_of_exactly_1000", "failed", "ImportError while checking AssertionError")]
        self.run_feature(cases=cases)
        self.assertEqual(self.report()["scenarios"][0]["result"], "test-defect")

    def test_a_scenario_that_did_not_run_blocks_both_verdicts(self):
        self.run_feature(cases=ALL_RED[:2])
        report = self.report()
        self.assertEqual(report["scenarios"][2]["result"], "not-run")
        self.assertFalse(report["red"]["valid"])
        self.assertFalse(report["green"]["valid"])

    def test_a_green_run(self):
        self.run_feature(cases=ALL_GREEN)
        self.assertEqual(self.classify("--expect", "green")[0], 0)
        self.assertTrue(self.report()["green"]["valid"])

    def test_cases_of_other_features_are_ignored_and_counted(self):
        self.run_feature(cases=ALL_GREEN + [case("test_something_else", "failed", "AssertionError")])
        report = self.report()
        self.assertEqual(report["unmapped_cases"], 1)
        self.assertTrue(report["green"]["valid"])

    def test_the_worst_result_of_a_scenario_counts(self):
        cases = [case("test_order_of_999", "passed"), case("test_order_of_999 [row 2]", "failed", "AssertionError")]
        self.run_feature(cases=cases)
        row = next(r for r in self.report()["scenarios"] if r["scenario"] == "Order of 999")
        self.assertEqual(row["result"], "expected-fail")

    def test_the_text_report_lists_scenarios_and_verdicts(self):
        self.run_feature()
        text = self.classify()[1]
        self.assertIn("expected-fail EX-007.1.1   Order of exactly 1000", text)
        self.assertIn("red: valid", text)
        self.assertIn("green: NOT valid", text)

    def test_classifying_needs_a_recorded_run(self):
        code, _, err = self.classify()
        self.assertEqual((code, "has not been run yet" in err), (2, True))


class GateTest(RunCase):
    """With a run command configured, bind needs a valid red and verify a green, from a current recorded run."""

    def setUp(self):
        super().setUp()
        self.walk_to("refine")
        lockfile.lock(self.root, self.feature_dir, "FEAT-007", "bind", [self.step])

    def refused(self, gate: str) -> str:
        with self.assertRaises(UsageError) as cm:
            self.gate(gate)
        return str(cm.exception)

    def test_bind_needs_a_recorded_run(self):
        self.assertIn("has not been run yet", self.refused("bind"))

    def test_bind_needs_the_run_to_be_a_valid_red(self):
        self.run_feature(cases=ALL_GREEN)
        self.assertIn("not a valid red", self.refused("bind"))
        self.run_feature(cases=ALL_RED)
        self.assertEqual(self.gate("bind")["gates"]["bind"]["result"], "pass")

    def test_a_run_goes_stale_when_a_step_or_a_feature_changes(self):
        self.run_feature(cases=ALL_RED)
        self.step.write_text("def then_ok():\n    assert 1 == 1\n", encoding="utf-8", newline="\n")
        self.assertIn("out of date", self.refused("bind"))
        self.run_feature(cases=ALL_RED)
        self.assertEqual(self.gate("bind")["gates"]["bind"]["result"], "pass")

    def test_verify_needs_a_green_run(self):
        self.run_feature(cases=ALL_RED)
        self.gate("bind")
        self.gate("tasks")
        self.gate("implement")
        self.assertIn("not a valid green", self.refused("verify"))
        self.run_feature(cases=ALL_GREEN)
        self.assertEqual(self.gate("verify")["phase"], "done")

    def test_the_run_that_proved_the_red_is_kept_when_later_runs_overwrite_the_latest(self):
        self.run_feature(cases=ALL_RED)
        self.gate("bind")
        self.run_feature(cases=ALL_GREEN)                                        # the green, or an auditor's rerun
        code, out, _ = self.classify("--run", "red", "--expect", "red")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.classify("--expect", "red")[0], 1)                  # the latest run is no longer a red
        self.assertEqual(self.classify("--run", "red", "--expect", "green")[0], 1)

    def test_a_kept_red_that_was_altered_is_refused(self):
        self.run_feature(cases=ALL_RED)
        self.gate("bind")
        kept = self.root / ".bdd" / ".runs" / "FEAT-007" / "red.json"
        text = kept.read_text(encoding="utf-8")
        self.assertIn('"mode": "all"', text)
        kept.write_text(text.replace('"mode": "all"', '"mode": "forged"'), encoding="utf-8")
        code, _, err = self.classify("--run", "red")
        self.assertEqual((code, "does not match" in err), (2, True))

    def test_there_is_no_kept_red_before_the_bind_gate(self):
        self.run_feature(cases=ALL_RED)
        code, _, err = self.classify("--run", "red")
        self.assertEqual((code, "no red run was kept" in err), (2, True))

    def test_projects_without_a_run_command_are_not_held_to_it(self):
        self.config()
        self.assertEqual(self.gate("bind")["gates"]["bind"]["result"], "pass")


class ProjectPythonTest(ProjectCase):
    """The project's tests run in the project's environment, not in the one that runs bdd; the choice comes from
    the configuration or the project, never from the environment variables of one command."""

    def make_env(self, folder: str) -> Path:
        scripts = self.root / folder / ("Scripts" if os.name == "nt" else "bin")
        scripts.mkdir(parents=True)
        python = scripts / ("python.exe" if os.name == "nt" else "python")
        python.write_text("", encoding="utf-8")
        return python

    def test_without_any_environment_it_is_the_interpreter_running_bdd(self):
        self.assertEqual(runner.project_python(self.root), sys.executable)

    def test_a_virtual_environment_in_the_project_is_found(self):
        python = self.make_env(".venv")
        self.assertEqual(runner.project_python(self.root), str(python))

    def test_only_this_platforms_environment_layout_counts(self):
        """A checkout shared by Windows and WSL: each side finds its own environment, never the other platform's."""
        windows = self.root / ".venv" / "Scripts" / "python.exe"
        linux = self.root / "venv" / "bin" / "python"
        for path in (windows, linux):
            path.parent.mkdir(parents=True)
            path.write_text("", encoding="utf-8")
        for layout, expected in (("Scripts/python.exe", windows), ("bin/python", linux)):
            with self.subTest(layout=layout), mock.patch.object(runner, "VENV_INTERPRETER", layout):
                self.assertEqual(runner.project_python(self.root), str(expected))

    def test_the_configured_interpreter_beats_the_one_in_the_project(self):
        self.make_env(".venv")
        chosen = self.make_env("elsewhere")
        self.config(f"python = {json.dumps(str(chosen))}\n")
        self.assertEqual(runner.project_python(self.root), str(chosen))

    def test_a_relative_choice_is_relative_to_the_project(self):
        chosen = self.make_env("tools-env")
        self.config(f"python = {json.dumps(chosen.relative_to(self.root).as_posix())}\n")
        self.assertEqual(Path(runner.project_python(self.root)), chosen)

    def test_a_configured_interpreter_that_does_not_exist_is_an_error(self):
        self.config('python = "no/such/python"\n')
        with self.assertRaises(UsageError) as cm:
            runner.project_python(self.root)
        self.assertIn("is not a file", str(cm.exception))

    def test_environment_variables_are_ignored(self):
        """A command can set them for itself; the evidence must not depend on that."""
        impostor = self.make_env("impostor")
        variables = {"VIRTUAL_ENV": str(impostor.parents[1]), "GREENLIGHT_PYTHON": str(impostor)}
        with mock.patch.dict(os.environ, variables):
            self.assertEqual(runner.project_python(self.root), sys.executable)

    def test_the_adapter_runs_its_tests_with_it(self):
        rules = cfg.RunRules("x", "{project_python} -m pytest -m {tag}", "--out {out}")
        python = self.make_env(".venv")
        words = runner.build_command(rules, self.root, "FEAT-007", Path("o.xml"))
        self.assertEqual(words[0], str(python))

    def test_variables_the_adapter_names_do_not_reach_the_runner(self):
        script = self.root / "env_probe.py"
        script.write_text("import os, sys\nprint(sorted(k for k in os.environ if k.startswith(('PYTEST_', 'KEEP_'))))\n",
                          encoding="utf-8")
        with mock.patch.dict(os.environ, {"PYTEST_ADDOPTS": "-k nothing", "KEEP_ME": "1"}):
            status, output = runner.execute([sys.executable, str(script)], self.root, 60, ("PYTEST_",))
        self.assertEqual((status, output.strip()), (0, "['KEEP_ME']"))


class JunitTest(unittest.TestCase):
    def test_outcomes_and_text(self):
        xml = (b'<testsuites><testsuite><testcase classname="a" name="p"/>'
               b'<testcase classname="a" name="f"><failure message="boom" type="AssertionError">trace</failure></testcase>'
               b'<testcase classname="a" name="e"><error message="bad import"/></testcase>'
               b'<testcase classname="a" name="s"><skipped message="not now"/></testcase></testsuite></testsuites>')
        cases = junit.parse(xml)
        self.assertEqual([c.outcome for c in cases], ["passed", "failed", "error", "skipped"])
        self.assertEqual(cases[1].text, "AssertionError\nboom\ntrace")
        self.assertEqual(cases[1].label, "a::f")

    def test_a_bare_testsuite_root_is_fine(self):
        self.assertEqual(len(junit.parse(b'<testsuite><testcase name="x"/></testsuite>')), 1)

    def test_entities_and_garbage_are_refused(self):
        for data in (b'<!DOCTYPE x [<!ENTITY a "b">]><testsuite/>', b"<!doctype x><testsuite/>", b"not xml"):
            with self.subTest(data=data), self.assertRaises(UsageError):
                junit.parse(data)

    def test_a_missing_file(self):
        with self.assertRaises(UsageError):
            junit.parse_file(Path("does-not-exist.xml"))


class ConfigAndGuardTest(RunCase):
    def test_the_tables_are_read_per_adapter(self):
        (rules,) = cfg.load(self.root).runs
        self.assertEqual((rules.adapter, rules.timeout), ("x", 600))
        self.assertEqual(rules.expected_fail, ("AssertionError", "BDD_EXPECTED_MISSING"))

    def test_bad_tables_are_config_errors(self):
        for table, message in (("[adapters.run]\nby_tag = 'x'\n", "needs report"),
                               ("[adapters.run]\nby_tag = ''\nreport = 'y'\n", "needs by_tag"),
                               ("[adapters.run]\nby_tag = 'x'\nreport = 'y'\ntimeout = 0\n", "timeout"),
                               ("[adapters.run]\nby_tag = 'x'\nreport = 'y'\nshuffle = 3\n", "shuffle must be a string"),
                               ("[adapters.run]\nby_tag = 'x'\nreport = 'y'\n[adapters.classify]\ntest_defect = ['(']\n",
                                "not a valid regular expression")):
            with self.subTest(table=table):
                self.config(tail=table)
                with self.assertRaises(cfg.ConfigError) as cm:
                    cfg.load(self.root)
                self.assertIn(message, str(cm.exception))

    def test_the_agent_cannot_write_a_recorded_run(self):
        path = self.root / ".bdd" / ".runs" / "FEAT-007" / "latest.json"
        reason = guard.evaluate({"tool_name": "Write", "cwd": str(self.root), "tool_input": {"file_path": str(path)}})
        self.assertIn("managed by the bdd command line", reason)
        reason = guard.evaluate({"tool_name": "Bash", "cwd": str(self.root),
                                 "tool_input": {"command": "echo {} > .bdd/.runs/FEAT-007/latest.json"}})
        self.assertIn("managed by", reason)


if __name__ == "__main__":
    unittest.main()
