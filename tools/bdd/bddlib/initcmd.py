"""`bdd init`: set a repository up for greenlight.

    bdd init --detect                       which adapters fit this repository, and why
    bdd init [--adapter NAME] [--autonomy LEVEL]
                                            create .bdd/ (config, glossary, ignore file) and apply the adapter
    bdd init --smoke                        prove the adapter's sample feature runs green, leaving nothing behind
    bdd init --standards                    add .bdd/standards.md (greenlight's default engineering standards) to a project that has none
    bdd init --refresh                      read the project's files again and record what is new (sources, quality checks, design, surfaces)

Nothing is overwritten, and an existing project is only extended (``--adapter`` on a project that has none). Setup also
records what the project's own files show: ``.bdd/sources.toml`` (the services and frameworks its dependencies name),
``[adapters.quality.NAME]`` checks for the tools it declares, ``[design]`` and ``[surfaces]``. Each is added only when the
project has none of it yet, so a run never changes what the person wrote.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import shutil
import sys
import tempfile
import tomllib
from pathlib import Path

from . import adapter, classify, runner, sharedvocab, sources, state, toolchain
from . import config as cfg
from .errors import UsageError
from .statecmd import guarded

IGNORED = (".enforcement/", ".integrity/", ".runs/")      # machine-local data: not for version control
SAMPLE = "FEAT-000"


def first_match(root: Path, rule: dict) -> str | None:
    """Why ``rule`` (a ``[detect]`` table: files to look at, words to look for) fits ``root``, or None."""
    words = [w.casefold() for w in rule.get("contains", [])]
    for pattern in rule.get("files", []):
        for path in sorted(p for p in root.iterdir() if p.is_file() and fnmatch.fnmatch(p.name, pattern)):
            text = path.read_text(encoding="utf-8", errors="replace").casefold()
            hit = next((w for w in words if w in text), None)
            if hit:
                return f"{path.name} mentions {hit}"
    return None


def detect(root: Path) -> list[tuple[str, str]]:
    """(adapter, reason) for every adapter whose detection rule matches a file in ``root``."""
    found = []
    for name in adapter.available():
        reason = first_match(root, adapter.load(adapter.find(name)).get("detect", {}))
        if reason:
            found.append((name, reason))
    return found


def config_text(autonomy: str, profiles: list[str] | None, python: str | None = None) -> str:
    lines = [f'autonomy = "{autonomy}"', 'language = "auto"', 'enforcement = "auto"']
    if python:
        lines.append("python = " + adapter.toml_value(python))
    if profiles:
        lines.append("profiles = " + adapter.toml_value(profiles))
    return "\n".join(lines) + "\n"


def add_standards(root: Path) -> str | None:
    """Copy greenlight's default standards to .bdd/standards.md unless the file exists. Returns the path made, or None."""
    target = root / cfg.BDD_DIR / "standards.md"
    if target.exists():
        return None
    shutil.copyfile(adapter.adapters_dir().parent / "templates" / "standards.md", target)
    return f"{cfg.BDD_DIR}/standards.md"


def require_project(here: Path) -> Path:
    root = cfg.find_root(here)
    if root is None:
        raise UsageError("not inside a greenlight project; run bdd init first")
    return root


def add_shared_vocabulary(root: Path, names: list[str]) -> list[str]:
    """Include shared vocabulary files (inside the project) in .bdd/vocabulary.toml and pin them. The person runs this after
    reading the files; an existing [vocabulary] table is left for the person to edit."""
    target = root / cfg.BDD_DIR / "vocabulary.toml"
    try:
        for name in names:
            sharedvocab.resolve_name(root, target, name)                  # refuses a file that is missing or leaves the project
    except sharedvocab.IncludeError as exc:
        raise UsageError(str(exc)) from exc
    text = target.read_text(encoding="utf-8") if target.is_file() else 'extends = "core"\n'
    if f"[{sharedvocab.TABLE}]" in text:
        raise UsageError(f"{cfg.BDD_DIR}/vocabulary.toml already has a [{sharedvocab.TABLE}] table; edit it yourself, then run "
                         "`bdd vocabulary pin`")
    listed = ", ".join(json.dumps(name) for name in names)
    table = f"\n\n[{sharedvocab.TABLE}]\n{sharedvocab.KEY} = [{listed}]\n"
    target.write_text(text.rstrip("\n") + table, encoding="utf-8", newline="\n")
    try:
        pinned = sharedvocab.pin(root, sharedvocab.closure(root, target))
    except sharedvocab.IncludeError as exc:
        raise UsageError(f"{exc} ({cfg.BDD_DIR}/vocabulary.toml was written; fix the include and run `bdd vocabulary pin`)") from exc
    return [f"{cfg.BDD_DIR}/vocabulary.toml (includes {len(names)} file(s))", f"{cfg.BDD_DIR}/{sharedvocab.LOCK_NAME} ({len(pinned)} pinned)"]


