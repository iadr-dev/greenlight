"""Project configuration: ``.bdd/config.toml`` (human-edited, read with tomllib)."""
from __future__ import annotations

import fnmatch
import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

ALL_PROFILES = ("base", "api", "ui", "cli", "lib")
DEFAULT_SIMILARITY = 0.85
BDD_DIR = ".bdd"
ENFORCEMENT_MODES = ("auto", "hard", "soft")
SCHEMA_VERSION = 1                       # of .bdd/ as a whole; `version` in config.toml, absent means 1


class ConfigError(ValueError):
    pass


IGNORED_DIRS = {"__pycache__", "node_modules", ".git"}


def pattern_matches(pattern: str, relative: str) -> bool:
    """Does the project-relative path ``relative`` match ``pattern``? One segment at a time, so ``*`` never crosses a
    slash and the same answer is given wherever it is asked (the guard, the lock, the digest)."""
    parts, names = pattern.split("/"), relative.split("/")
    return len(parts) == len(names) and all(fnmatch.fnmatchcase(n.casefold(), p.casefold()) for p, n in zip(parts, names))


def expand_pattern(root: Path, pattern: str) -> list[Path]:
    """The existing files that match ``pattern``, found by walking from its literal first segments."""
    literal: list[str] = []
    for segment in pattern.split("/"):
        if any(c in segment for c in "*?["):
            break
        literal.append(segment)
    base = root.joinpath(*literal[:-1]) if len(literal) == len(pattern.split("/")) else root.joinpath(*literal)
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if d not in IGNORED_DIRS and not d.startswith(".")]
        for name in filenames:
            candidate = Path(dirpath) / name
            if pattern_matches(pattern, candidate.relative_to(root).as_posix()):
                found.append(candidate)
    return sorted(found)


@dataclass(frozen=True)
class ScanRules:
    """How ``bdd scan`` reads one adapter's step definitions (``[adapters.scan]`` in config.toml)."""
    step_dirs: tuple[Path, ...]
    step_start: str                          # a line that starts a step definition; named group ``kind`` = given|when|then
    assert_patterns: tuple[str, ...] = ()    # evidence that a ``then`` body checks something
    sleep_patterns: tuple[str, ...] = ()     # fixed waits
    stub_patterns: tuple[str, ...] = ()      # a stub of a dependency; group 1 = what is stubbed


@dataclass(frozen=True)
class RunRules:
    """How to run an adapter's tests and read their failures (``[adapters.run]`` / ``[adapters.classify]``).

    Commands are split into words before ``{root}``, ``{python}`` (the interpreter running bdd),
    ``{project_python}`` (the project's own environment), ``{tag}``, ``{marker}``, ``{out}``, ``{seed}`` and
    ``{scenario}`` are filled in, so a value can never add words to the command."""
    adapter: str
    by_tag: str                              # runs the tests carrying {tag}
    report: str                              # extra words that make the runner write JUnit XML to {out}
    shuffle: str = ""                        # extra words for a random order with {seed}
    isolated: str = ""                       # extra words that select one {scenario}
    timeout: int = 600
    test_defect: tuple[str, ...] = ()        # failure text of a broken test (first match wins, checked first)
    expected_fail: tuple[str, ...] = ()      # failure text of a test that fails because the feature is missing
    scrub_env: tuple[str, ...] = ()          # environment variables with these prefixes never reach the runner


