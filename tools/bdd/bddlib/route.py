"""Which roles a task needs: the writer, the reviewers and the cards, read from the task's scenarios.

    bdd route FEAT-n [--json]

The orchestrator does not ask the person who should write or review a task: this command decides, from files the
feature already has, so the same feature is always routed the same way.

* the steps of the scenarios a task covers (``tasks.md``; a feature without one, such as one on the quick path, is one
  task ``T-<n>.0`` covering every example), resolved to the core instructions of the vocabulary: a screen
  step (``C.UI.*``, the application state) makes it a UI task, an API step an API task, a record or query step a data task;
  a project step counts as the core instructions it composes;
* signing in (``C.ACTOR.AUTH``), or a word about money, credentials or personal data in the rules the task covers or in
  their titles, makes it a security task.

A UI task is written by the ``ui-engineer``, any other by the ``implementer``. Every task is reviewed by the
``code-reviewer``; a UI task also by the ``ui-reviewer``, a security task by the ``security-reviewer``. Each reviewer
writes ``reviews/<task>-<reviewer>.md`` in the feature folder, and the implement gate waits for those reports.

Each task is also told what it builds against: the sections of the technical design it builds (``SECTION_NEEDS``) and
the inventory rows of its screens, its building blocks with the version a manifest declares, the outside services its
rules name (every one when they name none) with their ``.bdd/sources.toml`` entry, and its known risks (``risks``). The
``Design:`` and ``Risks:`` lines of ``tasks.md`` add to what is derived. ``plan_groups`` orders the tasks: tasks of one
group share no ``Areas:`` path and wait for none of each other, so their writers may run at the same time.

A feature started with this (``MARKER`` in its state) is held to it at the tasks and implement gates: every task has its
two lines (``line_problems``), its code review answers each of its risks (``risks.review_problems``) and its UI review
compares each of its rows with the design at 375 and 1280 px or says why it could not (``side_by_side_problems``).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path, PurePosixPath

from . import config as cfg
from . import featurefiles, gherkin, reviewfresh, reviewlog, risks, roles, store, trace, vocabulary
from .errors import StoreError, UsageError

PLUGIN_ROOT = Path(__file__).resolve().parents[3]
PRACTICES = PLUGIN_ROOT / "cards" / "practices"
REVIEWS_DIR = roles.REVIEWS_DIR
VERDICT = re.compile(r"^\s*Verdict:\s*(PASS|FINDINGS)\b", re.IGNORECASE | re.MULTILINE)

UI_STEPS = ("C.UI.", "C.STATE.GLOBAL", "C.STATE.VERIFY")
API_STEPS = ("C.API.",)
DATA_STEPS = ("C.ENTITY.", "C.QUERY.COUNT")
AUTH_STEPS = ("C.ACTOR.AUTH",)
# Words that make a task a security task when a rule it covers uses them: money, credentials, access and personal data.
SECURITY_WORDS = re.compile(
    r"\b(?:sign(?:s|ed)?[ -]in|log(?:s|ged)?[ -]in|login|logout|password|passwords|token|tokens|session|sessions|"
    r"permission|permissions|authori[sz]\w*|authenticat\w*|role|roles|admin|admins|secret|secrets|api key|"
    r"pay|pays|paid|payment|payments|refund|refunds|charge|charges|invoice|invoices|billing|card number|credit card|"
    r"personal data|email address|phone number|date of birth|address)\b", re.IGNORECASE)
CARDS = {"ui": ("ui-design", "accessibility"), "api": ("api-design",),
         "data": ("database-schema", "database-performance"), "security": ("security",)}
WRITERS, REVIEWERS = roles.WRITERS, roles.REVIEWERS


MARKER = "against_design"          # in state.json: the feature's tasks are built against the design, with their risks
ALWAYS = "always"
# The sections of design.md a task builds, when the section has rows: the facts of the task that make it build one (its
# kinds, its risks, or rows of its own in the trace, the building blocks or the outside services).
SECTION_NEEDS = {
    "Design trace": {"traced"},
    "Building blocks": {"blocks"},
    "External services": {"services"},
    "Architecture": {ALWAYS},
    "Patterns": {ALWAYS},
    "API contract": {"api"},
    "Data and performance": {"data", "unmapped storage errors", "large lists"},
    "Security and privacy": {"security", "authorisation", "personal data", "rate limits"},
    "Errors and resilience": {"api", "data", "concurrent writes", "retries and idempotency", "unmapped storage errors"},
    "State and offline": {"ui"},
    "Accessibility and language": {"ui"},
}
SHOWN_CHARS = 160


@dataclass
class Route:
    task: str
    title: str
    writer: str
    reviewers: list[str]
    cards: list[str]
    because: list[str] = field(default_factory=list)
    design: list[str] = field(default_factory=list)       # the sections of design.md the task builds
    rows: list[str] = field(default_factory=list)         # the ids of the inventory rows it builds
    screens: list[str] = field(default_factory=list)      # those rows: id, screen, file and states
    risks: list[str] = field(default_factory=list)        # the known risks its code must handle (``risks``)
    blocks: list[dict] = field(default_factory=list)      # the building blocks it uses: library, package, version, source
    services: list[dict] = field(default_factory=list)    # the outside services it may call, with their sources.toml entry
    depends_on: list[str] = field(default_factory=list)
    group: int = 0                                         # tasks of one group may be built at the same time
    after: list[str] = field(default_factory=list)        # the earlier tasks it waits for: its dependencies, shared areas
    alongside: list[str] = field(default_factory=list)    # the other tasks of its group


def _instruction_ids(vocab: vocabulary.Vocabulary, step: gherkin.Step, language: str) -> list[str]:
    ids: list[str] = []
    for match in vocab.resolve(step.kind, step.text, language):
        ids += list(match.entry.composes) if match.entry.source == "project" else [match.entry.id]
    return ids


def _scenarios_by_example(root: Path, feature_id: str) -> dict[str, list[tuple[gherkin.Feature, gherkin.Scenario, gherkin.Rule | None]]]:
    found: dict[str, list] = {}
    for path in featurefiles.spec_files(root, feature_id):
        try:
            feature = gherkin.parse(path.read_text(encoding="utf-8-sig"), path.as_posix())
        except gherkin.ParseError:
            continue                                           # `bdd lint` reports it; an unreadable file routes nothing
        for scenario, rule in feature.scenarios():
            for tag in feature.effective_tags(scenario, rule):
                if trace.EXAMPLE_ID.fullmatch(tag.lstrip("@")):
                    found.setdefault(tag.lstrip("@"), []).append((feature, scenario, rule))
    return found


def _steps(feature: gherkin.Feature, scenario: gherkin.Scenario, rule: gherkin.Rule | None) -> list[gherkin.Step]:
    steps = list(feature.background.steps) if feature.background else []
    if rule is not None and rule.background is not None:
        steps += rule.background.steps
    return steps + list(scenario.steps)


def _has(ids: list[str], prefixes: tuple[str, ...]) -> list[str]:
    return sorted({i for i in ids if i.startswith(prefixes)})


def routes(root: Path, feature_dir: Path, feature_id: str) -> list[Route]:
    config = cfg.load(root)
    vocab = vocabulary.load(config.vocabulary_file)
    rules = trace.read_ids(feature_dir / "rules.md", trace.RULE_LINE) or {}
    scenarios = _scenarios_by_example(root, feature_id)
    tasks = trace.read_tasks(feature_dir / "tasks.md") or {}
    claimed = {example for task in tasks.values() for example in task["examples"]}
    unclaimed = sorted((e for e in scenarios if e not in claimed), key=trace._sort_key)
    if unclaimed or not tasks:         # no tasks.md (the quick path), an empty one, or examples no task claims: still routed
        title = "the whole feature" if not tasks else "the examples no task claims"
        reserved = tasks.setdefault(whole_feature_task(feature_id), {"title": title, "examples": []})
        reserved["examples"] = reserved["examples"] + [e for e in unclaimed if e not in reserved["examples"]]   # never overwritten
    screens = designed_screens(root, config, feature_id)
    facts = DesignFacts.read(root, feature_dir)
    out: list[Route] = []
    for task_id, task in tasks.items():
        ids: list[str] = []
        texts: list[str] = []
        for example in task["examples"]:
            rule_id = trace.rule_of(example)
            texts.append(rules.get(rule_id, ""))
            for feature, scenario, rule in scenarios.get(example, []):
                texts += [rule.name if rule else "", scenario.name]
                for step in _steps(feature, scenario, rule):
                    ids += _instruction_ids(vocab, step, feature.language)
        ui, api, data, auth = (_has(ids, p) for p in (UI_STEPS, API_STEPS, DATA_STEPS, AUTH_STEPS))
        words = sorted({m.group(0).casefold() for text in texts for m in SECURITY_WORDS.finditer(text)})
        because = [f"screen steps ({', '.join(ui)})"] if ui else []
        because += [f"API steps ({', '.join(api)})"] if api else []
        because += [f"record steps ({', '.join(data)})"] if data else []
        because += [f"a signed-in actor ({', '.join(auth)})"] if auth else []
        because += [f"the rules mention {', '.join(words)}"] if words else []
        kinds = [k for k, hit in (("ui", ui), ("api", api), ("data", data), ("security", auth or words)) if hit]
        reviewers = ["code-reviewer"] + (["security-reviewer"] if "security" in kinds else []) + (["ui-reviewer"] if ui else [])
        cards = [c for k in kinds for c in CARDS[k] if (PRACTICES / f"{c}.md").is_file()]
        found = Route(task_id, task["title"], "ui-engineer" if ui else "implementer", reviewers, cards, because)
        facts.fill(found, task, kinds, texts, ids, screens)
        out.append(found)
    plan_groups(out, tasks)
    return out


_LINK = re.compile(r"https://[\w.-]+(?:/[\w.~/#?=&+%-]*)?")
_VERSION = re.compile(r"[\w.^~<>=*+ -]{1,40}")


def _cell(text: object) -> str:
    """A cell of design.md or sources.toml as the route shows it: plain words, a name or a path (``issues.safe_cell``),
    an https address of one host, or a version; anything else is not shown, so a cell cannot speak in greenlight's voice
    in the brief of a writer."""
    from . import docsrecord
    from .issues import safe_cell
    flat = str(text).strip()
    if not flat:
        return ""
    if _LINK.fullmatch(flat) and len(flat) <= SHOWN_CHARS and docsrecord.hostname(flat):
        return flat
    return flat if _VERSION.fullmatch(flat) and any(c.isdigit() for c in flat) else safe_cell(flat)


def _mentions(texts: list[str], *names: str) -> bool:
    return any(re.search(rf"(?<![\w-]){re.escape(n)}(?![\w-])", t, re.IGNORECASE) for n in names if n for t in texts)


@dataclass
class DesignFacts:
    """What the technical design, sources.toml and the manifests say, read once per feature for all its tasks."""
    tables: dict | None
    entries: dict[str, dict]                 # sources.toml by id (lower-cased)
    versions: dict[tuple[str, str], str]     # (ecosystem, package) -> the version a manifest declares

    @classmethod
    def read(cls, root: Path, feature_dir: Path) -> "DesignFacts":
        from . import designsections, sources
        tables = designsections.read(feature_dir)
        if tables is None:
            return cls(None, {}, {})
        entries = {key.casefold(): value for key, value in sources.load(root)[0].items()}
        versions = {(m.ecosystem, sources._normal(m.ecosystem, name)): version
                    for m in reversed(sources.manifests(root)) for name, version in m.deps.items()}
        return cls(tables, entries, versions)

    def fill(self, found: Route, task: dict, kinds: list[str], texts: list[str], ids: list[str],
             screens: dict[str, str]) -> None:
        """The task's design sections, rows, screens, risks, building blocks and services."""
        from . import designsections
        written_sections, written_rows = self._written_design(task.get("design") or "", screens)
        traced = self._traced(task) if self.tables else []
        rows = list(dict.fromkeys([r for r in screens if any(designsections._mentions(t.get("Screen"), r) for t in traced)]
                                  + written_rows))
        if "ui" in kinds and not rows:
            rows = list(screens)                     # a screen task the trace does not tie to a row: every row of the feature
        found.rows, found.screens = rows, [screens[r] for r in rows]
        derived = risks.from_texts(texts, ids)
        if self.tables is not None:
            blocks = self._blocks(traced)
            found.blocks, found.services = [block for block, _ in blocks], self._services(texts)
            derived |= risks.from_design(self.tables, bool({"api", "data", "security"} & set(kinds)),
                                         [kind for _, kind in blocks])
        found.risks = risks.ordered(derived | set(risks.parse_line(task.get("risks") or "")[0]))
        tags = {ALWAYS, *kinds, *found.risks} | {name for name, hit in (("traced", traced), ("blocks", found.blocks),
                                                                        ("services", found.services)) if hit}
        derived_sections = {name for name, needs in SECTION_NEEDS.items()
                            if self.tables is not None and needs & tags and self.tables[name].rows}
        found.design = [s.name for s in designsections.SECTIONS if s.name in derived_sections | written_sections]

    @staticmethod
    def _written_design(line: str, screens: dict[str, str]) -> tuple[set[str], list[str]]:
        """A ``Design:`` line of tasks.md: the section names it gives, and the inventory rows of the feature it names."""
        from . import designsections
        names = {s.name.casefold(): s.name for s in designsections.SECTIONS}
        parts = [" ".join(p.strip(" .*_`").split()) for p in re.split(r"[,;]", line)]
        return ({names[p.casefold()] for p in parts if p.casefold() in names},
                [r for r in screens if any(p.casefold() == r.casefold() for p in parts)])

    def _traced(self, task: dict) -> list:
        """The trace rows of the rules the task's examples belong to (``R-7.1`` and ``R-007.1`` are one rule)."""
        mine = {trace._sort_key(trace.rule_of(e)) for e in task["examples"]}
        return [r for r in self.tables["Design trace"].rows
                if {trace._sort_key(i) for i in re.findall(r"[RN]-\d+\.\d+", r.get("Rule"))} & mine]

    def _blocks(self, traced: list) -> list[tuple[dict, str]]:
        """The building blocks of the fields the task's trace rows name, every one when the task has no trace row; each
        with the kind of standard it is held to ("" for none)."""
        from . import designsections, sources
        elements = {designsections.normal(r.get("Element")) for r in traced}
        out = []
        for row in self.tables["Building blocks"].rows:
            if traced and designsections.normal(row.get("Field")) not in elements:
                continue
            try:
                package = designsections.parse_package(row.get("Package"))
            except ValueError:
                package = None
            version = "the platform" if package is None else self.versions.get(
                (package[0], sources._normal(*package)), "not a dependency yet")
            standard = designsections.standard_of(row.get("Kind"), row.get("Field"))
            out.append(({"field": _cell(row.get("Field")), "library": _cell(row.get("Library")),
                         "package": ":".join(package) if package else "-", "version": _cell(version),
                         "source": _cell(row.get("Source"))}, standard.kind if standard else ""))
        return out

    def _services(self, texts: list[str]) -> list[dict]:
        """The outside services of the design the task's rules or scenarios name; every one when they name none."""
        from . import designsections
        rows = []
        for row in self.tables["External services"].rows:
            key = designsections.service_key(self.entries, row.get("Service"))
            entry = self.entries.get(key, {})
            rows.append((_mentions(texts, key, str(entry.get("name", ""))), {
                "service": _cell(key), "call": _cell(row.get("Call")),
                **{field_name: _cell(entry.get(field_name, "")) for field_name in ("docs", "mcp", "cli", "plugin")}}))
        named = [service for hit, service in rows if hit]
        return named or [service for _, service in rows]


