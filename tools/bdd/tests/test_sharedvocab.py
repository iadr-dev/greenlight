"""Shared team vocabularies: included files are pinned, read-only for agents, free of cycles and conflicts."""
import contextlib
import io
import json
import os
import unittest

from bddlib import cli, guard, lint, sharedvocab, tripwire, vocabulary
from bddlib import config as cfg

from tests.helpers import ProjectCase

SHARED = 'extends = "core"\n\n[[steps]]\nid = "D.TEAM.CATALOG"\nkind = "given"\npattern = "the catalogue lists {item}"\n' \
         'composes = ["C.ENTITY.SEED"]\n'
INCLUDE = '[vocabulary]\ninclude = ["vendor/team.toml"]\n'


def toml(*names: str, steps: str = "") -> str:
    listed = ", ".join(json.dumps(n) for n in names)
    return f'extends = "core"\n{steps}\n[vocabulary]\ninclude = [{listed}]\n'


class SharedHelpers:
    def setUp(self):
        super().setUp()
        self.shared = self.write("vendor/team.toml", SHARED)
        self.main = self.write(".bdd/vocabulary.toml", 'extends = "core"\n\n' + INCLUDE)

    def issues(self) -> list:
        config = cfg.load(self.root)
        vocab = vocabulary.load(self.main)
        return lint.check_project_vocabulary(vocab, self.main, config, config.profiles)

    def codes(self) -> list[str]:
        return [i.code for i in self.issues()]

    def cli(self, *argv: str) -> tuple[int, str, str]:
        out, err, here = io.StringIO(), io.StringIO(), os.getcwd()
        os.chdir(self.root)
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = cli.main(list(argv))
        finally:
            os.chdir(here)
        return code, out.getvalue(), err.getvalue()


class LoadingTest(SharedHelpers, ProjectCase):
    def test_shared_steps_join_the_vocabulary_with_their_file(self):
        vocab = vocabulary.load(self.main)
        entry = vocab.by_id["D.TEAM.CATALOG"]
        self.assertEqual((entry.source, entry.origin), ("project", str(self.shared)))
        self.assertTrue(vocab.resolve("given", "the catalogue lists tea"))

    def test_a_file_met_twice_is_read_once_and_a_chain_is_followed(self):
        self.write("vendor/a.toml", toml("vendor/team.toml"))
        self.write("vendor/b.toml", toml("vendor/team.toml", "vendor/a.toml"))
        self.main.write_text(toml("vendor/b.toml", "vendor/a.toml"), encoding="utf-8", newline="\n")
        names = [sharedvocab.relative(self.root, p) for p in sharedvocab.closure(self.root, self.main)]
        self.assertEqual(names, ["vendor/b.toml", "vendor/team.toml", "vendor/a.toml"])

    def test_a_cycle_is_named(self):
        self.write("vendor/a.toml", toml("vendor/b.toml"))
        self.write("vendor/b.toml", toml("vendor/a.toml"))
        self.main.write_text(toml("vendor/a.toml"), encoding="utf-8", newline="\n")
        with self.assertRaises(vocabulary.VocabularyError) as cm:
            vocabulary.load(self.main)
        self.assertIn("vendor/a.toml -> vendor/b.toml -> vendor/a.toml", str(cm.exception))

    def test_a_vocabulary_cannot_include_the_project_file_itself(self):
        self.write("vendor/a.toml", toml(".bdd/vocabulary.toml"))
        self.main.write_text(toml("vendor/a.toml"), encoding="utf-8", newline="\n")
        with self.assertRaises(vocabulary.VocabularyError) as cm:
            vocabulary.load(self.main)
        self.assertIn("include cycle", str(cm.exception))

    def test_names_that_leave_the_project_or_are_not_toml_are_refused(self):
        for name, why in (("../outside.toml", "outside the project"), (str(self.root.parent / "x.toml"), "relative to the project root"),
                          ("vendor/team.json", "relative to the project root"), ("vendor/none.toml", "does not exist")):
            with self.subTest(name=name):
                self.main.write_text(toml(name), encoding="utf-8", newline="\n")
                with self.assertRaises(vocabulary.VocabularyError) as cm:
                    vocabulary.load(self.main)
                self.assertIn(why, str(cm.exception))

    def test_a_link_that_resolves_outside_the_project_is_refused(self):
        target = self.root.parent / f"{self.root.name}-elsewhere.toml"
        target.write_text(SHARED, encoding="utf-8")
        self.addCleanup(target.unlink)
        link = self.root / "vendor" / "link.toml"
        try:
            link.symlink_to(target)
        except OSError:
            self.skipTest("symbolic links are not available here")
        self.main.write_text(toml("vendor/link.toml"), encoding="utf-8", newline="\n")
        with self.assertRaises(vocabulary.VocabularyError) as cm:
            vocabulary.load(self.main)
        self.assertIn("outside the project", str(cm.exception))

    def test_an_include_list_that_is_not_a_list_of_names_is_refused(self):
        self.main.write_text('extends = "core"\n\n[vocabulary]\ninclude = "vendor/team.toml"\n', encoding="utf-8", newline="\n")
        with self.assertRaises(vocabulary.VocabularyError):
            vocabulary.load(self.main)


