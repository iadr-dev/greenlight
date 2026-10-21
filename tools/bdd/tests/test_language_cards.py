"""The language cards whose commands are checked in CI (evals/language-cards/*.sh) keep the card and the check together:
every command the card gives is run by the check, or the card says why it cannot be, and CI runs every check."""
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
CARDS = REPO / "cards" / "practices"
CHECKS = REPO / "evals" / "language-cards"
CI = REPO / ".github" / "workflows" / "ci.yml"
TOOLS = ("cargo", "swift", "swiftlint", "swift-format", "xcodebuild", "./gradlew")
COMMAND = re.compile(r"`([^`]+)`")

# Commands a card gives that its check does not run, with the reason the card states.
NOT_RUN = {
    "swift": {"xcodebuild build -scheme <scheme> SWIFT_TREAT_WARNINGS_AS_ERRORS=YES": "needs an Xcode project and scheme",
              "xcodebuild test": "needs an Xcode project and a simulator"},
    "kotlin": {"./gradlew spotlessCheck": "an alternative to ktlintCheck; the check runs ktlint",
               "./gradlew lint": "Android lint needs the Android Gradle Plugin"},
}


def card_commands(language: str) -> set[str]:
    """The commands in the card's "Commands" list (backticked, starting with one of the stack's tools)."""
    text = (CARDS / f"language-{language}.md").read_text(encoding="utf-8")
    section = text.split("2. Commands", 1)[1].split("\n3. ", 1)[0]
    return {c.strip() for c in COMMAND.findall(section) if c.strip().startswith(TOOLS)}


def normalised(text: str) -> str:
    """The check's text with the spellings the card does not use: the resolved swift-format, and `--quiet` (the check
    keeps the log short, the card gives the command a person types)."""
    return re.sub(r"\s+", " ", text.replace("$swift_format", "swift-format")).replace(" --quiet", "")


class LanguageCardChecksTest(unittest.TestCase):
    def test_every_check_runs_in_ci(self):
        ci = CI.read_text(encoding="utf-8")
        for script in sorted(CHECKS.glob("*.sh")):
            if script.name == "expect.sh":
                continue
            with self.subTest(check=script.name):
                self.assertIn(f"bash evals/language-cards/{script.name}", ci)

    def test_every_command_of_a_checked_card_is_run_or_explained(self):
        for script in sorted(CHECKS.glob("*.sh")):
            if script.name == "expect.sh":
                continue
            language = script.stem
            body = normalised(script.read_text(encoding="utf-8"))
            for command in sorted(card_commands(language)):
                with self.subTest(card=language, command=command):
                    if command in NOT_RUN.get(language, {}):
                        continue
                    words = [w for w in command.split() if not w.startswith("<")]
                    self.assertIn(" ".join(words), body, f"the {language} check does not run `{command}`")

    def test_the_checked_cards_say_they_were_run(self):
        for script in sorted(CHECKS.glob("*.sh")):
            if script.name == "expect.sh":
                continue
            with self.subTest(card=script.stem):
                text = (CARDS / f"language-{script.stem}.md").read_text(encoding="utf-8")
                self.assertIn(f"evals/language-cards/{script.name}", text)
                self.assertNotIn("were not run against a real project", text)


if __name__ == "__main__":
    unittest.main()
