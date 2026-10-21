"""Style warnings for feature files, from the point of view of the person who has to read them.

None of these is an error: a style finding never stops a gate, and a project can silence a rule it disagrees with in
``.bdd/config.toml`` (``[lint] ignore = ["L017"]``). They complement the errors of ``bdd lint`` (a step outside the
vocabulary, an implementation detail in a step, a bad trace tag) and the parse errors it already reports for a second
``Feature`` in one file and for an ``Or`` step keyword.

    L015 warning  steps are not in Given, When, Then order, or a phase comes back after a later one
    L016 warning  a scenario has more than 10 steps
    L017 warning  placeholder data (foo, bar, lorem, test, ...) where a realistic example value belongs
    L018 warning  a Background that only one scenario uses
    L019 warning  a Scenario Outline with one example row, or rows that differ only in case or spacing
    L020 warning  a scenario with no title, or text under its title (a title carried over several lines)
    L021 warning  a Feature, Rule, Background, Scenario, Examples or step not indented two spaces per level
    L022 warning  a line longer than 120 characters
    L023 warning  a blank line between two steps of one scenario
    L024 warning  no blank line between two scenarios that follow each other
    L025 warning  the file name is not kebab-case

The ideas come from the public "Gherkin guidelines for AI" by Andrew Knight (AutomationPanda); the rules here are our own
wording and leave out what conflicts with the closed step vocabulary.
"""
from __future__ import annotations

import re
from pathlib import Path

from . import gherkin
from .issues import WARNING, Issue

MAX_STEPS = 10
MAX_LINE = 120
INDENT = 2
RANKS = {"given": 0, "when": 1, "then": 2}
PLACEHOLDER_WORDS = frozenset({"foo", "bar", "baz", "lorem", "ipsum", "asdf", "xxx", "qwerty"})
PLACEHOLDER_VALUES = PLACEHOLDER_WORDS | {"test"}
INVALID_INPUT_HINTS = ("invalid", "nonsense", "malformed", "garbage", "gibberish")
INVALID_INPUT_TAGS = ("@invalid", "@invalid-input", "@placeholder-data")
KEBAB = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_WORDS = re.compile(r"[A-Za-z]+")
_QUOTED = re.compile(r'"([^"]*)"|\'([^\']*)\'')
_FENCE = ('"""', "```")


def _issue(path: str, line: int, code: str, message: str) -> Issue:
    return Issue(path, line, WARNING, code, message)


def _normal(cell: str) -> str:
    return " ".join(cell.casefold().split())


# -- structure ---------------------------------------------------------------------------
def check_order(scenario: gherkin.Scenario, path: str) -> list[Issue]:
    last = None
    for step in scenario.steps:
        rank = RANKS.get(step.kind)
        if rank is None:
            continue
        if last is not None and rank < RANKS[last]:
            return [_issue(path, step.line, "L015",
                           f'a {step.kind} step after a {last} step in "{scenario.name}": keep Given, When, Then in that '
                           "order, each phase once; a second behaviour is a second scenario")]
        last = step.kind
    return []


def check_length(scenario: gherkin.Scenario, path: str) -> list[Issue]:
    count = len(scenario.steps)
    if count <= MAX_STEPS:
        return []
    return [_issue(path, scenario.line, "L016",
                   f'"{scenario.name}" has {count} steps; aim for at most {MAX_STEPS} (split the behaviour or use a table)')]


def _is_placeholder_cell(cell: str) -> bool:
    words = [w.casefold() for w in _WORDS.findall(cell)]
    return _normal(cell) in PLACEHOLDER_VALUES or (bool(words) and all(w in PLACEHOLDER_WORDS for w in words))


def placeholder_in_step(step: gherkin.Step) -> str | None:
    """The first placeholder value a step carries in its text, quoted values or table, or None."""
    for match in _QUOTED.finditer(step.text):
        value = match.group(1) if match.group(1) is not None else match.group(2)
        if _is_placeholder_cell(value):
            return value
    for word in _WORDS.findall(step.text):
        if word.casefold() in PLACEHOLDER_WORDS:
            return word
    for row in step.table or []:
        for cell in row:
            if _is_placeholder_cell(cell):
                return cell
    return None