class ConflictTest(SharedHelpers, ProjectCase):
    STEP = '\n[[steps]]\nid = "%s"\nkind = "given"\npattern = "%s"\ncomposes = ["C.ENTITY.SEED"]\n'

    def test_a_project_step_cannot_reuse_a_shared_id(self):
        self.main.write_text('extends = "core"\n' + self.STEP % ("D.TEAM.CATALOG", "my own catalogue {item}") + "\n" + INCLUDE,
                             encoding="utf-8", newline="\n")
        with self.assertRaises(vocabulary.VocabularyError) as cm:
            vocabulary.load(self.main)
        self.assertIn("D.TEAM.CATALOG in .bdd/vocabulary.toml overrides the shared step of the same id in vendor/team.toml",
                      str(cm.exception))

    def test_two_shared_files_cannot_define_the_same_id(self):
        self.write("vendor/other.toml", SHARED)
        self.main.write_text(toml("vendor/team.toml", "vendor/other.toml"), encoding="utf-8", newline="\n")
        with self.assertRaises(vocabulary.VocabularyError) as cm:
            vocabulary.load(self.main)
        self.assertIn("defined by both vendor/team.toml and vendor/other.toml", str(cm.exception))

    def test_the_same_pattern_in_two_files_is_reported_where_the_second_is(self):
        sharedvocab.pin(self.root, [self.shared])
        self.main.write_text('extends = "core"\n' + self.STEP % ("D.MINE.CATALOG", "the catalogue lists {item}") + "\n" + INCLUDE,
                             encoding="utf-8", newline="\n")
        found = [i for i in self.issues() if i.code == "L014"]
        self.assertEqual(len(found), 1)
        self.assertIn("same pattern", found[0].message)
        self.assertIn("D.TEAM.CATALOG", found[0].message)
        self.assertEqual(found[0].path, str(self.main))                      # the file its owner can change
        self.assertNotIn("L010", self.codes())

    def test_a_near_duplicate_is_reported_in_the_file_that_holds_it(self):
        sharedvocab.pin(self.root, [self.shared])
        self.main.write_text('extends = "core"\n' + self.STEP % ("D.MINE.LISTS", "lists the catalogue {item}") + "\n" + INCLUDE,
                             encoding="utf-8", newline="\n")
        found = [i for i in self.issues() if i.code == "L010"]
        self.assertEqual([i.path for i in found], [str(self.main)])


class PinTest(SharedHelpers, ProjectCase):
    def test_an_unpinned_file_is_an_error_until_it_is_pinned(self):
        self.assertEqual(self.codes(), ["L013"])
        sharedvocab.pin(self.root, [self.shared])
        self.assertEqual(self.codes(), [])

    def test_a_changed_file_is_an_error_until_the_person_pins_it_again(self):
        sharedvocab.pin(self.root, [self.shared])
        self.shared.write_text(SHARED.replace("lists", "sells"), encoding="utf-8", newline="\n")
        found = self.issues()
        self.assertEqual([i.code for i in found], ["L013"])
        self.assertIn("changed since it was pinned", found[0].message)
        self.assertEqual(self.cli("vocabulary", "pin")[0], 0)
        self.assertEqual(self.codes(), [])

    def test_a_pin_for_a_file_no_longer_included_is_reported(self):
        sharedvocab.pin(self.root, [self.shared])
        self.main.write_text('extends = "core"\n', encoding="utf-8", newline="\n")
        self.assertEqual(sharedvocab.pin_problems(self.root, []), ["vendor/team.toml is pinned but no longer included; "
                                                                  "run `bdd vocabulary pin` to drop it"])

    def test_line_endings_do_not_change_the_pin(self):
        sharedvocab.pin(self.root, [self.shared])
        self.shared.write_bytes(SHARED.replace("\n", "\r\n").encode("utf-8"))
        self.assertEqual(self.codes(), [])

    def test_a_lock_that_is_not_a_lock_is_reported_not_trusted(self):
        self.write(".bdd/vocabulary.lock.json", '{"schema": 1, "files": []}')
        self.assertTrue(sharedvocab.pin_problems(self.root, [self.shared])[0].endswith("is not a vocabulary lock"))


