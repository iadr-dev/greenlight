"""The model each agent runs on: [models] in .bdd/config.toml, shown by `bdd status`, checked by `bdd doctor`."""
import contextlib
import io
import json
import os
import unittest
from unittest import mock

from bddlib import cli, doctor, guard, models
from bddlib import config as cfg

from tests.helpers import ProjectCase

DEFAULTS = {"product-analyst": "opus", "qa-designer": "opus", "system-analyst": "opus", "step-engineer": "sonnet",
            "implementer": "sonnet", "ui-engineer": "sonnet", "code-reviewer": "opus", "security-reviewer": "opus",
            "ui-reviewer": "opus", "spec-auditor": "opus"}


class ModelsCase(ProjectCase):
    def status(self, *argv: str) -> str:
        out, here = io.StringIO(), os.getcwd()
        os.chdir(self.root)
        try:
            with contextlib.redirect_stdout(out):
                self.assertEqual(cli.main(["status", *argv]), 0)
        finally:
            os.chdir(here)
        return out.getvalue()


class ModelsConfigTest(ModelsCase):
    def test_without_a_models_table_every_agent_keeps_the_model_of_its_agent_file(self):
        self.assertEqual(cfg.load(self.root).models, ())
        self.assertEqual(models.defaults(), DEFAULTS)
        self.assertEqual({c.agent: c.model for c in models.choices(())}, DEFAULTS)
        self.assertIn("models: product-analyst opus, qa-designer opus, system-analyst opus, step-engineer sonnet, "
                      "implementer sonnet, ui-engineer sonnet, code-reviewer opus", self.status())

    def test_a_model_chosen_in_the_config_replaces_the_default_and_says_where_it_comes_from(self):
        self.config(tail='\n[models]\nimplementer = "opus"\ncode-reviewer = "sonnet"\n')
        chosen = cfg.load(self.root).models
        self.assertEqual(chosen, (("implementer", "opus"), ("code-reviewer", "sonnet")))
        picked = {c.agent: (c.model, c.chosen) for c in models.choices(chosen)}
        self.assertEqual(picked["implementer"], ("opus", True))
        self.assertEqual(picked["qa-designer"], ("opus", False))
        line = self.status()
        self.assertIn("implementer opus (.bdd/config.toml)", line)
        self.assertIn("code-reviewer sonnet (.bdd/config.toml)", line)
        self.assertNotIn("run `bdd doctor`", line)
        report = json.loads(self.status("--json"))
        self.assertIn({"agent": "implementer", "model": "opus", "chosen": True}, report["models"])
        self.assertEqual(report["model_problems"], [])

    def test_a_choice_that_cannot_be_used_keeps_the_default_and_is_named(self):
        self.config(tail='\n[models]\nimplementer = "gpt-5"\ncoder = "opus"\n')
        chosen = cfg.load(self.root).models
        self.assertEqual(next(c for c in models.choices(chosen) if c.agent == "implementer").model, "sonnet")
        found = models.problems(chosen)
        self.assertIn('implementer = "gpt-5" is not a model the Agent tool accepts (fable, haiku, opus, sonnet)', found[0])
        self.assertIn("coder is not a greenlight agent", found[1])
        self.assertIn("models: 2 choice(s) in [models] cannot be used; run `bdd doctor`", self.status())

    def test_a_value_that_is_not_a_name_is_reported_and_does_not_stop_the_tools(self):
        """A config error makes the guard refuse every call, so a wrong value must not be one."""
        self.config(tail='\n[models]\nimplementer = 4\n')
        chosen = cfg.load(self.root).models
        self.assertIn('implementer = "4" is not a model the Agent tool accepts', models.problems(chosen)[0])
        self.assertIn("implementer sonnet,", self.status())

    def test_models_that_is_not_a_table_is_a_config_error(self):
        self.config(top_level='models = "opus"\n')
        with self.assertRaisesRegex(cfg.ConfigError, r"\[models\] is a table that maps an agent to the name of a model"):
            cfg.load(self.root)

    def test_an_agent_file_that_cannot_be_read_shows_an_unknown_model(self):
        with mock.patch.object(models, "AGENTS_DIR", self.root / "no-agents"):
            self.assertEqual(set(models.defaults().values()), {"unknown"})
            self.assertIn("implementer unknown", self.status())

    def test_the_agents_are_the_ones_the_guard_limits(self):
        self.assertEqual(set(models.AGENTS), set(guard.AGENT_WRITES))


class ModelsDoctorTest(ModelsCase):
    def test_the_doctor_reports_a_model_the_agent_tool_does_not_accept(self):
        self.config(tail='\n[models]\nimplementer = "gpt-5"\n')
        check = doctor.check_models(self.root)
        self.assertEqual(check.status, "fail")
        self.assertIn('implementer = "gpt-5" is not a model the Agent tool accepts', check.detail)
        self.assertIn("remove the line", check.fix)

    def test_the_doctor_accepts_the_defaults_and_good_choices(self):
        self.assertEqual(doctor.check_models(self.root).status, "ok")
        self.config(tail='\n[models]\nimplementer = "opus"\n')
        check = doctor.check_models(self.root)
        self.assertEqual((check.status, check.detail), ("ok", "1 chosen in .bdd/config.toml"))

    def test_the_doctor_fails_a_value_that_is_not_a_name_and_a_table_that_is_not_one(self):
        for top_level, tail in (("", '\n[models]\nimplementer = 4\n'), ('models = "opus"\n', "")):
            with self.subTest(top_level=top_level, tail=tail):
                self.config(top_level=top_level, tail=tail)
                self.assertEqual(doctor.check_models(self.root).status, "fail")


if __name__ == "__main__":
    unittest.main()
