"""What a project's own files say it is built from: its dependency manifests, and the services and frameworks they name.

``bdd init`` reads the manifests (package.json, pyproject.toml, requirements*.txt, go.mod, pom.xml, build.gradle*,
*.csproj, pubspec.yaml, Cargo.toml, Gemfile) of the project and of the folders just below it, matches the dependencies
against ``data/services.json`` and writes one entry per match to ``.bdd/sources.toml``: the service, its official
documentation, the vendor's command-line tool and plugin when there is one, and the version the manifest declares. A
package that is not in the catalog is not guessed at. The file is the person's: later runs only add entries it lacks.
"""
from __future__ import annotations

import fnmatch
import json
import os
import re
import tomllib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from . import config as cfg

SOURCES_FILE = "sources.toml"
ECOSYSTEMS = ("npm", "pypi", "go", "maven", "nuget", "pub", "cargo", "gem")
SKIPPED_DIRS = {"node_modules", "vendor", "dist", "build", "target", "out", "venv", "env", "__pycache__", "Pods", "coverage"}
MAX_DEPTH = 2
MAX_FILE_BYTES = 2_000_000
DATA = Path(__file__).resolve().parent / "data" / "services.json"
HEADER = ("# What this project is built from, found by `bdd init` in its dependency manifests.\n"
          "# This file is yours: edit an entry or add `ignore = true` to one you do not want. `bdd init --refresh` adds\n"
          "# entries it does not find here and never rewrites one that is.\n")


@dataclass(frozen=True)
class Manifest:
    path: str                                   # project-relative file, with forward slashes
    folder: str                                 # project-relative folder ("" is the project itself)
    ecosystem: str
    deps: dict[str, str]                        # dependency (or plugin) name -> the version the file declares
    flags: frozenset[str] = frozenset()         # facts about the file: "bin", "scripts", "tool:ruff", "pm:pnpm", ...
    files: frozenset[str] = frozenset()         # names of the files in the folder


@dataclass(frozen=True)
class Service:
    id: str
    name: str
    kind: str                                   # service | framework
    docs: str
    cli: str
    plugin: str
    surfaces: tuple[str, ...]
    packages: dict[str, tuple[str, ...]]
    files: tuple[str, ...] = ()                 # project files that show the service without a dependency (supabase/config.toml)


@dataclass(frozen=True)
class Source:
    service: Service
    package: str
    version: str
    found_in: str
    mcp: str = ""


@lru_cache(maxsize=1)
def catalog() -> tuple[Service, ...]:
    entries = json.loads(DATA.read_text(encoding="utf-8"))["services"]
    return tuple(Service(e["id"], e["name"], e["kind"], e["docs"], e["cli"], e["plugin"], tuple(e["surfaces"]),
                         {k: tuple(v) for k, v in e["packages"].items()}, tuple(e.get("files", ()))) for e in entries)


def _read(path: Path) -> str:
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return ""
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


