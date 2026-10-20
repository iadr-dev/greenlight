"""`bdd trace FEAT-n`: the traceability matrix rule -> example -> scenario -> task, built from files alone.

Sources (each is optional, because a feature is traced while it is still being built):

* ``rules.md`` in the feature folder: lines that start with a rule id (``R-007.1``) or a
  non-functional requirement id (``N-007.1``), optionally after a list marker or heading marks;
* ``test-design.md``: lines that start with an example id (``EX-007.1.2``);
* the feature files tagged ``@FEAT-007``: scenarios carry ``@R-…`` and ``@EX-…`` tags;
* ``tasks.md``: a task starts at a line that begins with ``T-007.2``; the example ids mentioned up to
  the next task are the scenarios it owns.

A gap is a link that is missing or points at something that does not exist. Only artifacts that exist
are compared, so a feature that has no ``tasks.md`` yet is not reported as having unowned scenarios.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from . import featurefiles, gherkin, tagcheck

_LEAD = r"^\s*(?:[-*+]\s+|\d+[.)]\s+|#{1,6}\s+)?[*_`]*"
_TAIL = r"[*_`]*[\s:.\-–—]*(.*)$"
RULE_LINE = re.compile(_LEAD + r"([RN]-\d+\.\d+)" + _TAIL)
EXAMPLE_LINE = re.compile(_LEAD + r"(EX-\d+\.\d+\.\d+)" + _TAIL)
TASK_LINE = re.compile(_LEAD + r"(T-\d+\.\d+)" + _TAIL)
EXAMPLE_ID = re.compile(r"EX-\d+\.\d+\.\d+")


@dataclass
class Gap:
    code: str
    message: str


def read_ids(path: Path, pattern: re.Pattern) -> dict[str, str] | None:
    """{id: text} for the lines of ``path`` that start with an id, or None if the file does not exist."""
    if not path.is_file():
        return None
    found: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        match = pattern.match(line)
        if match:
            found.setdefault(match.group(1), match.group(2).strip())
    return found


def read_tasks(path: Path) -> dict[str, dict] | None:
    """{task id: {"title", "examples": [ids]}}; a task owns the example ids written up to the next task."""
    if not path.is_file():
        return None
    tasks: dict[str, dict] = {}
    current: dict | None = None
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        match = TASK_LINE.match(line)
        if match:
            current = tasks.setdefault(match.group(1), {"title": match.group(2).strip(), "examples": []})
        if current is not None:
            current["examples"] += [e for e in EXAMPLE_ID.findall(line) if e not in current["examples"]]
    return tasks


def scenario_rows(root: Path, files: list[Path]) -> tuple[list[dict], list[Gap]]:
    rows: list[dict] = []
    problems: list[Gap] = []
    for file in files:
        rel = file.relative_to(root).as_posix()
        try:
            feature = gherkin.parse(file.read_text(encoding="utf-8-sig"), rel)
        except gherkin.ParseError as exc:
            problems.append(Gap("T000", f"{rel}:{exc.line} cannot be read: {exc.message}"))
            continue
        for scenario, rule in feature.scenarios():
            tags = feature.effective_tags(scenario, rule)
            rule_tag = next((m.group(0)[1:] for m in map(tagcheck.RULE.fullmatch, tags) if m), None)
            example = next((m.group(0)[1:] for m in map(tagcheck.EXAMPLE.fullmatch, tags) if m), None)
            rows.append({"path": rel, "line": scenario.line, "name": scenario.name, "rule": rule_tag, "example": example})
    return rows, problems


def rule_of(example: str) -> str:
    feature, rule, _ = example[3:].split(".")
    return f"R-{feature}.{rule}"


def build(root: Path, feature_dir: Path, feature_id: str) -> dict:
    rules = read_ids(feature_dir / "rules.md", RULE_LINE)
    designed = read_ids(feature_dir / "test-design.md", EXAMPLE_LINE)
    tasks = read_tasks(feature_dir / "tasks.md")
    scenarios, gaps = scenario_rows(root, featurefiles.spec_files(root, feature_id))
    by_example: dict[str, list[dict]] = {}
    for row in scenarios:
        if row["example"]:
            by_example.setdefault(row["example"], []).append(row)
    owners: dict[str, list[str]] = {}
    for task_id, task in (tasks or {}).items():
        for example in task["examples"]:
            owners.setdefault(example, []).append(task_id)

    example_ids = sorted(set(designed or {}) | set(by_example), key=_sort_key)
    rule_ids = sorted(set(rules or {}) | {rule_of(e) for e in example_ids}, key=_sort_key)
    matrix = []
    for rule_id in rule_ids:
        examples = [{"id": e, "text": (designed or {}).get(e, ""), "scenarios": by_example.get(e, []),
                     "tasks": owners.get(e, [])} for e in example_ids if rule_of(e) == rule_id]
        matrix.append({"id": rule_id, "text": (rules or {}).get(rule_id, ""), "examples": examples})

    gaps += find_gaps(rules, designed, tasks, scenarios, by_example, owners, matrix)
    return {"feature": feature_id, "rules": matrix, "gaps": [vars(g) for g in gaps],
            "sources": {"rules.md": rules is not None, "test-design.md": designed is not None,
                        "tasks.md": tasks is not None, "scenarios": len(scenarios)},
            "totals": {"rules": len(matrix), "examples": len(example_ids), "scenarios": len(scenarios),
                       "tasks": len(tasks or {})}}


def _sort_key(identifier: str) -> tuple:
    prefix, numbers = identifier.split("-", 1)
    return (prefix, *(int(n) for n in numbers.split(".")))


def find_gaps(rules, designed, tasks, scenarios, by_example, owners, matrix) -> list[Gap]:
    gaps: list[Gap] = []
    traced = designed is not None or bool(scenarios)
    for rule in matrix:
        if rules is not None and rule["id"].startswith("R-") and rule["id"] not in rules:
            gaps.append(Gap("T004", f"{rule['id']} is used by examples or scenarios but is not in rules.md"))
        if traced and rules is not None and rule["id"] in rules and rule["id"].startswith("R-") and not rule["examples"]:
            gaps.append(Gap("T001", f"{rule['id']} has no example"))
        for example in rule["examples"]:
            if not example["scenarios"]:
                gaps.append(Gap("T002", f"{example['id']} has no scenario"))
            if designed is not None and example["id"] not in designed and example["scenarios"]:
                gaps.append(Gap("T003", f"{example['id']} is used by a scenario but is not in test-design.md"))
            if tasks is not None and example["scenarios"] and not example["tasks"]:
                gaps.append(Gap("T006", f"{example['id']} is not owned by any task"))
    known = {e["id"] for r in matrix for e in r["examples"]}
    for task_id, task in (tasks or {}).items():
        gaps += [Gap("T005", f"{task_id} names {e}, which is not a known example") for e in task["examples"] if e not in known]
    for row in scenarios:
        if row["example"] is None:
            gaps.append(Gap("T007", f"{row['path']}:{row['line']} scenario \"{row['name']}\" has no @EX tag"))
    return gaps


def render(report: dict) -> str:
    lines = [f"# Traceability: {report['feature']}", "", "| Rule | Example | Scenario | Task |", "|---|---|---|---|"]
    for rule in report["rules"]:
        label = f"{rule['id']} {rule['text']}".strip()
        if not rule["examples"]:
            lines.append(f"| {label} | | | |")
        for example in rule["examples"]:
            scenarios = "<br>".join(f"{s['path']}:{s['line']} {s['name']}" for s in example["scenarios"]) or ""
            named = f"{example['id']} {example['text']}".strip()
            lines.append(f"| {label} | {named} | {scenarios} | {', '.join(example['tasks'])} |")
            label = ""
    totals = report["totals"]
    lines += ["", f"{totals['rules']} rule(s), {totals['examples']} example(s), {totals['scenarios']} scenario(s), "
                  f"{totals['tasks']} task(s)."]
    if report["gaps"]:
        lines += ["", "Gaps:"] + [f"- {g['code']} {g['message']}" for g in report["gaps"]]
    else:
        lines += ["No gaps."]
    return "\n".join(lines)
