"""A small Gherkin parser (stdlib only).

Supports what greenlight needs: ``# language:`` headers with localized keywords, Feature,
Rule, Background, Scenario, Scenario Outline, Examples, steps, data tables, doc strings,
tags and comments. It builds a plain-dataclass tree and raises ``ParseError`` with a line
number on anything it cannot place, instead of guessing.

Not supported (and reported as errors where they would be silently wrong): the legacy
``Scenarios:`` alias is accepted, but Gherkin's older ``Feature``-level step syntax is not.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Iterator

LANG_FILE = Path(__file__).resolve().parent / "data" / "gherkin-languages.json"
_LANG_COMMENT = re.compile(r"^\s*#\s*language\s*:\s*([A-Za-z-]+)\s*$")
_TAG = re.compile(r"@\S+")
STEP_KINDS = ("given", "when", "then")


class ParseError(ValueError):
    def __init__(self, message: str, line: int, path: str = "<string>"):
        super().__init__(f"{path}:{line}: {message}")
        self.message, self.line, self.path = message, line, path


@dataclass
class Step:
    keyword: str          # as written, e.g. "And" or "並且"
    kind: str             # given | when | then (And/But/* inherit the previous kind)
    text: str
    line: int
    table: list[list[str]] | None = None
    docstring: str | None = None
    docstring_type: str | None = None
    comments: list[str] = field(default_factory=list)   # comment lines directly above the step

    @property
    def proposed(self) -> bool:
        """True if marked ``# proposed-step``: a step the author wants added to the vocabulary."""
        return any(c.lower().startswith("proposed-step") for c in self.comments)


@dataclass
class Examples:
    name: str
    tags: list[str]
    header: list[str]
    rows: list[list[str]]
    line: int


@dataclass
class Background:
    name: str
    steps: list[Step]
    line: int


@dataclass
class Scenario:
    name: str
    tags: list[str]
    steps: list[Step]
    line: int
    outline: bool = False
    examples: list[Examples] = field(default_factory=list)
    description: str = ""


@dataclass
class Rule:
    name: str
    tags: list[str]
    line: int
    description: str = ""
    background: Background | None = None
    scenarios: list[Scenario] = field(default_factory=list)


@dataclass
class Feature:
    name: str
    tags: list[str]
    language: str
    line: int
    description: str = ""
    background: Background | None = None
    children: list[Scenario | Rule] = field(default_factory=list)

    def scenarios(self) -> Iterator[tuple[Scenario, Rule | None]]:
        """Every scenario with its enclosing Rule (None if directly under the Feature)."""
        for child in self.children:
            if isinstance(child, Rule):
                for sc in child.scenarios:
                    yield sc, child
            else:
                yield child, None

    def effective_tags(self, scenario: Scenario, rule: Rule | None = None) -> list[str]:
        """Tags that apply to a scenario: feature + rule + scenario (+ its Examples blocks)."""
        tags = list(self.tags) + (list(rule.tags) if rule else []) + list(scenario.tags)
        for ex in scenario.examples:
            tags += ex.tags
        return list(dict.fromkeys(tags))


@lru_cache(maxsize=1)
def languages() -> dict:
    return json.loads(LANG_FILE.read_text(encoding="utf-8"))


class _Keywords:
    """Keyword lookup for one language."""

    HEADERS = ("feature", "rule", "background", "scenario", "scenarioOutline", "examples")

    def __init__(self, code: str, path: str, line: int):
        langs = languages()
        if code not in langs:
            raise ParseError(f"unknown language {code!r} in '# language:' header", line, path)
        spec = langs[code]
        self.code = code
        # Longest first so "Scenario Outline" wins over "Scenario".
        self.headers = sorted(
            ((kw, role) for role in self.HEADERS for kw in spec.get(role, [])),
            key=lambda pair: -len(pair[0]))
        self.steps = sorted(
            ((kw, role) for role in ("given", "when", "then", "and", "but") for kw in spec.get(role, [])),
            key=lambda pair: -len(pair[0]))

    def header(self, text: str) -> tuple[str, str] | None:
        for kw, role in self.headers:
            if text.startswith(kw + ":"):
                return role, text[len(kw) + 1:].strip()
        return None

    def step(self, text: str) -> tuple[str, str, str] | None:
        """Return (keyword as written, role, rest) if the line starts with a step keyword."""
        for kw, role in self.steps:
            if text.startswith(kw):
                # "* " is listed under every role in the language data; it always continues
                # the previous step's kind, like And/But.
                return kw.strip(), ("and" if kw.strip() == "*" else role), text[len(kw):].strip()
        return None


