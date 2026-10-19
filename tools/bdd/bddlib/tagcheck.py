"""Trace tags: the join key between rules, examples, scenarios, tasks and reports.

    @FEAT-007            on the Feature
    @R-007.3             on each Rule (or on the scenario when there are no Rule blocks)
    @EX-007.3.2          on each scenario / outline: one example per scenario

L005 reports a missing, malformed, repeated or inconsistent tag; L006 a repeated example id.
"""
from __future__ import annotations

import re
from collections import defaultdict

from . import gherkin
from .issues import ERROR, Issue

FEAT = re.compile(r"@FEAT-(\d+)")
RULE = re.compile(r"@R-(\d+)\.(\d+)")
EXAMPLE = re.compile(r"@EX-(\d+)\.(\d+)\.(\d+)")
_LOOKS_LIKE_TRACE = re.compile(r"@(?:FEAT|R|EX)-\S*")
_KINDS = {"FEAT": FEAT, "R": RULE, "EX": EXAMPLE}
_EXPECTED = {"FEAT": "@FEAT-<n>", "R": "@R-<feature>.<n>", "EX": "@EX-<feature>.<rule>.<n>"}


def _kind_of(tag: str) -> str:
    return tag[1:].split("-", 1)[0]


def split_tags(tags: list[str], path: str, line: int) -> tuple[dict[str, list[re.Match]], list[Issue]]:
    """Group trace tags by kind; report ones that look like trace tags but are malformed."""
    groups: dict[str, list[re.Match]] = defaultdict(list)
    problems = []
    for tag in tags:
        if not _LOOKS_LIKE_TRACE.fullmatch(tag):
            continue
        kind = _kind_of(tag)
        match = _KINDS[kind].fullmatch(tag)
        if match:
            groups[kind].append(match)
        else:
            problems.append(Issue(path, line, ERROR, "L005", f"malformed trace tag {tag} (expected {_EXPECTED[kind]})"))
    return groups, problems


def _exactly_one(groups, kind: str, where: str, path: str, line: int) -> tuple[re.Match | None, list[Issue]]:
    found = groups.get(kind, [])
    if len(found) == 1:
        return found[0], []
    problem = "missing" if not found else f"repeated ({', '.join(m.group(0) for m in found)})"
    return None, [Issue(path, line, ERROR, "L005", f"{where} needs exactly one {_EXPECTED[kind]} tag: {problem}")]


def check_trace_tags(feature: gherkin.Feature, path: str) -> list[Issue]:
    issues: list[Issue] = []
    groups, problems = split_tags(feature.tags, path, feature.line)
    issues += problems
    feat, found = _exactly_one(groups, "FEAT", "the Feature", path, feature.line)
    issues += found
    for scenario, rule in feature.scenarios():
        issues += check_scenario(feature, scenario, rule, feat, path)
    issues += check_rules(feature, feat, path)
    return issues + duplicate_examples(feature, path)


def check_rules(feature: gherkin.Feature, feat: re.Match | None, path: str) -> list[Issue]:
    issues = []
    for rule in (c for c in feature.children if isinstance(c, gherkin.Rule)):
        groups, problems = split_tags(rule.tags, path, rule.line)
        rule_tag, found = _exactly_one(groups, "R", f'Rule "{rule.name}"', path, rule.line)
        issues += problems + found
        if rule_tag and feat and rule_tag.group(1) != feat.group(1):
            issues.append(Issue(path, rule.line, ERROR, "L005",
                                f"{rule_tag.group(0)} belongs to feature {rule_tag.group(1)}, not {feat.group(1)}"))
    return issues


def check_scenario(feature: gherkin.Feature, scenario: gherkin.Scenario, rule: gherkin.Rule | None,
                   feat: re.Match | None, path: str) -> list[Issue]:
    groups, _inherited_problems = split_tags(feature.effective_tags(scenario, rule), path, scenario.line)
    own = scenario.tags + [t for ex in scenario.examples for t in ex.tags]
    issues = split_tags(own, path, scenario.line)[1]      # malformed tags are reported where they are written
    where = f'Scenario "{scenario.name}"'
    rule_tag, found = _exactly_one(groups, "R", where, path, scenario.line)
    issues += found
    example, found = _exactly_one(groups, "EX", where, path, scenario.line)
    issues += found
    if example and feat and example.group(1) != feat.group(1):
        issues.append(Issue(path, scenario.line, ERROR, "L005",
                            f"{example.group(0)} belongs to feature {example.group(1)}, not {feat.group(1)}"))
    if example and rule_tag and example.group(1, 2) != rule_tag.group(1, 2):
        issues.append(Issue(path, scenario.line, ERROR, "L005",
                            f"{example.group(0)} does not belong to {rule_tag.group(0)}"))
    return issues


def duplicate_examples(feature: gherkin.Feature, path: str) -> list[Issue]:
    seen: dict[str, str] = {}
    issues = []
    for scenario, _rule in feature.scenarios():
        for match in (EXAMPLE.fullmatch(t) for t in scenario.tags):
            if not match:
                continue
            tag = match.group(0)
            if tag in seen:
                issues.append(Issue(path, scenario.line, ERROR, "L006",
                                    f'{tag} is already used by Scenario "{seen[tag]}"; every scenario needs its own example id'))
            else:
                seen[tag] = scenario.name
    return issues
