"""Adapters: a directory with ``adapter.toml``, a guide, and ``templates/`` to copy into a project.

    bdd adapter list
    bdd adapter apply NAME      copy the templates into the project and add the adapter to .bdd/config.toml

``apply`` never overwrites a file that exists, and refuses an adapter the project already has.
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


def config_block(data: dict) -> str:
    """The ``[[adapters]]`` tables of config.toml for this adapter."""
    lines = ["", "[[adapters]]", f"name = {toml_value(data['name'])}"]
    lines += [f"{key} = {toml_value(value)}" for key, value in data.get("paths", {}).items()]
    for table in ("run", "classify", "scan"):
        if table in data:
            lines += ["", f"[adapters.{table}]"] + [f"{k} = {toml_value(v)}" for k, v in data[table].items()]
    return "\n".join(lines) + "\n"


def template_files(path: Path) -> list[Path]:
    base = path / "templates"
    return sorted(p for p in base.rglob("*") if p.is_file() and p.name != ".gitkeep" and "__pycache__" not in p.parts)


def apply(root: Path, name: str) -> tuple[list[str], list[str]]:
    """Copy the templates and register the adapter. Returns (created, left alone because they exist)."""
    path = find(name)
    data = load(path)
    config_path = root / cfg.BDD_DIR / "config.toml"
    existing = config_path.read_text(encoding="utf-8") if config_path.is_file() else ""
    if any(a.get("name") == name for a in tomllib.loads(existing).get("adapters", [])):
        raise UsageError(f"adapter {name} is already in .bdd/config.toml")
    created, kept = [], []
    for source in template_files(path):
        rel = source.relative_to(path / "templates")
        target = root / rel
        if target.exists():
            kept.append(rel.as_posix())
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        created.append(rel.as_posix())
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(existing.rstrip("\n") + ("\n" if existing.strip() else "") + config_block(data),
                           encoding="utf-8", newline="\n")
    return created, kept


def run(argv: list[str]) -> int:
    if argv[:1] == ["list"] and len(argv) == 1:
        print("\n".join(available()) or "no adapters installed")
        return 0
    if argv[:1] == ["apply"] and len(argv) == 2:
        def action() -> int:
            created, kept = apply(project_root(), argv[1])
            print(f"adapter {argv[1]} added: {len(created)} file(s) created" + (f", {len(kept)} left alone" if kept else ""))
            print("\n".join(f"  + {p}" for p in created))
            print("\n".join(f"  = {p} (exists)" for p in kept))
            return 0
        return guarded("adapter", action)
    print("usage: bdd adapter list | bdd adapter apply NAME", file=sys.stderr)
    return 2
