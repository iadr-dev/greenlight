"""The technical design of a feature: the fourteen sections of ``design.md``, each a table, read and checked.

A feature started since the technical design (``technical_design`` in its state) has these sections in ``design.md``,
below the Mermaid views that ``design`` checks. Each holds one table with the columns of ``SECTIONS``; a section that
does not apply holds one row whose first cell is ``n/a`` and whose next cell says why. ``check`` refuses, by section
and row, what a reviewer would otherwise find after the code:

    a screen row of the approved design that names the feature and is not traced, or a field of it that is not
    a field of the trace with no building block, a building block of a standard kind without its standard
    a building block whose source cannot be opened, or is a version file
    an outside call without evidence recorded with ``bdd docs FEAT-n --service``
    a layer the architecture does not have, a pattern whose example file does not exist
    a query without an index, an operation (each endpoint is one) without a budget, a migration without a rollback
    an endpoint without an authorisation row, endpoints without a rate limit decision
    a screen without its states, or without its accessibility row
    a section that is missing, has no table, or is empty without a reason

``install_problems`` names, for the tasks and implement gates, each building block whose package is not a dependency of
the project, with the one line the person types to add it: an agent never installs a package.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from . import config as cfg
from . import designfolder, docsrecord, productmap, sources, trace
from .errors import StoreError, UsageError
from .issues import ERROR, Issue

DESIGN_FILE = "design.md"
MARKER = "technical_design"            # in state.json: the feature was started with the technical design
CARD = "cards/practices/standard-values.md"
NOT_APPLICABLE = {"n/a", "na", "not applicable"}
EMPTY = {"", "-", "—", "–"}
MISSING = EMPTY | {"none", "n/a", "no"}
MIN_REASON = 8


@dataclass(frozen=True)
class Column:
    name: str
    required: bool = True


@dataclass(frozen=True)
class Section:
    name: str
    columns: tuple[Column, ...]

    @property
    def header(self) -> str:
        return "| " + " | ".join(c.name for c in self.columns) + " |"


def _section(name: str, *columns: str, optional: tuple[str, ...] = ()) -> Section:
    return Section(name, tuple(Column(c, c not in optional) for c in columns))


SECTIONS = (
    _section("Design trace", "Screen", "Element", "Rule", "API field", "Component", optional=("Screen", "API field", "Component")),
    _section("Building blocks", "Field", "Kind", "Standard", "Library", "Package", "Source", optional=("Package",)),
    _section("External services", "Service", "Call", "Quota", "Cost", "On failure"),
    _section("Architecture", "Piece", "Layer", "Path"),
    _section("Patterns", "Pattern", "Example file", "Use for"),
    _section("API contract", "Endpoint", "Request", "Response", "Version", "Older clients"),
    _section("Data and performance", "Kind", "Name", "Detail", "Index", "Budget", "Rollback",
             optional=("Index", "Budget", "Rollback")),
    _section("Security and privacy", "Kind", "Subject", "Decision", "Enforced in"),
    _section("Errors and resilience", "Failure", "The user sees", "Retry and idempotency"),
    _section("State and offline", "Screen", "States", "Kept where", "Offline and reconnect"),
    _section("Accessibility and language", "Screen", "Labels and focus", "Contrast and text size", "Strings and locale"),
    _section("Observability", "Signal", "Kind", "Shows"),
    _section("Configuration and delivery", "Setting", "Per environment", "Deploy order"),
    _section("Test strategy", "Level", "What it tests", "Where"),
)
DATA_KINDS = ("table", "migration", "query", "operation", "cache", "volume", "job")
SECURITY_KINDS = ("authorisation", "authorization", "validation", "secret", "personal data", "rate limit", "threat")


@dataclass(frozen=True)
class Standard:
    kind: str
    what: str
    words: tuple[str, ...]                   # a field named with one of these is of this kind, when its Kind names none
    token: str                               # the standard, as the Standard cell must name it


STANDARDS = (
    Standard("phone", "a phone number", ("phone", "telephone", "mobile number", "fax"), "E.164"),
    Standard("country", "a country", ("country",), "ISO 3166"),
    Standard("money", "an amount of money", ("price", "amount", "money", "currency", "fee", "balance", "salary"), "ISO 4217"),
    Standard("time zone", "a time zone", ("time zone", "timezone"), "IANA"),
    Standard("language", "a language or locale", ("language", "locale"), "BCP 47"),
    Standard("date", "a date, time or duration", ("date", "datetime", "timestamp", "duration"), "ISO 8601"),
)
_KIND_WORDS = {"currency": "money", "timezone": "time zone", "tz": "time zone", "locale": "language", "datetime": "date",
               "time": "date", "timestamp": "date", "duration": "date", "telephone": "phone"}


@dataclass(frozen=True)
class Row:
    line: int
    cells: dict[str, str]

    def get(self, column: str) -> str:
        return self.cells.get(column.casefold(), "")


@dataclass
class Table:
    section: Section
    line: int = 0                            # the heading's line; 0 when the section is missing
    has_table: bool = False
    rows: list[Row] = field(default_factory=list)
    reason: str | None = None                # why the section does not apply, from its n/a row

    @property
    def found(self) -> bool:
        return self.line > 0


def plain(cell: str) -> str:
    return productmap.plain(cell)


def normal(text: str) -> str:
    return " ".join(plain(text).casefold().split())


def _blank(value: str, missing: set[str] = EMPTY) -> bool:
    return normal(value) in missing


_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")


def parse(text: str) -> dict[str, Table]:
    """Every section of ``SECTIONS`` as read from the text: its heading line, its table's rows and its n/a reason."""
    lines = text.splitlines()
    tables = {s.name: Table(s) for s in SECTIONS}
    headings = [(n, len(m.group(1)), m.group(2)) for n, line in enumerate(lines, start=1) if (m := _HEADING.match(line))]
    for index, (number, level, title) in enumerate(headings):
        section = next((s for s in SECTIONS if normal(title).startswith(s.name.casefold())), None)
        if section is None or tables[section.name].found:
            continue
        end = next((n for n, lvl, _ in headings[index + 1:] if lvl <= level), len(lines) + 1)
        table = tables[section.name]
        table.line = number
        body = lines[number:end - 1]
        wanted = [c.name.casefold() for c in section.columns]
        for found in productmap.tables(body):
            headers = [h.strip("*_ ") for h in found.headers]
            if not all(name in headers for name in wanted):
                continue
            table.has_table = True
            for line, cells in found.rows:
                row = Row(number + line, {h: plain(cells[i]) if i < len(cells) else "" for i, h in enumerate(headers)})
                if normal(row.get(section.columns[0].name)) in NOT_APPLICABLE:
                    reason = " ".join(plain(c) for c in cells[1:] if plain(c)).strip()
                    table.reason = reason if len(reason) >= MIN_REASON else table.reason
                else:
                    table.rows.append(row)
            break
    return tables


