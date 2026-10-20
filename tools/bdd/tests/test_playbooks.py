import json
import re
import unittest
from pathlib import Path

from bddlib import cards, cli, state

REPO = Path(__file__).resolve().parents[3]
PHASES = REPO / "phases"
HEADINGS = ["Inputs", "Steps", "Output files", "Gate", "Pitfalls"]
BDD_COMMAND = re.compile(r"\bbdd ([a-z][a-z-]*)")
GATE_COMMAND = re.compile(r"bdd gate FEAT-n ([a-z-]+) --result")


def playbook(name: str) -> str:
    return (PHASES / f"{name}.md").read_text(encoding="utf-8")


class PlaybookTest(unittest.TestCase):
    def test_every_phase_has_a_playbook_with_the_same_shape(self):
        for phase in (p for p in state.PHASES if p != "done"):
            with self.subTest(phase=phase):
                text = playbook(phase)
                found = [h.split(" (")[0] for h in cards.sections(text) if h.split(" (")[0] in HEADINGS]
                self.assertEqual(found, HEADINGS)
                self.assertRegex(text, r"(?m)^Agent: (the )?\*\*[a-z-]+\*\*", "the playbook names the agent that runs it")

    def test_there_is_a_playbook_for_nothing_else_but_the_quick_and_adoption_paths(self):
        names = {p.stem for p in PHASES.glob("*.md")}
        self.assertEqual(names - set(state.PHASES), {"quick", "adopt"})

    def test_the_quick_path_keeps_the_approvals_and_the_red_gate(self):
        text = playbook("quick")
        for kept in ("approves the rules", "approves the examples", "red", "lock", "guard"):
            self.assertIn(kept, text)

    def test_every_bdd_command_named_exists(self):
        for path in PHASES.glob("*.md"):
            for command in set(BDD_COMMAND.findall(path.read_text(encoding="utf-8"))):
                with self.subTest(playbook=path.stem, command=command):
                    self.assertIn(command, cli.COMMANDS)

    def test_every_bdd_command_a_skill_names_exists(self):
        for path in (REPO / "skills").glob("*/SKILL.md"):
            for command in set(BDD_COMMAND.findall(path.read_text(encoding="utf-8"))):
                with self.subTest(skill=path.parent.name, command=command):
                    self.assertIn(command, cli.COMMANDS)

    def test_the_gate_each_playbook_records_is_a_real_machine_gate_of_its_phase(self):
        own = {"discover": "discover", "test-design": "test-design", "system-map": "system-map", "refine": "refine",
               "bind": "bind", "tasks": "tasks", "implement": "implement", "verify": "verify"}
        for phase, gate in own.items():
            with self.subTest(phase=phase):
                self.assertIn(gate, GATE_COMMAND.findall(playbook(phase)))
        for path in PHASES.glob("*.md"):
            for gate in GATE_COMMAND.findall(path.read_text(encoding="utf-8")):
                self.assertIn(gate, state.MACHINE_GATES, path.name)

    def test_cards_and_templates_named_exist(self):
        index = {c["id"] for c in json.loads((REPO / "cards" / "index.json").read_text(encoding="utf-8"))["cards"]}
        for path in PHASES.glob("*.md"):
            text = path.read_text(encoding="utf-8")
            header = next((line for line in text.splitlines() if line.startswith("Agent:")), "")
            for name in re.findall(r"`([a-z][a-z-]*)`", header.split("Cards:", 1)[-1] if "Cards:" in header else ""):
                with self.subTest(playbook=path.stem, card=name):
                    self.assertIn(name, index)
            for template in re.findall(r"templates/([a-z-]+\.md)", text):
                with self.subTest(playbook=path.stem, template=template):
                    self.assertTrue((REPO / "templates" / template).is_file())
            for card in re.findall(r"read (?:the )?`([a-z][a-z-]+)`", text):
                with self.subTest(playbook=path.stem, read=card):
                    self.assertIn(card, index)


class FeatureSkillTest(unittest.TestCase):
    """The orchestrator's table agrees with the phases, the agents and the gates of the tool."""

    TEXT = (REPO / "skills" / "feature" / "SKILL.md").read_text(encoding="utf-8")
    ROWS = re.findall(r"^\| ([a-z-]+) \| ([a-z-]+(?:, one task at a time)?|you) \|", TEXT, re.MULTILINE)

    def test_every_phase_but_done_has_a_row_with_its_agent_in_order(self):
        self.assertEqual([phase for phase, _ in self.ROWS], [p for p in state.PHASES if p != "done"])
        for phase, who in self.ROWS:
            agent = who.split(",")[0]
            with self.subTest(phase=phase):
                if agent != "you":
                    self.assertTrue((REPO / "agents" / f"{agent}.md").is_file(), agent)
                    self.assertRegex((PHASES / f"{phase}.md").read_text(encoding="utf-8"), rf"(?m)^Agent: \*\*{agent}\*\*")

    def test_every_gate_it_records_is_a_machine_gate_and_every_phase_gate_is_covered(self):
        gates = set(re.findall(r"bdd gate FEAT-n ([a-z-]+) --result", self.TEXT))
        self.assertEqual(gates, set(state.MACHINE_GATES))

    def test_the_human_gates_and_the_commands_it_gives_the_person_are_the_real_ones(self):
        for gate in ("rules", "examples"):
            self.assertIn(f"/greenlight:approve FEAT-n {gate}", self.TEXT)
        for command in ("state next-id", "state init", "approve FEAT-n --verify", "mode FEAT-n --switch"):
            self.assertIn(command, self.TEXT)
        self.assertIn("state", cli.COMMANDS)

    def test_the_skill_never_hands_the_agents_the_job_of_recording(self):
        self.assertIn("you are the only one who records", self.TEXT)


if __name__ == "__main__":
    unittest.main()
