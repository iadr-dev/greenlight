#!/usr/bin/env python3
"""Move the language versions named in the workflows and the adapters' CI templates to the newest supported release.

    python tools/pins/bump.py [--write]

Without ``--write`` it only prints what it would change. The target of a product is the newest release cycle on
https://endoflife.date that has been out for 30 days and is not at its end of life; for a product that has long-term-support cycles
(Node, Java, .NET) only those count. A pin is only ever moved up. A file that names two different versions of the same
language (a matrix, a minimum on purpose) is left alone and listed, because which one is meant is not for a script to
guess. A pin whose line has the comment `pins: hold` and the reason is never moved (the tool it needs does not
support the newer version yet); remove the comment when it does. Nothing is merged here: the workflow opens a pull request and the repository's own CI decides. Standard library
only.
"""
from __future__ import annotations

import argparse
import datetime
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check  # noqa: E402


SETTLE = 30                     # days a release cycle is out before a pin moves to it: the setup actions and tools catch up


def supported(row: dict, today: datetime.date) -> bool:
    eol, released = row.get("eol"), row.get("releaseDate")
    try:
        if released and datetime.date.fromisoformat(str(released)) > today - datetime.timedelta(days=SETTLE):
            return False
        if eol is True or (isinstance(eol, str) and datetime.date.fromisoformat(eol) <= today):
            return False
    except ValueError:
        return False
    return True


def target(table: list, today: datetime.date) -> str | None:
    """The newest supported cycle (a long-term-support one where the product has them), or None."""
    rows = [r for r in table if isinstance(r, dict) and supported(r, today) and re.fullmatch(r"\d+(\.\d+)*", str(r.get("cycle")))]
    if any(r.get("lts") for r in rows):
        rows = [r for r in rows if r.get("lts")]
    return str(max(rows, key=lambda r: check.numeric(str(r["cycle"])))["cycle"]) if rows else None


def moved(value: str, cycle: str) -> str | None:
    """``value`` written for ``cycle`` in the same shape ("22" -> "24", "10.0.x" -> "11.0.x"), or None when it cannot be."""
    dotted_x = value.endswith(".x")
    base = value[:-2] if dotted_x else value
    parts, goal = base.split("."), cycle.split(".")
    if len(parts) > len(goal) and not dotted_x:
        return None                                  # a pin finer than a cycle ("3.13.1"): not ours to move
    new = ".".join(goal + ["0"] * (len(parts) - len(goal)))
    if check.numeric(new) <= check.numeric(base):
        return None
    return new + (".x" if dotted_x else "")


HOLD = "pins: hold"                   # in a comment on the line: the pin stays, and the comment says why


def held(text: str, m: re.Match) -> bool:
    start = text.rfind("\n", 0, m.start()) + 1
    end = text.find("\n", m.end())
    return HOLD in text[start:end if end >= 0 else len(text)]


def pin_value(text: str, key: str) -> set[str]:
    return {m["value"] for m in check.RUNTIME.finditer(text) if m["key"] == key and not held(text, m)}


def rewrite(text: str, key: str, value: str, new: str) -> str:
    pattern = rf"(?m)^(\s*-?\s*{re.escape(key)}\s*:\s*[\"']?){re.escape(value)}(?=[\"']?(\s|$))(?![^\n]*{HOLD})"
    return re.sub(pattern, lambda m: m.group(1) + new, text)


def goal(product: str, cycles: dict[str, str | None], fetch, today: datetime.date, skipped: list[str]) -> str | None:
    """The cycle ``product`` moves to, asked for once; a product with no answer is said once."""
    if product not in cycles:
        table = fetch(f"https://endoflife.date/api/{product}.json")
        cycles[product] = target(table, today) if isinstance(table, list) else None
        if cycles[product] is None:
            skipped.append(f"{product}: no answer from endoflife.date; left alone")
    return cycles[product]


def plan(root: Path, fetch, today: datetime.date) -> tuple[dict[Path, str], list[str], list[str]]:
    """(new text per file, one line per change, one line per pin left alone and why)."""
    changes: list[str] = []
    skipped: list[str] = []
    texts: dict[Path, str] = {}
    cycles: dict[str, str | None] = {}
    for path in check.files(root):
        original = text = path.read_text(encoding="utf-8", errors="replace")
        for key in sorted({m["key"] for m in check.RUNTIME.finditer(original)}):
            found = pin_value(original, key)
            if not found:
                continue
            if len(found) > 1:
                skipped.append(f"{check.rel(root, path)}: {key} names {', '.join(sorted(found))}; left alone")
                continue
            cycle = goal(check.RUNTIME_KEYS[key], cycles, fetch, today, skipped)
            (value,) = found
            new = moved(value, cycle) if cycle else None
            if new:
                text = rewrite(text, key, value, new)
                changes.append(f"{check.RUNTIME_KEYS[key]} {value} -> {new} in {check.rel(root, path)}")
        if text != original:
            texts[path] = text
    return texts, changes, skipped


def summary(changes: list[str], skipped: list[str]) -> str:
    by_move: dict[str, list[str]] = defaultdict(list)
    for line in changes:
        head, where = line.split(" in ", 1)
        by_move[head].append(where)
    lines = [f"- {move} ({len(places)} file{'s' if len(places) != 1 else ''})" for move, places in sorted(by_move.items())]
    if skipped:
        lines += ["", "Left alone:"] + [f"- {line}" for line in skipped]
    return "\n".join(lines)


def log_entry(root: Path, changes: list[str]) -> None:
    """Record the change under Unreleased in the changelog (every pull request of this repository does)."""
    moves = sorted({line.split(" in ", 1)[0] for line in changes})
    entry = ("### Changed\n- Pinned language versions moved to the newest supported release by the update automation: "
             + "; ".join(moves) + ". The adapters' CI templates and guides name the new versions; their own CI proved them (D62).\n\n")
    log = root / "CHANGELOG.md"
    text = log.read_text(encoding="utf-8")
    log.write_text(text.replace("## [Unreleased]\n\n", "## [Unreleased]\n\n" + entry, 1), encoding="utf-8", newline="\n")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Move the pinned language versions to the newest supported release.")
    ap.add_argument("--write", action="store_true", help="change the files (default: only print)")
    args = ap.parse_args(argv)
    texts, changes, skipped = plan(check.REPO, check.fetch_json, datetime.date.today())
    text = summary(changes, skipped)
    print(text or "nothing to change")
    if args.write:
        for path, new in texts.items():
            path.write_text(new, encoding="utf-8", newline="")
        if changes:
            log_entry(check.REPO, changes)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