def read(feature_dir: Path) -> dict[str, Table] | None:
    path = feature_dir / DESIGN_FILE
    return parse(path.read_text(encoding="utf-8-sig")) if path.is_file() else None


# -- what the checks read besides design.md ----------------------------------------------------------------------------
@dataclass
class Context:
    root: Path
    feature_id: str
    rules: set[str]
    screens: list[designfolder.Row]          # the inventory rows of the approved design that name the feature
    evidence: set[str]                        # services with design evidence recorded (lower-cased)
    services: dict[str, dict]                 # sources.toml entries by id
    layers: str | None                        # the Layers section of .bdd/architecture.md, lower-cased; None: no architecture


def feature_screens(root: Path) -> list[designfolder.Row]:
    """The rows of the design's inventory (``[design]`` in ``.bdd/config.toml``, ``design/`` by default)."""
    try:
        config = cfg.load(root)
        inventory = root / designfolder.files_of(config, designfolder.folder_of(config))["inventory"]
        return designfolder.inventory_rows(inventory)[0] if inventory.is_file() else []
    except (UsageError, cfg.ConfigError, OSError, ValueError):
        return []


def screens_of(root: Path, feature_id: str) -> list[designfolder.Row]:
    return [r for r in feature_screens(root) if feature_id in r.features]


