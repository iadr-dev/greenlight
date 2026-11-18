"""What a project's own files say about its tools, its design folder and the surfaces it ships.

``bdd init`` uses this to fill in ``.bdd/config.toml``:

* ``quality``: a ``[adapters.quality.NAME]`` check for each formatter, linter, type checker and architecture checker the
  project itself declares (a dependency of its manifest, its own config file, or the toolchain its manifest implies). A tool
  nobody declared is never proposed.
* ``design``: a ``[design]`` table when the project has a ``design/`` folder with a DESIGN.md or an inventory.
* ``surfaces``: a ``[surfaces]`` table of the web, iOS, Android, API and command-line surfaces it ships, each set to the
  adapter that verifies it or to ``unverified``.
"""
from __future__ import annotations

import fnmatch
import os
import posixpath
import re
from dataclasses import dataclass
from pathlib import Path

from . import adapter
from . import config as cfg
from . import sources
from .sources import Manifest, Source, toml_string

ESLINT_CONFIGS = tuple(f"eslint.config.{ext}" for ext in ("js", "mjs", "cjs", "ts", "mts")) + (
    ".eslintrc", ".eslintrc.json", ".eslintrc.js", ".eslintrc.cjs", ".eslintrc.yml", ".eslintrc.yaml")
DEPCRUISE_CONFIGS = tuple(f".dependency-cruiser.{ext}" for ext in ("js", "cjs", "mjs", "json"))
GOLANGCI_CONFIGS = tuple(f".golangci.{ext}" for ext in ("yml", "yaml", "toml", "json"))


@dataclass(frozen=True)
class Tool:
    """One check ``bdd init`` may propose, and what makes the project's own files declare the tool.

    A project declares a tool when one of ``declared_by`` (dependency names, ``*`` allowed) is in its manifest, one of
    ``declared_by_files`` (file names, or ``tool:NAME`` for a ``[tool.NAME]`` table of pyproject.toml) is in its folder, or
    the tool is part of the ``toolchain`` its manifest implies. ``needs`` lists files without one of which the command
    would only fail (a TypeScript project without tsconfig.json): then the tool is not proposed."""
    ecosystem: str
    name: str
    command: str
    declared_by: tuple[str, ...] = ()
    declared_by_files: tuple[str, ...] = ()
    needs: tuple[str, ...] = ()
    toolchain: bool = False
    unless: tuple[str, ...] = ()
    fail_on_output: bool = False
    exclude: str = ""          # words that leave a folder out ({dir}): the adapter's own test folder is not the project's code


PY = "{project_python} -m"
TOOLS = (
    Tool("npm", "tsc", "{node} tsc --noEmit", ("typescript",), needs=("tsconfig.json",)),
    Tool("npm", "eslint", "{node} eslint .", ("eslint",), needs=ESLINT_CONFIGS, exclude="--ignore-pattern {dir}"),
    Tool("npm", "prettier", "{node} prettier --check .", ("prettier",), exclude="!{dir}"),
    Tool("npm", "biome", "{node} biome check .", ("@biomejs/biome",), needs=("biome.json", "biome.jsonc")),
    Tool("npm", "dependency-cruiser", "{node} depcruise {src}", ("dependency-cruiser",), needs=DEPCRUISE_CONFIGS),
    Tool("pypi", "ruff", f"{PY} ruff check .", ("ruff",), ("tool:ruff", "ruff.toml", ".ruff.toml"), exclude="--extend-exclude {dir}"),
    Tool("pypi", "ruff-format", f"{PY} ruff format --check .", ("ruff",), ("tool:ruff", "ruff.toml", ".ruff.toml"),
         exclude="--extend-exclude {dir}"),
    Tool("pypi", "black", f"{PY} black --check .", ("black",), ("tool:black",), exclude="--extend-exclude /{dir}/"),
    Tool("pypi", "mypy", f"{PY} mypy .", ("mypy",), ("tool:mypy", "mypy.ini", ".mypy.ini"), exclude="--exclude ^{dir}/"),
    Tool("pypi", "pyright", f"{PY} pyright", ("pyright",), ("tool:pyright", "pyrightconfig.json")),
    Tool("pypi", "flake8", f"{PY} flake8 .", ("flake8",), (".flake8",), exclude="--extend-exclude {dir}"),
    Tool("pypi", "import-linter", '{project_python} -c "from importlinter.cli import lint_imports_command; lint_imports_command()"',
         ("import-linter",), ("tool:importlinter", ".importlinter"), needs=("tool:importlinter", ".importlinter")),
    Tool("go", "gofmt", "gofmt -l .", toolchain=True, fail_on_output=True),
    Tool("go", "go-vet", "go vet ./...", toolchain=True),
    Tool("go", "golangci-lint", "golangci-lint run ./...", ("github.com/golangci/golangci-lint*",), GOLANGCI_CONFIGS),
    Tool("maven", "ktlint", "./gradlew -q ktlintCheck", ("org.jlleitschuh.gradle.ktlint", "org.jmailen.kotlinter", "com.pinterest*:ktlint*"),
         needs=("gradlew",)),
    Tool("maven", "detekt", "./gradlew -q detekt", ("io.gitlab.arturbosch.detekt", "io.gitlab.arturbosch.detekt:*"), needs=("gradlew",)),
    Tool("maven", "spotless", "./gradlew -q spotlessCheck", ("com.diffplug.spotless",), needs=("gradlew",)),
    Tool("maven", "spotless", "mvn -B -ntp -q spotless:check", ("*:spotless-maven-plugin",), needs=("pom.xml",)),
    Tool("maven", "checkstyle", "mvn -B -ntp -q checkstyle:check", ("*:maven-checkstyle-plugin",), needs=("pom.xml",)),
    Tool("pub", "flutter-analyze", "flutter analyze", ("flutter",)),
    Tool("pub", "dart-analyze", "dart analyze", toolchain=True, unless=("flutter",)),
    Tool("pub", "dart-format", "dart format --output=none --set-exit-if-changed .", toolchain=True),
    Tool("cargo", "cargo-fmt", "cargo fmt --check", toolchain=True),
    Tool("cargo", "clippy", "cargo clippy --all-targets -- -D warnings", toolchain=True),
    Tool("nuget", "dotnet-format", "dotnet format --verify-no-changes --no-restore", toolchain=True),
    Tool("gem", "rubocop", "bundle exec rubocop", ("rubocop",), (".rubocop.yml",)),
)


