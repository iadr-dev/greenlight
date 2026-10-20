"""Knowledge cards: small Markdown files with front matter that agents scan cheaply and read in full only when picked.

    cards/techniques/boundary-value.md      kind: technique    test-design techniques
    cards/practices/pre-mortem.md           kind: practice     ways of working in a phase
    cards/instructions/C.API.CALL.md        kind: instruction  one per core instruction (id = instruction id)
    cards/runners/godog.md                  kind: runner       one per test runner for the generic adapter

    bdd cards build [--check]    write cards/index.json; with --check only compare (CI fails on drift)
    bdd cards list [--kind K]    front matter only, one card per line

Every card has an ``id`` equal to its file name, the ``kind`` of its folder, and a ``## Known pitfalls``
section with something in it: the auditor checks cards against their pitfalls, so a card without them is
not finished.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from . import frontmatter, state, store
from .errors import UsageError
from .statecmd import guarded

SCHEMA = 1
INDEX = "index.json"
FOLDERS = {"technique": "techniques", "practice": "practices", "instruction": "instructions", "runner": "runners"}
REQUIRED = {"technique": ("apply_when", "output", "cost"), "practice": ("apply_when", "output"),
            "instruction": ("apply_when",), "runner": ("apply_when",)}
OPTIONAL = ("pairs_with", "phase")
COSTS = ("low", "medium", "high")
SECTIONS = {"technique": ("Intent", "How to apply", "Known pitfalls"), "practice": ("Intent", "How to apply", "Known pitfalls"),
            "instruction": ("Semantics", "Known pitfalls"), "runner": ("Run", "Known pitfalls")}
_HEADING = re.compile(r"^##\s+(.*?)\s*$", re.MULTILINE)


def cards_dir() -> Path:
    import os
    plugin = os.environ.get("CLAUDE_PLUGIN_ROOT")
    return (Path(plugin) if plugin else Path(__file__).resolve().parents[3]) / "cards"


def card_files(base: Path) -> list[Path]:
    return sorted(p for p in base.rglob("*.md") if p.is_file())


def sections(body: str) -> dict[str, str]:
    """{heading: text} for the ``##`` sections of a card body."""
    marks = list(_HEADING.finditer(body))
    return {m.group(1): body[m.end(): marks[i + 1].start() if i + 1 < len(marks) else len(body)].strip()
            for i, m in enumerate(marks)}


def check_card(base: Path, path: Path) -> tuple[dict | None, list[str]]:
    """(index entry, problems) for one card."""
    rel = path.relative_to(base).as_posix()
    try:
        meta, body = frontmatter.parse(path.read_text(encoding="utf-8-sig"))
    except frontmatter.FrontmatterError as exc:
        return None, [f"{rel}: {exc}"]
    problems = []
    kind = meta.get("kind")
    if kind not in FOLDERS:
        return None, [f"{rel}: kind must be one of {', '.join(FOLDERS)}"]
    if path.parent.name != FOLDERS[kind] or path.parent.parent != base:
        problems.append(f"{rel}: a {kind} card belongs in cards/{FOLDERS[kind]}/")
    if meta.get("id") != path.stem:
        problems.append(f"{rel}: id must equal the file name ({path.stem!r}), not {meta.get('id')!r}")
    for key in REQUIRED[kind]:
        if not isinstance(meta.get(key), str) or not meta[key].strip():
            problems.append(f"{rel}: {key} is required and must be a non-empty value")
    if kind == "technique" and meta.get("cost") not in COSTS:
        problems.append(f"{rel}: cost must be one of {', '.join(COSTS)}")
    unknown = set(meta) - {"id", "kind", *REQUIRED[kind], *OPTIONAL}
    if unknown:
        problems.append(f"{rel}: unknown front matter key(s) {', '.join(sorted(unknown))}")
    if "phase" in meta and meta["phase"] not in state.PHASES:
        problems.append(f"{rel}: phase must be one of {', '.join(state.PHASES)}")
    if "pairs_with" in meta and not isinstance(meta["pairs_with"], list):
        problems.append(f"{rel}: pairs_with must be a list like [a, b]")
    found = sections(body)
    for name in SECTIONS[kind]:
        if not found.get(name):
            problems.append(f"{rel}: the '## {name}' section is missing or empty")
    entry = {"id": meta.get("id"), "kind": kind, "path": rel,
             **{k: meta[k] for k in (*REQUIRED[kind], *OPTIONAL) if k in meta}}
    return entry, problems


def build(base: Path) -> tuple[dict, list[str]]:
    """(index, problems) for every card under ``base``."""
    entries, problems = [], []
    for path in card_files(base):
        entry, found = check_card(base, path)
        problems += found
        if entry:
            entries.append(entry)
    ids = [e["id"] for e in entries]
    problems += [f"id {i!r} is used by more than one card" for i in sorted({i for i in ids if ids.count(i) > 1})]
    for entry in entries:
        problems += [f"{entry['path']}: pairs_with names {other!r}, which is not a card"
                     for other in entry.get("pairs_with", []) if isinstance(other, str) and other not in ids]
    return {"schema": SCHEMA, "cards": sorted(entries, key=lambda e: (e["kind"], e["id"]))}, problems


def render_index(index: dict) -> str:
    return json.dumps(index, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def run(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="bdd cards", description="Build, check and list the knowledge cards.")
    sub = ap.add_subparsers(dest="action", required=True)
    build_parser = sub.add_parser("build", help="write cards/index.json")
    build_parser.add_argument("--check", action="store_true", help="only compare with the file on disk (exit 1 on drift)")
    list_parser = sub.add_parser("list", help="front matter of every card, one per line")
    list_parser.add_argument("--kind", choices=tuple(FOLDERS))
    args = ap.parse_args(argv)
    return guarded("cards", lambda: do_build(args.check) if args.action == "build" else do_list(args.kind))


def do_build(check: bool) -> int:
    base = cards_dir()
    index, problems = build(base)
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 1
    text, path = render_index(index), base / INDEX
    current = path.read_text(encoding="utf-8") if path.is_file() else None
    if check:
        if current != text:
            print(f"{INDEX} is out of date; run `bdd cards build`", file=sys.stderr)
            return 1
        print(f"{len(index['cards'])} card(s), index in sync")
        return 0
    if current != text:
        path.write_text(text, encoding="utf-8", newline="\n")
    print(f"{len(index['cards'])} card(s) indexed" + ("" if current != text else " (unchanged)"))
    return 0


def do_list(kind: str | None) -> int:
    path = cards_dir() / INDEX
    if not path.is_file():
        raise UsageError(f"{path} does not exist; run `bdd cards build`")
    for card in store.read_json(path, "the card index")["cards"]:
        if kind in (None, card["kind"]):
            print(f"{card['id']}\t{card['kind']}\t{card['apply_when']}")
    return 0