def write_project(root: Path, autonomy: str, profiles: list[str] | None, python: str | None = None) -> list[str]:
    if autonomy not in state.AUTONOMY:
        raise UsageError(f"autonomy must be one of {', '.join(state.AUTONOMY)}")
    bdd = root / cfg.BDD_DIR
    if (bdd / "config.toml").exists():
        raise UsageError(f"{bdd / 'config.toml'} already exists; this repository is already set up")
    created = []
    (bdd / "features").mkdir(parents=True, exist_ok=True)
    for rel, text in (("config.toml", config_text(autonomy, profiles, python)), (".gitignore", "".join(f"{i}\n" for i in IGNORED))):
        (bdd / rel).write_text(text, encoding="utf-8", newline="\n")
        created.append(f"{cfg.BDD_DIR}/{rel}")
    glossary = bdd / "glossary.md"
    if not glossary.exists():
        shutil.copyfile(adapter.adapters_dir().parent / "templates" / "glossary.md", glossary)
        created.append(f"{cfg.BDD_DIR}/glossary.md")
    created += [made for made in (add_standards(root),) if made]
    return created


def relative_files(root: Path, files: tuple[Path, ...]) -> frozenset[str]:
    names = set()
    for path in files:
        try:
            names.add(path.relative_to(root).as_posix())
        except ValueError:
            continue
    return frozenset(names)


def sources_lines(detected: list[sources.Source], problem: str | None) -> list[str]:
    services = [s for s in detected if s.service.kind == "service"]
    frameworks = [s for s in detected if s.service.kind == "framework"]
    lines = ["sources: " + (", ".join(s.service.id for s in services) or "none recognised")]
    if frameworks:
        lines.append("frameworks: " + ", ".join(s.service.id for s in frameworks))
    tools = [(s.service.cli, bool(shutil.which(s.service.cli))) for s in services if s.service.cli]
    if tools:
        lines.append("vendor tools: " + ", ".join(f"{cli} ({'found' if there else 'not installed'})" for cli, there in tools))
    plugins = [s.service.plugin.split("@", 1)[0] for s in detected if s.service.plugin]
    if plugins:
        lines.append("vendor plugins: " + ", ".join(plugins) + " (`bdd helpers` shows which are installed)")
    return lines + ([f"note: {problem}"] if problem else [])


def quality_record(data: dict, checks: list[toolchain.Check]) -> tuple[str, str]:
    """(the line to print, the text to add to config.toml)."""
    if any("quality" in a for a in data.get("adapters", [])):
        return "quality: the checks already in .bdd/config.toml are kept", ""
    if not data.get("adapters"):
        return ("quality: none recorded yet; add an adapter (bdd init --adapter NAME), then run bdd init --refresh"
                if checks else "quality: none declared by the project's files"), ""
    if not checks:
        return "quality: none declared by the project's files", ""
    return "quality: " + ", ".join(c.name for c in checks), toolchain.quality_text(checks)


def design_record(root: Path, data: dict) -> tuple[str, str]:
    if "design" in data:
        return "design: already in .bdd/config.toml", ""
    design = toolchain.find_design(root)
    return "design: " + toolchain.design_summary(design), toolchain.design_text(design) if design else ""


def surfaces_record(root: Path, data: dict, found: list[sources.Manifest], detected: list[sources.Source]) -> tuple[list[str], str]:
    if "surfaces" in data:
        return ["surfaces: already in .bdd/config.toml"], ""
    configured = [str(a.get("name")) for a in data.get("adapters", []) if a.get("name")]
    assessed = toolchain.assess(toolchain.detect_surfaces(root, found, detected), configured, [n for n, _ in detect(root)])
    if not assessed:
        return ["surfaces: none detected"], ""
    line = "surfaces: " + ", ".join(f"{s.name} ({s.verified_by})" for s in assessed)
    return [line, *toolchain.unverified_lines(assessed, configured)], toolchain.surfaces_text(assessed)


def unreadable(extra: str, whole: str) -> str | None:
    """Why the records ``extra`` would break the configuration ``whole``, or None. The config is read the way every command
    reads it, so a table that fails here would make the guard refuse every call."""
    try:
        tomllib.loads(whole)
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / cfg.BDD_DIR).mkdir()
            (Path(tmp) / cfg.BDD_DIR / "config.toml").write_text('[[adapters]]\nname = "x"\nfeatures = "f"\n' + extra,
                                                                encoding="utf-8", newline="\n")
            cfg.load(Path(tmp))
    except (tomllib.TOMLDecodeError, cfg.ConfigError) as exc:
        return str(exc)
    return None