@dataclass(frozen=True)
class Check:
    name: str
    command: str
    cwd: str
    fail_on_output: bool


@dataclass(frozen=True)
class Project:
    """The manifests of one folder and ecosystem, as one."""
    folder: str
    ecosystem: str
    deps: dict[str, str]
    flags: frozenset[str]
    files: frozenset[str]


def projects(found: list[Manifest]) -> list[Project]:
    merged: dict[tuple[str, str], Project] = {}
    for m in found:
        key = (m.folder, m.ecosystem)
        old = merged.get(key)
        merged[key] = Project(m.folder, m.ecosystem, {**(old.deps if old else {}), **m.deps},
                              (old.flags if old else frozenset()) | m.flags, (old.files if old else frozenset()) | m.files)
    return list(merged.values())


def _has(project: Project, tokens: tuple[str, ...]) -> bool:
    return any(t in project.files or t in project.flags for t in tokens)


def _declared(tool: Tool, project: Project) -> bool:
    if tool.toolchain:
        return True
    return (any(fnmatch.fnmatchcase(dep.casefold().replace("_", "-"), pattern) for dep in project.deps for pattern in tool.declared_by)
            or _has(project, tool.declared_by_files))


def usable(tool: Tool, project: Project) -> bool:
    return (_declared(tool, project) and (not tool.needs or _has(project, tool.needs))
            and not any(dep in project.deps for dep in tool.unless))


def node_runner(project: Project, root_files: frozenset[str]) -> str:
    """How to start a tool installed in the project's own node_modules, from the package manager it already uses."""
    names = project.files | root_files
    manager = next((f.removeprefix("pm:") for f in sorted(project.flags) if f.startswith("pm:")), "")
    if manager == "pnpm" or "pnpm-lock.yaml" in names:
        return "pnpm exec"
    if manager == "yarn" or "yarn.lock" in names:
        return "yarn"
    return "npx --no-install"


def overlap_notes(root: Path, checks: list[Check], owned: tuple[str, ...]) -> list[str]:
    """A TypeScript check cannot leave a folder out on its command line: it reads the project's tsconfig.json. Say so when that
    file does not name the adapter's own test folder, because tsc would then type-check greenlight's plumbing too."""
    notes = []
    for check in checks:
        if not check.name.startswith("tsc"):
            continue
        for inside in left_out(check.cwd, owned):
            config = root / check.cwd / "tsconfig.json"
            text = config.read_text(encoding="utf-8", errors="replace") if config.is_file() else ""
            if f'"{inside}' not in text:
                where = f"{check.cwd}/" if check.cwd else ""
                notes.append(f"note: {where}tsconfig.json does not leave out {inside}/ (greenlight's locked plumbing); if {check.name} "
                             f'reports errors there, add "{inside}" to its exclude')
    return notes


