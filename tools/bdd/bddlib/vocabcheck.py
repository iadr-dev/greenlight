"""Checks on a project's own domain steps (``.bdd/vocabulary.toml``).

    L004 error  a pattern mentions an implementation detail (URL, SQL, selector, ...)
    L010 error  a pattern is nearly identical to another one and has no ``justification``
    L012 error  a domain step does not compose core instructions properly
"""
from __future__ import annotations

import re
from pathlib import Path

from . import denylist
from .issues import ERROR, Issue
from .vocabulary import Entry, Vocabulary

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


def check_near_duplicates(entries: list[Entry], threshold: float, path: str, source: str) -> list[Issue]:
    issues = []
    for i, a in enumerate(entries):
        for b in entries[i + 1:]:
            if a.kind != b.kind or (a.source == "core" and b.source == "core"):
                continue
            unjustified = [e for e in (a, b) if e.source == "project" and not e.justification]
            if not unjustified:
                continue
            best = max(((similarity(pa.text, pb.text), pa.text, pb.text)
                        for pa in _own_patterns(a) for pb in _own_patterns(b)), default=None)
            if best and best[0] >= threshold:
                target = unjustified[-1]      # the later definition is the duplicate
                issues.append(Issue(path, locate(source, target.id), ERROR, "L010",
                                    f'{a.id} "{best[1]}" and {b.id} "{best[2]}" are nearly identical '
                                    f"(similarity {best[0]:.2f} >= {threshold:.2f}): reuse one, "
                                    f"or give {target.id} a `justification`"))
    return issues


def check_vocabulary(vocab: Vocabulary, profiles: tuple[str, ...], threshold: float,
                     path: Path | str, source: str) -> list[Issue]:
    """All findings for the project's domain steps. ``source`` is the file text (for line numbers)."""
    path = str(path)
    issues: list[Issue] = []
    enabled = set(profiles)
    for entry in (e for e in vocab.entries if e.source == "project"):
        line = locate(source, entry.id)
        issues += check_details(entry, path, line)
        issues += check_composition(entry, vocab, enabled, path, line)
    issues += check_near_duplicates(vocab.entries, threshold, path, source)
    return sorted(issues, key=lambda i: (i.line, i.code))
