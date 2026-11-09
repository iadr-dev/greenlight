"""What the person is asked to approve, in plain words, and what changed since they last approved it.

An approval of the rules or the examples covers whole files, and a feature file can be two thousand lines long. This
module reads the same files into *items* (a rule, a scenario) and keeps one small record of them with each approval:

    {"R-007.1": {"text": "Orders of 1000 or more get 10% off.", "parts": {"why": "9f2c..."}},
     "EX-007.1.1": {"text": "Order of 1000", "rule": "R-007.1", "parts": {"steps": "a41b..."}}}

``text`` is the rule's statement or the scenario's title as the author wrote it, in the feature's own language. A part
is a hash of one more piece of the item, so a change to it is seen without keeping its text. Comparing the record of the
last approval with the files now gives the items added, removed and changed; ``render`` prints them. Reading is all
this module does: it never writes a record.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from . import featurefiles
from .errors import UsageError

NOUN = {"rules": ("rule", "rules"), "examples": ("scenario", "scenarios")}
BULLET = re.compile(r"^\s*[-*+]\s+([^:]{1,40}):\s*(.*)$")
HEADING = re.compile(r"^\s*#{1,6}\s")
LABEL = {"rules": "statement", "examples": "title"}


def digest(lines: list[str]) -> str:
    text = "\n".join(" ".join(line.split()) for line in lines)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _item(text: str, parts: dict[str, list[str]], detail: list[str], rule: str | None = None) -> dict:
    item = {"text": " ".join(text.split()), "parts": {name: digest(lines) for name, lines in parts.items()}, "detail": detail}
    if rule:
        item["rule"] = rule
    return item


# -- reading the files into items ------------------------------------------------------------
def rule_items(path: Path) -> dict[str, dict]:
    """The rules of ``rules.md``: the line that starts with the id, and the ``- Why:`` style lines under it."""
    from . import trace

    found: dict[str, dict] = {}
    current: dict | None = None
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        match = trace.RULE_LINE.match(line)
        if match:
            current = {"id": match.group(1), "text": match.group(2).strip(), "parts": {}, "detail": []}
            found.setdefault(current["id"], current)
        elif current is None or HEADING.match(line):
            current = None
        elif bullet := BULLET.match(line):
            label, value = bullet.group(1).strip(), bullet.group(2).strip()
            current["parts"][label.lower()] = [value]
            current["detail"].append(f"{label}: {value}")
    return {key: _item(item["text"], item["parts"], item["detail"]) for key, item in found.items()}


def step_lines(steps: list) -> list[str]:
    lines: list[str] = []
    for step in steps:
        lines.append(f"{step.keyword.strip()} {step.text}".strip())
        lines += ["| " + " | ".join(row) + " |" for row in step.table or []]
        lines += (step.docstring or "").splitlines()
    return lines


def tag_of(tags: list[str], pattern: re.Pattern[str]) -> str | None:
    return next((tag[1:] for tag in tags if pattern.fullmatch(tag)), None)


def scenario_items(files: list[Path]) -> dict[str, dict]:
    """The scenarios of the feature files by their ``@EX-`` tag (by title when there is none), and each Background."""
    from . import gherkin, tagcheck

    found: dict[str, dict] = {}

    def add(key: str, item: dict) -> None:
        count = 1
        unique = key
        while unique in found:
            count += 1
            unique = f"{key} ({count})"
        found[unique] = item

    for file in files:
        feature = gherkin.parse(file.read_text(encoding="utf-8-sig"), file.name)
        if feature.background:
            add("Background", _item("Background", {"steps": step_lines(feature.background.steps)}, step_lines(feature.background.steps)))
        for scenario, rule in feature.scenarios():
            tags = feature.effective_tags(scenario, rule)
            steps = step_lines(scenario.steps)
            tables = [[" | ".join(block.header), *(" | ".join(row) for row in block.rows)] for block in scenario.examples]
            parts = {"steps": steps, **({"examples": [line for table in tables for line in table]} if tables else {})}
            add(tag_of(tags, tagcheck.EXAMPLE) or scenario.name,
                _item(scenario.name, parts, steps + [f"| {line} |" for table in tables for line in table], tag_of(tags, tagcheck.RULE)))
    return found


def items(root: Path, feature_dir: Path, feature_id: str, gate: str) -> dict[str, dict]:
    """The items of what ``gate`` approves, read from the files as they are now."""
    if gate == "rules":
        path = feature_dir / "rules.md"
        if not path.is_file():
            raise UsageError(f"there is nothing to summarise: {path.relative_to(root).as_posix()} does not exist yet")
        return rule_items(path)
    files = featurefiles.spec_files(root, feature_id)
    if not files:
        raise UsageError(f"there is nothing to summarise: no .feature file is tagged @{feature_id}")
    try:
        return scenario_items(files)
    except ValueError as exc:                       # gherkin.ParseError
        raise UsageError(f"cannot summarise the examples: {exc}") from exc


def snapshot(found: dict[str, dict]) -> dict[str, dict]:
    """What is kept with an approval: the items without the lines that are only for showing."""
    return {key: {name: value for name, value in item.items() if name != "detail"} for key, item in found.items()}


# -- comparing -------------------------------------------------------------------------------
def natural(key: str) -> list[str | int]:
    """Sorts ``EX-7.1.2`` before ``EX-7.1.10``. A removed item has no place in the files, and the kept record is stored sorted."""
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", key)]


def changed_parts(gate: str, old: dict, new: dict) -> list[str]:
    names = [LABEL[gate]] if old["text"] != new["text"] else []
    names += ["rule"] if old.get("rule") != new.get("rule") else []
    old_parts, new_parts = old["parts"], new["parts"]
    return names + [name for name in dict.fromkeys([*old_parts, *new_parts]) if old_parts.get(name) != new_parts.get(name)]


def compare(gate: str, old: dict[str, dict], new: dict[str, dict]) -> dict:
    """The items added, removed and changed between the record of an approval and the files now, in file order."""
    changed = {key: names for key, item in new.items() if key in old and (names := changed_parts(gate, old[key], item))}
    return {"added": [key for key in new if key not in old], "removed": sorted((key for key in old if key not in new), key=natural),
            "changed": changed, "unchanged": sum(1 for key in new if key in old and key not in changed)}


def summarise(gate: str, current: dict[str, dict], approval: dict | None, rejected: dict | None, same_files: bool = True) -> dict:
    """The summary of ``gate``: everything when it was never approved, else only what differs from the last approval.

    ``approval`` is the last approval that counts, or None; ``rejected`` the rejection that came after it, or None;
    ``same_files`` whether the files are byte for byte what that approval covered."""
    base = {"gate": gate, "total": len(current), "current": current, "rejected": rejected, "same_files": same_files}
    if approval is None:
        return {**base, "state": "first", "since": None, "added": list(current), "removed": [], "changed": {}, "unchanged": 0}
    since = approval["at"]
    if approval.get("items") is None:
        return {**base, "state": "unknown", "since": since, "added": [], "removed": [], "changed": {}, "unchanged": 0}
    diff = compare(gate, approval["items"], current)
    return {**base, "state": "changed" if diff["added"] or diff["removed"] or diff["changed"] else "unchanged", "since": since,
            "old": approval["items"], **diff}


# -- showing -------------------------------------------------------------------------------
def count(n: int, gate: str) -> str:
    one, many = NOUN[gate]
    return f"{n} {one if n == 1 else many}"


def headline(summary: dict, feature: str) -> str:
    gate, state = summary["gate"], summary["state"]
    if state == "first":
        return f"{feature} {gate}, not approved before: {count(summary['total'], gate)}."
    day = summary["since"][:10]
    if state == "unknown":
        return (f"{feature} {gate}: the approval of {day} kept no list of its items, so what changed since cannot be shown; "
                f"all {count(summary['total'], gate)} are listed.")
    if state == "unchanged" and not summary["same_files"]:
        return (f"{feature} {gate}: no {NOUN[gate][0]} changed since the approval of {day}, but the file was edited around them "
                f"(layout, comments or other text), so it has to be approved again ({count(summary['total'], gate)}).")
    if state == "unchanged":
        return f"{feature} {gate}: no change since the approval of {day} ({count(summary['total'], gate)})."
    parts = []
    if summary["changed"]:
        parts.append(f"{count(len(summary['changed']), gate)} changed")
    if summary["added"]:
        parts.append(f"{len(summary['added'])} added")
    if summary["removed"]:
        parts.append(f"{len(summary['removed'])} removed")
    return f"{feature} {gate}, since the approval of {day}: " + ", ".join(parts) + "."


def item_lines(key: str, item: dict, with_detail: bool) -> list[str]:
    rule = f"  ({item['rule']})" if item.get("rule") else ""
    lines = [f"  {key}  {item['text']}{rule}"]
    if with_detail:
        lines += [f"    {line}" for line in item.get("detail", [])]
    return lines


def render(summary: dict, feature: str) -> str:
    """The summary as the person reads it: the feature's own words under greenlight's few headings."""
    gate, state = summary["gate"], summary["state"]
    lines = [headline(summary, feature)]
    if summary["rejected"]:
        lines.append(f"Rejected on {summary['rejected']['at'][:10]}: {summary['rejected'].get('reason') or 'no reason given'}")
    current = summary["current"]
    if state in ("first", "unknown"):
        for key, item in current.items():
            lines += item_lines(key, item, gate == "rules")
        return "\n".join(lines)
    if summary["changed"]:
        lines.append("Changed:")
        for key, names in summary["changed"].items():
            lines += item_lines(key, current[key], True)
            lines.append("    changed: " + ", ".join(names))
            if LABEL[gate] in names:
                lines.append(f"    was: {summary['old'][key]['text']}")
    if summary["added"]:
        lines.append("Added:")
        for key in summary["added"]:
            lines += item_lines(key, current[key], True)
    if summary["removed"]:
        lines.append("Removed:")
        for key in summary["removed"]:
            lines += item_lines(key, summary["old"][key], False)
    if state == "changed" and summary["unchanged"]:
        lines.append(f"Unchanged: {count(summary['unchanged'], gate)} (not shown).")
    return "\n".join(lines)


def facts(summary: dict, feature: str) -> dict:
    """The summary for the HTML report: the same words, as data."""
    text = render(summary, feature).splitlines()
    return {"gate": summary["gate"], "headline": text[0], "lines": text[1:]}