class GuardTest(SharedHelpers, ProjectCase):
    def write_as(self, agent: str | None, rel: str):
        payload = {"tool_name": "Write", "cwd": str(self.root), "tool_input": {"file_path": str(self.root / rel)}}
        if agent:
            payload["agent_type"] = f"greenlight:{agent}"
        return guard.evaluate(payload)

    def bash_as(self, agent: str, command: str):
        return guard.evaluate({"tool_name": "Bash", "cwd": str(self.root), "agent_type": f"greenlight:{agent}",
                               "tool_input": {"command": command}})

    def test_agents_cannot_write_an_included_file_or_the_lock(self):
        for agent in ("implementer", "qa-designer", "step-engineer", "system-analyst"):
            for rel in ("vendor/team.toml", ".bdd/vocabulary.lock.json"):
                with self.subTest(agent=agent, rel=rel):
                    self.assertIn("managed by the bdd command line", self.write_as(agent, rel))

    def test_other_files_in_the_same_folder_are_not_affected(self):
        self.assertIsNone(self.write_as("implementer", "vendor/unrelated.py"))

    def test_a_shell_command_naming_them_is_refused(self):
        for command in ("echo x >> vendor/team.toml", "cp evil.toml vendor/team.toml", "echo {} > .bdd/vocabulary.lock.json"):
            with self.subTest(command=command):
                self.assertIn("managed by", self.bash_as("implementer", command))
        self.assertIsNone(self.bash_as("implementer", "cat vendor/other.txt"))

    def test_the_bare_name_after_a_cd_and_a_glob_are_refused_too(self):
        for command in ("cd vendor && echo x > team.toml", "echo x > vendor/t*.toml", "echo x > vendor/te?m.toml",
                        "cd vendor; cp /tmp/evil.toml ./team.toml"):
            with self.subTest(command=command):
                self.assertIn("managed by", self.bash_as("implementer", command))

    def test_pinning_is_the_persons_act_for_every_tool_call(self):
        for command in ("bdd vocabulary pin", "${CLAUDE_PLUGIN_ROOT}/tools/bdd/bdd vocabulary pin && echo ok",
                        "bdd init --shared-vocabulary vendor/team.toml"):
            for agent in ("implementer", "qa-designer", None):
                with self.subTest(command=command, agent=agent):
                    payload = {"tool_name": "Bash", "cwd": str(self.root), "tool_input": {"command": command}}
                    if agent:
                        payload["agent_type"] = f"greenlight:{agent}"
                    self.assertIn("the person's act", guard.evaluate(payload))
        self.assertIsNone(self.bash_as("implementer", "bdd vocabulary list"))

    def test_bdd_pr_write_counts_as_a_write_to_the_description_file(self):
        command = "${CLAUDE_PLUGIN_ROOT}/tools/bdd/bdd pr FEAT-007 --write"
        self.assertIn("may not write production files", self.bash_as("qa-designer", command))
        self.assertIsNone(self.bash_as("implementer", command))
        self.assertIsNone(self.bash_as("qa-designer", "bdd pr FEAT-007"))

    def test_a_broken_include_list_does_not_uncover_pinned_files(self):
        sharedvocab.pin(self.root, [self.shared])
        self.main.write_text('extends = "core"\n\n[vocabulary]\ninclude = [\n', encoding="utf-8", newline="\n")   # not TOML
        self.assertEqual(sharedvocab.safe_closure(self.main), [])
        self.assertEqual(sharedvocab.protected_files(self.main), [self.shared.resolve()])
        self.assertIn("managed by the bdd command line", self.write_as("implementer", "vendor/team.toml"))
        self.assertIn("managed by", self.bash_as("implementer", "echo x > vendor/team.toml"))

    def test_a_cycle_does_not_uncover_the_files_it_names(self):
        self.write("vendor/a.toml", toml("vendor/b.toml"))
        self.write("vendor/b.toml", toml("vendor/a.toml"))
        self.main.write_text(toml("vendor/a.toml"), encoding="utf-8", newline="\n")
        self.assertEqual({p.name for p in sharedvocab.protected_files(self.main)}, {"a.toml", "b.toml"})
        self.assertIn("managed by the bdd command line", self.write_as("implementer", "vendor/a.toml"))