def _label(folder: str) -> str:
    return re.sub(r"[^a-z0-9_-]+", "-", folder.casefold()).strip("-")[:20]


def left_out(folder: str, owned: tuple[str, ...]) -> list[str]:
    """The adapter-owned folders inside ``folder``, relative to it."""
    prefix = f"{folder}/" if folder else ""
    return [d.removeprefix(prefix) for d in owned if d.startswith(prefix) and d != folder]


def owned_folders(data: dict) -> tuple[str, ...]:
    """The folder of each configured adapter's own tests (the folder its features, steps and drivers share), relative to the
    project. greenlight's plumbing is locked there, so the project's formatter and linter are not asked about it."""
    folders = []
    for entry in data.get("adapters", []):
        paths = [str(entry[key]) for key in ("features", "steps", "drivers") if key in entry]
        common = posixpath.commonpath([p.replace("\\", "/") for p in paths]) if len(paths) > 1 else ""
        base = str(entry.get("root", "")).strip("/")
        if common and common != "." and "/" not in common:                # a folder of its own, such as tests
            folders.append(f"{base}/{common}" if base else common)
    return tuple(dict.fromkeys(folders))


def proposed_checks(root: Path, found: list[Manifest], owned: tuple[str, ...] = ()) -> list[Check]:
    """The checks the project's own files declare, in the order of its folders. Two folders that declare the same tool get
    the folder's name as a suffix. ``owned`` are the folders of the adapter's own tests: a tool that can leave a folder out
    does."""
    root_files = frozenset(os.listdir(root))
    chosen: list[tuple[Tool, Project, str]] = []
    for project in projects(found):
        for tool in TOOLS:
            if tool.ecosystem == project.ecosystem and usable(tool, project):
                folder = project.folder
                src = "src" if (root / folder / "src").is_dir() else "."
                command = tool.command.replace("{node}", node_runner(project, root_files)).replace("{src}", src)
                if tool.exclude:
                    command = " ".join([command, *(tool.exclude.format(dir=d) for d in left_out(folder, owned))])
                chosen.append((tool, project, command))
    taken: dict[str, int] = {}
    for tool, _, _ in chosen:
        taken[tool.name] = taken.get(tool.name, 0) + 1
    checks, used = [], set()
    for tool, project, command in chosen:
        name = tool.name if taken[tool.name] == 1 else f"{tool.name}-{_label(project.folder) or 'root'}"
        if name not in used:
            used.add(name)
            checks.append(Check(name, command, project.folder, tool.fail_on_output))
    return checks


def quality_text(checks: list[Check]) -> str:
    lines = ["", "# Quality checks found in this project's own files by `bdd init`; `bdd check FEAT-n` runs them. Edit or delete freely."]
    for check in checks:
        lines += ["", f"[adapters.quality.{check.name}]", f"command = {toml_string(check.command)}"]
        if check.cwd:
            lines.append(f"cwd = {toml_string(check.cwd)}")
        if check.fail_on_output:
            lines.append("fail_on_output = true")
    return "\n".join(lines) + "\n"


def find_design(root: Path) -> cfg.Design | None:
    """The design files of the project: ``design/`` with a DESIGN.md or an inventory. Nothing else is read."""
    folder = root / "design"
    if not folder.is_dir():
        return None
    names = {p.name.casefold(): p.name for p in folder.iterdir() if p.is_file()}
    system, inventory = names.get("design.md"), names.get("inventory.md")
    if not system and not inventory:
        return None
    screens = next((d for d in folder.iterdir() if d.is_dir() and d.name.casefold() == "screens"), None)
    has_screens = screens is not None and any(screens.iterdir())
    return cfg.Design(f"design/{system}" if system else "", f"design/{screens.name}/*" if has_screens else "",
                      f"design/{inventory}" if inventory else "")


def design_text(design: cfg.Design) -> str:
    lines = ["", "[design]"]
    lines += [f"{key} = {toml_string(value)}" for key, value in (("system", design.system), ("screens", design.screens),
                                                               ("inventory", design.inventory)) if value]
    return "\n".join(lines) + "\n"


def design_summary(design: cfg.Design | None) -> str:
    return ", ".join(v for v in (design.system, design.screens, design.inventory) if v) if design else "none found"


