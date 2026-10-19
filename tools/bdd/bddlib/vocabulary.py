"""Step vocabulary: the core instruction set plus a project's domain steps.

A *pattern* is step text with typed placeholders, e.g. ``{actor} has a cart worth {amount:int}``.
It is compiled to a regular expression and matched against whole step lines. Core
instructions live in ``vocabulary/core.json`` (plugin-owned); domain steps live in the
project's ``.bdd/vocabulary.toml`` and compose core instructions.
"""
from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[3]
CORE_FILE = PLUGIN_ROOT / "vocabulary" / "core.json"

KINDS = ("given", "when", "then")
PROFILES = ("base", "api", "ui", "cli", "lib")
REQUIRES = ("none", "table", "docstring", "table_or_docstring", "table_or_docstring_optional")

# Full-width punctuation is normalised to ASCII on both the pattern and the step text, so a
# zh-TW author may type either form of the colon or comma.
_FULLWIDTH = str.maketrans({"：": ":", "，": ",", "（": "(", "）": ")",
                            "；": ";", "！": "!", "？": "?"})

_OUTLINE_PARAM = r"<[^<>]+>"
_TYPE_REGEX = {
    "int": r"-?\d+",
    "decimal": r"-?\d+(?:\.\d+)?",
    "string": r'"[^"]*"',
    "name": r'"[^"]+"|[^\s":]+(?: [^\s":]+)*?',
    "datetime": r'"?\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:?\d{2})?)?"?',
    "duration": r"\d+(?:\.\d+)? ?(?:ms|milliseconds?|s|secs?|seconds?|m|mins?|minutes?|h|hours?|d|days?|w|weeks?)",
    "bool": r"true|false|yes|no|on|off",
}
_PLACEHOLDER = re.compile(r"\{([A-Za-z_]\w*)(?::(enum\([^)]*\)|[A-Za-z]+))?\}")


class VocabularyError(ValueError):
    pass


def normalize(text: str) -> str:
    return " ".join(text.translate(_FULLWIDTH).split())


@dataclass(frozen=True)
class Param:
    name: str
    type: str  # int | decimal | string | name | datetime | duration | bool | enum(a,b)


@dataclass(frozen=True)
class Pattern:
    text: str
    regex: re.Pattern
    params: tuple[Param, ...]

    def match(self, step_text: str) -> dict[str, str] | None:
        m = self.regex.fullmatch(normalize(step_text))
        if not m:
            return None
        return {p.name: (v[1:-1] if p.type == "string" and v.startswith('"') else v)
                for p, v in zip(self.params, m.groups())}


def _literal(chunk: str) -> str:
    """Regex for fixed text between placeholders: words are escaped, any run of spaces matches."""
    return r"\s+".join(re.escape(word) for word in chunk.split(" "))


def compile_pattern(text: str) -> Pattern:
    """Compile ``text`` to a Pattern. Raises VocabularyError for unknown types/duplicate names."""
    norm = normalize(text)
    pieces, params, pos = [], [], 0
    for m in _PLACEHOLDER.finditer(norm):
        pieces.append(_literal(norm[pos:m.start()]))
        name = m.group(1)
        # An untyped placeholder is a logical name, unless it is itself a type name: {duration}.
        ptype = m.group(2) or (name if name in _TYPE_REGEX else "name")
        if any(p.name == name for p in params):
            raise VocabularyError(f"pattern {text!r}: parameter {{{name}}} appears twice")
        if ptype.startswith("enum("):
            options = [o.strip() for o in ptype[5:-1].split(",") if o.strip()]
            if not options:
                raise VocabularyError(f"pattern {text!r}: enum for {{{name}}} has no values")
            body = "|".join(re.escape(o) for o in options)
        elif ptype in _TYPE_REGEX:
            body = _TYPE_REGEX[ptype]
        else:
            raise VocabularyError(f"pattern {text!r}: unknown parameter type {ptype!r} for {{{name}}}")
        pieces.append(f"((?:{body})|{_OUTLINE_PARAM})")
        params.append(Param(name, ptype))
        pos = m.end()
    pieces.append(_literal(norm[pos:]))
    if "{" in norm[pos:] or "}" in norm[pos:]:
        raise VocabularyError(f"pattern {text!r}: malformed placeholder")
    regex = re.compile("".join(pieces), re.IGNORECASE)
    return Pattern(text, regex, tuple(params))


