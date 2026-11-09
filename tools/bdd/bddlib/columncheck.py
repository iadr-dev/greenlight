"""L026: the exact record tables of one entity in a feature use one column set.

``the {entity} records are:`` compares the whole record set, and a driver reads an entity as one record shape. When
two such tables of one entity have different columns, at least one of them can never pass (Fieldly's CR-001.2 and
CR-002.1 each cost a reopened approval). The cases the check leaves alone:

* a table with no rows (it passes with any shape);
* ``the {entity} records include:`` (a partial check by design);
* the seeding table, which the test-data card asks to hold only the columns that matter to the rule;
* a table whose header holds an Examples ``<parameter>``.

A project whose driver reads only the columns a table lists (Fieldly's work orders: a projection set before each step)
has no such limit; it says so, per entity or for all, in ``.bdd/config.toml`` (``[lint] projected_records = ["work
order"]`` or ``["*"]``). Without that, the way out is one column set with an empty cell for an absent value,
``records include:``, or a second entity for the extra columns. An error cannot be silenced in ``[lint] ignore``.
"""
from __future__ import annotations

import re
from collections import Counter

from . import gherkin, vocabulary
from .issues import ERROR, Issue

VERIFY = "C.ENTITY.VERIFY"
CODE = "L026"
_EXAMPLE = re.compile(r"@(EX-\d+\.\d+\.\d+)")
_PARAMETER = re.compile(r"<[^<>]+>")


def _is_exact(match: vocabulary.Match) -> bool:
    """The first pattern of an entry, in any language, is the exact comparison (``are``); the next ones are subsets."""
    return any(match.pattern in patterns and patterns.index(match.pattern) == 0 for patterns in match.entry.patterns.values())


def _tables(feature: gherkin.Feature, vocab: vocabulary.Vocabulary) -> dict[str, list[tuple[str, int, list[str]]]]:
    """{entity: [(where, line, columns as written)]} for every non-empty exact record table, in file order."""
    found: dict[str, list[tuple[str, int, list[str]]]] = {}
    groups = [("the Background", feature.background.steps if feature.background else [])]
    for scenario, rule in feature.scenarios():
        tag = next((m.group(1) for t in feature.effective_tags(scenario, rule) if (m := _EXAMPLE.fullmatch(t))), None)
        groups.append((tag or f'"{scenario.name}"', scenario.steps))
    for where, steps in groups:
        for step in steps:
            if step.kind != "then" or not step.table or len(step.table) < 2:
                continue
            matches = vocab.resolve(step.kind, step.text, feature.language)
            if len(matches) != 1 or matches[0].entry.id != VERIFY or not _is_exact(matches[0]):
                continue
            entity, header = matches[0].params.get("entity", "").strip(), [cell.strip() for cell in step.table[0]]
            if entity and not _PARAMETER.search(entity) and not any(_PARAMETER.search(cell) for cell in header):
                found.setdefault(" ".join(entity.casefold().split()), []).append((where, step.line, header))
    return found


def check_feature(feature: gherkin.Feature, vocab: vocabulary.Vocabulary, path: str,
                  projected: frozenset[str] = frozenset()) -> list[Issue]:
    issues: list[Issue] = []
    if "*" in projected:
        return issues
    for entity, tables in _tables(feature, vocab).items():
        if entity in projected:
            continue
        sets = [frozenset(c.casefold() for c in header) for _, _, header in tables]
        if len(set(sets)) < 2:
            continue
        usual = Counter(sets).most_common(1)[0][0]
        first = next(table for table, columns in zip(tables, sets) if columns == usual)
        reported: set[frozenset[str]] = set()
        for (where, line, header), columns in zip(tables, sets):
            if columns == usual or columns in reported:
                continue
            reported.add(columns)
            issues.append(Issue(path, line, ERROR, CODE,
                                f'{where}: {entity} table has columns {", ".join(header)}; {first[0]} has {", ".join(first[2])}; '
                                'check one column set per entity (an empty cell stands for a value that is absent; '
                                '"records include:" accepts a part of a record). If the driver of this entity reads only the '
                                f'columns a table lists, say so: [lint] projected_records = ["{entity}"] in .bdd/config.toml'))
    return issues
