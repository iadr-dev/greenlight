"""Turning Gherkin tables and doc strings into data, and comparing data the way the instructions say."""
from __future__ import annotations

import json
import re
from typing import Any


def parse_value(text: str) -> Any:
    """A cell or doc string as data: JSON when it parses (numbers, true, null, lists, objects), else the text."""
    text = text.strip()
    try:
        return json.loads(text)
    except ValueError:
        return text


def rows(table: list[list[str]] | None) -> list[dict[str, Any]]:
    """A table with a header row as a list of dicts."""
    if not table:
        return []
    header, *body = table
    return [{name: parse_value(cell) for name, cell in zip(header, row)} for row in body]


def payload(table: list[list[str]] | None, docstring: str | None) -> Any:
    """The data a step carries: a doc string as JSON or text, or a table (one row becomes an object)."""
    if docstring is not None:
        return parse_value(docstring)
    found = rows(table)
    return found[0] if len(found) == 1 else found


def sort_key(row: Any) -> str:
    """A stable order for comparing record sets, where the order does not matter."""
    return json.dumps(row, sort_keys=True, default=str)


def normalise_text(text: str) -> str:
    """Line endings and surrounding whitespace do not matter; blank lines do not either."""
    return "\n".join(line.rstrip() for line in text.replace("\r\n", "\n").strip().split("\n") if line.strip())


def assert_equal(actual: Any, expected: Any, what: str) -> None:
    assert actual == expected, f"{what}: expected {expected!r} but got {actual!r}"


def assert_subset(actual: Any, expected: Any, what: str) -> None:
    """Every field of ``expected`` is in ``actual`` (recursively); lists must contain each expected item."""
    problem = subset_problem(actual, expected, "")
    assert problem is None, f"{what}: {problem} (actual: {actual!r})"


def subset_problem(actual: Any, expected: Any, path: str) -> str | None:
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return f"{path or 'value'} should be an object"
        for key, value in expected.items():
            if key not in actual:
                return f"{path + '.' if path else ''}{key} is missing"
            problem = subset_problem(actual[key], value, f"{path + '.' if path else ''}{key}")
            if problem:
                return problem
        return None
    if isinstance(expected, list):
        if not isinstance(actual, list):
            return f"{path or 'value'} should be a list"
        for item in expected:
            if not any(subset_problem(candidate, item, path) is None for candidate in actual):
                return f"{path or 'value'} has no item matching {item!r}"
        return None
    return None if actual == expected else f"{path or 'value'} is {actual!r}, expected {expected!r}"


def assert_text_contains(actual: str, expected: str, what: str) -> None:
    wanted, got = normalise_text(expected), normalise_text(actual)
    assert wanted in got, f"{what} does not contain {wanted!r}; it is {got!r}"


_DURATION = re.compile(r"(\d+(?:\.\d+)?)\s*(seconds?|secs?|s|minutes?|mins?|m|hours?|hrs?|h|days?|d|weeks?|w)\b", re.IGNORECASE)
_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}


def duration_seconds(text: str) -> float:
    """'2 days', '30 minutes', '1h 30m' as seconds."""
    found = _DURATION.findall(text)
    assert found and not _DURATION.sub("", text).strip(" ,and"), f"cannot read the duration {text!r}"
    return sum(float(number) * _SECONDS[unit[0].lower()] for number, unit in found)
