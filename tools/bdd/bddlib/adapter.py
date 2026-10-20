"""Adapters: a directory with ``adapter.toml``, a guide, and ``templates/`` to copy into a project.

    bdd adapter list
    bdd adapter apply NAME [--into DIR]
                                copy the templates into the project (or into its folder DIR) and add the adapter
                                to .bdd/config.toml

``apply`` never overwrites a file that exists, and refuses an adapter the project already has in that folder.
``--into`` is for a repository with several adapters, for example a backend in ``api`` and a web front end in ``web``:
the adapter's files and its run command then live under that folder, and ``bdd run`` runs every adapter.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tomllib
from pathlib import Path

from . import config as cfg
from .errors import UsageError
from .statecmd import guarded, project_root

NAME_CHARS = set("abcdefghijklmnopqrstuvwxyz0123456789-")
ADAPTER_FILE = "adapter.toml"
REQUIRED = (ADAPTER_FILE, "guide.md", "templates")
SKIPPED_PARTS = {"__pycache__", "node_modules"}      # installed tooling and caches are never part of a template


def adapters_dir() -> Path:
    plugin = os.environ.get("CLAUDE_PLUGIN_ROOT")
    return (Path(plugin) if plugin else Path(__file__).resolve().parents[3]) / "adapters"


def available() -> list[str]:
    base = adapters_dir()
    return sorted(p.name for p in base.iterdir() if p.is_dir() and (p / ADAPTER_FILE).is_file()) if base.is_dir() else []


def find(name: str) -> Path:
    if not name or set(name) - NAME_CHARS:
        raise UsageError(f"{name!r} is not an adapter name; choose from {', '.join(available()) or '(none installed)'}")
    path = adapters_dir() / name
    if name not in available():
        raise UsageError(f"no adapter named {name}; choose from {', '.join(available()) or '(none installed)'}")
    missing = [r for r in REQUIRED if not (path / r).exists()]
    if missing:
        raise UsageError(f"adapter {name} is incomplete: missing {', '.join(missing)}")
    return path


def load(path: Path) -> dict:
    try:
        data = tomllib.loads((path / ADAPTER_FILE).read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise UsageError(f"{path / ADAPTER_FILE}: {exc}") from exc
    if data.get("name") != path.name:
        raise UsageError(f"{path / ADAPTER_FILE}: name must be {path.name!r}")
    return data


def toml_value(value) -> str:
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(toml_value(v) for v in value) + "]"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(str(value), ensure_ascii=False)


def config_block(data: dict, into: str = "") -> str:
    """The ``[[adapters]]`` tables of config.toml for this adapter (``root`` names the folder it works in)."""
    lines = ["", "[[adapters]]", f"name = {toml_value(data['name'])}"]
    if into:
        lines.append(f"root = {toml_value(into)}")
    lines += [f"{key} = {toml_value(value)}" for key, value in data.get("paths", {}).items()]
    for table in ("run", "classify", "scan"):
        if table in data:
            lines += ["", f"[adapters.{table}]"] + [f"{k} = {toml_value(v)}" for k, v in data[table].items()]
    return "\n".join(lines) + "\n"


def template_files(path: Path) -> list[Path]:
    base = path / "templates"
    return sorted(p for p in base.rglob("*") if p.is_file() and p.name != ".gitkeep" and not SKIPPED_PARTS & set(p.parts))


def destination(root: Path, into: str) -> str:
    """The folder ``--into`` names, checked to be a folder inside the project (blank: the project itself)."""
    base = cfg.adapter_base({"root": into}, root / cfg.BDD_DIR / "config.toml")
    target = (root / base).resolve() if base else root.resolve()
    if target != root.resolve() and root.resolve() not in target.parents:
        raise UsageError(f"--into {into!r} is outside the project")
    return base


def apply(root: Path, name: str, into: str = "") -> tuple[list[str], list[str]]:
    """Copy the templates and register the adapter. Returns (created, left alone because they exist)."""
    path = find(name)
    data = load(path)
    base = destination(root, into)
    config_path = root / cfg.BDD_DIR / "config.toml"
    existing = config_path.read_text(encoding="utf-8") if config_path.is_file() else ""
    if any(a.get("name") == name and cfg.adapter_base(a, config_path) == base for a in tomllib.loads(existing).get("adapters", [])):
        raise UsageError(f"adapter {name} is already in .bdd/config.toml" + (f" for {base}" if base else ""))
    created, kept = [], []
    for source in template_files(path):
        rel = Path(base) / source.relative_to(path / "templates") if base else source.relative_to(path / "templates")
        target = root / rel
        if target.exists():
            kept.append(rel.as_posix())
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        created.append(rel.as_posix())
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(existing.rstrip("\n") + ("\n" if existing.strip() else "") + config_block(data, base),
                           encoding="utf-8", newline="\n")
    return created, kept


def run(argv: list[str]) -> int:
    if argv[:1] == ["list"] and len(argv) == 1:
        print("\n".join(available()) or "no adapters installed")
        return 0
    if argv[:1] == ["apply"] and (len(argv) == 2 or (len(argv) == 4 and argv[2] == "--into")):
        def action() -> int:
            created, kept = apply(project_root(), argv[1], argv[3] if len(argv) == 4 else "")
            print(f"adapter {argv[1]} added: {len(created)} file(s) created" + (f", {len(kept)} left alone" if kept else ""))
            print("\n".join(f"  + {p}" for p in created))
            print("\n".join(f"  = {p} (exists)" for p in kept))
            return 0
        return guarded("adapter", action)
    print("usage: bdd adapter list | bdd adapter apply NAME [--into DIR]", file=sys.stderr)
    return 2
