"""Implementation details that must not appear in business-readable steps.

Features and domain-step patterns describe behaviour. URLs, HTTP verbs and status codes,
SQL, selectors, code calls and class names belong in drivers and the system map. Text inside
double quotes is data (a value the scenario uses) and is not inspected. ``<outline>``
parameters and ``{placeholders}`` are not matched by any rule below.
"""
from __future__ import annotations

import re

_QUOTED = re.compile(r'"[^"]*"')

_RULES: tuple[tuple[str, re.Pattern], ...] = (
    ("URL", re.compile(r"https?://|\bwww\.", re.IGNORECASE)),
    ("HTTP verb with a path", re.compile(r"\b(?:GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+/")),
    ("URL path", re.compile(r"(?<![\w/])/[A-Za-z][\w-]*(?:/[\w{}:.-]+)+")),
    ("HTTP status code", re.compile(r"\bHTTP\s*\d{3}\b|\bstatus(?:\s+code)?\s+[1-5]\d{2}\b", re.IGNORECASE)),
    ("SQL", re.compile(r"\b(?:SELECT\s.+\sFROM|INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM|"
                       r"DROP\s+TABLE|CREATE\s+TABLE|ALTER\s+TABLE)\b")),
    ("CSS or DOM selector", re.compile(r"(?<![\w&])#[A-Za-z][\w-]*|\bdata-testid\b|\bquerySelector\w*|"
                                       r"\bgetBy[A-Z]\w*|\bxpath\b|\bcss=|\bclass(?:Name)?=", re.IGNORECASE)),
    ("HTML markup", re.compile(r"</(?:div|span|button|input|form|table|ul|li|a|p)>|"
                               r"<(?:div|span|button|input|form|table)\b[^>]*\s\w+=")),
    ("code call", re.compile(r"\b[A-Za-z_]\w*\.[A-Za-z_]\w*\(|\.(?:click|fill|type|submit|get|post)\(")),
    ("class name", re.compile(r"\b[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]+)*"
                              r"(?:Controller|Service|Repository|Impl|Handler|Manager|Factory|Dao|Mapper)\b")),
)


def implementation_details(text: str) -> list[tuple[str, str]]:
    """Return ``(category, matched text)`` for every implementation detail found in ``text``."""
    scrubbed = _QUOTED.sub('""', text)
    found = []
    for category, rule in _RULES:
        match = rule.search(scrubbed)
        if match:
            found.append((category, match.group(0).strip()))
    return found
