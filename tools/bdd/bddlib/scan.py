r"""`bdd scan FEAT-n`: deterministic checks on the step definitions and drivers of a feature.

Language-specific knowledge lives in the adapter's ``[adapters.scan]`` table of ``.bdd/config.toml``:

    [adapters.scan]
    step_start      = '^\s*@(?P<kind>given|when|then)\b'     # a line that starts a step definition
    assert_patterns = ['\bassert\b', 'pytest\.raises', 'expect_']
    sleep_patterns  = ['time\.sleep\(', 'asyncio\.sleep\(']
    stub_patterns   = ['mock\.patch\([^\w.]([\w.]+)']        # group 1 = what is stubbed

A step definition runs from its start line to the next one. Findings:

    S2  a ``then`` step definition that contains none of ``assert_patterns``
    E3  a fixed wait (``sleep_patterns``) anywhere in the steps and drivers
    S4  a stub of something ``system.md`` does not list under its Dependencies heading

Comment-only lines (``#``, ``//``) are ignored.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from . import config as cfg
from .errors import UsageError
from .issues import ERROR, Issue

SKIPPED = {"__pycache__", "node_modules", ".git"}
_COMMENT = re.compile(r"^\s*(#|//)")
_HEADING = re.compile(r"^\s*#{1,6}\s*(.*)$")
_ITEM = re.compile(r"^\s*[-*+]\s+[`*_]*([\w.\-/]+)")


def step_files(rules: cfg.ScanRules) -> list[Path]:
    files: list[Path] = []
    for directory in rules.step_dirs:
        for dirpath, dirnames, filenames in os.walk(directory):
            dirnames[:] = sorted(d for d in dirnames if d not in SKIPPED and not d.startswith("."))
            files += [Path(dirpath) / name for name in sorted(filenames) if not name.startswith(".")]
    return files


def read_lines(path: Path) -> list[str] | None:
    try:
        return path.read_text(encoding="utf-8-sig").splitlines()
    except (UnicodeDecodeError, OSError):
        return None                                   # binary or unreadable: nothing to scan


def declared_dependencies(system_md: Path) -> set[str] | None:
    """Names listed under a heading that mentions dependencies, lower-cased; None if there is no such list."""
    if not system_md.is_file():
        return None
    names: set[str] = set()
    in_section = found = False
    for line in system_md.read_text(encoding="utf-8-sig").splitlines():
        heading = _HEADING.match(line)
        if heading:
            in_section = "dependenc" in heading.group(1).casefold()
            found = found or in_section
        elif in_section and (item := _ITEM.match(line)):
            names.add(item.group(1).casefold())
    return names if found else None


def code_lines(lines: list[str]) -> list[tuple[int, str]]:
    return [(number, line) for number, line in enumerate(lines, start=1) if not _COMMENT.match(line)]


def scan_file(root: Path, path: Path, rules: cfg.ScanRules, declared: set[str] | None) -> list[Issue]:
    lines = read_lines(path)
    if lines is None:
        return []
    rel = path.relative_to(root).as_posix()
    start = re.compile(rules.step_start, re.IGNORECASE)
    asserts = [re.compile(p) for p in rules.assert_patterns]
    sleeps = [re.compile(p) for p in rules.sleep_patterns]
    stubs = [re.compile(p) for p in rules.stub_patterns]
    issues: list[Issue] = []
    starts: list[tuple[int, str]] = []                 # (index into lines, kind)
    for number, line in code_lines(lines):
        if match := start.search(line):
            starts.append((number - 1, match.group("kind").casefold()))
        if any(p.search(line) for p in sleeps):
            issues.append(Issue(rel, number, ERROR, "E3", "fixed wait: wait for the condition instead of sleeping"))
        for pattern in stubs:
            for found in pattern.finditer(line):
                issues += undeclared_stub(rel, number, found.group(1), declared)
    for position, (index, kind) in enumerate(starts):
        end = starts[position + 1][0] if position + 1 < len(starts) else len(lines)
        body = [line for _, line in code_lines(lines[index:end])]
        if kind == "then" and not any(p.search(line) for line in body for p in asserts):
            issues.append(Issue(rel, index + 1, ERROR, "S2", "this then step never asserts anything"))
    return issues


def undeclared_stub(rel: str, number: int, target: str, declared: set[str] | None) -> list[Issue]:
    if declared is None:
        return [Issue(rel, number, ERROR, "S4", f"{target} is stubbed but system.md has no Dependencies list to check it against")]
    if any(name in target.casefold() for name in declared):
        return []
    return [Issue(rel, number, ERROR, "S4", f"{target} is stubbed but is not a declared dependency in system.md "
                                           f"(declared: {', '.join(sorted(declared)) or 'none'})")]


def scan(root: Path, feature_dir: Path) -> list[Issue]:
    config = cfg.load(root)
    if not config.scans:
        raise UsageError("no [adapters.scan] table in .bdd/config.toml; the adapter says how to read its step definitions")
    declared = declared_dependencies(feature_dir / "system.md")
    issues: list[Issue] = []
    for rules in config.scans:
        for path in step_files(rules):
            issues += scan_file(root, path, rules, declared)
    return sorted(issues, key=lambda i: (i.path, i.line, i.code))