@dataclass(frozen=True)
class Config:
    root: Path | None = None                 # directory that contains .bdd/ (None outside a project)
    profiles: tuple[str, ...] = ALL_PROFILES
    near_duplicate_similarity: float = DEFAULT_SIMILARITY
    feature_dirs: tuple[Path, ...] = ()
    step_dirs: tuple[Path, ...] = ()         # step definitions + drivers
    test_dirs: tuple[Path, ...] = ()         # features + steps + drivers: not "production source"
    autonomy: str = "standard"
    language: str = "auto"
    allow_headless_approvals: bool = False   # accept approvals typed into `claude -p` (CI-driven flows)
    enforcement: str = "auto"                # auto | hard | soft: see approvals.self_reported_problem
    scans: tuple[ScanRules, ...] = ()        # one per adapter that has an [adapters.scan] table
    version: int = SCHEMA_VERSION            # the schema this project's .bdd/ is at
    support_files: tuple[Path, ...] = ()     # the adapter's own test plumbing (conftest.py, ...): bound like steps
    support_patterns: tuple[str, ...] = ()   # patterns (relative, with * and ?) for plumbing files that may not exist yet
    python: str = ""                         # the interpreter the project's tests run with (blank: .venv, venv, or bdd's own)
    runs: tuple[RunRules, ...] = ()          # one per adapter that has an [adapters.run] table

    @property
    def vocabulary_file(self) -> Path | None:
        return self.root / BDD_DIR / "vocabulary.toml" if self.root else None


def find_root(start: Path | str | None = None) -> Path | None:
    """Nearest directory at or above ``start`` that contains a ``.bdd`` directory."""
    here = Path(start or Path.cwd()).resolve()
    for candidate in (here, *here.parents):
        if (candidate / BDD_DIR).is_dir():
            return candidate
    return None


def _patterns(table: dict, key: str, path: Path) -> tuple[str, ...]:
    values = table.get(key, [])
    if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
        raise ConfigError(f"{path}: {key} must be a list of regular expressions")
    for value in values:
        try:
            re.compile(value)
        except re.error as exc:
            raise ConfigError(f"{path}: {key}: {value!r} is not a valid regular expression ({exc})") from exc
    return tuple(values)


def _scan_rules(root: Path, adapter: dict, path: Path) -> ScanRules | None:
    table = adapter.get("scan")
    if table is None:
        return None
    if not isinstance(table, dict) or not isinstance(table.get("step_start"), str):
        raise ConfigError(f"{path}: [adapters.scan] needs step_start, a regular expression with a (?P<kind>...) group")
    start = _patterns({"step_start": [table["step_start"]]}, "step_start", path)[0]
    if "kind" not in re.compile(start).groupindex:
        raise ConfigError(f"{path}: [adapters.scan] step_start needs a named group (?P<kind>given|when|then)")
    dirs = tuple(root / adapter[key] for key in ("steps", "drivers") if key in adapter)
    return ScanRules(dirs, start, _patterns(table, "assert_patterns", path), _patterns(table, "sleep_patterns", path),
                     _patterns(table, "stub_patterns", path))


def _prefixes(table: dict, path: Path) -> tuple[str, ...]:
    values = table.get("scrub_env", [])
    if not isinstance(values, list) or not all(isinstance(v, str) and v for v in values):
        raise ConfigError(f"{path}: [adapters.run] scrub_env must be a list of variable name prefixes")
    return tuple(values)


def _run_rules(adapter: dict, path: Path) -> RunRules | None:
    table = adapter.get("run")
    if table is None:
        return None
    for key in ("by_tag", "report"):
        if not isinstance(table.get(key), str) or not table[key].strip():
            raise ConfigError(f"{path}: [adapters.run] needs {key}, the command words as one string")
    for key in ("shuffle", "isolated"):
        if not isinstance(table.get(key, ""), str):
            raise ConfigError(f"{path}: [adapters.run] {key} must be a string")
    timeout = table.get("timeout", 600)
    if isinstance(timeout, bool) or not isinstance(timeout, int) or timeout < 1:
        raise ConfigError(f"{path}: [adapters.run] timeout must be a whole number of seconds")
    classify = adapter.get("classify", {})
    return RunRules(str(adapter.get("name", "")), table["by_tag"], table["report"], table.get("shuffle", ""),
                    table.get("isolated", ""), timeout, _patterns(classify, "test_defect", path),
                    _patterns(classify, "expected_fail", path), _prefixes(table, path))