def plan_groups(found: list[Route], tasks: dict[str, dict]) -> None:
    """The order the tasks may be built in: a task waits for the tasks it depends on (``Depends on:``) and for every
    earlier task whose ``Areas:`` overlap its own, and a task with no area paths waits for all and is waited for by all.
    Tasks of one group wait for none of each other. Dependencies on a later task are honoured; a cycle is broken in
    the order of tasks.md."""
    from . import reviewfresh
    known = [r.task for r in found]
    areas = {r.task: reviewfresh.area_paths((tasks.get(r.task) or {}).get("areas") or "") for r in found}
    for r in found:
        named = trace.TASK_ID.findall((tasks.get(r.task) or {}).get("depends") or "")
        r.depends_on = [t for t in dict.fromkeys(named) if t in known and t != r.task]

    def overlap(a: str, b: str) -> bool:
        if not areas[a] or not areas[b]:
            return True
        return any(reviewfresh._inside(x, y) or reviewfresh._inside(y, x) for x in areas[a] for y in areas[b])

    placed: dict[str, int] = {}
    waiting = list(found)
    while waiting:
        ready = next((r for r in waiting if all(d in placed for d in r.depends_on)), waiting[0])
        waiting.remove(ready)
        before = [t for t in placed if overlap(t, ready.task)]
        ready.after = sorted(set(before) | {d for d in ready.depends_on if d in placed}, key=known.index)
        ready.group = max((placed[t] for t in ready.after), default=0) + 1
        placed[ready.task] = ready.group
    for r in found:
        r.alongside = [o.task for o in found if o.group == r.group and o.task != r.task]


