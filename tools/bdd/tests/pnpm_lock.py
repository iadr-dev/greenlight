"""Reading the parts of a ``pnpm-lock.yaml`` the tests check, with the standard library only (no YAML parser is installed).

The file is machine-written with a fixed layout, so two readings are enough: the direct dependencies of the root importer
(what ``package.json`` asked for and the version that was locked) and the integrity hash of every locked package. With a
``packageManager`` field pnpm 12 writes two YAML documents: the first locks pnpm itself, the last is the project's lock.
"""
import re
from pathlib import Path

_DIRECT = re.compile(r"^      ('?)(?P<name>[^\s'][^:]*?)\1:\n        specifier: (?P<specifier>\S+)\n        version: (?P<version>\S+)$", re.M)
_PACKAGE = re.compile(r"^  ('?)(?P<key>[^\s'][^:]*?)\1:\n    resolution: \{(?P<resolution>[^}]*)\}$", re.M)
_DOCUMENT_BREAK = "\n---\n"


def _project(lock: Path) -> str:
    return lock.read_text(encoding="utf-8").split(_DOCUMENT_BREAK)[-1]


def _section(text: str, start: str, end: str) -> str:
    head = text.index(f"\n{start}:\n") + len(start) + 3
    tail = text.find(f"\n{end}:\n", head)
    return text[head:tail if tail != -1 else len(text)]


def direct_dependencies(lock: Path) -> dict[str, tuple[str, str]]:
    """{package: (the specifier in package.json, the version that was locked)} for the root importer's dependencies."""
    root = _section(_project(lock), "importers", "packages").split("\n\n  ")[0]
    return {m["name"]: (m["specifier"], m["version"]) for m in _DIRECT.finditer(root)}


def integrity(lock: Path) -> dict[str, str]:
    """{package@version: its sha512 integrity} for every locked package; a package without one maps to an empty string."""
    packages = _section(_project(lock), "packages", "snapshots")
    found = {}
    for m in _PACKAGE.finditer(packages):
        hashed = re.search(r"integrity: (sha512-[A-Za-z0-9+/=]+)", m["resolution"])
        found[m["key"]] = hashed[1] if hashed else ""
    return found
