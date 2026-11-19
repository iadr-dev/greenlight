"""The product's design, read and checked: the design folder, the feature map and the architecture.

The design folder is the folder of ``[design] system`` (or ``inventory``) in ``.bdd/config.toml``, ``design/`` by default:

    design/PRODUCT.md        who uses the product, their jobs, the platforms
    design/DESIGN.md         the design system and the design contract
    design/tokens.json       the design tokens; the screens use them through a stylesheet named tokens*.css
    design/inventory.md      the screen inventory: | ID | Screen | States | Feature | File |
    design/flows.html        the flows between the screens
    design/screens/*.html    the screens, every state of a row in an element marked
                             <section data-screen="S-OR-01" data-state="empty">
    .bdd/product.md          the feature map (``productmap``)
    .bdd/architecture.md     the architecture decisions, one section per heading of ``ARCHITECTURE``

An inventory table is any table with an ``ID`` and a ``Screen`` column; ``Key states``, ``BDD`` and ``Comp`` are read as
``States``, ``Feature`` and ``File``, so an inventory written before greenlight (a link per row to a board of screens)
is read as it is. Findings:

    DS1  a file of the design is missing                 IN1  there is no inventory table
    DS2  PRODUCT.md has no section on users, jobs or      IN2  a row has no screen name, no states or no feature
         platforms                                        IN3  a row id is used twice
    AR1  the architecture lacks a section                 IN4  a row names a feature the product map does not list
    AR2  a section of the architecture is empty           IN5  a row names no screen file
    AR3  the stack table lacks a surface of the product   IN6  a screen file is missing, or outside the design folder
    SC1  a screen file does not show a state of its row   SC3  a stylesheet a screen links is missing
    SC2  a screen does not use the design tokens          SC4  tokens.json is not valid JSON
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath

from . import config as cfg
from . import productmap
from .errors import UsageError
from .issues import ERROR, Issue

DEFAULT_FOLDER = "design"
GALLERY = "gallery.html"
PRODUCT_MAP = f"{cfg.BDD_DIR}/{productmap.FILE}"
ARCHITECTURE = f"{cfg.BDD_DIR}/architecture.md"
ARCHITECTURE_SECTIONS = ("Stack per surface", "Layers", "Hosting and environments", "Authentication", "Data store",
                         "Security baseline and threat model", "Observability", "CI and delivery")
PRODUCT_SECTIONS = {"users": ("user",), "jobs": ("job", "purpose"), "platforms": ("platform",)}
INVENTORY_COLUMNS = {"id": ("id",), "screen": ("screen", "name", "page", "message"), "states": ("states", "key states"),
                     "feature": ("feature", "features", "bdd"), "file": ("file", "screen file", "comp")}
_SKIP_DIRS = {"__pycache__", "node_modules"}
_LINK = re.compile(r"\]\(([^)\s]+)")
_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)


@dataclass(frozen=True)
class Row:
    id: str
    screen: str
    states: tuple[str, ...]
    features: tuple[str, ...]
    file: str                    # as the row writes it, relative to the inventory's folder; "" when it names none
    section: str
    line: int


@dataclass
class Screen:
    """A screen file as the checks and the gallery need it."""
    rel: str                                             # relative to the project
    shown: set[tuple[str, str]] = field(default_factory=set)   # (data-screen, data-state) on one element
    stylesheets: list[str] = field(default_factory=list)
    names_tokens: bool = False


@dataclass
class Design:
    root: Path
    folder: str
    rows: list[Row]
    features: list[productmap.Feature]
    screens: dict[str, Screen]
    issues: list[Issue]

    def path(self, name: str) -> str:
        return f"{self.folder}/{name}"


def state_name(text: str) -> str:
    """How a state is written in a data-state attribute: lower case, words joined by hyphens."""
    return "-".join(re.sub(r"[^\w\s-]", " ", text.casefold()).split())


def folder_of(config: cfg.Config) -> str:
    """The design folder, relative to the project. It is a folder of its own: never the project itself, nor .bdd."""
    design = config.design
    named = next((v for v in ((design.system, design.inventory) if design else ()) if v), "")
    folder = PurePosixPath(named).parent.as_posix() if named else DEFAULT_FOLDER
    if folder in ("", ".") or folder.split("/")[0].casefold() == cfg.BDD_DIR:
        raise UsageError(f"the design files have to be in a folder of their own, such as {DEFAULT_FOLDER}/ ([design] in "
                         f"{cfg.BDD_DIR}/config.toml names {named!r})")
    return folder


def files_of(config: cfg.Config, folder: str) -> dict[str, str]:
    design = config.design
    return {"product": f"{folder}/PRODUCT.md", "system": (design.system if design and design.system else f"{folder}/DESIGN.md"),
            "inventory": (design.inventory if design and design.inventory else f"{folder}/inventory.md"),
            "tokens": f"{folder}/tokens.json", "flows": f"{folder}/flows.html"}


def inside(root: Path, folder: str, path: Path) -> bool:
    try:
        path.resolve().relative_to((root / folder).resolve())
    except (ValueError, OSError):
        return False
    return True


def artifacts(root: Path, folder: str) -> list[str]:
    """What an approval of the design covers, relative to the project: every file of the design folder (not hidden ones,
    nor the gallery, which ``bdd gallery`` writes from the rest), the feature map and the architecture."""
    base = root / folder
    found = []
    if base.is_dir():
        for path in base.rglob("*"):
            parts = path.relative_to(base).parts
            if path.is_file() and not any(p.startswith(".") or p in _SKIP_DIRS for p in parts) and parts != (GALLERY,):
                found.append(path.relative_to(root).as_posix())
    found += [rel for rel in (PRODUCT_MAP, ARCHITECTURE) if (root / rel).is_file()]
    return sorted(found)


def covers(folder: str, rel: str) -> bool:
    """Is the project-relative path ``rel`` one that the approval of the design folder covers (added or not)?"""
    if rel in (PRODUCT_MAP, ARCHITECTURE):
        return True
    if not rel.startswith(folder + "/"):
        return False
    parts = rel[len(folder) + 1:].split("/")
    return parts != [GALLERY] and not any(p.startswith(".") or p in _SKIP_DIRS for p in parts)


# -- reading --------------------------------------------------------------------------------------------------------
class _ScreenParser(HTMLParser):
    def __init__(self, screen: Screen):
        super().__init__(convert_charrefs=True)
        self.screen = screen

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {name.casefold(): value or "" for name, value in attrs}
        if "data-state" in values:
            self.screen.shown.add((values.get("data-screen", ""), state_name(values["data-state"])))
        if tag == "link" and "stylesheet" in values.get("rel", "").casefold().split() and values.get("href"):
            self.screen.stylesheets.append(values["href"])

    handle_startendtag = handle_starttag


def read_screen(root: Path, rel: str) -> Screen:
    screen = Screen(rel)
    text = (root / rel).read_text(encoding="utf-8-sig", errors="replace")
    _ScreenParser(screen).feed(text)
    screen.names_tokens = "tokens.json" in text
    return screen


def file_of(cell: str) -> str:
    link = _LINK.search(cell)
    target = link.group(1) if link else productmap.plain(cell)
    target = target.split("#", 1)[0].strip()
    return "" if target.casefold() in productmap.NONE else target


def split_states(cell: str) -> tuple[str, ...]:
    return tuple(s for s in (productmap.plain(part) for part in re.split(r"[,;]", cell)) if s and s.casefold() not in productmap.NONE)


def inventory_rows(path: Path) -> tuple[list[Row], int]:
    """The rows of every inventory table, and how many such tables there are."""
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    headings = {n: m.group(2) for n, line in enumerate(lines, start=1) if (m := _HEADING.match(line))}
    rows: list[Row] = []
    count = 0
    for table in productmap.tables(lines):
        at = {key: productmap.column(table.headers, names) for key, names in INVENTORY_COLUMNS.items()}
        if at["id"] is None or at["screen"] is None:
            continue
        count += 1
        section = next((headings[n] for n in sorted(headings, reverse=True) if n < table.line), "")
        for line, row in table.rows:
            def cell(key: str) -> str:
                index = at[key]
                return row[index] if index is not None and index < len(row) else ""
            rows.append(Row(productmap.plain(cell("id")), productmap.plain(cell("screen")), split_states(cell("states")),
                            productmap.ids_in(cell("feature")), file_of(cell("file")), section, line))
    return rows, count


def sections(path: Path) -> dict[str, tuple[int, list[str]]]:
    """The second-level sections of a Markdown file: heading -> (its line, the lines under it, comments removed)."""
    text = _COMMENT.sub("", path.read_text(encoding="utf-8-sig"))
    found: dict[str, tuple[int, list[str]]] = {}
    current: list[str] | None = None
    for number, line in enumerate(text.splitlines(), start=1):
        heading = _HEADING.match(line)
        if heading and len(heading.group(1)) <= 2:
            current = [] if len(heading.group(1)) == 2 else None
            if current is not None:
                found[heading.group(2)] = (number, current)
        elif current is not None:
            current.append(line)
    return found


def filled(lines: list[str]) -> bool:
    """Does a section say anything? A table with a header and no rows (the template's) says nothing."""
    empty_tables = {n for table in productmap.tables(lines) if not table.rows for n in (table.line, table.line + 1)}
    return any(line.strip() for n, line in enumerate(lines, start=1) if n not in empty_tables)


def find_section(found: dict[str, tuple[int, list[str]]], name: str) -> tuple[int, list[str]] | None:
    wanted = name.casefold()
    return next((value for heading, value in found.items() if heading.casefold().startswith(wanted)), None)


# -- checking -------------------------------------------------------------------------------------------------------
def check_architecture(root: Path, surfaces: list[str]) -> list[Issue]:
    path = root / ARCHITECTURE
    if not path.is_file():
        return [Issue(ARCHITECTURE, 1, ERROR, "DS1", "there is no architecture; write it from templates/architecture.md")]
    found = sections(path)
    issues = []
    for name in ARCHITECTURE_SECTIONS:
        section = find_section(found, name)
        if section is None:
            issues.append(Issue(ARCHITECTURE, 1, ERROR, "AR1", f'the architecture has no "{name}" section'))
        elif not filled(section[1]):
            issues.append(Issue(ARCHITECTURE, section[0], ERROR, "AR2", f'the "{name}" section is empty'))
    stack = find_section(found, ARCHITECTURE_SECTIONS[0])
    if stack is not None and filled(stack[1]):
        named = {productmap.plain(row[0]).casefold() for table in productmap.tables(stack[1]) for _, row in table.rows if row}
        if not named:
            issues.append(Issue(ARCHITECTURE, stack[0], ERROR, "AR3", "the stack per surface needs a table: | Surface | Stack |"))
        for surface in surfaces:
            if surface.casefold() not in named:
                issues.append(Issue(ARCHITECTURE, stack[0], ERROR, "AR3",
                                    f"the product ships the {surface} surface, but the stack table has no row for it"))
    return issues


def check_product(root: Path, rel: str) -> list[Issue]:
    found = sections(root / rel)
    return [Issue(rel, 1, ERROR, "DS2", f"PRODUCT.md has no section on {what} (a heading that names it)")
            for what, words in PRODUCT_SECTIONS.items()
            if not any(any(word in heading.casefold() for word in words) for heading in found)]


def check_rows(design: Design, inventory: str, known: set[str]) -> list[Issue]:
    issues: list[Issue] = []
    seen: set[str] = set()
    base = PurePosixPath(inventory).parent
    for row in design.rows:
        where = (inventory, row.line, ERROR)
        if not row.screen or not row.states or not row.features:
            missing = [what for what, value in (("a screen name", row.screen), ("its states", row.states),
                                                ("a feature id", row.features)) if not value]
            issues.append(Issue(*where, "IN2", f"{row.id or 'a row'} needs " + ", ".join(missing)))
        if row.id in seen:
            issues.append(Issue(*where, "IN3", f"{row.id} is used for two rows"))
        seen.add(row.id)
        for feature in row.features:
            if known and feature not in known:
                issues.append(Issue(*where, "IN4", f"{row.id} names {feature}, which the product map ({PRODUCT_MAP}) does not list"))
        if not row.file:
            issues.append(Issue(*where, "IN5", f"{row.id} names no screen file; every row is drawn in a screen file"))
            continue
        rel = (base / row.file).as_posix()
        screen = design.screens.get(_normal(rel))
        if screen is None:
            issues.append(Issue(*where, "IN6", f"{row.id} names {row.file}, which is not a file in the design folder"))
            continue
        for state in row.states:
            if (row.id, state_name(state)) not in screen.shown:
                issues.append(Issue(*where, "SC1", f'{row.id} lists the state {state}, but {row.file} shows no '
                                                   f'data-state="{state_name(state)}" for it'))
    return issues


def check_screens(design: Design) -> list[Issue]:
    issues: list[Issue] = []
    for rel, screen in sorted(design.screens.items()):
        linked = []
        for href in screen.stylesheets:
            if re.match(r"^[a-z][a-z0-9+.-]*:|^//", href, re.IGNORECASE):
                continue
            target = (PurePosixPath(rel).parent / href.split("?")[0].split("#")[0]).as_posix()
            linked.append(PurePosixPath(target).name)
            if not (design.root / target).is_file() or not inside(design.root, design.folder, design.root / target):
                issues.append(Issue(rel, 1, ERROR, "SC3", f"it links {href}, which is not a file in the design folder"))
        if not screen.names_tokens and not any(name.casefold().startswith("tokens") for name in linked):
            issues.append(Issue(rel, 1, ERROR, "SC2", "it does not use the design tokens: link the stylesheet made from "
                                                      "tokens.json (tokens.css)"))
    return issues


def _normal(rel: str) -> str:
    parts: list[str] = []
    for part in rel.split("/"):
        if part == "..":
            if parts:
                parts.pop()
            else:
                parts.append(part)
        elif part not in ("", "."):
            parts.append(part)
    return "/".join(parts)


def load(root: Path, config: cfg.Config | None = None) -> Design:
    """Read the whole design and check it. Reads only files inside the project; a screen is read only inside the design
    folder."""
    config = config or cfg.load(root)
    folder = folder_of(config)
    files = files_of(config, folder)
    design = Design(root, folder, [], [], {}, [])
    issues = design.issues
    for key in ("product", "system", "inventory", "tokens", "flows"):
        if not (root / files[key]).is_file():
            issues.append(Issue(files[key], 1, ERROR, "DS1", f"{files[key]} does not exist yet"))
    design.features, map_issues = productmap.read(root / PRODUCT_MAP)
    issues += map_issues
    issues += check_architecture(root, [name for name, _ in config.surfaces])
    if (root / files["product"]).is_file():
        issues += check_product(root, files["product"])
    if (root / files["tokens"]).is_file():
        try:
            json.loads((root / files["tokens"]).read_text(encoding="utf-8-sig"))
        except ValueError as exc:
            issues.append(Issue(files["tokens"], 1, ERROR, "SC4", f"tokens.json is not valid JSON ({exc})"))
    named: list[str] = []
    if (root / files["inventory"]).is_file():
        design.rows, tables = inventory_rows(root / files["inventory"])
        if not tables:
            issues.append(Issue(files["inventory"], 1, ERROR, "IN1", "the inventory has no table with ID and Screen columns"))
        base = PurePosixPath(files["inventory"]).parent
        named = [_normal((base / row.file).as_posix()) for row in design.rows if row.file]
    pattern = config.design.screens if config.design and config.design.screens else f"{folder}/screens/*"
    globbed = [p.relative_to(root).as_posix() for p in sorted(root.glob(pattern)) if p.is_file() and p.suffix in (".html", ".htm")]
    for rel in dict.fromkeys([*named, *globbed]):
        target = root / rel
        if rel.split("/")[0] != ".." and target.is_file() and inside(root, folder, target):
            design.screens[rel] = read_screen(root, rel)
    issues += check_rows(design, files["inventory"], {f.id for f in design.features})
    issues += check_screens(design)
    return design