def designed_screens(root: Path, config: cfg.Config, feature_id: str) -> dict[str, str]:
    """The rows of the design's screen inventory (``[design]``) that name the feature: {id: id, screen, file and states}."""
    from . import designfolder
    try:
        inventory = designfolder.files_of(config, designfolder.folder_of(config))["inventory"]
        rows = designfolder.inventory_rows(root / inventory)[0] if (root / inventory).is_file() else []
    except (UsageError, OSError, ValueError):
        return {}
    base = PurePosixPath(inventory).parent
    return {r.id: f"{r.id} {r.screen}: {(base / r.file).as_posix() if r.file else 'no screen file'} ({', '.join(r.states)})"
            for r in rows if feature_id in r.features and r.id}


def whole_feature_task(feature_id: str) -> str:
    """The task id that stands for the whole feature when it has no ``tasks.md``: ``T-007.0`` for FEAT-007."""
    return f"T-{feature_id.split('-', 1)[1]}.0"


def review_path(feature_dir: Path, task_id: str, reviewer: str) -> Path:
    return feature_dir / REVIEWS_DIR / f"{task_id}-{reviewer}.md"


def finished_agents(root: Path) -> dict[str, str]:
    """{agent id: agent type} for every agent the plugin's SubagentStop hook saw finish in this project."""
    from . import agentcost                                 # light at hook time: only the gate needs it
    return {str(e["agent_id"]): str(e.get("agent", "")) for e in agentcost.read_entries(root)}


