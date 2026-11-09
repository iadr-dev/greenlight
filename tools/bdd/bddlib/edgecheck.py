"""The edges a rule that uses the boundary card must record in ``test-design.md``.

The ``boundary-value`` card lists the edges of what a rule limits, and the auditor used to find the ones a designer
forgot after the code was written (Fieldly's CR-001.4, CR-002.3, CR-003.3 and CR-003.4). A rule whose section names the
card in its ``Techniques:`` line needs, by the kind of value its text speaks of:

    a date or a time        leap day
    text, a length, digits  empty, maximum length
    a page of a list        page size 1

An edge is recorded when a bullet of the rule's section (an example, an exclusion) mentions it, or when a bullet says
there is no such boundary and why:

    - No leap day boundary: the date is only compared with today, never added to or counted from

Which kind a rule speaks of is read from its words, so the reason line is the way out of a false match. The check
leaves out the generic edges (first, last, one past): they depend on numbers a sentence does not let a program read
reliably, and stay with the auditor (T3).
"""
from __future__ import annotations

import re
from pathlib import Path

from . import trace

CARD = "boundary-value"
HEADING = re.compile(r"^#{2,}\s+(.*\S)\s*$")
RULE_ID = re.compile(r"\b[RN]-\d+\.\d+\b")
TECHNIQUES = re.compile(r"^\s*Techniques\s*:\s*(.*)$", re.IGNORECASE)
BULLET = re.compile(r"^\s*(?:[-*]|\d+[.)])\s+")
NO_BOUNDARY = re.compile(r"^\s*(?:[-*]\s+)?No\s+(?P<edge>[a-z0-9 ]+?)\s+boundary\s*:\s*(?P<reason>.*)$", re.IGNORECASE)

DATE = re.compile(r"\b(?:dates?|calendar|days?|months?|years?|birthday|weekday|start time|end time|deadline|expir\w*)\b"
                  r"|\b\d{4}-\d{2}-\d{2}\b", re.IGNORECASE)
TEXT = re.compile(r"\b(?:characters?|length|digits?|too long|longer than)\b", re.IGNORECASE)
PAGING = re.compile(r"\b(?:pages of|per page|page size|paged|paging|pagination|cursor)\b", re.IGNORECASE)

# edge -> (what a rule's words must say for the edge to apply, what a bullet says when it records the edge)
EDGES = {
    "leap day": (DATE, re.compile(r"leap|\b29\s+feb|\bfeb(?:ruary)?\.?\s+29|\b0?2[-/]29\b|閏", re.IGNORECASE)),
    "empty": (TEXT, re.compile(r"\bempty\b|\bblank\b|white\s?space|\bno characters\b|zero[- ]length|空白|空字", re.IGNORECASE)),
    "maximum length": (TEXT, re.compile(r"\bmax(?:imum)?\b|\blongest\b|\btoo long\b|\bone (?:character |char )?over\b|"
                                         r"\bover the limit\b|\bat the limit\b|上限|最大", re.IGNORECASE)),
    "page size 1": (PAGING, re.compile(r"page[- ]size(?: of| is)?[ =:]*1\b|\b(?:1|one) (?:item|row|record|result)s? per page\b|"
                                       r"\bsize 1\b|\bpage of (?:1|one)\b|\bone[- ]item page\b|\bsingle[- ]item page\b", re.IGNORECASE)),
}
LIMIT = re.compile(r"(?:\bat most|\bup to|\bmaximum(?: of)?|\bno more than|\blimit of|\bwithin)\s+(\d+)\b"
                   r"|\b(\d+)[- ]?(?:characters?|chars?|digits?|letters?)\b", re.IGNORECASE)
KINDS = {"leap day": "a date", "empty": "text", "maximum length": "text", "page size 1": "a page of a list"}


def _sections(text: str) -> list[tuple[str, list[str]]]:
    sections: list[tuple[str, list[str]]] = []
    for line in text.splitlines():
        heading = HEADING.match(line)
        if heading:
            sections.append((heading.group(1), []))
        elif sections:
            sections[-1][1].append(line)
    return sections


def _bullets(lines: list[str]) -> list[str]:
    """The bullets of a section with their wrapped lines: the examples and exclusions, not the prose around them."""
    found: list[str] = []
    wrapped = False
    for line in lines:
        if BULLET.match(line):
            found.append(line)
            wrapped = True
        elif wrapped and line.strip() and line[:1].isspace():
            found[-1] += " " + line.strip()
        else:
            wrapped = False
    return found


def _limits(words: str) -> set[int]:
    return {int(n) for match in LIMIT.finditer(words) for n in match.groups() if n}


def _recorded(bullets: list[str], words: str) -> tuple[set[str], list[str]]:
    """The edges the bullets record (an example mentions it, or a reason says there is none), and the reasons too short.
    A bullet that names the limit the rule states, or the value just over it, records the maximum length."""
    limits = {str(n + step) for n in _limits(words) for step in (0, 1)}
    edges: set[str] = set()
    thin: list[str] = []
    for bullet in bullets:
        said = NO_BOUNDARY.match(bullet)
        if said and said.group("edge").casefold() in EDGES:
            edge = said.group("edge").casefold()
            if len(said.group("reason").split()) >= 2:
                edges.add(edge)
            else:
                thin.append(edge)
            continue
        edges.update(edge for edge, (_, seen) in EDGES.items() if seen.search(bullet))
        if limits.intersection(re.findall(r"\d+", bullet)):
            edges.add("maximum length")
    return edges, thin


def problems(feature_dir: Path) -> list[str]:
    """One line per rule that uses the boundary card and lacks an edge; empty when ``test-design.md`` does not exist."""
    design = feature_dir / "test-design.md"
    if not design.is_file():
        return []
    rules = trace.read_ids(feature_dir / "rules.md", trace.RULE_LINE) or {}
    found: list[str] = []
    for heading, lines in _sections(design.read_text(encoding="utf-8-sig")):
        ids = RULE_ID.findall(heading)
        techniques = next((m.group(1) for m in map(TECHNIQUES.match, lines) if m), "")
        if not ids or CARD not in techniques:
            continue
        words = " ".join([heading, *(rules.get(i, "") for i in ids)])
        recorded, thin = _recorded(_bullets(lines), words)
        for edge, (applies, _) in EDGES.items():
            if not applies.search(words) or edge in recorded:
                continue
            reason = (f'the reason after "No {edge} boundary:" is too short to be a reason' if edge in thin else
                      f"add an example for it, or a line \"- No {edge} boundary: <why this rule has none>\"")
            found.append(f"{' and '.join(ids)} uses the {CARD} card for {KINDS[edge]} but records no {edge}: {reason} "
                         "in its section of test-design.md")
    return found
