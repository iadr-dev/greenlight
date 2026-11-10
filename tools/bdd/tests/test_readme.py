"""The README and the docs a newcomer follows name only commands, flags, files, links and counts that exist.

Commands: every `bdd COMMAND ...` in a code span or a fenced block of README.md, docs/quickstart.md and
docs/troubleshooting.md must be a command of the CLI, and every `--flag` on it must be in that command's `--help`. A
fenced block whose opening line has the word `not-bdd` after the language (```text not-bdd) is skipped: use it for a
`bdd` that is not this program. A `bdd` code span that runs over two lines is not read, so keep each on one line.
"""
import contextlib
import functools
import io
import re
import unittest
from pathlib import Path
from typing import NamedTuple

from bddlib import cli, helpers, state

REPO = Path(__file__).resolve().parents[3]
BDDLIB = REPO / "tools" / "bdd" / "bddlib"
COMMAND_DOCS = [REPO / "README.md", REPO / "docs" / "quickstart.md", REPO / "docs" / "troubleshooting.md"]
LINKED_DOCS = [REPO / "README.md", *sorted((REPO / "docs").glob("*.md"))]
SKIP_MARKER = "not-bdd"
# These commands read hook input from stdin or run their checks when started, so `--help` is not asked of them: a flag
# is looked up in the source of the module that implements the command.
NO_HELP = frozenset({"doctor", "guard", "tripwire", "codex-hook", "subagent-stop"})
REPO_FOLDERS = ("adapters", "agents", "cards", "docs", "evals", "hooks", "phases", "review", "skills", "specs", "templates",
                "tools", "vocabulary")

FENCE = re.compile(r"^\s*(`{3,}|~{3,})(.*)$")
SPAN = re.compile(r"`([^`\n]+)`")
COMMAND = re.compile(r"(?:(?<![\w/.\-<])bdd|tools/bdd/bdd\"?)\s+(?P<command>[a-z][a-z-]*)(?P<rest>[^`\n]*)")
FLAG = re.compile(r"(?<![\w-])--[a-z][a-z-]*")
LINK = re.compile(r"\]\((?P<target>[^)\s]+)\)|(?:href|src)=\"(?P<attr>[^\"]+)\"")
HEADING = re.compile(r"^#{1,6}\s+(?P<text>.+?)\s*#*\s*$")
WORDS = r"zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|\d+"
# "two adapters" can mean the two a project uses, so adapters are counted only as "the nine adapters" or "all nine adapters".
COUNT = re.compile(rf"\b(?:(?:the|all)\s+(?P<all>{WORDS})\s+adapters|(?P<some>{WORDS})\s+"
                   r"(?P<noun>skills|slash commands|agents|test stacks|phases|recommended plugins|recommended helpers))\b",
                   re.IGNORECASE)