def _seen_by(root: Path, feature_dir: Path, reviewer: str, seals: dict[tuple[str, str], dict],
             log: dict[tuple[str, str], dict]) -> set[tuple[str, str]]:
    """(file, hash) pairs that a report of this feature by this kind of reviewer, as that reviewer wrote it, was sealed with:
    a file another task changed after this report, and that kind of reviewer read as it is now, is not news to it."""
    folder = reviewlog.key(root, feature_dir) + "/"
    seen: set[tuple[str, str]] = set()
    for (where, kind), seal in seals.items():
        line, code = log.get((where, kind)), seal.get("code")
        if kind != reviewer or not where.startswith(folder) or line is None or not isinstance(code, dict):
            continue
        try:
            if reviewlog.digest((root / str(line.get("file") or where)).read_text(encoding="utf-8-sig")) != line.get("sha256"):
                continue
        except OSError:
            continue
        if isinstance(code.get("files"), dict):
            seen.update((name, digest) for name, digest in code["files"].items())
    return seen


def _again(reviewer: str, gate: str) -> str:
    if gate == "verify":
        return (f"the feature is in verify: go back to implement with /greenlight:change, run the {reviewer} there and pass "
                "the implement gate again (files a test tool generated belong in .gitignore)")
    return f"run the {reviewer} again"