def context(root: Path, feature_dir: Path, feature_id: str) -> Context:
    rules = set((trace.read_ids(feature_dir / "rules.md", trace.RULE_LINE) or {}))
    try:
        evidence = {str(e.get("service", "")).casefold() for e in docsrecord.entries(feature_dir) if e.get("service")}
    except StoreError:                         # an unreadable record backs no call; `bdd docs --list` says why
        evidence = set()
    services = {key.casefold(): value for key, value in sources.load(root)[0].items()}
    layers = None
    architecture = root / designfolder.ARCHITECTURE
    if architecture.is_file():
        found = designfolder.find_section(designfolder.sections(architecture), "Layers")
        layers = " ".join(found[1]).casefold() if found else None
    return Context(root, feature_id, rules, screens_of(root, feature_id), evidence, services, layers)


def service_key(services: dict[str, dict], cell: str) -> str:
    """A service as sources.toml knows it: its id when the cell names the id or the name of an entry."""
    wanted = normal(cell)
    for key, entry in services.items():
        if wanted in (key, normal(str(entry.get("name", "")))):
            return key
    return wanted


# -- checking ------------------------------------------------------------------------------------------------------
class Findings:
    def __init__(self) -> None:
        self.issues: list[Issue] = []

    def add(self, line: int, code: str, section: str, message: str) -> None:
        self.issues.append(Issue(DESIGN_FILE, max(line, 1), ERROR, code, f"{section}: {message}"))


def _mentions(cell: str, row_id: str) -> bool:
    return re.search(rf"(?<![\w-]){re.escape(row_id)}(?![\w-])", cell, re.IGNORECASE) is not None


def _screen_of(cell: str, screens: list[designfolder.Row]) -> str:
    """The key of the screen a cell names: an inventory row's id when it names one, else its words."""
    return next((r.id for r in screens if _mentions(cell, r.id)), normal(cell))


def _label(key: str, screens: list[designfolder.Row]) -> str:
    row = next((r for r in screens if r.id == key), None)
    return f"{row.id} ({row.screen})" if row else f'"{key}"'


def _structure(tables: dict[str, Table], out: Findings) -> None:
    for table in tables.values():
        name = table.section.name
        if not table.found:
            out.add(1, "TD1", name, f"the section is missing; copy it from templates/design.md ({table.section.header}) "
                                    "and fill it in, or give it one row n/a with the reason it does not apply")
        elif not table.has_table:
            out.add(table.line, "TD2", name, f"the section has no table with the columns {table.section.header}")
        elif not table.rows and table.reason is None:
            out.add(table.line, "TD3", name, "the section holds no row; write its rows, or one row n/a with the reason it "
                                             "does not apply")
        for row in table.rows:
            first = row.get(table.section.columns[0].name) or row.get(table.section.columns[1].name)
            for column in table.section.columns:
                if column.required and _blank(row.get(column.name)):
                    out.add(row.line, "TD4", name, f'row "{first}" has nothing under "{column.name}"; fill it in')


def _trace(tables: dict[str, Table], ctx: Context, out: Findings) -> list[str]:
    """Check the trace against the screens and the rules; return the keys of the screens the trace names."""
    table = tables["Design trace"]
    rows = table.rows
    for screen in ctx.screens:
        traced = [r for r in rows if _mentions(r.get("Screen"), screen.id)]
        label = f"{screen.id} ({screen.screen})"
        if not traced:
            out.add(table.line, "TD10", "Design trace", f"design row {label} is not traced; add a row for each element "
                                                       "of the screen with its rule, API field and component")
            continue
        elements = {normal(r.get("Element")) for r in traced}
        for name in screen.fields:
            if normal(name) not in elements:
                out.add(table.line, "TD11", "Design trace", f'design row {label} lists the field "{name}", which no row '
                                                           "traces; add it, or change the design with the person")
    for row in rows:
        element = row.get("Element")
        named = re.findall(r"[RN]-\d+\.\d+", row.get("Rule"))
        unknown = [r for r in named if r not in ctx.rules]
        if not named or unknown:
            what = ", ".join(unknown) if unknown else row.get("Rule") or "nothing"
            out.add(row.line, "TD12", "Design trace", f'"{element}" names {what}, which is not a rule of rules.md; name the '
                                                      "rule it serves")
        if _blank(row.get("API field")) and _blank(row.get("Component")):
            out.add(row.line, "TD13", "Design trace", f'"{element}" names neither an API field nor a component')
    keys = [_screen_of(r.get("Screen"), ctx.screens) for r in rows if not _blank(r.get("Screen"))]
    return list(dict.fromkeys(keys + [s.id for s in ctx.screens]))