NUMBERS = {word: n for n, word in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve".split())}


class Shown(NamedTuple):
    path: str
    line: int
    command: str
    rest: str


def code_snippets(text: str):
    """(line number, code) for every fenced line that is not marked `not-bdd` and every inline code span."""
    skipping = False
    fence = None
    for number, line in enumerate(text.splitlines(), 1):
        opening = FENCE.match(line)
        if fence is None and opening:
            fence = opening.group(1)[0]
            skipping = SKIP_MARKER in opening.group(2).split()
            continue
        if fence is not None:
            if opening and opening.group(1)[0] == fence and not opening.group(2).strip():
                fence = None
                skipping = False
            elif not skipping:
                yield number, re.split(r"\s#\s", line)[0]
            continue
        for span in SPAN.finditer(line):
            yield number, span.group(1)


def shown_commands(text: str, path: str = "") -> list[Shown]:
    return [Shown(path, number, match.group("command"), match.group("rest"))
            for number, code in code_snippets(text) for match in COMMAND.finditer(code)]


def prose_outside_fences(text: str) -> str:
    kept, fence = [], None
    for line in text.splitlines():
        opening = FENCE.match(line)
        if fence is None and opening:
            fence = opening.group(1)[0]
        elif fence is not None and opening and opening.group(1)[0] == fence and not opening.group(2).strip():
            fence = None
        elif fence is None:
            kept.append(line)
    return "\n".join(kept)


@functools.lru_cache(maxsize=None)
def help_text(*argv: str) -> str:
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        try:
            cli.main([*argv, "--help"])
        except SystemExit:
            pass
    return out.getvalue()


def source_text(command: str) -> str:
    return (BDDLIB / f"{cli.COMMANDS[command][0]}.py").read_text(encoding="utf-8")


def choices(text: str) -> set[str]:
    return {word for group in re.findall(r"\{([a-z][a-z,-]*)\}", text) for word in group.split(",")}


def problems_of(shown: Shown) -> list[str]:
    where = f"{shown.path}:{shown.line}: bdd {shown.command}{shown.rest}".rstrip()
    if shown.command not in cli.COMMANDS:
        return [f"{where}: there is no command `{shown.command}` (commands: {', '.join(sorted(cli.COMMANDS))})"]
    words = shown.rest.split()
    found: list[str] = []
    if shown.command in NO_HELP:
        known = source_text(shown.command)
    else:
        known = help_text(shown.command)
        first = words[0] if words else ""
        valid = choices(known)
        if valid and re.fullmatch(r"[a-z][a-z-]*", first) and first not in valid:
            found.append(f"{where}: `{first}` is not one of {sorted(valid)}")
        if valid and first in valid:
            known += help_text(shown.command, first)
    across = cli.ACROSS_WORKSPACE if shown.command in cli.ACROSS_WORKSPACE else ()
    for flag in FLAG.findall(shown.rest):
        if flag not in known and not (flag == "--workspace" and across):
            found.append(f"{where}: `{flag}` is not an option of `bdd {shown.command}`")
    return found


def slug(heading: str) -> str:
    plain = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", heading).replace("`", "")
    return re.sub(r"[^\w\- ]", "", plain.lower()).replace(" ", "-")


@functools.lru_cache(maxsize=None)
def anchors(path: Path) -> frozenset[str]:
    found: set[str] = set()
    seen: dict[str, int] = {}
    for line in prose_outside_fences(path.read_text(encoding="utf-8")).splitlines():
        heading = HEADING.match(line)
        if heading:
            base = slug(heading.group("text"))
            count = seen.get(base, 0)
            found.add(base if count == 0 else f"{base}-{count}")
            seen[base] = count + 1
    return frozenset(found)


def link_problems(path: Path, text: str) -> list[str]:
    found = []
    for match in LINK.finditer(prose_outside_fences(text)):
        target = match.group("target") or match.group("attr")
        if re.match(r"[a-z][a-z0-9+.-]*:", target, re.IGNORECASE):
            continue
        name, _, fragment = target.partition("#")
        destination = (path.parent / name).resolve() if name else path
        label = f"{path.relative_to(REPO).as_posix()}: ({target})"
        if not destination.exists():
            found.append(f"{label}: there is no file {name}")
        elif fragment and destination.suffix == ".md" and fragment not in anchors(destination):
            found.append(f"{label}: {destination.name} has no heading #{fragment}")
    return found


def counts() -> dict[str, int]:
    skills = len(list((REPO / "skills").glob("*/SKILL.md")))
    adapters = len([p for p in (REPO / "adapters").iterdir() if p.is_dir()])
    recommended = len([h for h in helpers.CATALOG if h.recommended])
    return {"skills": skills, "slash commands": skills, "agents": len(list((REPO / "agents").glob("*.md"))),
            "adapters": adapters, "test stacks": adapters, "phases": len(state.PHASES) - 1,
            "recommended plugins": recommended, "recommended helpers": recommended}


def stated(match: re.Match) -> tuple[int, str]:
    """The number a COUNT match says and the noun it counts."""
    said = (match.group("all") or match.group("some")).lower()
    return (int(said) if said.isdigit() else NUMBERS[said]), ("adapters" if match.group("all") else match.group("noun").lower())


def count_problems(path: Path, text: str) -> list[str]:
    actual = counts()
    found = []
    for match in COUNT.finditer(prose_outside_fences(text)):
        said, noun = stated(match)
        if said != actual[noun]:
            found.append(f"{path.relative_to(REPO).as_posix()}: says {match.group(0)!r}, the files have {actual[noun]}")
    return found


def path_problems(path: Path, text: str) -> list[str]:
    found = []
    for number, code in code_snippets(text):
        for word in code.replace('"', " ").split():
            word = word.strip("`'(),;:.")
            top = word.split("/", 1)[0]
            if "/" not in word or top not in REPO_FOLDERS or re.search(r"[<>*{}$\[\]]|\.\.\.", word):
                continue
            if not (REPO / word.rstrip("/")).exists():
                found.append(f"{path.relative_to(REPO).as_posix()}:{number}: there is no {word}")
    return found


class ReadmeMatchesCodeTest(unittest.TestCase):
    def shown(self) -> list[Shown]:
        return [item for path in COMMAND_DOCS
                for item in shown_commands(path.read_text(encoding="utf-8"), path.relative_to(REPO).as_posix())]

    def test_the_docs_show_commands(self):
        self.assertGreater(len(self.shown()), 20)

    def test_every_command_and_flag_shown_exists(self):
        found = [problem for shown in self.shown() for problem in problems_of(shown)]
        self.assertEqual([], found)

    def test_every_relative_link_and_anchor_has_a_target(self):
        found = [problem for path in LINKED_DOCS for problem in link_problems(path, path.read_text(encoding="utf-8"))]
        self.assertEqual([], found)

    def test_every_stated_count_matches_the_files(self):
        found = [problem for path in LINKED_DOCS for problem in count_problems(path, path.read_text(encoding="utf-8"))]
        self.assertEqual([], found)

    def test_counts_are_stated_somewhere(self):
        text = "\n".join(p.read_text(encoding="utf-8") for p in LINKED_DOCS)
        nouns = {stated(m)[1] for m in COUNT.finditer(text)}
        self.assertTrue({"adapters", "agents", "test stacks", "slash commands"} <= nouns, nouns)

    def test_every_repository_path_named_in_code_exists(self):
        found = [problem for path in COMMAND_DOCS for problem in path_problems(path, path.read_text(encoding="utf-8"))]
        self.assertEqual([], found)


class CheckersTest(unittest.TestCase):
    """The checks fail on what they are meant to catch."""

    def test_a_misspelled_command_is_reported(self):
        found = [p for s in shown_commands("Run `bdd aprove FEAT-001 rules`.", "x.md") for p in problems_of(s)]
        self.assertEqual(1, len(found))
        self.assertIn("no command `aprove`", found[0])

    def test_an_unknown_flag_is_reported(self):
        shown = shown_commands("```sh\nbdd approve FEAT-001 rules --sumary\n```\n", "x.md")
        found = [p for s in shown for p in problems_of(s)]
        self.assertEqual(1, len(found))
        self.assertIn("--sumary", found[0])

    def test_a_flag_of_a_subcommand_is_read_from_its_help(self):
        self.assertEqual([], [p for s in shown_commands("`bdd state next-id`", "x.md") for p in problems_of(s)])

    def test_an_unknown_subcommand_is_reported(self):
        found = [p for s in shown_commands("`bdd state shwo FEAT-001`", "x.md") for p in problems_of(s)]
        self.assertEqual(1, len(found))

    def test_the_wrapper_path_form_is_read(self):
        shown = shown_commands('```sh\nsh "<plugin folder>/tools/bdd/bdd" statuss\n```\n', "x.md")
        self.assertEqual(["statuss"], [s.command for s in shown])

    def test_a_not_bdd_block_is_skipped(self):
        text = "```text not-bdd\nbdd frobnicate --now\n```\n```text\nbdd status\n```\n"
        self.assertEqual(["status"], [s.command for s in shown_commands(text)])

    def test_prose_and_file_names_are_not_commands(self):
        text = "The `bdd` program and `.bdd/config.toml` and `bdd ...` are not commands. Use bdd status in prose."
        self.assertEqual([], shown_commands(text))

    def test_a_comment_after_a_command_is_not_read(self):
        shown = shown_commands("```text\nbdd status        # shows --nothing\n```\n")
        self.assertEqual([], [f for s in shown for f in FLAG.findall(s.rest)])

    def test_a_flag_of_a_command_without_help_is_read_from_its_source(self):
        self.assertEqual([], [p for s in shown_commands("`bdd tripwire --accept`") for p in problems_of(s)])
        self.assertEqual(1, len([p for s in shown_commands("`bdd tripwire --acept`") for p in problems_of(s)]))

    def test_a_link_to_a_missing_file_or_heading_is_reported(self):
        readme = REPO / "README.md"
        found = link_problems(readme, "[a](docs/nothing.md) [b](docs/concepts.md#no-such-heading) [c](docs/concepts.md#locks)")
        self.assertEqual(2, len(found), found)

    def test_a_link_inside_a_code_block_is_not_read(self):
        self.assertEqual([], link_problems(REPO / "README.md", "```md\n[a](docs/nothing.md)\n```\n"))

    def test_a_wrong_count_is_reported(self):
        readme = REPO / "README.md"
        self.assertEqual(1, len(count_problems(readme, "There are 99 agents.")))
        self.assertEqual(1, len(count_problems(readme, "It covers all 7 adapters.")))
        self.assertEqual([], count_problems(readme, f"There are {counts()['agents']} agents."))
        self.assertEqual([], count_problems(readme, "A project with two adapters."))

    def test_a_missing_repository_path_is_reported(self):
        readme = REPO / "README.md"
        self.assertEqual(1, len(path_problems(readme, "See `phases/nothing.md` and `phases/quick.md`.")))

    def test_headings_become_github_anchors(self):
        self.assertEqual("running-bdd-yourself", slug("Running `bdd` yourself"))
        self.assertEqual("6-change-your-mind-later", slug("6. Change your mind later"))


if __name__ == "__main__":
    unittest.main()