def _about_invalid_input(scenario: gherkin.Scenario) -> bool:
    name = scenario.name.casefold()
    return any(hint in name for hint in INVALID_INPUT_HINTS) or any(tag in INVALID_INPUT_TAGS for tag in scenario.tags)


def check_placeholders(scenario: gherkin.Scenario, path: str) -> list[Issue]:
    if _about_invalid_input(scenario):
        return []
    issues = []
    for step in scenario.steps:
        value = placeholder_in_step(step)
        if value:
            issues.append(_issue(path, step.line, "L017", f'"{value}" looks like placeholder data; use a realistic example '
                                                           "value (a name, an amount, a date), or mark the scenario as invalid input"))
            break
    for examples in scenario.examples:
        cell = next((c for row in examples.rows for c in row if _is_placeholder_cell(c)), None)
        if cell:
            issues.append(_issue(path, examples.line, "L017", f'"{cell}" looks like placeholder data in the Examples; use '
                                                              "realistic example values"))
    return issues


def check_outline_rows(scenario: gherkin.Scenario, path: str) -> list[Issue]:
    if not scenario.outline or not scenario.examples:
        return []
    rows = [(examples, tuple(_normal(c) for c in row)) for examples in scenario.examples for row in examples.rows]
    where = scenario.examples[0].line
    if len(rows) < 2:
        return [_issue(path, where, "L019", f'Scenario Outline "{scenario.name}" has {len(rows)} example row(s); '
                                            "use a Scenario unless the inputs change the behaviour")]
    seen: dict[tuple[str, ...], int] = {}
    for examples, key in rows:
        if key in seen:
            return [_issue(path, examples.line, "L019", f'two example rows of "{scenario.name}" differ only in case or '
                                                        "spacing; one of them adds nothing")]
        seen[key] = examples.line
    return []


def check_title(scenario: gherkin.Scenario, path: str) -> list[Issue]:
    if not scenario.name.strip():
        return [_issue(path, scenario.line, "L020", "this scenario has no title; name the behaviour it specifies")]
    if scenario.description.strip():
        return [_issue(path, scenario.line, "L020", f'"{scenario.name}" has text under its title; keep the title on one '
                                                    "line and put the detail in the steps")]
    return []


def check_backgrounds(feature: gherkin.Feature, path: str) -> list[Issue]:
    issues = []
    everything = [scenario for scenario, _rule in feature.scenarios()]
    if feature.background and feature.background.steps and len(everything) == 1:
        issues.append(_issue(path, feature.background.line, "L018",
                             "this Background is used by one scenario; put its steps in the scenario"))
    for child in feature.children:
        if isinstance(child, gherkin.Rule) and child.background and child.background.steps and len(child.scenarios) == 1:
            issues.append(_issue(path, child.background.line, "L018",
                                 f'the Background of Rule "{child.name}" is used by one scenario; put its steps in the scenario'))
    return issues


def check_structure(feature: gherkin.Feature, path: str) -> list[Issue]:
    issues = check_backgrounds(feature, path)
    for scenario, _rule in feature.scenarios():
        for check in (check_order, check_length, check_placeholders, check_outline_rows, check_title):
            issues += check(scenario, path)
    return issues


# -- layout ------------------------------------------------------------------------------
def _blocks(feature: gherkin.Feature) -> list[tuple[int, int, str]]:
    """(line, expected indent, what) for every block header and step."""
    found = [(feature.line, 0, "Feature")]

    def container(node, level: int, label: str) -> None:
        found.append((node.line, level, label))
        for step in node.steps:
            found.append((step.line, level + INDENT, "a step"))
        for examples in getattr(node, "examples", []):
            found.append((examples.line, level + INDENT, "Examples"))

    if feature.background:
        container(feature.background, INDENT, "Background")
    for child in feature.children:
        if isinstance(child, gherkin.Rule):
            found.append((child.line, INDENT, "Rule"))
            if child.background:
                container(child.background, 2 * INDENT, "Background")
            for scenario in child.scenarios:
                container(scenario, 2 * INDENT, "Scenario")
        else:
            container(child, INDENT, "Scenario")
    return found


