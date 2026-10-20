"""Checks on a project's own domain steps (``.bdd/vocabulary.toml``).

    L004 error  a pattern mentions an implementation detail (URL, SQL, selector, ...)
    L010 error  a pattern is nearly identical to another one and has no ``justification``
    L012 error  a domain step does not compose core instructions properly
    L014 error  two project or shared steps define the very same pattern, so a step matching it is ambiguous
"""
from __future__ import annotations

import re
from pathlib import Path

from . import denylist
from .issues import ERROR, Issue
from .vocabulary import Entry, Vocabulary, normalize

_WORD = re.compile(r"[^\W\d_]+|\d+|\{\}", re.UNICODE)
_PLACEHOLDER = re.compile(r"\{[^{}]*\}")


def pattern_tokens(pattern_text: str) -> frozenset[str]:
    """Word set of a pattern with every placeholder reduced to one ``{}`` token."""
    return frozenset(w.lower() for w in _WORD.findall(_PLACEHOLDER.sub("{}", pattern_text)))


def similarity(a: str, b: str) -> float:
    ta, tb = pattern_tokens(a), pattern_tokens(b)
    return len(ta & tb) / len(ta | tb) if ta | tb else 0.0


def locate(source: str, entry_id: str) -> int:
    """1-based line of ``id = "<entry_id>"`` in the vocabulary file (1 if not found)."""
    needle = re.compile(r'^\s*id\s*=\s*["\']' + re.escape(entry_id) + r'["\']')
    for number, line in enumerate(source.splitlines(), start=1):
        if needle.match(line):
            return number
    return 1


def _own_patterns(entry: Entry):
    return [p for patterns in entry.patterns.values() for p in patterns]


def check_details(entry: Entry, path: str, line: int) -> list[Issue]:
    return [Issue(path, line, ERROR, "L004",
                  f'{entry.id} pattern "{p.text}" mentions an implementation detail '
                  f'({category}: "{snippet}"); describe the behaviour in business terms')
            for p in _own_patterns(entry) for category, snippet in denylist.implementation_details(p.text)]


def check_composition(entry: Entry, vocab: Vocabulary, profiles: set[str], path: str, line: int) -> list[Issue]:
    def bad(message: str) -> Issue:
        return Issue(path, line, ERROR, "L012", f"{entry.id}: {message}")

    if not entry.composes:
        return [bad("a domain step must list the core instructions it composes (`composes = [...]`)")]
    composed = [vocab.by_id[c] for c in entry.composes if c in vocab.by_id]
    issues = [bad(f"composes {c.id}, whose profile(s) {'/'.join(c.profiles)} are not enabled")
              for c in composed if c.source == "core" and not profiles.intersection(c.profiles)]
    if entry.kind in ("when", "then") and not any(c.kind == entry.kind for c in composed):
        verb = "act" if entry.kind == "when" else "assert"
        issues.append(bad(f"a `{entry.kind}` step must compose at least one `{entry.kind}` core instruction "
                          f"so that it really does {verb} (a step that only arranges proves nothing)"))
    return issues


def where(entry: Entry, path: str, texts: dict[str, str]) -> tuple[str, int]:
    """The file an entry was read from and the line it starts on."""
    file = entry.origin or path
    return file, locate(texts.get(file, ""), entry.id)


def to_report(candidates: list[Entry], path: str) -> Entry:
    """The duplicate to report: the one in the project's own file, which its owner can change, else the later one."""
    own = [e for e in candidates if (e.origin or path) == path]
    return (own or candidates)[-1]


def exact_duplicates(a: Entry, b: Entry) -> list[str]:
    """Pattern texts that ``a`` and ``b`` both define, compared as the lint compares steps."""
    mine = {normalize(p.text).casefold() for p in _own_patterns(a)}
    return sorted(mine & {normalize(p.text).casefold() for p in _own_patterns(b)})


def check_exact_duplicates(entries: list[Entry], path: str, texts: dict[str, str]) -> list[Issue]:
    issues = []
    project = [e for e in entries if e.source == "project"]
    for i, a in enumerate(project):
        for b in project[i + 1:]:
            if a.kind != b.kind:
                continue
            for text in exact_duplicates(a, b):
                target = to_report([a, b], path)
                other = a if target is b else b
                file, line = where(target, path, texts)
                issues.append(Issue(file, line, ERROR, "L014",
                                    f'{target.id} and {other.id} ({where(other, path, texts)[0]}) define the same pattern '
                                    f'"{text}": a step that matches it is ambiguous; keep one definition'))
    return issues


def near_duplicate(a: Entry, b: Entry, threshold: float, path: str, texts: dict[str, str]) -> Issue | None:
    """L010 for one pair of entries, or None when the pair is fine (or is reported as an exact duplicate)."""
    if a.kind != b.kind or (a.source == "core" and b.source == "core"):
        return None
    if a.source == b.source == "project" and exact_duplicates(a, b):
        return None                                              # reported as L014
    unjustified = [e for e in (a, b) if e.source == "project" and not e.justification]
    if not unjustified:
        return None
    best = max(((similarity(pa.text, pb.text), pa.text, pb.text)
                for pa in _own_patterns(a) for pb in _own_patterns(b)), default=None)
    if not best or best[0] < threshold:
        return None
    target = to_report(unjustified, path)
    file, line = where(target, path, texts)
    return Issue(file, line, ERROR, "L010",
                 f'{a.id} "{best[1]}" and {b.id} "{best[2]}" are nearly identical '
                 f"(similarity {best[0]:.2f} >= {threshold:.2f}): reuse one, or give {target.id} a `justification`")


def check_near_duplicates(entries: list[Entry], threshold: float, path: str, source: str,
                          texts: dict[str, str] | None = None) -> list[Issue]:
    texts = {path: source, **(texts or {})}
    found = (near_duplicate(a, b, threshold, path, texts) for i, a in enumerate(entries) for b in entries[i + 1:])
    return [issue for issue in found if issue]


def check_vocabulary(vocab: Vocabulary, profiles: tuple[str, ...], threshold: float,
                     path: Path | str, source: str, shared_texts: dict[str, str] | None = None) -> list[Issue]:
    """All findings for the project's domain steps and the shared ones. ``source`` is the project file's text and
    ``shared_texts`` the text of each included file by path (both for line numbers)."""
    path = str(path)
    texts = {path: source, **(shared_texts or {})}
    issues: list[Issue] = []
    enabled = set(profiles)
    for entry in (e for e in vocab.entries if e.source == "project"):
        file, line = where(entry, path, texts)
        issues += check_details(entry, file, line)
        issues += check_composition(entry, vocab, enabled, file, line)
    issues += check_exact_duplicates(vocab.entries, path, texts)
    issues += check_near_duplicates(vocab.entries, threshold, path, source, texts)
    return sorted(issues, key=lambda i: (i.path, i.line, i.code))