def standard_of(kind: str, name: str) -> Standard | None:
    """The standard a building block is held to: by its Kind when that names a standard kind, else by the field's name."""
    words = normal(kind)
    words = _KIND_WORDS.get(words, words)
    by_kind = next((s for s in STANDARDS if s.kind == words or words.startswith(s.kind)), None)
    if by_kind is not None or words not in ("", "text", "string", "number", "integer", "free text"):
        return by_kind
    field_name = normal(name)
    return next((s for s in STANDARDS if any(re.search(rf"\b{re.escape(w)}\b", field_name) for w in s.words)), None)


def _squash(text: str) -> str:
    return re.sub(r"[\s.\-_:]", "", text.casefold())


def parse_package(cell: str) -> tuple[str, str] | None:
    """``npm:libphonenumber-js`` as (ecosystem, name); None for ``-`` (a platform API)."""
    if _blank(cell, MISSING | {"platform"}):
        return None
    ecosystem, _, name = plain(cell).partition(":")
    if ecosystem.strip().casefold() not in sources.ECOSYSTEMS or not name.strip():
        raise ValueError(cell)
    return ecosystem.strip().casefold(), name.strip()


def _blocks(tables: dict[str, Table], ctx: Context, out: Findings) -> None:
    table = tables["Building blocks"]
    blocks = {normal(r.get("Field")): r for r in table.rows}
    for row in tables["Design trace"].rows:
        element = row.get("Element")
        if not _blank(row.get("API field")) and normal(element) not in blocks:
            out.add(table.line or row.line, "TD20", "Building blocks", f'field "{element}" has no building block; add a row '
                                                                       f"with its kind, standard, library and documentation ({CARD})")
    for row in table.rows:
        name = row.get("Field")
        standard = standard_of(row.get("Kind"), name)
        if standard is not None and _squash(standard.token) not in _squash(row.get("Standard")):
            out.add(row.line, "TD21", "Building blocks", f'"{name}" is {standard.what}: its standard is {standard.token} '
                                                         f"({CARD})")
        source = row.get("Source")
        problem = None if _blank(source) else docsrecord.source_problem(ctx.root, source)
        if problem:
            out.add(row.line, "TD22", "Building blocks", f'"{name}": {problem}')
        try:
            parse_package(row.get("Package"))
        except ValueError:
            out.add(row.line, "TD23", "Building blocks", f'"{name}": write the package as ECOSYSTEM:NAME '
                                                         f"({', '.join(sources.ECOSYSTEMS)}), or - for a platform API")


def _services(tables: dict[str, Table], ctx: Context, out: Findings) -> None:
    for row in tables["External services"].rows:
        service = row.get("Service")
        if service_key(ctx.services, service) not in ctx.evidence:
            out.add(row.line, "TD30", "External services",
                    f"the call to {service} has no evidence on record; the orchestrator records the official page, an MCP "
                    f"lookup or a CLI run with `bdd docs {ctx.feature_id} --service {normal(service)} --source URL` "
                    "(or --mcp SERVER --query TEXT, or --cli COMMAND)")


def _example_file(root: Path, cell: str) -> Path | None:
    name = re.sub(r":\d+(?:-\d+)?$", "", plain(cell).strip("`'\" "))
    if not name or PurePosixPath(name.replace("\\", "/")).is_absolute() or re.match(r"[a-z]+://", name):
        return None
    target = root / name
    try:
        target.resolve().relative_to(root.resolve())
    except (ValueError, OSError):
        return None
    return target if target.is_file() else None


