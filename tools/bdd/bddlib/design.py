"""`bdd design FEAT-n`: checks on the Mermaid design view (``design.md``) of a feature.

The file holds fenced ``mermaid`` blocks, only the views the feature needs. Findings:

    D1  there is no design.md, or it holds no mermaid block
    D2  a fence is never closed
    D3  a block does not start with a known diagram type
    D4  unbalanced brackets (text in double quotes is ignored)
    D5  something that makes a diagram active: click, href, link directives, init directives, scripts
    D6  a ``%% interface: NAME`` comment names an interface that ``system.md`` does not list

A diagram says which interfaces of ``system.md`` it shows with ``%% interface: place order`` comments (a comment is
plain text to every renderer), so the check needs no knowledge of the diagram syntax.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from . import store
from .errors import StoreError, UsageError
from .issues import ERROR, Issue

DESIGN_FILE = "design.md"
HEADERS = ("flowchart", "graph", "sequenceDiagram", "classDiagram", "erDiagram", "stateDiagram-v2", "stateDiagram")
_FENCE = re.compile(r"^\s*(`{3,}|~{3,})\s*(\w*)\s*$")
_QUOTED = re.compile(r'"[^"\n]*"')
_CARDINALITY = re.compile(r"[|o}{]{1,2}(?:--|\.\.)[|o}{]{1,2}")      # erDiagram relations such as ||--|{
_ACTIVE =re.compile(r"(^\s*(click|link|links|callback)\b)|href|javascript:|<script|%%\{", re.IGNORECASE | re.MULTILINE)
_INTERFACE = re.compile(r"^\s*%%\s*interface\s*:\s*(.+?)\s*$", re.IGNORECASE)
_HEADING = re.compile(r"^\s*#{1,6}\s*(.*)$")
PAIRS = {")": "(", "]": "[", "}": "{"}


def blocks(lines: list[str]) -> tuple[list[tuple[int, list[str]]], list[int]]:
    """The mermaid blocks as (first line number, lines), and the line numbers of fences never closed."""
    found: list[tuple[int, list[str]]] = []
    open_at: tuple[int, str, str] | None = None
    body: list[str] = []
    for number, line in enumerate(lines, start=1):
        fence = _FENCE.match(line)
        if open_at is None:
            if fence and fence.group(2).lower() == "mermaid":
                open_at, body = (number, fence.group(1), fence.group(2)), []
        elif fence and fence.group(1)[0] == open_at[1][0] and len(fence.group(1)) >= len(open_at[1]) and not fence.group(2):
            found.append((open_at[0] + 1, body))
            open_at = None
        else:
            body.append(line)
    return found, [open_at[0]] if open_at else []


def interfaces(system_md: Path) -> set[str]:
    """Logical names in the first column of the table under an Interfaces heading, lower-cased."""
    names: set[str] = set()
    if not system_md.is_file():
        return names
    in_section = False
    for line in system_md.read_text(encoding="utf-8-sig").splitlines():
        heading = _HEADING.match(line)
        if heading:
            in_section = "interface" in heading.group(1).casefold()
        elif in_section and line.lstrip().startswith("|"):
            cell = line.strip().strip("|").split("|")[0].strip().strip("`*_ ").casefold()
            if cell and not set(cell) <= set("-: ") and cell != "logical name":
                names.add(cell)
    return names


def _balanced(text: str) -> bool:
    stack: list[str] = []
    for char in _CARDINALITY.sub("-", _QUOTED.sub("", text)):
        if char in "([{":
            stack.append(char)
        elif char in PAIRS and (not stack or stack.pop() != PAIRS[char]):
            return False
    return not stack


def lint(feature_dir: Path) -> list[Issue]:
    path = feature_dir / DESIGN_FILE
    shown = DESIGN_FILE
    if not path.is_file():
        return [Issue(shown, 1, ERROR, "D1", "there is no design.md; write the design view in the system-map phase")]
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    found, unclosed = blocks(lines)
    issues = [Issue(shown, n, ERROR, "D2", "this fence is never closed") for n in unclosed]
    if not found and not unclosed:
        issues.append(Issue(shown, 1, ERROR, "D1", "design.md holds no ```mermaid block"))
    known = interfaces(feature_dir / "system.md")
    for start, body in found:
        content = [(start + i, text) for i, text in enumerate(body) if text.strip() and not text.strip().startswith("%%")]
        if not content or content[0][1].split()[0] not in HEADERS:
            issues.append(Issue(shown, start, ERROR, "D3", "a diagram must start with one of: " + ", ".join(HEADERS)))
        if not _balanced("\n".join(text for _, text in content)):
            issues.append(Issue(shown, start, ERROR, "D4", "brackets are not balanced in this diagram"))
        for match in _ACTIVE.finditer("\n".join(body)):
            line = start + "\n".join(body)[:match.start()].count("\n")
            issues.append(Issue(shown, line, ERROR, "D5", f"'{match.group().strip()}' makes a diagram active; diagrams are plain text"))
        for i, text in enumerate(body):
            named = _INTERFACE.match(text)
            if named and named.group(1).casefold() not in known:
                issues.append(Issue(shown, start + i, ERROR, "D6", f"interface '{named.group(1)}' is not in the Interfaces table of system.md"))
    return issues


def run(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="bdd design", description="Check the Mermaid design view of a feature.")
    ap.add_argument("feature", help="feature id, e.g. FEAT-007")
    args = ap.parse_args(argv)
    try:
        from .statecmd import project_root
        issues = lint(store.find_feature_dir(project_root(), args.feature))
    except (UsageError, StoreError) as exc:
        print(f"bdd design: {exc}", file=sys.stderr)
        return 2
    print("\n".join(str(i) for i in issues) if issues else f"{args.feature}: design view is fine")
    return 1 if issues else 0