_PEP508 = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[[^\]]*\])?\s*([^;#]*)")


def _requirement(line: str) -> tuple[str, str] | None:
    found = _PEP508.match(line)
    return (found.group(1), found.group(2).strip()) if found else None


def _requirements(lines) -> dict[str, str]:
    deps = {}
    for line in lines:
        if isinstance(line, str) and not line.lstrip().startswith(("-", "#", ".", "/")) and (parsed := _requirement(line)):
            deps.setdefault(parsed[0], parsed[1])
    return deps


def _package_json(text: str) -> tuple[dict[str, str], frozenset[str]]:
    data = json.loads(text)
    deps: dict[str, str] = {}
    for section in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        table = data.get(section)
        if isinstance(table, dict):
            deps.update({str(k): str(v) for k, v in table.items()})
    flags = {"bin"} if data.get("bin") else set()
    manager = str(data.get("packageManager", "")).split("@", 1)[0]
    if manager in ("pnpm", "yarn", "npm", "bun"):
        flags.add(f"pm:{manager}")
    return deps, frozenset(flags)


def _pyproject(text: str) -> tuple[dict[str, str], frozenset[str]]:
    data = tomllib.loads(text)
    project = data.get("project", {})
    deps = _requirements(project.get("dependencies", []))
    for group in (project.get("optional-dependencies") or {}).values():
        deps.update(_requirements(group))
    for group in (data.get("dependency-groups") or {}).values():
        deps.update(_requirements(group))
    poetry = data.get("tool", {}).get("poetry", {})
    for table in (poetry.get("dependencies"), poetry.get("dev-dependencies"),
                  *(g.get("dependencies") for g in (poetry.get("group") or {}).values())):
        for name, spec in (table or {}).items():
            deps.setdefault(name, spec if isinstance(spec, str) else str((spec or {}).get("version", "")))
    deps.update(_requirements(data.get("tool", {}).get("uv", {}).get("dev-dependencies", [])))
    flags = {f"tool:{name}" for name in data.get("tool", {})}
    if project.get("scripts"):
        flags.add("scripts")
    return deps, frozenset(flags)


_GO_REQUIRE = re.compile(r"^\s*(?:require\s+|tool\s+)?(\S+\.\S+)\s+(v\S+)\s*(//.*)?$")
_GO_TOOL = re.compile(r"^\s*tool\s+(\S+\.\S+)\s*$")


def _go_mod(text: str) -> dict[str, str]:
    deps: dict[str, str] = {}
    for line in text.splitlines():
        found = _GO_REQUIRE.match(line)
        if found and "indirect" not in (found.group(3) or ""):
            deps.setdefault(found.group(1), found.group(2))
        elif tool := _GO_TOOL.match(line):
            deps.setdefault(tool.group(1), "")
    return deps


_POM = re.compile(r"<(?:dependency|parent|plugin)>\s*<groupId>\s*([^<\s]+)\s*</groupId>\s*<artifactId>\s*([^<\s]+)\s*</artifactId>"
                  r"(?:\s*<version>\s*([^<\s]+)\s*</version>)?")
_POM_PLUGIN = re.compile(r"<plugin>\s*<artifactId>\s*([^<\s]+)\s*</artifactId>")
_GRADLE_COORD = re.compile(r"""["']([\w.\-]+):([\w.\-]+)(?::([\w.\-${}]+))?["']""")
_GRADLE_PLUGIN = re.compile(r"""(?:\bid\s*\(?\s*|\bkotlin\s*\(\s*)["']([\w.\-]+)["']""")


def _pom(text: str) -> dict[str, str]:
    deps = {f"{g}:{a}": v or "" for g, a, v in _POM.findall(text)}
    for artifact in _POM_PLUGIN.findall(text):
        deps.setdefault(f"org.apache.maven.plugins:{artifact}", "")
    return deps


def _gradle(text: str, folder: Path) -> tuple[dict[str, str], frozenset[str]]:
    deps = {f"{g}:{a}": v for g, a, v in _GRADLE_COORD.findall(text)}
    deps.update({plugin: "" for plugin in _GRADLE_PLUGIN.findall(text)})
    catalog_file = folder / "gradle" / "libs.versions.toml"
    if catalog_file.is_file():
        try:
            data = tomllib.loads(_read(catalog_file))
        except tomllib.TOMLDecodeError:
            data = {}
        for lib in (data.get("libraries") or {}).values():
            module = lib.get("module") if isinstance(lib, dict) else None
            if isinstance(lib, str):
                module = ":".join(lib.split(":")[:2])
            if isinstance(module, str):
                deps.setdefault(module, "")
        for plugin in (data.get("plugins") or {}).values():
            if isinstance(plugin, dict) and isinstance(plugin.get("id"), str):
                deps.setdefault(plugin["id"], "")
    return deps, frozenset({"android"} if "com.android.application" in deps or "com.android.application" in text else ())


_CSPROJ = re.compile(r"""<PackageReference\s+[^>]*?Include\s*=\s*"([^"]+)"(?:[^>]*?Version\s*=\s*"([^"]*)")?""")


def _csproj(text: str) -> dict[str, str]:
    deps = {name: version for name, version in _CSPROJ.findall(text)}
    if re.search(r'<Project\s+Sdk\s*=\s*"Microsoft\.NET\.Sdk\.Web"', text):
        deps.setdefault("Microsoft.AspNetCore.App", "")
    return deps


def _pubspec(text: str) -> dict[str, str]:
    deps: dict[str, str] = {}
    section = ""
    for line in text.splitlines():
        if line.strip().startswith("#") or not line.strip():
            continue
        top = re.match(r"^([A-Za-z_]+):\s*$", line)
        if top:
            section = top.group(1)
            continue
        item = re.match(r"^ {2}([A-Za-z0-9_]+):\s*(.*?)\s*(#.*)?$", line)
        if item and section in ("dependencies", "dev_dependencies"):
            deps.setdefault(item.group(1), item.group(2))
    return deps


def _cargo(text: str, folder: Path) -> tuple[dict[str, str], frozenset[str]]:
    data = tomllib.loads(text)
    deps: dict[str, str] = {}
    tables = [data.get(s) for s in ("dependencies", "dev-dependencies", "build-dependencies")]
    tables.append((data.get("workspace") or {}).get("dependencies"))
    for table in tables:
        for name, spec in (table or {}).items():
            deps.setdefault(name, spec if isinstance(spec, str) else str((spec or {}).get("version", "")))
    return deps, frozenset({"bin"} if data.get("bin") or (folder / "src" / "main.rs").is_file() else ())


_GEM = re.compile(r"""^\s*gem\s+["']([\w\-.]+)["'](?:\s*,\s*["']([^"']+)["'])?""", re.MULTILINE)


def _manifest(root: Path, folder: Path, name: str, names: frozenset[str]) -> Manifest | None:
    """One manifest file read, or None when the file is not one or cannot be read. An unreadable file is a project that
    cannot be described, not a failure of setup."""
    text = _read(folder / name)
    rel_folder = folder.relative_to(root).as_posix() if folder != root else ""
    path = f"{rel_folder}/{name}" if rel_folder else name
    flags: frozenset[str] = frozenset()
    try:
        if name == "package.json":
            ecosystem, (deps, flags) = "npm", _package_json(text)
        elif name == "pyproject.toml":
            ecosystem, (deps, flags) = "pypi", _pyproject(text)
        elif re.fullmatch(r"requirements[\w.\-]*\.txt", name):
            ecosystem, deps = "pypi", _requirements(text.splitlines())
        elif name == "go.mod":
            ecosystem, deps = "go", _go_mod(text)
        elif name == "pom.xml":
            ecosystem, deps = "maven", _pom(text)
        elif name in ("build.gradle", "build.gradle.kts"):
            ecosystem, (deps, flags) = "maven", _gradle(text, folder)
        elif name.endswith(".csproj"):
            ecosystem, deps = "nuget", _csproj(text)
        elif name == "pubspec.yaml":
            ecosystem, deps = "pub", _pubspec(text)
        elif name == "Cargo.toml":
            ecosystem, (deps, flags) = "cargo", _cargo(text, folder)
        elif name == "Gemfile":
            ecosystem, deps = "gem", {n: v or "" for n, v in _GEM.findall(text)}
        else:
            return None
    except (ValueError, TypeError, AttributeError):                 # JSON, TOML and unexpected shapes
        ecosystem, deps = ECOSYSTEM_OF.get(name, "npm"), {}
    return Manifest(path, rel_folder, ecosystem, deps, flags, names)


ECOSYSTEM_OF = {"package.json": "npm", "pyproject.toml": "pypi", "go.mod": "go", "pom.xml": "maven", "pubspec.yaml": "pub",
                "Cargo.toml": "cargo", "Gemfile": "gem", "build.gradle": "maven", "build.gradle.kts": "maven"}
_MANIFEST_NAME = re.compile(r"package\.json|pyproject\.toml|requirements[\w.\-]*\.txt|go\.mod|pom\.xml|build\.gradle(\.kts)?|"
                            r".*\.csproj|pubspec\.yaml|Cargo\.toml|Gemfile")


def manifests(root: Path, skip: frozenset[str] = frozenset()) -> list[Manifest]:
    """The manifests of ``root`` and of the folders up to ``MAX_DEPTH`` below it, the project's own first. ``skip`` holds
    project-relative files that are not the project's (the adapter's own test tooling)."""
    found: list[Manifest] = []
    for dirpath, dirnames, filenames in os.walk(root):
        folder = Path(dirpath)
        depth = len(folder.relative_to(root).parts)
        dirnames[:] = sorted(d for d in dirnames if d not in SKIPPED_DIRS and not d.startswith(".")) if depth < MAX_DEPTH else []
        names = frozenset(filenames) | frozenset(dirnames)
        for name in sorted(filenames):
            if _MANIFEST_NAME.fullmatch(name):
                rel = (folder / name).relative_to(root).as_posix()
                manifest = None if rel in skip else _manifest(root, folder, name, names)
                if manifest is not None:
                    found.append(manifest)
    return sorted(found, key=lambda m: (len(Path(m.path).parts), m.path))


def _normal(ecosystem: str, name: str) -> str:
    return name.casefold().replace("_", "-") if ecosystem in ("pypi", "nuget") else name


def _matches(service: Service, ecosystem: str, name: str) -> bool:
    given = _normal(ecosystem, name)
    return any(fnmatch.fnmatchcase(given, _normal(ecosystem, pattern)) for pattern in service.packages.get(ecosystem, ()))


def project_mcp_servers(root: Path) -> list[str]:
    """The names of the MCP servers the project itself configures (``.mcp.json``)."""
    try:
        data = json.loads(_read(root / ".mcp.json"))
        return [str(name) for name in data.get("mcpServers", {})]
    except (ValueError, AttributeError):
        return []


def detect(root: Path, found: list[Manifest]) -> list[Source]:
    """One source per catalog entry that a dependency of the project names (or, for a few, a file only that service has), in
    the catalog's order."""
    servers = project_mcp_servers(root)
    sources = []
    for service in catalog():
        hit = next(((m.path, n, v) for m in found for n, v in m.deps.items() if _matches(service, m.ecosystem, n)), None)
        if hit is None:
            file = next((f for f in service.files if (root / f).exists()), None)
            hit = (file, "", "") if file else None
        if hit:
            where, package, version = hit
            mcp = next((s for s in servers if service.id in s.casefold()), "")
            sources.append(Source(service, package, version, where, mcp))
    return sources


def toml_string(value: str) -> str:
    """``value`` as a TOML basic string, whatever it holds: a name read from a manifest or a folder can carry a quote, a
    backslash, a line break, a control character or bytes that are not text, and none of them may end the string or add a key."""
    out = []
    for ch in value:
        if ch in '"\\':
            out.append("\\" + ch)
        elif ch < " " or ch == "\x7f":
            out.append(f"\\u{ord(ch):04x}")
        else:
            out.append("�" if "\ud800" <= ch <= "\udfff" else ch)
    return '"' + "".join(out) + '"'


def entry_text(source: Source) -> str:
    s = source.service
    lines = [f"[{s.id}]", f"name = {toml_string(s.name)}", f"docs = {toml_string(s.docs)}"]
    if source.package:
        lines.append(f"package = {toml_string(source.package)}")
    if source.version:
        lines.append(f"version = {toml_string(source.version)}")
    for key, value in (("cli", s.cli), ("plugin", s.plugin), ("mcp", source.mcp)):
        if value:
            lines.append(f"{key} = {toml_string(value)}")
    lines += [f"kind = {toml_string(s.kind)}", f"found_in = {toml_string(source.found_in)}"]
    return "\n".join(lines) + "\n"


def path_of(root: Path) -> Path:
    return root / cfg.BDD_DIR / SOURCES_FILE


def load(root: Path) -> tuple[dict[str, dict], str | None]:
    """(entries by id, a problem or None). A file that cannot be read gives no entries and says why: nothing here may stop a
    command."""
    path = path_of(root)
    if not path.is_file():
        return {}, None
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError, UnicodeDecodeError) as exc:
        return {}, f"{cfg.BDD_DIR}/{SOURCES_FILE} could not be read ({exc}); fix it or delete it"
    return {k: v for k, v in data.items() if isinstance(v, dict) and not v.get("ignore")}, None


def write_missing(root: Path, sources: list[Source]) -> tuple[list[str], str | None]:
    """Add the sources the file does not have yet. Returns (the ids added, a problem or None). An entry that is there, even
    one the person changed or marked ``ignore``, is left exactly as it is."""
    path = path_of(root)
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    try:
        present = set(tomllib.loads(text)) if text else set()
    except tomllib.TOMLDecodeError as exc:
        return [], f"{cfg.BDD_DIR}/{SOURCES_FILE} could not be read ({exc}); nothing was added"
    new = [s for s in sources if s.service.id not in present]
    if not new:
        return [], None
    body = text.rstrip("\n") + "\n\n" if text.strip() else HEADER + "\n"
    written = body + "\n".join(entry_text(s) for s in new)
    try:
        tomllib.loads(written)
    except tomllib.TOMLDecodeError as exc:
        return [], f"{cfg.BDD_DIR}/{SOURCES_FILE} was not changed: the new entries would not read back ({exc})"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(written, encoding="utf-8", newline="\n")
    return [s.service.id for s in new], None
