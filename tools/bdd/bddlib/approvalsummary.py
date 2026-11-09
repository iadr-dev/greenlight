"""What the person is asked to approve, in plain words, and what changed since they last approved it.

An approval of the rules or the examples covers whole files, and a feature file can be two thousand lines long. This
module reads the same files into *items* (a rule, a scenario) and keeps one small record of them with each approval:

    items    {"R-007.1": {"text": "Orders of 1000 or more get 10% off.", "parts": {"why": "9f2c...", "all": "51d0..."}},
              "EX-007.1.1": {"text": "Order of 1000", "rule": "R-007.1", "parts": {"steps": "a41b...", "all": "c3e8..."}}}
    outside  "07ab..."     a hash of every line that belongs to no item

``text`` is the rule's statement or the scenario's title as the author wrote it, in the feature's own language. A part is
a hash of one more piece of the item, so a change to it is seen without keeping its text; the part ``all`` hashes every
line of the item, so a change to any of them is seen even when no other part names it. The files are cut into items and
the text between them, with nothing left over, so no word of an approved file can change without the summary naming it:
an item that was added, removed or changed, or the text outside the items. Comparing the record of the last approval with
the files now gives that; ``render`` prints it. Reading is all this module does: it never writes a record.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from . import featurefiles
from .errors import UsageError

NOUN = {"rules": ("rule", "rules"), "examples": ("scenario", "scenarios")}
OUTSIDE = {"rules": "text outside the rules (headings, out of scope, glossary or notes)",
           "examples": "text outside the scenarios (names, descriptions, tags or comments of the feature and its rules)"}
BULLET = re.compile(r"^\s*[-*+]\s+([^:]{1,40}):\s*(.*)$")
HEADING = re.compile(r"^\s*#{1,6}\s")
LABEL = {"rules": "statement", "examples": "title"}
PART_WORDS = {"all": "other text of the item", "notes": "free text under the rule"}
OUTSIDE_SHOWN = 12


def significant(lines: list[str]) -> list[str]:
    """The lines with their spacing normalised and the empty ones dropped: what a reader would call the words."""
    return [" ".join(line.split()) for line in lines if line.strip()]


def digest(lines: list[str]) -> str:
    return hashlib.sha256("\n".join(significant(lines)).encode("utf-8")).hexdigest()[:16]


def _item(text: str, parts: dict[str, list[str]], detail: list[str], lines: list[str], rule: str | None = None) -> dict:
    item = {"text": " ".join(text.split()), "parts": {name: digest(values) for name, values in {**parts, "all": lines}.items()},
            "detail": detail}
    if rule:
        item["rule"] = rule
    return item


def unique(found: dict, key: str) -> str:
    """``key``, or ``key (2)``, ``key (3)`` when an item of that name is already there: a repeated id is an item of its own."""
    count, name = 1, key
    while name in found:
        count += 1
        name = f"{key} ({count})"
    return name


def outside_of(lines: list[str]) -> dict:
    return {"digest": digest(lines), "lines": significant(lines)}


# -- reading the files into items ------------------------------------------------------------
def rule_items(path: Path) -> tuple[dict[str, dict], dict]:
    """The rules of ``rules.md`` and the text outside them.

    A rule is its line that starts with the id and every line under it up to the next rule or heading: the ``- Why:`` style
    lines (every value of a label that is repeated) and any other text. Everything else is outside the rules."""
    from . import trace

    groups: list[tuple[str, str, list[str]]] = []
    outside: list[str] = []
    current: list[str] | None = None
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        match = trace.RULE_LINE.match(line)
        if match:
            current = [line]
            groups.append((match.group(1), match.group(2).strip(), current))
        elif current is not None and not HEADING.match(line):
            current.append(line)
        else:
            current = None
            outside.append(line)
    found: dict[str, dict] = {}
    for key, text, lines in groups:
        labelled: dict[str, list[str]] = {}
        notes: list[str] = []
        detail: list[str] = []
        for line in lines[1:]:
            if not line.strip():
                continue
            bullet = BULLET.match(line)
            if bullet:
                label, value = bullet.group(1).strip(), bullet.group(2).strip()
                labelled.setdefault(label.lower(), []).append(value)
                detail.append(f"{label}: {value}")
            else:
                notes.append(line)
                detail.append(" ".join(line.split()))
        found[unique(found, key)] = _item(text, {**labelled, **({"notes": notes} if notes else {})}, detail, lines)
    return found, outside_of(outside)


def step_lines(steps: list) -> list[str]:
    lines: list[str] = []
    for step in steps:
        lines.append(f"{step.keyword.strip()} {step.text}".strip())
        lines += ["| " + " | ".join(row) + " |" for row in step.table or []]
        lines += (step.docstring or "").splitlines()
    return lines


def tag_of(tags: list[str], pattern: re.Pattern[str]) -> str | None:
    return next((tag[1:] for tag in tags if pattern.fullmatch(tag)), None)


def first_line(lines: list[str], keyword_line: int) -> int:
    """Index of the first line of a construct whose keyword is on ``keyword_line`` (1-based): its tag and comment lines come first."""
    index = keyword_line - 1
    while index > 0 and lines[index - 1].lstrip().startswith(("@", "#")):
        index -= 1
    return index


def scenario_items(files: list[Path]) -> tuple[dict[str, dict], dict]:
    """The scenarios of the feature files and the text outside them.

    A scenario is everything from its tags to the start of the next scenario, background or rule: steps, tables, doc
    strings, descriptions and comments. A Background is an item of its own. The feature's and the rules' own lines (names,
    descriptions, tags) are outside the scenarios."""
    from . import gherkin, tagcheck

    found: dict[str, dict] = {}
    outside: list[str] = []
    for file in files:
        lines = file.read_text(encoding="utf-8-sig").splitlines()
        feature = gherkin.parse("\n".join(lines), file.name)
        marks: list[tuple[int, str, object, object]] = []
        if feature.background:
            marks.append((first_line(lines, feature.background.line), "background", feature.background, None))
        for child in feature.children:
            if isinstance(child, gherkin.Rule):
                marks.append((first_line(lines, child.line), "rule", child, None))
                if child.background:
                    marks.append((first_line(lines, child.background.line), "background", child.background, child))
                marks += [(first_line(lines, sc.line), "scenario", sc, child) for sc in child.scenarios]
            else:
                marks.append((first_line(lines, child.line), "scenario", child, None))
        marks.sort(key=lambda mark: mark[0])
        starts = [mark[0] for mark in marks] + [len(lines)]
        outside += lines[:starts[0]] if marks else lines
        for position, (start, kind, node, rule) in enumerate(marks):
            span = lines[start:starts[position + 1]]
            if kind == "rule":
                outside += span
            elif kind == "background":
                steps = step_lines(node.steps)
                where = file.name if rule is None else f"{file.name}, {tag_of(rule.tags, tagcheck.RULE) or rule.name}"
                found[unique(found, f"Background ({where})")] = _item("Background", {"steps": steps}, steps, span)
            else:
                tags = feature.effective_tags(node, rule)
                steps = step_lines(node.steps)
                tables = [[" | ".join(block.header), *(" | ".join(row) for row in block.rows), *block.tags] for block in node.examples]
                parts = {"steps": steps, "tags": node.tags, "description": node.description.splitlines()}
                if tables:
                    parts["examples"] = [line for table in tables for line in table]
                found[unique(found, tag_of(tags, tagcheck.EXAMPLE) or node.name)] = _item(
                    node.name, {name: values for name, values in parts.items() if values}, steps + [f"| {line} |" for table in tables for line in table],
                    span, tag_of(tags, tagcheck.RULE))
    return found, outside_of(outside)


def read(root: Path, feature_dir: Path, feature_id: str, gate: str) -> dict:
    """The items of what ``gate`` approves and the text outside them, read from the files as they are now."""
    if gate == "rules":
        path = feature_dir / "rules.md"
        if not path.is_file():
            raise UsageError(f"there is nothing to summarise: {path.relative_to(root).as_posix()} does not exist yet")
        found, outside = rule_items(path)
        return {"items": found, "outside": outside}
    files = featurefiles.spec_files(root, feature_id)
    if not files:
        raise UsageError(f"there is nothing to summarise: no .feature file is tagged @{feature_id}")
    try:
        found, outside = scenario_items(files)
    except ValueError as exc:                       # gherkin.ParseError
        raise UsageError(f"cannot summarise the examples: {exc}") from exc
    return {"items": found, "outside": outside}


def snapshot(reading: dict) -> tuple[dict[str, dict], str]:
    """What is kept with an approval: the items without the lines that are only for showing, and the hash of the rest."""
    kept = {key: {name: value for name, value in item.items() if name != "detail"} for key, item in reading["items"].items()}
    return kept, reading["outside"]["digest"]


# -- comparing -------------------------------------------------------------------------------
def natural(key: str) -> list[str | int]:
    """Sorts ``EX-7.1.2`` before ``EX-7.1.10``. Removed items are known only from the kept record, which state.json stores with its
    keys in text order, so they are put back in number order; the others keep the order of the files."""
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", key)]


def changed_parts(gate: str, old: dict, new: dict) -> list[str]:
    names = [LABEL[gate]] if old["text"] != new["text"] else []
    names += ["rule"] if old.get("rule") != new.get("rule") else []
    old_parts, new_parts = old["parts"], new["parts"]
    names += [name for name in dict.fromkeys([*old_parts, *new_parts]) if old_parts.get(name) != new_parts.get(name)]
    return [name for name in names if name != "all" or len(names) == 1]


def compare(gate: str, old: dict[str, dict], new: dict[str, dict]) -> dict:
    """The items added, removed and changed between the record of an approval and the files now, in file order."""
    changed = {key: names for key, item in new.items() if key in old and (names := changed_parts(gate, old[key], item))}
    return {"added": [key for key in new if key not in old], "removed": sorted((key for key in old if key not in new), key=natural),
            "changed": changed, "unchanged": sum(1 for key in new if key in old and key not in changed)}


def summarise(gate: str, reading: dict, approval: dict | None, rejected: dict | None, same_files: bool = True,
              members: list[str] | None = None) -> dict:
    """The summary of ``gate``: everything when it was never approved, else only what differs from the last approval.

    ``approval`` is the last approval that counts, or None; ``rejected`` the rejection that came after it, or None;
    ``same_files`` whether the files are byte for byte what that approval covered; ``members`` what changed in the files of
    the workspace's other repositories, which are not listed here."""
    current = reading["items"]
    base = {"gate": gate, "total": len(current), "current": current, "rejected": rejected, "same_files": same_files,
            "members": members or [], "outside": reading["outside"], "outside_changed": False}
    if approval is None:
        return {**base, "state": "first", "since": None, "added": list(current), "removed": [], "changed": {}, "unchanged": 0}
    since = approval["at"]
    if approval.get("items") is None or approval.get("outside") is None:
        return {**base, "state": "unknown", "since": since, "added": [], "removed": [], "changed": {}, "unchanged": 0}
    diff = compare(gate, approval["items"], current)
    outside_changed = approval["outside"] != reading["outside"]["digest"]
    changed = diff["added"] or diff["removed"] or diff["changed"] or outside_changed or base["members"]
    return {**base, "state": "changed" if changed else "unchanged", "since": since, "old": approval["items"],
            "outside_changed": outside_changed, **diff}


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
        return (f"{feature} {gate}: no {NOUN[gate][0]} and no other text changed since the approval of {day}, but the file differs "
                f"in spacing or line breaks, so it has to be approved again ({count(summary['total'], gate)}).")
    if state == "unchanged":
        return f"{feature} {gate}: no change since the approval of {day} ({count(summary['total'], gate)})."
    parts = []
    if summary["changed"]:
        parts.append(f"{count(len(summary['changed']), gate)} changed")
    if summary["added"]:
        parts.append(f"{len(summary['added'])} added")
    if summary["removed"]:
        parts.append(f"{len(summary['removed'])} removed")
    if summary["outside_changed"]:
        parts.append(f"{OUTSIDE[gate].split(' (')[0]} changed")
    if summary["members"]:
        parts.append("files of other repositories changed")
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
            lines.append("    changed: " + ", ".join(PART_WORDS.get(name, name) for name in names))
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
    if summary["outside_changed"]:
        shown = summary["outside"]["lines"]
        lines.append(f"Also changed: {OUTSIDE[gate]}. It now reads:")
        lines += [f"  {line}" for line in shown[:OUTSIDE_SHOWN]] + ([f"  ... and {len(shown) - OUTSIDE_SHOWN} more lines"] if len(shown) > OUTSIDE_SHOWN else [])
    lines += [f"Also changed: {problem}" for problem in summary["members"]]
    if state == "changed" and summary["unchanged"]:
        lines.append(f"Unchanged: {count(summary['unchanged'], gate)} (not shown).")
    return "\n".join(lines)


def facts(summary: dict, feature: str) -> dict:
    """The summary for the HTML report: the same words, as data."""
    text = render(summary, feature).splitlines()
    return {"gate": summary["gate"], "headline": text[0], "lines": text[1:]}