class TripwireTest(SharedHelpers, ProjectCase):
    def test_included_files_and_the_lock_are_watched(self):
        sharedvocab.pin(self.root, [self.shared])
        watched = {p.resolve() for p in tripwire.watched_files(self.root, None)}
        self.assertIn(self.shared.resolve(), watched)
        self.assertIn((self.root / ".bdd" / "vocabulary.lock.json").resolve(), watched)

    def test_a_broken_include_list_keeps_pinned_files_watched(self):
        sharedvocab.pin(self.root, [self.shared])
        self.main.write_text('extends = "core"\n\n[vocabulary]\ninclude = [\n', encoding="utf-8", newline="\n")   # not TOML
        watched = {p.resolve() for p in tripwire.watched_files(self.root, None)}
        self.assertIn(self.shared.resolve(), watched)

    def test_a_change_is_a_violation_once_the_baseline_exists(self):
        sharedvocab.pin(self.root, [self.shared])
        tripwire.accept(self.root, None)
        self.shared.write_text(SHARED.replace("lists", "hides"), encoding="utf-8", newline="\n")
        found = tripwire.check(self.root, None, "Bash")
        self.assertTrue(any(f["kind"] == "changed" and f["path"].endswith("vendor/team.toml") for f in found))


class CommandTest(SharedHelpers, ProjectCase):
    def test_list_check_and_pin(self):
        code, out, _ = self.cli("vocabulary", "list")
        self.assertEqual(code, 0)
        self.assertIn("1 project or shared step(s); 1 included file(s)", out)
        self.assertIn("D.TEAM.CATALOG", out)
        self.assertIn("vendor/team.toml", out)
        self.assertEqual(self.cli("vocabulary", "check")[0], 1)                 # not pinned yet
        code, out, _ = self.cli("vocabulary", "pin")
        self.assertEqual(code, 0)
        self.assertIn("vendor/team.toml", out)
        self.assertEqual(self.cli("vocabulary", "check")[0], 0)

    def test_list_as_json(self):
        data = json.loads(self.cli("vocabulary", "list", "--json")[1])
        self.assertEqual((data["included"], data["steps"][0]["file"]), (["vendor/team.toml"], "vendor/team.toml"))

    def test_pin_refuses_a_cycle(self):
        self.write("vendor/team.toml", toml("vendor/team.toml"))
        code, _, err = self.cli("vocabulary", "pin")
        self.assertEqual(code, 2)
        self.assertIn("include cycle", err)
        self.assertFalse((self.root / ".bdd" / "vocabulary.lock.json").exists())

    def test_lint_reports_an_unpinned_file(self):
        self.write("features/ok.feature", "@FEAT-007\nFeature: x\n")
        code, out, _ = self.cli("lint", "features/ok.feature")
        self.assertEqual(code, 1)
        self.assertIn("L013", out)

    def test_init_includes_and_pins_in_one_step(self):
        self.main.unlink()
        code, out, _ = self.cli("init", "--shared-vocabulary", "vendor/team.toml")
        self.assertEqual(code, 0, out)
        self.assertEqual(sharedvocab.read_pins(self.root).keys(), {"vendor/team.toml"})
        self.assertEqual(self.cli("vocabulary", "check")[0], 0)
        code, _, err = self.cli("init", "--shared-vocabulary", "vendor/team.toml")
        self.assertEqual(code, 2)
        self.assertIn("already has a [vocabulary] table", err)

    def test_init_refuses_a_file_outside_the_project(self):
        self.main.unlink()
        code, _, err = self.cli("init", "--shared-vocabulary", "../outside.toml")
        self.assertEqual(code, 2)
        self.assertIn("outside the project", err)
        self.assertFalse(self.main.exists())


if __name__ == "__main__":
    unittest.main()
