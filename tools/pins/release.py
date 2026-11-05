#!/usr/bin/env python3
"""Prepare the next patch release: the version in every place it is written, and the changelog section.

    python tools/pins/release.py [--write]

Prints the new version. With ``--write`` it edits the files (the workflow commits them to a branch and opens the pull
request, as every release of this repository is made). The places are the plugin manifest, the marketplace entry, the
package version, and the release tag the adapters' CI templates and guides clone. The changelog's *Unreleased* content
becomes the section of the new version. Nothing is released while *Unreleased* is empty. Standard library only.
"""
from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
CLONE = re.compile(r"((?:GREENLIGHT_REF:\s*|--branch\s+)v)\d+\.\d+\.\d+")
INTRO = "A patch release made by the update automation: the language versions the workflows and the adapters' CI templates pin were brought up to date."


def current(root: Path) -> str:
    version = json.loads((root / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["version"]
    if not SEMVER.match(version):
        raise SystemExit(f"plugin.json version {version!r} is not MAJOR.MINOR.PATCH")
    return version


def patch_after(version: str) -> str:
    major, minor, patch = version.split(".")
    return f"{major}.{minor}.{int(patch) + 1}"


def unreleased_span(text: str) -> tuple[int, int] | None:
    """(start, end) of the text between the Unreleased heading and the next version heading."""
    heading = "## [Unreleased]\n"
    start = text.find(heading)
    if start < 0:
        return None
    start += len(heading)
    end = text.find("\n## [", start)
    return (start, end) if end >= 0 else None


def unreleased(text: str) -> str:
    span = unreleased_span(text)
    return text[span[0]:span[1]].strip() if span else ""


def changelog(text: str, version: str, today: datetime.date) -> str:
    body = unreleased(text)
    if not body:
        raise SystemExit("nothing under Unreleased in CHANGELOG.md: nothing to release")
    start, end = unreleased_span(text)
    section = f"\n## [{version}] - {today.isoformat()}\n\n{INTRO}\n\n{body}\n"
    return text[:start] + section + text[end:]


def inside(path: Path) -> Path:
    """``path`` when it is a file of this repository, else the run stops."""
    resolved = path.resolve()
    if not resolved.is_relative_to(REPO):
        raise SystemExit(f"{path} is outside the repository")
    return resolved


def stamp(path: Path, old: str, new: str) -> None:
    path = inside(path)
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace(f'"version": "{old}"', f'"version": "{new}"').replace(f'__version__ = "{old}"', f'__version__ = "{new}"'),
                    encoding="utf-8", newline="\n")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Prepare the next patch release.")
    ap.add_argument("--write", action="store_true", help="edit the files (default: only print the new version)")
    args = ap.parse_args(argv)
    old = current(REPO)
    new = patch_after(old)
    if not SEMVER.match(new):
        raise SystemExit(f"{new!r} is not MAJOR.MINOR.PATCH")
    log = REPO / "CHANGELOG.md"
    release_log = changelog(log.read_text(encoding="utf-8"), new, datetime.date.today())
    if args.write:
        for rel in (".claude-plugin/plugin.json", ".claude-plugin/marketplace.json", "tools/bdd/bddlib/__init__.py"):
            stamp(REPO / rel, old, new)
        for path in sorted(REPO.glob("adapters/*/ci/github-actions.yml")) + sorted(REPO.glob("adapters/*/ci.md")):
            path = inside(path)
            text = path.read_text(encoding="utf-8")
            if CLONE.search(text):
                path.write_text(CLONE.sub(lambda m: f"{m.group(1)}{new}", text), encoding="utf-8", newline="\n")
        log.write_text(release_log, encoding="utf-8", newline="\n")
    print(new)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
