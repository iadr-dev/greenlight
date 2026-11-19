"""The product's feature map, ``.bdd/product.md``: every feature of the product, decided once before any is built.

    | ID | Feature | Description | Depends on | Order |
    |---|---|---|---|---|
    | FEAT-001 | Sign in | A shopper signs in with their email. | - | 1 |
    | FEAT-002 | Orders | A signed-in shopper places an order. | FEAT-001 | 2 |

Every table whose header has an ``ID`` column is read; other tables (a glossary, a phase plan) are left alone. Findings:

    PM1  there is no product map, or it lists no feature
    PM2  an id is not FEAT-<number>, or is used twice
    PM3  a feature has no name or no description
    PM4  a feature depends on an id the map does not list
    PM5  the dependencies go round in a circle
    PM6  the build order is not a whole number, or a feature is built before a feature it depends on
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .issues import ERROR, Issue, safe_cell

FILE = "product.md"
FEATURE_ID = re.compile(r"FEAT-\d+")
_SEPARATOR = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")
NONE = {"", "-", "—", "none", "n/a"}
COLUMNS = {"id": ("id",), "name": ("feature", "name"), "description": ("description", "what it does"),
           "depends": ("depends on", "depends", "dependencies"), "order": ("order", "build order")}


@dataclass(frozen=True)
class Table:
    line: int                                   # the header's line number
    headers: tuple[str, ...]                    # lower-cased, stripped
    rows: tuple[tuple[int, tuple[str, ...]], ...]


@dataclass(frozen=True)
class Feature:
    id: str
    name: str
    description: str
    depends: tuple[str, ...]
    order: str
    line: int


def cells(line: str) -> tuple[str, ...]:
    """The cells of a Markdown table row; ``\\|`` is a pipe inside a cell."""
    inner = line.strip()
    inner = inner[1:] if inner.startswith("|") else inner
    inner = inner[:-1] if inner.endswith("|") and not inner.endswith("\\|") else inner
    return tuple(cell.replace("\\|", "|").strip() for cell in re.split(r"(?<!\\)\|", inner))


def tables(lines: list[str]) -> list[Table]:
    """Every Markdown table of the text: a row of cells, a separator row, then the rows up to the first line that is not one."""
    found: list[Table] = []
    index = 0
    while index < len(lines) - 1:
        line = lines[index]
        if line.lstrip().startswith("|") and _SEPARATOR.match(lines[index + 1]):
            headers = tuple(h.casefold() for h in cells(line))
            rows = []
            index += 2
            while index < len(lines) and lines[index].lstrip().startswith("|"):
                rows.append((index + 1, cells(lines[index])))
                index += 1
            found.append(Table(index - len(rows) - 1, headers, tuple(rows)))
            continue
        index += 1
    return found


def column(headers: tuple[str, ...], names: tuple[str, ...]) -> int | None:
    return next((i for i, h in enumerate(headers) if h.strip("*_ ") in names), None)


def plain(cell: str) -> str:
    """A cell without Markdown emphasis or code marks."""
    return re.sub(r"[*_`]", "", cell).strip()


def ids_in(cell: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(FEATURE_ID.findall(cell)))


def read(path: Path) -> tuple[list[Feature], list[Issue]]:
    """The features of the map and what is wrong with it."""
    shown = f".bdd/{FILE}"
    if not path.is_file():
        return [], [Issue(shown, 1, ERROR, "PM1", "there is no product map; the ux-designer writes it from the product spec")]
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    features: list[Feature] = []
    issues: list[Issue] = []
    for table in tables(lines):
        at = {key: column(table.headers, names) for key, names in COLUMNS.items()}
        if at["id"] is None:
            continue
        for line, row in table.rows:
            def cell(key: str) -> str:
                index = at[key]
                return plain(row[index]) if index is not None and index < len(row) else ""
            features.append(Feature(cell("id"), cell("name"), cell("description"),
                                    () if cell("depends").casefold() in NONE else ids_in(cell("depends")), cell("order"), line))
    if not features:
        return [], [Issue(shown, 1, ERROR, "PM1", "the product map lists no feature yet (a table with an ID column)")]
    seen: set[str] = set()
    for f in features:
        if not FEATURE_ID.fullmatch(f.id):
            issues.append(Issue(shown, f.line, ERROR, "PM2", f"'{safe_cell(f.id)}' is not a feature id (FEAT-<number>)"))
        elif f.id in seen:
            issues.append(Issue(shown, f.line, ERROR, "PM2", f"{f.id} is listed twice"))
        seen.add(f.id)
        if not f.name or not f.description:
            issues.append(Issue(shown, f.line, ERROR, "PM3", f"{f.id} needs a name and a one-line description"))
    known = {f.id: f for f in features}
    for f in features:
        for dep in f.depends:
            if dep not in known:
                issues.append(Issue(shown, f.line, ERROR, "PM4", f"{f.id} depends on {dep}, which the map does not list"))
    issues += [Issue(shown, known[fid].line, ERROR, "PM5", f"{fid} depends on itself through {' -> '.join(path_)}")
               for fid, path_ in cycles(known)]
    for f in features:
        if not f.order.isdigit():
            issues.append(Issue(shown, f.line, ERROR, "PM6", f"{safe_cell(f.id)} has no build order (a whole number, 1 first)"))
            continue
        for dep in f.depends:
            other = known.get(dep)
            if other is not None and other.order.isdigit() and int(other.order) >= int(f.order):
                issues.append(Issue(shown, f.line, ERROR, "PM6", f"{f.id} is built at order {safe_cell(f.order)}, but it depends on "
                                                                 f"{dep}, built at order {other.order}"))
    return features, issues


def cycles(known: dict[str, Feature]) -> list[tuple[str, list[str]]]:
    """Each feature that reaches itself through its dependencies, with the way round (reported once per circle)."""
    found, reported = [], set()
    for start in known:
        stack = [(start, [start])]
        visited: set[str] = set()
        while stack:
            current, path_ = stack.pop()
            for dep in known[current].depends:
                if dep == start:
                    circle = frozenset(path_)
                    if circle not in reported:
                        reported.add(circle)
                        found.append((start, [*path_, start]))
                elif dep in known and dep not in visited:
                    visited.add(dep)
                    stack.append((dep, [*path_, dep]))
    return found