CLI_LIBRARIES = {"npm": ("commander", "yargs", "oclif", "@oclif/core"), "pypi": ("click", "typer"),
                 "go": ("github.com/spf13/cobra", "github.com/urfave/cli*"), "cargo": ("clap",)}


def detect_surfaces(root: Path, found: list[Manifest], sources: list[Source]) -> list[str]:
    """The surfaces the product ships that the project's files show, in the fixed order of ``cfg.SURFACES``."""
    seen = {s for source in sources for s in source.service.surfaces}
    if any("android" in m.flags for m in found):
        seen.add("android")
    for folder in (root, root / "ios"):
        if folder.is_dir() and any(e.name.endswith((".xcodeproj", ".xcworkspace")) for e in folder.iterdir()):
            seen.add("ios")
    for m in found:
        libraries = CLI_LIBRARIES.get(m.ecosystem, ())
        if {"bin", "scripts"} & m.flags or any(fnmatch.fnmatchcase(d, p) for d in m.deps for p in libraries):
            seen.add("cli")
    return [s for s in cfg.SURFACES if s in seen]


def adapter_surfaces(name: str) -> tuple[str, ...]:
    return tuple(adapter.load(adapter.find(name)).get("surfaces", []))


@dataclass(frozen=True)
class Surface:
    name: str
    verified_by: str            # the configured adapter that covers it, or cfg.UNVERIFIED
    could_be: tuple[str, ...]   # adapters greenlight has that cover it and are not configured


def assess(detected: list[str], configured: list[str], fitting: list[str]) -> list[Surface]:
    """``fitting`` are the adapters whose own detection rule matches the project: only they are offered for a surface."""
    covering = {n: adapter_surfaces(n) for n in adapter.available()}
    result = []
    for surface in detected:
        by = next((n for n in configured if surface in covering.get(n, ())), cfg.UNVERIFIED)
        could = tuple(n for n, covers in covering.items() if surface in covers and n in fitting and n not in configured) if by == cfg.UNVERIFIED else ()
        result.append(Surface(surface, by, could))
    return result


def surfaces_text(assessed: list[Surface]) -> str:
    return "\n[surfaces]\n" + "".join(f"{s.name} = {toml_string(s.verified_by)}\n" for s in assessed)


def unverified_lines(assessed: list[Surface], configured: list[str]) -> list[str]:
    """What to tell the person about each surface no configured adapter covers."""
    pending = [s for s in assessed if s.verified_by == cfg.UNVERIFIED]
    lines = []
    mobile = [s for s in pending if s.name in ("ios", "android") and not s.could_be]
    if len(mobile) == 2:
        lines.append("mobile screens: no adapter, recorded as unverified")
        pending = [s for s in pending if s not in mobile]
    for s in pending:
        label = f"{s.name} screens" if s.name in ("web", "ios", "android") else s.name
        if s.could_be:
            by = f"not checked by {', '.join(configured)}" if configured else "not checked, no adapter is set up yet"
            target = " --into web" if s.name == "web" else ""
            lines.append(f"{label}: {by}; {', '.join(s.could_be)} {'covers' if len(s.could_be) == 1 else 'cover'} {s.name} (add it with `bdd adapter apply {s.could_be[0]}{target}`)")
        else:
            lines.append(f"{label}: no adapter, recorded as unverified")
    return lines


def recorded(root: Path, config: cfg.Config) -> dict:
    """What setup recorded, as `bdd status` shows it: the sources, the quality checks and the design files."""
    entries, problem = sources.load(root)
    return {"sources": list(entries), "quality_checks": [c.name for c in config.quality.checks] if config.quality else [],
            "design": vars(config.design) if config.design else None, "sources_problem": problem}


def recorded_lines(facts: dict) -> list[str]:
    lines = []
    if facts["sources"]:
        lines.append("sources: " + ", ".join(facts["sources"]))
    if facts["quality_checks"]:
        lines.append("quality checks: " + ", ".join(facts["quality_checks"]))
    if facts["design"]:
        lines.append("design: " + design_summary(cfg.Design(**facts["design"])))
    if facts["sources_problem"]:
        lines.append(f"warning: {facts['sources_problem']}")
    return lines


def unverified(config: cfg.Config) -> list[str]:
    """The recorded surfaces no adapter of the project covers now, in the fixed order. The record is what setup knew; an adapter
    added since counts."""
    covered = {s for rules in config.runs for s in adapter_surfaces(rules.adapter)} if config.runs else set()
    pending = {surface for surface, value in config.surfaces if value == cfg.UNVERIFIED}
    return [s for s in cfg.SURFACES if s in pending and s not in covered]