def record_project(root: Path) -> None:
    """Read the project's own files and record what they show, adding only what the project does not have yet. Prints one
    line for each record."""
    config_path = root / cfg.BDD_DIR / "config.toml"
    text = config_path.read_text(encoding="utf-8")
    data = tomllib.loads(text)
    found = sources.manifests(root, relative_files(root, cfg.load(root).support_files))
    detected = sources.detect(root, found)
    had_sources = sources.path_of(root).is_file()
    added, problem = sources.write_missing(root, detected)
    if added and not had_sources:
        print(f"  + {cfg.BDD_DIR}/{sources.SOURCES_FILE}")
    owned = toolchain.owned_folders(data)
    checks = toolchain.proposed_checks(root, found, owned)
    quality_line, quality_text = quality_record(data, checks)
    design_line, design_text = design_record(root, data)
    surface_lines, surfaces_text = surfaces_record(root, data, found, detected)
    notes = [*toolchain.overlap_notes(root, checks, owned), *toolchain.skipped_for_overlap(root, found, owned)] if quality_text else []
    print("\n".join([*sources_lines(detected, problem), design_line, quality_line, *surface_lines, *notes]))
    extra = quality_text + design_text + surfaces_text
    if extra:
        new = text.rstrip("\n") + "\n" + extra
        problem = unreadable(extra, new)
        if problem:
            print(f"note: the records were not written because they would not read back ({problem})")
        else:
            config_path.write_text(new, encoding="utf-8", newline="\n")


def do_init(root: Path, name: str | None, autonomy: str, python: str | None = None) -> int:
    existing = root / cfg.BDD_DIR / "config.toml"
    created: list[str] = []
    if existing.exists():
        if not name:
            raise UsageError("this repository is already set up; name an adapter to add with --adapter")
    else:
        profiles = adapter.load(adapter.find(name)).get("profiles") if name else None
        created += write_project(root, autonomy, profiles, python)
    if name:
        files, kept = adapter.apply(root, name)
        created += files
        print(f"adapter {name} added" + (f" ({len(kept)} existing file(s) left alone)" if kept else ""))
    print("\n".join(f"  + {path}" for path in created))
    record_project(root)
    print("next: bdd init --smoke   (proves the sample feature runs green)" if name else
          "next: bdd init --detect, then bdd init --adapter NAME")
    return 0


def do_smoke(root: Path) -> int:
    config = cfg.load(root)
    rules = runner.pick_rules(config, None)
    feature_dir = state.create(root, SAMPLE, "Sample", "standard")
    try:
        record = runner.run_feature(root, SAMPLE, classify.feature_scenarios(root, SAMPLE), [rules])
        report = classify.classify_run(record, classify.feature_scenarios(root, SAMPLE), list(config.runs))
    finally:
        shutil.rmtree(feature_dir, ignore_errors=True)
        shutil.rmtree(runner.runs_dir(root, SAMPLE), ignore_errors=True)
    if report["green"]["valid"]:
        print(f"the sample feature runs green ({len(report['scenarios'])} scenarios); nothing was left behind")
        return 0
    print(classify.render(report), file=sys.stderr)
    print("the sample feature is not green; check the adapter's requirements (see its guide.md)", file=sys.stderr)
    return 1


def run(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="bdd init", description="Set this repository up for greenlight.")
    ap.add_argument("--detect", action="store_true", help="list the adapters that fit this repository")
    ap.add_argument("--adapter", help="the adapter to apply (see bdd adapter list)")
    ap.add_argument("--autonomy", default="guided", choices=state.AUTONOMY, help="default autonomy level (default: guided)")
    ap.add_argument("--python", help="the interpreter the project's tests run with (default: .venv or venv in the project)")
    ap.add_argument("--smoke", action="store_true", help="run the adapter's sample feature and clean up")
    ap.add_argument("--shared-vocabulary", action="append", metavar="FILE",
                    help="include a shared vocabulary file (inside the project) in .bdd/vocabulary.toml and pin it; repeatable")
    ap.add_argument("--refresh", action="store_true",
                    help="read the project's files again and add the sources, quality checks, design and surfaces it lacks")
    ap.add_argument("--standards", action="store_true",
                    help="add .bdd/standards.md (greenlight's default engineering standards) to a project that has none")
    args = ap.parse_args(argv)

    def action() -> int:
        here = Path.cwd()
        if args.detect:
            found = detect(here)
            print("\n".join(f"{name}: {why}" for name, why in found) or "no adapter matched this repository")
            return 0
        if args.shared_vocabulary:
            root = require_project(here)
            print("\n".join(f"  + {made}" for made in add_shared_vocabulary(root.resolve(), args.shared_vocabulary)))
            return 0
        if args.standards:
            made = add_standards(require_project(here))
            print(f"  + {made}" if made else f"{cfg.BDD_DIR}/standards.md already exists; nothing changed")
            return 0
        if args.refresh:
            record_project(require_project(here).resolve())
            return 0
        if args.smoke:
            return do_smoke(require_project(here))
        root = cfg.find_root(here) or here
        if args.python and not Path(args.python).is_file():
            raise UsageError(f"--python {args.python!r} is not a file")
        return do_init(root, args.adapter, args.autonomy, str(Path(args.python).resolve()) if args.python else None)

    try:
        return guarded("init", action)
    except cfg.ConfigError as exc:
        print(f"bdd init: {exc}", file=sys.stderr)
        return 2