def _older_than_code(root: Path, rel: str, reviewer: str, gate: str, line: dict, seal: dict | None,
                     seen: Callable[[], set[tuple[str, str]]]) -> str | None:
    """The problem when the report has no seal, or its seal records production files that changed after its reviewer
    finished, and no other report of that reviewer kind was sealed with them as they are now. A seal that says the files
    could not be told (``Unjudged``) leaves the report as it is; anything that stops the check from running is a problem
    too, so a report is never passed on what could not be read."""
    again = _again(reviewer, gate)
    if seal is None:
        if line.get("agent_id") in (None, ""):
            return f"{rel} was written without an agent id, so it cannot be sealed: the {reviewer} subagent writes it; {again}"
        return f"{rel} has no record of the code it was written against (the {reviewer}'s SubagentStop did not seal it): {again}"
    if seal.get("error"):
        return f"{rel}: the code it covers could not be read when the {reviewer} finished ({seal['error']}); {again}"
    if seal["code"] is None:
        return None
    try:
        news = reviewfresh.changed(root, seal["code"])
    except Exception as exc:
        return f"{rel}: whether the code it covers changed could not be checked ({type(exc).__name__}: {exc}); {again}"
    if news:
        known = seen()
        news = {name: digest for name, digest in news.items() if digest is None or (name, digest) not in known}
    if not news:
        return None
    shown = ", ".join(list(news)[:3]) + (f" and {len(news) - 3} more" if len(news) > 3 else "")
    return f"{rel} is older than the code it covers: {shown} changed after the {reviewer} finished; {again}"