def _places(tables: dict[str, Table], ctx: Context, out: Findings) -> None:
    for row in tables["Architecture"].rows:
        layer = normal(row.get("Layer"))
        if ctx.layers is not None and layer and layer not in ctx.layers:
            out.add(row.line, "TD40", "Architecture", f'"{row.get("Piece")}" is in the layer "{row.get("Layer")}", which the '
                                                      f"Layers section of {designfolder.ARCHITECTURE} does not have")
    for row in tables["Patterns"].rows:
        if _example_file(ctx.root, row.get("Example file")) is None:
            out.add(row.line, "TD50", "Patterns", f'the example file {row.get("Example file")} of "{row.get("Pattern")}" is '
                                                  "not a file of the project; name a file that shows the pattern")


def _data_and_security(tables: dict[str, Table], out: Findings) -> None:
    data, security = tables["Data and performance"], tables["Security and privacy"]
    endpoints = [r.get("Endpoint") for r in tables["API contract"].rows]
    for row in data.rows:
        kind, name = normal(row.get("Kind")), row.get("Name")
        if kind not in DATA_KINDS:
            out.add(row.line, "TD60", "Data and performance", f'"{name}" has the kind "{row.get("Kind")}"; the kinds are '
                                                              + ", ".join(DATA_KINDS))
        elif kind == "query" and _blank(row.get("Index"), MISSING):
            out.add(row.line, "TD61", "Data and performance", f'query "{name}" has no index; name the index it uses, or '
                                                              "the one this feature adds")
        elif kind == "operation" and _blank(row.get("Budget"), MISSING):
            out.add(row.line, "TD62", "Data and performance", f'operation "{name}" has no budget, such as p95 under 300 ms')
        elif kind == "migration" and _blank(row.get("Rollback"), MISSING):
            out.add(row.line, "TD63", "Data and performance", f'migration "{name}" has no rollback; say how it is undone')
    operations = [normal(r.get("Name")) for r in data.rows if normal(r.get("Kind")) == "operation"]
    kinds = [(normal(r.get("Kind")), normal(r.get("Subject"))) for r in security.rows]
    for endpoint in endpoints:
        wanted = normal(endpoint)
        if not any(wanted in name for name in operations):
            out.add(data.line, "TD64", "Data and performance", f"operation {endpoint} has no budget; add a row operation | "
                                                               f"{endpoint} | ... with its budget")
        if not any(kind.startswith("authori") and wanted in subject for kind, subject in kinds):
            out.add(security.line, "TD70", "Security and privacy", f"endpoint {endpoint} has no authorisation row; add one "
                                                                   "that says who may call it, on which records, and where "
                                                                   "the server checks it")
    if endpoints and not any(kind == "rate limit" for kind, _ in kinds):
        out.add(security.line, "TD71", "Security and privacy", "no rate limit is decided for the endpoints; add a rate limit "
                                                               "row (one that says none, and why, is a decision too)")
    for row in security.rows:
        if normal(row.get("Kind")) not in SECURITY_KINDS:
            out.add(row.line, "TD72", "Security and privacy", f'"{row.get("Subject")}" has the kind "{row.get("Kind")}"; '
                                                              "the kinds are " + ", ".join(SECURITY_KINDS))


def _screens(tables: dict[str, Table], ctx: Context, keys: list[str], out: Findings) -> None:
    states_table, access = tables["State and offline"], tables["Accessibility and language"]
    for key in keys:
        label = _label(key, ctx.screens)
        row = next((r for r in states_table.rows if _screen_of(r.get("Screen"), ctx.screens) == key), None)
        inventory = next((s for s in ctx.screens if s.id == key), None)
        if row is None:
            out.add(states_table.line, "TD80", "State and offline", f"screen {label} has no row; add one with its states, "
                                                                    "where they are kept and what happens offline")
        elif inventory is not None:
            listed = {designfolder.state_name(s) for s in designfolder.split_states(row.get("States"))}
            for state in inventory.states:
                if designfolder.state_name(state) not in listed:
                    out.add(row.line, "TD81", "State and offline", f'screen {label} does not list its state "{state}"')
        if not any(_screen_of(r.get("Screen"), ctx.screens) == key for r in access.rows):
            out.add(access.line, "TD82", "Accessibility and language", f"screen {label} has no row; add its labels and "
                                                                       "focus, contrast and text size, strings and locale")