def split_cells(line: str, number: int, path: str) -> list[str]:
    """Split a table row. Supports the escapes \\| \\\\ and \\n inside cells."""
    body = line.strip()
    if not (body.startswith("|") and body.endswith("|") and len(body) >= 2):
        raise ParseError("table row must start and end with '|'", number, path)
    inner = body[1:-1]
    cells, buf, i = [], [], 0
    while i < len(inner):
        ch = inner[i]
        if ch == chr(92) and i + 1 < len(inner):
            nxt = inner[i + 1]
            buf.append({"|": "|", chr(92): chr(92), "n": chr(10)}.get(nxt, ch + nxt))
            i += 2
            continue
        if ch == "|":
            cells.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
        i += 1
    cells.append("".join(buf).strip())
    return cells


class _Parser:
    def __init__(self, text: str, path: str):
        self.lines = text.lstrip(chr(0xFEFF)).splitlines()
        self.path = path
        self.i = 0
        self.kw: _Keywords | None = None
        self.pending_tags: list[str] = []
        self.feature: Feature | None = None
        self.rule: Rule | None = None
        self.container: Background | Scenario | None = None   # where steps go
        self.last_kind: str | None = None
        self.last_step: Step | None = None
        self.examples: Examples | None = None
        self.desc_target: Feature | Rule | Scenario | None = None
        self.pending_comments: list[str] = []

    def err(self, msg: str, line: int | None = None) -> ParseError:
        return ParseError(msg, line if line is not None else self.i + 1, self.path)

    # -- header ------------------------------------------------------------------------
    def detect_language(self) -> None:
        code = "en"
        for n, raw in enumerate(self.lines, start=1):
            s = raw.strip()
            if not s:
                continue
            m = _LANG_COMMENT.match(s)
            if m:
                code = m.group(1)
                self.kw = _Keywords(code, self.path, n)
                return
            if not s.startswith("#"):
                break
        self.kw = _Keywords(code, self.path, 1)

    # -- main loop ---------------------------------------------------------------------
    def parse(self) -> Feature:
        self.detect_language()
        while self.i < len(self.lines):
            self.consume_line()
            self.i += 1
        if self.feature is None:
            raise self.err("no Feature found", 1)
        if self.pending_tags:
            raise self.err("tags at end of file are not followed by anything", len(self.lines))
        return self.feature

    def consume_line(self) -> None:
        s = self.lines[self.i].strip()
        if not s:
            return
        if s.startswith("#"):
            self.pending_comments.append(s.lstrip("#").strip())
            return
        if s.startswith("@"):
            self.pending_tags += _TAG.findall(s)
            return
        if s.startswith("|"):
            self.table_row(s)
            return
        if s.startswith('"""') or s.startswith("```"):
            self.docstring(s)
            return
        header = self.kw.header(s)
        if header:
            self.start_block(*header)
            return
        step = self.kw.step(s)
        if step and self.container is not None:
            self.add_step(*step)
            return
        self.add_description(s)   # also covers "When ..." prose in a Feature/Rule description

    # -- blocks ------------------------------------------------------------------------
    def take_tags(self) -> list[str]:
        tags, self.pending_tags = self.pending_tags, []
        return tags

    def start_block(self, role: str, title: str) -> None:
        line = self.i + 1
        self.last_step = self.last_kind = None
        self.pending_comments = []
        if role == "feature":
            self.start_feature(title, line)
            return
        if self.feature is None:
            raise self.err(f"{role} before Feature", line)
        {"rule": self.start_rule, "background": self.start_background,
         "scenario": self.start_scenario, "scenarioOutline": self.start_scenario,
         "examples": self.start_examples}[role](title, line, role)

    def start_feature(self, title: str, line: int) -> None:
        if self.feature is not None:
            raise self.err("only one Feature per file", line)
        self.feature = Feature(title, self.take_tags(), self.kw.code, line)
        self.desc_target, self.container, self.examples, self.rule = self.feature, None, None, None

    def start_rule(self, title: str, line: int, role: str = "rule") -> None:
        self.rule = Rule(title, self.take_tags(), line)
        self.feature.children.append(self.rule)
        self.desc_target, self.container, self.examples = self.rule, None, None

    def start_background(self, title: str, line: int, role: str = "background") -> None:
        if self.pending_tags:
            raise self.err("tags are not allowed on Background", line)
        owner = self.rule or self.feature
        started = bool(self.rule.scenarios) if owner is self.rule else bool(self.feature.children)
        if owner.background is not None or started:
            raise self.err("Background must come first and only once per Feature/Rule", line)
        owner.background = Background(title, [], line)
        self.container, self.examples, self.desc_target = owner.background, None, None

    def start_scenario(self, title: str, line: int, role: str) -> None:
        sc = Scenario(title, self.take_tags(), [], line, outline=(role == "scenarioOutline"))
        (self.rule.scenarios if self.rule else self.feature.children).append(sc)
        self.container, self.examples, self.desc_target = sc, None, sc

    def start_examples(self, title: str, line: int, role: str = "examples") -> None:
        if not isinstance(self.container, Scenario) or not self.container.outline:
            raise self.err("Examples is only allowed inside a Scenario Outline", line)
        self.examples = Examples(title, self.take_tags(), [], [], line)
        self.container.examples.append(self.examples)
        self.last_step, self.desc_target = None, None

    def add_description(self, s: str) -> None:
        if self.pending_tags:
            raise self.err("tags must be followed by Feature, Rule, Scenario or Examples")
        target = self.desc_target
        if target is None or self.container_has_steps():
            raise self.err(f"unexpected text {s!r} (a step must start with Given/When/Then/And/But/*)")
        target.description = (target.description + "\n" + s).strip()

    def container_has_steps(self) -> bool:
        return bool(isinstance(self.container, (Scenario, Background)) and self.container.steps)

    # -- steps, tables, doc strings ----------------------------------------------------
    def add_step(self, keyword: str, role: str, text: str) -> None:
        if self.pending_tags:
            raise self.err("tags must be followed by Feature, Rule, Scenario or Examples")
        if self.container is None or self.examples is not None:
            raise self.err(f"step {keyword!r} outside a Scenario or Background")
        if role in STEP_KINDS:
            kind = role
        elif self.last_kind:
            kind = self.last_kind
        else:
            raise self.err(f"step {keyword!r} has no preceding Given/When/Then to continue")
        step = Step(keyword, kind, text, self.i + 1, comments=self.pending_comments)
        self.pending_comments = []
        self.container.steps.append(step)
        self.last_step, self.last_kind, self.desc_target = step, kind, None

    def table_row(self, s: str) -> None:
        cells = split_cells(s, self.i + 1, self.path)
        if self.examples is not None:
            if not self.examples.header:
                self.examples.header = cells
            elif len(cells) != len(self.examples.header):
                raise self.err(f"Examples row has {len(cells)} cells, header has {len(self.examples.header)}")
            else:
                self.examples.rows.append(cells)
            return
        step = self.last_step
        if step is None or step.docstring is not None:
            raise self.err("table is only allowed directly after a step or under Examples")
        if step.table is None:
            step.table = [cells]
        elif len(cells) != len(step.table[0]):
            raise self.err(f"table row has {len(cells)} cells, header has {len(step.table[0])}")
        else:
            step.table.append(cells)

    def docstring(self, opener: str) -> None:
        step = self.last_step
        if step is None or step.table is not None or step.docstring is not None:
            raise self.err("doc string is only allowed directly after a step")
        delim = opener[:3]
        indent = len(self.lines[self.i]) - len(self.lines[self.i].lstrip())
        step.docstring_type = opener[3:].strip() or None
        body, start = [], self.i + 1
        self.i += 1
        while self.i < len(self.lines):
            raw = self.lines[self.i]
            if raw.strip() == delim:
                step.docstring = "\n".join(body)
                return
            body.append(raw[indent:] if raw[:indent].strip() == "" else raw.lstrip())
            self.i += 1
        raise self.err(f"doc string opened with {delim} is never closed", start)


def parse(text: str, path: str = "<string>") -> Feature:
    return _Parser(text, path).parse()


def parse_file(path: str | Path) -> Feature:
    p = Path(path)
    return parse(p.read_text(encoding="utf-8-sig"), str(p))
