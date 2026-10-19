"""Finding ``.feature`` files."""
from __future__ import annotations

import re
from pathlib import Path

from . import config as cfg
from .errors import UsageError


def collect_files(paths: list[Path]) -> list[Path]:
    """Expand directories to their .feature files. An explicit file must itself be a .feature:
    lint is called by tools and agents, and parse errors quote the text they stumble on, so it
    must not be usable to read arbitrary files."""
    files: list[Path] = []
    for p in paths:
        if p.is_dir():
            files += sorted(f for f in p.rglob("*.feature")
                            if not any(part.startswith(".") or part == "node_modules" for part in f.relative_to(p).parts))
        elif p.is_file() and p.suffix == ".feature":
            files.append(p)
        elif p.is_file():
            raise UsageError(f"{p} is not a .feature file")
        else:
            raise FileNotFoundError(str(p))
    return files


def tagged_files(files: list[Path], tag: str) -> list[Path]:
    """The files in which ``tag`` (e.g. ``@FEAT-007``) appears on a tag line.

    A plain text scan rather than a parse: it must still find a file that someone edited
    into something that no longer parses."""
    pattern = re.compile(r"^\s*(?:@\S+\s+)*" + re.escape(tag) + r"(?=\s|$)", re.MULTILINE)
    return [f for f in files if pattern.search(f.read_text(encoding="utf-8-sig"))]


def spec_files(root: Path, feature_id: str) -> list[Path]:
    """The .feature files in the configured feature directories that carry @<feature_id>."""
    dirs = list(cfg.load(root).feature_dirs)
    if not dirs:
        raise UsageError("no feature directories are configured in .bdd/config.toml; pass the files explicitly")
    return tagged_files(collect_files(dirs), "@" + feature_id)