def check(root: Path, feature_dir: Path, feature_id: str) -> list[Issue]:
    """What is missing from the technical design of the feature (an empty list: nothing)."""
    tables = read(feature_dir)
    if tables is None:
        return [Issue(DESIGN_FILE, 1, ERROR, "D1", "there is no design.md; write it from templates/design.md in the "
                                                   "system-map phase")]
    ctx = context(root, feature_dir, feature_id)
    out = Findings()
    _structure(tables, out)
    keys = _trace(tables, ctx, out)
    _blocks(tables, ctx, out)
    _services(tables, ctx, out)
    _places(tables, ctx, out)
    _data_and_security(tables, out)
    _screens(tables, ctx, keys, out)
    return sorted(out.issues, key=lambda i: i.line)


def has_screens(feature_dir: Path, screens: list[designfolder.Row]) -> bool:
    """Does the design show the feature on a screen: a trace row with a screen, or an inventory row that names it?"""
    tables = read(feature_dir)
    return bool(screens) or bool(tables and any(not _blank(r.get("Screen")) for r in tables["Design trace"].rows))


# -- packages the person adds ----------------------------------------------------------------------------------------
_ADD = {"cargo": "cargo add {name}", "go": "go get {name}", "gem": "bundle add {name}", "nuget": "dotnet add package {name}"}


def install_line(manifest: sources.Manifest | None, ecosystem: str, name: str) -> str:
    """The one line that adds the package to the project, from the tools its manifest shows."""
    flags, files = (manifest.flags, manifest.files) if manifest else (frozenset(), frozenset())
    deps = manifest.deps if manifest else {}
    if ecosystem == "npm":
        manager = next((f.removeprefix("pm:") for f in sorted(flags) if f.startswith("pm:")), "")
        manager = manager or next((m for m, lock in (("pnpm", "pnpm-lock.yaml"), ("yarn", "yarn.lock"), ("bun", "bun.lockb"),
                                                     ("bun", "bun.lock")) if lock in files), "npm")
        line = f"npm install {name}" if manager == "npm" else f"{manager} add {name}"
    elif ecosystem == "pypi":
        line = (f"uv add {name}" if "uv.lock" in files else f"poetry add {name}" if "poetry.lock" in files
                else f"python -m pip install {name}")
    elif ecosystem == "pub":
        line = f"{'flutter' if 'flutter' in deps else 'dart'} pub add {name}"
    elif ecosystem == "maven":
        return f"add {name} to {manifest.path if manifest else 'the build file'} (the build tool has no add command)"
    else:
        line = _ADD[ecosystem].format(name=name)
    folder = manifest.folder if manifest else ""
    return f"cd {folder} && {line}" if folder else line


def install_problems(root: Path, feature_dir: Path) -> list[str]:
    """Each building block whose package no manifest of the project declares, with the line the person types."""
    tables = read(feature_dir)
    if tables is None:
        return []
    found = sources.manifests(root)
    problems = []
    for row in tables["Building blocks"].rows:
        try:
            package = parse_package(row.get("Package"))
        except ValueError:
            continue                                         # `bdd design` reports the cell
        if package is None:
            continue
        ecosystem, name = package
        of_kind = [m for m in found if m.ecosystem == ecosystem]
        wanted = sources._normal(ecosystem, name)
        if any(wanted in {sources._normal(ecosystem, d) for d in m.deps} for m in of_kind):
            continue
        line = install_line(of_kind[0] if of_kind else None, ecosystem, name)
        problems.append(f"{name} ({ecosystem}) is not a dependency of the project: the person types ! {line} "
                        "(an agent may not install packages)")
    return problems