def check_indentation(feature: gherkin.Feature, lines: list[str], path: str) -> list[Issue]:
    issues = []
    for number, expected, what in sorted(_blocks(feature)):
        if number > len(lines):
            continue
        raw = lines[number - 1]
        lead = raw[:len(raw) - len(raw.lstrip())]
        if "\t" in lead:
            issues.append(_issue(path, number, "L021", f"{what} is indented with a tab; use {INDENT} spaces per level"))
        elif len(lead) != expected:
            issues.append(_issue(path, number, "L021",
                                 f"{what} is indented {len(lead)} spaces; expected {expected} ({INDENT} per level)"))
    return issues


def check_long_lines(lines: list[str], path: str) -> list[Issue]:
    inside = False
    issues = []
    for number, raw in enumerate(lines, start=1):
        if raw.strip().startswith(_FENCE):
            inside = not inside
            continue
        if not inside and len(raw) > MAX_LINE:
            issues.append(_issue(path, number, "L022", f"this line has {len(raw)} characters; keep lines under {MAX_LINE}"))
    return issues


def _blank_between(lines: list[str], first: int, second: int) -> int | None:
    """The line number of a blank line between two steps, outside any doc string, or None."""
    inside = False
    for number in range(first + 1, second):
        text = lines[number - 1].strip()
        if text.startswith(_FENCE):
            inside = not inside
        elif not text and not inside:
            return number
    return None


def check_blank_between_steps(feature: gherkin.Feature, lines: list[str], path: str) -> list[Issue]:
    containers = [c for c in (feature.background, *(r.background for r in feature.children if isinstance(r, gherkin.Rule))) if c]
    containers += [scenario for scenario, _rule in feature.scenarios()]
    issues = []
    for node in containers:
        for before, after in zip(node.steps, node.steps[1:]):
            blank = _blank_between(lines, before.line, after.line)
            if blank:
                issues.append(_issue(path, blank, "L023", "no blank line between the steps of one scenario"))
                break
    return issues


def _block_start(lines: list[str], line: int) -> int:
    """The first line of a scenario's block: its header, or the tag and comment lines directly above it."""
    start = line
    while start > 1 and lines[start - 2].strip().startswith(("@", "#")):
        start -= 1
    return start


def check_blank_between_scenarios(feature: gherkin.Feature, lines: list[str], path: str) -> list[Issue]:
    groups: list[list[gherkin.Scenario]] = [[c for c in feature.children if isinstance(c, gherkin.Scenario)]]
    groups += [child.scenarios for child in feature.children if isinstance(child, gherkin.Rule)]
    issues = []
    for group in groups:
        for before, after in zip(group, group[1:]):
            start = _block_start(lines, after.line)
            if start > before.line and start > 1 and lines[start - 2].strip():
                issues.append(_issue(path, after.line, "L024", f'no blank line between "{before.name}" and "{after.name}"'))
    return issues


def check_file_name(path: str) -> list[Issue]:
    name = Path(path).name
    if not name.endswith(".feature"):
        return []
    stem = name[:-len(".feature")]
    if KEBAB.fullmatch(stem):
        return []
    return [_issue(path, 1, "L025", f'the file name "{name}" is not kebab-case (lower-case words joined by hyphens)')]


def check_layout(feature: gherkin.Feature, text: str, path: str) -> list[Issue]:
    lines = text.lstrip("\ufeff").splitlines()
    return (check_indentation(feature, lines, path) + check_long_lines(lines, path)
            + check_blank_between_steps(feature, lines, path) + check_blank_between_scenarios(feature, lines, path)
            + check_file_name(path))


def check_feature(feature: gherkin.Feature, text: str, path: str, ignore: frozenset[str] = frozenset()) -> list[Issue]:
    """Every style warning for one parsed file, minus the codes the project silenced."""
    issues = check_structure(feature, path) + check_layout(feature, text, path)
    return [issue for issue in issues if issue.code not in ignore]