def review_problems(root: Path, feature_dir: Path, feature_id: str, hooks_seen: bool = False, gate: str = "implement",
                    against: bool = False, found: list[Route] | None = None) -> list[str]:
    """Why the implement gate may not pass yet: a review the routing asks for is missing or has no verdict, or, where the
    hooks run, its content is not what that reviewer wrote to that file (``reviewlog``), or the production files of its
    task changed after the reviewer finished (``reviewfresh``). ``gate`` only words what to do about a stale report. For a
    feature built against its design (``against``), a code review must also answer every risk of its task, and a UI
    review compare every screen row of its task with its design or say why it could not."""
    problems: list[str] = []
    log = reviewlog.recorded(root) if hooks_seen else {}
    finished = finished_agents(root) if hooks_seen else {}
    seals = reviewlog.seals(root) if hooks_seen else {}
    for route in found if found is not None else routes(root, feature_dir, feature_id):
        for reviewer in route.reviewers:
            path = review_path(feature_dir, route.task, reviewer)
            rel = path.relative_to(feature_dir).as_posix()
            text = path.read_text(encoding="utf-8-sig", errors="replace") if path.is_file() else None
            if text is None:
                problems.append(f"{route.task} has no {reviewer} report ({rel})")
                continue
            if not VERDICT.search(text):
                problems.append(f"{rel} has no 'Verdict: PASS' or 'Verdict: FINDINGS' line")
                continue
            if hooks_seen and not reviewlog.written_by(root, path, reviewer, log, finished):
                problems.append(f"{rel} is not what the {reviewer} agent wrote: a report counts only as its own reviewer "
                                "wrote it, unchanged; run the reviewer again")
                continue
            if hooks_seen:
                where = (reviewlog.key(root, path), reviewer)
                older = _older_than_code(root, rel, reviewer, gate, log[where], seals.get(where),
                                         lambda kind=reviewer: _seen_by(root, feature_dir, kind, seals, log))
                problems += [older] if older else []
            if against and reviewer == "code-reviewer":
                problems += risks.review_problems(rel, text, route.risks)
            if against and reviewer == "ui-reviewer":
                problems += side_by_side_problems(feature_dir, rel, text, route.rows)
    return problems


WIDTHS = (375, 1280)
PNG = b"\x89PNG\r\n\x1a\n"
_COMPARED = re.compile(r"^[ \t]*(?:[-*+][ \t]+)?(?P<row>[\w.-]+)[ \t]+(?P<width>\d{3,4})[ \t]*px[ \t]*:[ \t]*"
                       r"(?P<built>[^\s|,]+)[ \t]*[|,][ \t]*(?P<design>[^\s|,]+)[ \t]*$", re.IGNORECASE | re.MULTILINE)
_HEADING = re.compile(r"^#{1,6}[ \t]+(?P<title>[^\n]*)$")
_SCREENSHOT = re.compile(r"[A-Za-z0-9][\w.-]{0,120}\.png", re.IGNORECASE)


def _section_lines(text: str, title: str) -> list[str]:
    """The lines under the report's heading ``title``, up to the next heading."""
    lines, inside = [], False
    for line in text.splitlines():
        heading = _HEADING.match(line)
        if heading:
            inside = heading.group("title").strip().casefold() == title.casefold()
        elif inside and line.strip():
            lines.append(line.strip(" -*+\t"))
    return lines


def _is_png(folder: Path, name: str) -> bool:
    """Is ``name`` a picture file of the reviews folder itself (a plain file name ending in .png, no folder, drive or
    other mark) that starts as a PNG?"""
    if not _SCREENSHOT.fullmatch(name):
        return False
    try:
        with (folder / name).open("rb") as handle:
            return handle.read(len(PNG)) == PNG
    except (OSError, ValueError):
        return False


