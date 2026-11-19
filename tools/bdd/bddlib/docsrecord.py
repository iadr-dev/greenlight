"""The documentation a task was written from: what the writer read, recorded per task by the orchestrator.

    bdd docs FEAT-n --task T-n.m --library NAME --version V --source URL_OR_FILE
    bdd docs FEAT-n --task T-n.m --none "why this task calls no library"
    bdd docs FEAT-n --service NAME --source URL_OR_FILE | --mcp SERVER --query TEXT | --cli COMMAND [--task T-n.m]
    bdd docs FEAT-n [--list]

``--service`` records the evidence for an outside call of the technical design (``designsections``) before any task
exists: the service's official page, a documentation lookup through an MCP server, or a run of its command-line tool.
When ``.bdd/sources.toml`` lists the service, the page must be on its official site and the server and the tool the ones
it names. With ``--task`` it is the evidence a writer checked the task's own calls to the service against; it does not
stand in for the task's record of the libraries it calls.

A writer is told to read the current documentation of every library it calls instead of recalling it. It cannot run this
command (it reports, the orchestrator records); the report's "documentation consulted" lines become records here. A record
names the library and its version and a source anyone can open (an https address, or a file such as the installed package's
own documentation or type definitions), and the implement gate refuses while a task has neither a record nor a stated reason
for having none. This is a trail for the reviewer and the auditor to check the code against, not proof that the writer
followed it: whether the code matches the documentation is their judgement.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

from . import config as cfg
from . import route, store
from .errors import StoreError, UsageError

RECORD = "docs-consulted.json"
# Files that name a version or a dependency and say nothing about how a library is used: no source for a record.
VERSION_FILES = re.compile(
    r"(?i)^(?:package(?:-lock)?\.json|pnpm-lock\.yaml|yarn\.lock|npm-shrinkwrap\.json|bun\.lockb?|pyproject\.toml|"
    r"requirements[\w.-]*\.(?:txt|in)|poetry\.lock|uv\.lock|pipfile(?:\.lock)?|setup\.(?:py|cfg)|go\.(?:mod|sum)|"
    r"cargo\.(?:toml|lock)|pom\.xml|build\.gradle(?:\.kts)?|settings\.gradle(?:\.kts)?|libs\.versions\.toml|"
    r"gemfile(?:\.lock)?|composer\.(?:json|lock)|pubspec\.(?:yaml|lock)|package\.swift|packages\.lock\.json|"
    r"[\w.-]+\.(?:csproj|fsproj|vbproj|sln)|[\w.-]+\.lock)$")
TASK = re.compile(r"T-\d+\.\d+")
MIN_REASON = 8


def record_path(feature_dir: Path) -> Path:
    return feature_dir / RECORD


def entries(feature_dir: Path) -> list[dict]:
    path = record_path(feature_dir)
    if not path.is_file():
        return []
    return list(store.read_json(path, "the documentation record").get("entries", []))


def source_problem(root: Path, source: str) -> str | None:
    """Why ``source`` is not something a reader can open, or None when it is an https address or an existing file."""
    if VERSION_FILES.match(Path(source.split("?", 1)[0].replace("\\", "/")).name):
        return ("a version file is not documentation: give the library's documentation page, or a file of the installed "
                "package that documents it (its README, docs folder or type definitions)")
    if re.fullmatch(r"https://[^\s/]+\.[^\s/]+\S*", source):
        return None
    target = Path(source)
    if not target.is_absolute():
        target = root / target
    if source and not re.match(r"[a-z]+://", source) and target.exists():
        return None
    return "the source must be an https address or a file that exists (the installed package's own documentation or types)"


def add(root: Path, feature_dir: Path, feature_id: str, task: str, library: str | None, version: str | None,
        source: str | None, none: str | None) -> dict:
    known = {r.task for r in route.routes(root, feature_dir, feature_id)}
    if not TASK.fullmatch(task) or task not in known:
        raise UsageError(f"{task} is not a task of {feature_id}; the tasks are {', '.join(sorted(known)) or '(none)'}")
    if none is not None:
        if library or version or source:
            raise UsageError("--none stands alone: a task either read some documentation or calls no library")
        if len(none.strip()) < MIN_REASON:
            raise UsageError(f"--none needs a reason of at least {MIN_REASON} characters")
        entry = {"task": task, "kind": "none", "reason": none.strip()}
    else:
        if not (library and version and source):
            raise UsageError("a record needs --library, --version and --source (or --none REASON)")
        problem = source_problem(root, source)
        if problem:
            raise UsageError(problem)
        entry = {"task": task, "kind": "doc", "library": library.strip(), "version": version.strip(), "source": source.strip()}
    entry["at"] = store.utc_now()
    path = record_path(feature_dir)
    store.write_json(path, {"schema": store.SCHEMA, "entries": [*entries(feature_dir), entry]})
    return entry


DOC_SERVERS = ("context7", "microsoft-docs", "microsoft-learn")   # documentation MCP servers that serve any vendor's docs
RUNNERS = ("npx", "bunx", "pnpm dlx", "yarn dlx", "npm exec")


_UNSAFE_ADDRESS = re.compile(r"[\s\\@%\x7f]|[^\x20-\x7e]")


def hostname(url: str) -> str | None:
    """The host a browser opens for an https address, lower-cased, IDNA-encoded and without a trailing dot; None for an
    address that is not plainly one host: userinfo, a backslash, an escape, white space or a control character, a port
    other than 443, or no host at all."""
    if _UNSAFE_ADDRESS.search(url):
        return None
    try:
        parts = urlsplit(url)
        port = parts.port
        host = (parts.hostname or "").rstrip(".")
        host = host.encode("idna").decode("ascii") if host else ""
    except ValueError:                                   # UnicodeError is one
        return None
    if parts.scheme != "https" or not host or parts.username is not None or port not in (None, 443):
        return None
    return host


def site_of(host: str) -> str:
    """The registrable part of a host: ``supabase.com`` for ``docs.supabase.com``, ``example.co.uk`` for a host below it."""
    labels = host.split(".")
    keep = 3 if len(labels) >= 3 and len(labels[-1]) == 2 and labels[-2] in ("co", "com", "org", "net", "ac", "gov", "edu") else 2
    return ".".join(labels[-keep:])


def on_site(url: str, docs: str) -> bool:
    """Is ``url`` an address on the official site of the documentation ``docs`` (the site, or a host below it)?"""
    host, official = hostname(url), hostname(docs)
    if host is None or official is None:
        return False
    site = site_of(official)
    return host == site or host.endswith("." + site)


def _program(command: str) -> str:
    words = command.split()
    for runner in RUNNERS:
        if " ".join(words[:len(runner.split())]) == runner:
            words = words[len(runner.split()):]
    return words[0].casefold() if words else ""


def add_evidence(root: Path, feature_dir: Path, service: str, source: str | None, mcp: str | None, query: str | None,
                 cli: str | None, task: str | None = None) -> dict:
    """Record what a call to ``service`` was checked against: its official page (or a file of the installed package), a
    lookup through an MCP server, or a run of the vendor's command-line tool; for the design, or with ``task`` for the code
    of that task. ``.bdd/sources.toml`` names the service's official site, server and tool when it lists the service; then
    the evidence has to come from them."""
    from . import designsections, sources
    if sum(x is not None for x in (source, mcp, cli)) != 1:
        raise UsageError("evidence is one of --source URL_OR_FILE, --mcp SERVER --query TEXT, or --cli COMMAND")
    if task is not None and not TASK.fullmatch(task):
        raise UsageError(f"--task names a task id such as T-007.1, not {task!r}")
    services = {key.casefold(): value for key, value in sources.load(root)[0].items()}
    key = designsections.service_key(services, service)
    if not key:
        raise UsageError("--service needs the name of the service, as .bdd/sources.toml names it")
    entry_of = services.get(key, {})
    entry: dict = {"service": key, **({"task": task} if task else {})}
    if source is not None:
        problem = source_problem(root, source)
        if problem:
            raise UsageError(problem)
        docs = str(entry_of.get("docs", ""))
        address = re.match(r"[a-z]+://", source, re.IGNORECASE) is not None
        if address and hostname(source) is None:
            raise UsageError(f"{source} is not an https address of one host (no user name, port, escape or backslash)")
        if address and docs and not on_site(source, docs):
            raise UsageError(f"{source} is not on the official site of {key} ({docs}): give its official page, an MCP lookup "
                             "(--mcp) or a CLI run (--cli)")
        entry.update(kind="page", source=source.strip())
    elif mcp is not None:
        if not (query or "").strip():
            raise UsageError("--mcp needs --query: what was looked up")
        named = {str(entry_of.get("mcp", "")).casefold(), str(entry_of.get("plugin", "")).split("@", 1)[0].casefold()} - {""}
        if entry_of and named and not any(n in mcp.casefold() for n in named | set(DOC_SERVERS)):
            raise UsageError(f"the MCP server {mcp} is not one .bdd/sources.toml names for {key} ({', '.join(sorted(named))}) "
                             f"nor a documentation server ({', '.join(DOC_SERVERS)})")
        entry.update(kind="mcp", server=mcp.strip(), query=query.strip())
    else:
        program, wanted = _program(cli or ""), _program(str(entry_of.get("cli", "")))
        if not program:
            raise UsageError("--cli needs the command that was run")
        if wanted and program != wanted:
            raise UsageError(f"the command runs {program}, but .bdd/sources.toml names {wanted} as the tool of {key}")
        entry.update(kind="cli", command=cli.strip())
    entry["at"] = store.utc_now()
    store.write_json(record_path(feature_dir), {"schema": store.SCHEMA, "entries": [*entries(feature_dir), entry]})
    return entry


def problems(root: Path, feature_dir: Path, feature_id: str, found: list | None = None) -> list[str]:
    """Why the implement gate may not pass: a task with no record of the documentation read, and no reason for having none.
    Evidence for an outside service (``--service``) is not a record of the libraries the task calls."""
    try:
        have = {e.get("task") for e in entries(feature_dir) if not e.get("service")}
    except StoreError as exc:
        return [str(exc)]
    found = found if found is not None else route.routes(root, feature_dir, feature_id)
    return [f"{r.task} has no documentation record: `bdd docs {feature_id} --task {r.task} --library NAME --version V "
            "--source URL` for each library it calls, or `--none \"reason\"`" for r in found if r.task not in have]


def describe(entry: dict) -> str:
    if entry.get("service"):
        how = {"page": entry.get("source"), "mcp": f"{entry.get('server')}: {entry.get('query')}",
               "cli": f"ran {entry.get('command')}"}.get(str(entry.get("kind")), "")
        return f"{entry.get('task') or 'design'}  {entry['service']}  {how}"
    if entry.get("kind") == "none":
        return f"{entry['task']}  no library: {entry.get('reason', '')}"
    return f"{entry['task']}  {entry.get('library')} {entry.get('version')}  {entry.get('source')}"


def run(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="bdd docs", description="Record the documentation a task was written from.")
    ap.add_argument("feature", help="feature id, e.g. FEAT-007")
    ap.add_argument("--task", help="the task id, e.g. T-007.1")
    ap.add_argument("--library")
    ap.add_argument("--version")
    ap.add_argument("--source", help="an https address, or a file (the installed package's documentation or types)")
    ap.add_argument("--none", metavar="REASON", help="the task calls no library; say why")
    ap.add_argument("--service", help="the evidence for a call of the technical design: the service, as sources.toml names it")
    ap.add_argument("--mcp", metavar="SERVER", help="with --service: the MCP server the documentation was looked up with")
    ap.add_argument("--query", help="with --mcp: what was looked up")
    ap.add_argument("--cli", metavar="COMMAND", help="with --service: the vendor command-line tool run that was read")
    ap.add_argument("--list", action="store_true", help="print the records of the feature")
    args = ap.parse_args(argv)
    try:
        from .statecmd import project_root
        root = project_root()
        feature_dir = store.find_feature_dir(root, args.feature)
        if args.service is not None:
            if args.library or args.version or args.none is not None:
                raise UsageError("--service records the evidence for a call to a service; it takes --source, --mcp with "
                                 "--query, or --cli, and --task for the task that makes the call")
            entry = add_evidence(root, feature_dir, args.service, args.source, args.mcp, args.query, args.cli, args.task)
            print(f"recorded: {entry.get('task') or 'design'} evidence for {entry['service']}")
            return 0
        if args.list or not args.task:
            found = entries(feature_dir)
            print("\n".join(describe(e) for e in found) or f"{args.feature}: no documentation recorded yet")
            return 0
        entry = add(root, feature_dir, args.feature, args.task, args.library, args.version, args.source, args.none)
    except (UsageError, StoreError, cfg.ConfigError) as exc:
        print(f"bdd docs: {exc}", file=sys.stderr)
        return 2
    print(f"recorded: {entry['task']} " + (f"{entry['library']} {entry['version']}" if entry["kind"] == "doc" else "no library"))
    return 0