@dataclass(frozen=True)
class Entry:
    id: str
    kind: str
    source: str                       # core | project
    patterns: dict[str, tuple[Pattern, ...]]   # language -> patterns; "*" = any language
    profiles: tuple[str, ...] = ()
    requires: str = "none"
    composes: tuple[str, ...] = ()
    description: str = ""
    justification: str = ""
    owner: str = ""
    maps_to: dict = field(default_factory=dict)

    def candidates(self, language: str) -> tuple[Pattern, ...]:
        """Patterns to try for a feature written in ``language`` (its own, plus English / any-language)."""
        seen, out = set(), []
        for key in (language, "en", "*"):
            for p in self.patterns.get(key, ()):
                if p.text not in seen:
                    seen.add(p.text)
                    out.append(p)
        return tuple(out)


@dataclass(frozen=True)
class Match:
    entry: Entry
    pattern: Pattern
    params: dict[str, str]


class Vocabulary:
    def __init__(self, entries: list[Entry]):
        ids = [e.id for e in entries]
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        if dupes:
            raise VocabularyError(f"duplicate vocabulary ids: {', '.join(dupes)}")
        self.entries = entries
        self.by_id = {e.id: e for e in entries}

    def resolve(self, kind: str, text: str, language: str = "en") -> list[Match]:
        """All entries whose pattern matches ``text``. One match per entry (its first matching
        pattern wins). More than one result means the step is ambiguous."""
        found = []
        for entry in self.entries:
            if entry.kind != kind:
                continue
            for pattern in entry.candidates(language):
                params = pattern.match(text)
                if params is not None:
                    found.append(Match(entry, pattern, params))
                    break
        return found


def _patterns(raw, where: str) -> tuple[Pattern, ...]:
    if not isinstance(raw, list) or not raw or not all(isinstance(x, str) for x in raw):
        raise VocabularyError(f"{where}: patterns must be a non-empty list of strings")
    return tuple(compile_pattern(x) for x in raw)


def load_core(path: Path | str = CORE_FILE) -> list[Entry]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    entries = []
    for raw in data["instructions"]:
        where = raw.get("id", "<no id>")
        if raw.get("kind") not in KINDS:
            raise VocabularyError(f"{where}: kind must be one of {KINDS}")
        if raw.get("requires", "none") not in REQUIRES:
            raise VocabularyError(f"{where}: unknown requires {raw.get('requires')!r}")
        profiles = tuple(raw.get("profiles", ()))
        if not profiles or any(p not in PROFILES for p in profiles):
            raise VocabularyError(f"{where}: profiles must be a non-empty subset of {PROFILES}")
        patterns = {"en": _patterns(raw["patterns"], where)}
        for lang, texts in (raw.get("i18n") or {}).items():
            patterns[lang] = _patterns(texts, f"{where} [{lang}]")
        entries.append(Entry(raw["id"], raw["kind"], "core", patterns, profiles,
                             raw.get("requires", "none"), description=raw.get("semantics", "")))
    return entries


def load_project(path: Path | str, core_ids: set[str] | None = None) -> list[Entry]:
    """Read a project's ``vocabulary.toml``. ``core_ids`` (if given) validates ``composes``."""
    data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("extends", "core") != "core":
        raise VocabularyError("vocabulary.toml: 'extends' must be \"core\"")
    entries = []
    for raw in data.get("steps", []):
        where = raw.get("id", "<no id>")
        if not str(raw.get("id", "")).startswith("D."):
            raise VocabularyError(f"{where}: domain step ids must start with 'D.'")
        if raw.get("kind") not in KINDS:
            raise VocabularyError(f"{where}: kind must be one of {KINDS}")
        texts = raw.get("patterns") or ([raw["pattern"]] if "pattern" in raw else None)
        composes = tuple(raw.get("composes", ()))
        if core_ids is not None:
            unknown = [c for c in composes if c not in core_ids]
            if unknown:
                raise VocabularyError(f"{where}: composes unknown core instruction(s) {', '.join(unknown)}")
        entries.append(Entry(raw["id"], raw["kind"], "project", {"*": _patterns(texts, where)},
                             requires=raw.get("requires", "table_or_docstring_optional"), composes=composes,
                             description=raw.get("description", ""), justification=raw.get("justification", ""),
                             owner=raw.get("owner", ""), maps_to=dict(raw.get("maps_to", {}))))
    return entries


def load(project_file: Path | str | None = None) -> Vocabulary:
    core = load_core()
    project = load_project(project_file, {e.id for e in core}) if project_file and Path(project_file).exists() else []
    return Vocabulary(core + project)