def side_by_side_problems(feature_dir: Path, rel: str, text: str, rows: list[str]) -> list[str]:
    """Why a UI review does not show its task's screens next to their design: a row with no comparison at each width
    (``O-SI-01 375 px: built.png | design.png`` under *Side by side*, both PNG files in ``reviews/``) and no line under
    *Not checked* that names the row and says why it could not be compared."""
    from .issues import safe_cell
    compared = {(m.group("row").casefold(), int(m.group("width"))): (m.group("built"), m.group("design"))
                for m in _COMPARED.finditer(text)}
    excused = _section_lines(text, "Not checked")
    problems = []
    for row in rows:
        if any(_mentions([line], row) and len(line) - len(row) >= risks.MIN_REASON for line in excused):
            continue
        if not all((row.casefold(), width) in compared for width in WIDTHS):
            problems.append(f"{rel} neither compares {safe_cell(row)} with its design at "
                            f"{' and '.join(map(str, WIDTHS))} px nor says under Not checked why it could not")
            continue
        for width in WIDTHS:
            built, designed = compared[(row.casefold(), width)]
            if built.casefold() == designed.casefold():
                problems.append(f"{rel}: {safe_cell(row)} at {width} px names one screenshot for the built screen and the "
                                "design; save one of each")
                continue
            problems += [f"{rel}: the screenshot {safe_cell(name)} of {safe_cell(row)} at {width} px is not a PNG file in "
                         f"{REVIEWS_DIR}/" for name in (built, designed) if not _is_png(feature_dir / REVIEWS_DIR, name)]
    return problems


def line_problems(feature_dir: Path, feature_id: str) -> list[str]:
    """For a feature built against its design: the tasks of tasks.md with no ``Design:`` or ``Risks:`` line, and the words
    of a Risks: line that are not known risks."""
    tasks = trace.read_tasks(feature_dir / "tasks.md") or {}
    missing = unwritten(tasks)
    problems = [f"{', '.join(missing)} {'has' if len(missing) == 1 else 'have'} no Design: or Risks: line in tasks.md: copy "
                f"them from `bdd route {feature_id}` (Risks: none when it names none)"] if missing else []
    return problems + [gap.message for gap in trace.risk_gaps(tasks)]


def unwritten(tasks: dict[str, dict]) -> list[str]:
    """The tasks that have no Design: or no Risks: line (a task list written before them)."""
    return [t for t, task in tasks.items() if task["design"] is None or task["risks"] is None]


def describe(route: Route) -> str:
    lines = [f"{route.task} {route.title}".rstrip(), f"  writer: {route.writer}", f"  reviewers: {', '.join(route.reviewers)}",
             f"  cards: {', '.join(route.cards) or '(the language card only)'}"]
    lines += [f"  because: {'; '.join(route.because)}"] if route.because else []
    design = "; ".join(part for part in (", ".join(route.design), ", ".join(route.rows)) if part)
    lines += [f"  design: {design}"] if design else []
    lines += [f"  screens: {'; '.join(route.screens)}"] if route.screens else []
    lines.append(f"  risks: {', '.join(route.risks) or 'none'}")
    lines += [f"  blocks: {'; '.join(_block(b) for b in route.blocks)}"] if route.blocks else []
    lines += [f"  services: {'; '.join(_service(s) for s in route.services)}"] if route.services else []
    order = f"  runs in: group {route.group}"
    order += f", after {', '.join(route.after)}" if route.after else ""
    order += f", with {', '.join(route.alongside)}" if route.alongside else ""
    return "\n".join(lines + [order])


def _block(block: dict) -> str:
    return f"{block['field']}: {block['library']} ({block['package']} {block['version']}), {block['source']}"


def _service(service: dict) -> str:
    where = ", ".join(f"{k} {service[k]}" for k in ("docs", "mcp", "cli", "plugin") if service.get(k))
    return f"{service['service']} ({service['call']}): {where or 'not in .bdd/sources.toml'}"


def run(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="bdd route", description="Name the writer, the reviewers and the cards of each task.")
    ap.add_argument("feature", help="feature id, e.g. FEAT-007")
    ap.add_argument("--json", action="store_true", help="print the routes as JSON")
    args = ap.parse_args(argv)
    try:
        from .statecmd import project_root
        root = project_root()
        feature_dir = store.find_feature_dir(root, args.feature)
        found = routes(root, feature_dir, args.feature)
    except (UsageError, StoreError, cfg.ConfigError, vocabulary.VocabularyError) as exc:
        print(f"bdd route: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps([asdict(r) for r in found], indent=2))
        return 0
    print("\n".join(describe(r) for r in found) or f"{args.feature}: tasks.md names no task")
    missing = unwritten(trace.read_tasks(feature_dir / "tasks.md") or {})
    if missing:
        print(f"note: tasks.md has no Design: or Risks: line for {', '.join(missing)}; the ones above are derived "
              "from the rules, the steps and the design")
    return 0