def _support(root: Path, data: dict, path: Path) -> tuple[tuple[Path, ...], tuple[str, ...]]:
    """(files, patterns): the plumbing files named by the adapters, and the patterns that also match files made later."""
    files: list[Path] = []
    patterns: list[str] = []
    for adapter in data.get("adapters", []):
        names = adapter.get("support", [])
        if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
            raise ConfigError(f"{path}: support must be a list of file names or patterns")
        for name in names:
            if "**" in name:
                raise ConfigError(f"{path}: support pattern {name!r}: ** is not supported; use one * per folder level")
            if any(c in name for c in "*?["):
                patterns.append(name)
                files += expand_pattern(root, name)
            else:
                files.append(root / name)
    return tuple(files), tuple(patterns)


def _python(data: dict, path: Path) -> str:
    value = data.get("python", "")
    if not isinstance(value, str):
        raise ConfigError(f"{path}: python must be the path of an interpreter")
    return value


def _schema_version(data: dict, path: Path) -> int:
    version = data.get("version", 1)
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise ConfigError(f"{path}: version must be a whole number from 1")
    if version > SCHEMA_VERSION:
        raise ConfigError(f"{path}: this project is at schema {version} but this greenlight understands up to "
                          f"{SCHEMA_VERSION}; upgrade greenlight (/plugin update greenlight)")
    return version


# Commands that must keep working whatever the project's version (hooks must never fail on it).
VERSION_EXEMPT = {"doctor", "guard", "tripwire", "migrate"}
VERSION_EXEMPT_FLAGS = {"approve": "--from-hook", "status": "--brief"}


def version_problem(command: str, args: list[str]) -> str | None:
    """Why this command may not run on the project around the current directory, or None."""
    if command in VERSION_EXEMPT or VERSION_EXEMPT_FLAGS.get(command) in args:
        return None
    root = find_root()
    if root is None:
        return None
    try:
        version = load(root).version
    except ConfigError as exc:
        return str(exc)
    if version < SCHEMA_VERSION:
        return (f"this project is at schema {version} but this greenlight writes schema {SCHEMA_VERSION}; "
                "run `bdd migrate` first")
    return None


def load(root: Path | str | None) -> Config:
    """Read ``<root>/.bdd/config.toml``. Without a root or file, every profile is enabled."""
    if root is None:
        return Config()
    root = Path(root)
    path = root / BDD_DIR / "config.toml"
    if not path.exists():
        return Config(root=root)
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path}: {exc}") from exc
    version = _schema_version(data, path)
    profiles = tuple(data.get("profiles", ALL_PROFILES))
    unknown = [p for p in profiles if p not in ALL_PROFILES]
    if unknown:
        raise ConfigError(f"{path}: unknown profile(s) {', '.join(unknown)}; choose from {', '.join(ALL_PROFILES)}")
    gates = data.get("gates", {})
    enforcement = data.get("enforcement", "auto")
    if enforcement not in ENFORCEMENT_MODES:
        raise ConfigError(f"{path}: enforcement must be one of {', '.join(ENFORCEMENT_MODES)}")
    return Config(
        root=root,
        profiles=profiles,
        near_duplicate_similarity=float(gates.get("near_duplicate_step_similarity", DEFAULT_SIMILARITY)),
        feature_dirs=tuple(root / a["features"] for a in data.get("adapters", []) if "features" in a),
        step_dirs=tuple(root / a[key] for a in data.get("adapters", []) for key in ("steps", "drivers") if key in a),
        test_dirs=tuple(root / a[key] for a in data.get("adapters", []) for key in ("features", "steps", "drivers")
                        if key in a) + _support(root, data, path)[0],
        autonomy=data.get("autonomy", "standard"),
        language=data.get("language", "auto"),
        allow_headless_approvals=bool(data.get("approvals", {}).get("allow_headless", False)),
        enforcement=enforcement,
        scans=tuple(r for r in (_scan_rules(root, a, path) for a in data.get("adapters", [])) if r),
        version=version,
        support_files=_support(root, data, path)[0],
        support_patterns=_support(root, data, path)[1],
        python=_python(data, path),
        runs=tuple(r for r in (_run_rules(a, path) for a in data.get("adapters", [])) if r),
    )
