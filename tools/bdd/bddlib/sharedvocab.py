"""Shared team vocabularies: domain steps kept in files that several projects (or one platform team) maintain.

A project's ``.bdd/vocabulary.toml`` names them:

    [vocabulary]
    include = ["vendor/team-vocabulary.toml"]

Each name is a ``.toml`` file inside the project (a vendored copy or a git submodule), relative to the project root;
a file may include others, a file is read once however often it is named, and a cycle is an error. A name that leaves
the project after symlinks are resolved is refused. The included files use the same format as the project's own (domain
steps with ids starting ``D.``, each composing core instructions).

Every included file is pinned by hash in ``.bdd/vocabulary.lock.json``. ``bdd vocabulary pin`` records the hashes after
the person has read the files; ``bdd lint`` and ``bdd vocabulary check`` report a file that changed, was added or is no
longer included until it is pinned again, and the guard and the tripwire keep agents away from the included files and
from the lock.
"""
from __future__ import annotations

import tomllib
from pathlib import Path

from . import config as cfg
from . import lockfile, store
from .errors import StoreError

LOCK_NAME = "vocabulary.lock.json"
SCHEMA = 1
MAX_DEPTH = 8
TABLE = "vocabulary"
KEY = "include"


class IncludeError(ValueError):
    """A shared vocabulary cannot be used; the message says why and where."""


def project_root(vocabulary_file: Path) -> Path:
    here = vocabulary_file.resolve().parent
    return (cfg.find_root(here) or here).resolve()


def lock_path(root: Path) -> Path:
    return root / cfg.BDD_DIR / LOCK_NAME


def relative(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def read_table(path: Path, root: Path) -> list[str]:
    """The names listed under ``[vocabulary] include`` in ``path`` (empty when there are none)."""
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise IncludeError(f"{relative(root, path)}: cannot be read as a vocabulary file ({exc})") from exc
    table = data.get(TABLE, {})
    names = table.get(KEY, []) if isinstance(table, dict) else None
    if names is None or not isinstance(names, list) or not all(isinstance(n, str) and n.strip() for n in names):
        raise IncludeError(f"{relative(root, path)}: [{TABLE}] {KEY} must be a list of file names")
    return names


def resolve_name(root: Path, including: Path, name: str) -> Path:
    where = relative(root, including)
    named = Path(name)
    if named.is_absolute() or named.suffix != ".toml":
        raise IncludeError(f'{where}: include "{name}" must be a .toml file named relative to the project root')
    target = (root / named).resolve()
    if not target.is_relative_to(root.resolve()):
        raise IncludeError(f'{where}: include "{name}" resolves outside the project; a shared vocabulary must live inside it '
                           "(vendor it or add it as a submodule)")
    if not target.is_file():
        raise IncludeError(f'{where}: include "{name}" does not exist')
    return target


def closure(root: Path, main: Path) -> list[Path]:
    """Every file included by ``main``, directly or not, in the order they are met. Raises IncludeError."""
    root, main = root.resolve(), main.resolve()
    found: list[Path] = []

    def visit(path: Path, chain: tuple[Path, ...]) -> None:
        if len(chain) > MAX_DEPTH:
            raise IncludeError(f"{relative(root, path)}: includes are nested more than {MAX_DEPTH} levels deep")
        for name in read_table(path, root):
            target = resolve_name(root, path, name)
            if target in chain or target == main:
                loop = " -> ".join(relative(root, p) for p in (*chain, target))
                raise IncludeError(f"include cycle: {loop}")
            if target not in found:
                found.append(target)
                visit(target, (*chain, target))

    if main.is_file():
        visit(main, (main,))
    return found


def safe_closure(vocabulary_file: Path | None) -> list[Path]:
    """The included files, or none when the vocabulary cannot be read (for callers that must not fail)."""
    if vocabulary_file is None or not vocabulary_file.is_file():
        return []
    try:
        return closure(project_root(vocabulary_file), vocabulary_file)
    except (IncludeError, OSError):
        return []


def named_files(root: Path, names: list[str]) -> list[Path]:
    """The existing files inside the project that ``names`` (project-relative) point at, links resolved."""
    found = []
    for name in names:
        target = (root / name).resolve()
        if target.is_relative_to(root.resolve()) and target.is_file() and target not in found:
            found.append(target)
    return found


def listed_files(root: Path, main: Path) -> list[Path]:
    """Every file the include lists name that exists, followed through nested lists, skipping what cannot be read."""
    start, found, queue = main.resolve(), [], [main.resolve()]
    while queue:
        try:
            names = read_table(queue.pop(), root)
        except IncludeError:
            continue
        for target in named_files(root, names):
            if target != start and target not in found:
                found.append(target)
                queue.append(target)
    return found


def protected_files(vocabulary_file: Path | None) -> list[Path]:
    """The shared files the guard keeps agents away from and the tripwire watches. This fails closed: besides the files the
    include list resolves to, it holds the ones the include list names however it reads (a broken list, a cycle) and every
    file the lock names, so breaking the include list does not uncover a file that was pinned."""
    if vocabulary_file is None or not vocabulary_file.is_file():
        return []
    root = project_root(vocabulary_file)
    found = safe_closure(vocabulary_file)
    try:
        pinned = list(read_pins(root) or {})
    except (StoreError, OSError):
        pinned = []
    others = listed_files(root, vocabulary_file) + named_files(root, pinned)
    return found + [f for f in dict.fromkeys(others) if f not in found]


# -- pins ----------------------------------------------------------------------------------
def read_pins(root: Path) -> dict[str, str] | None:
    """The pinned hashes by project-relative name, or None when nothing was ever pinned."""
    path = lock_path(root)
    if not path.is_file():
        return None
    data = store.read_json(path, "the vocabulary lock")
    files = data.get("files") if isinstance(data, dict) else None
    valid = (isinstance(data, dict) and data.get("schema") == SCHEMA and isinstance(files, dict)
             and all(isinstance(k, str) and isinstance(v, str) for k, v in files.items()))
    if not valid:
        raise StoreError(f"{path} is not a vocabulary lock")
    return files


def digests(root: Path, files: list[Path]) -> dict[str, str]:
    return {relative(root, f): lockfile.file_digest(f) for f in files}


def pin(root: Path, files: list[Path]) -> dict[str, str]:
    """Record the hashes of ``files`` as the approved shared vocabulary."""
    pinned = digests(root, files)
    store.write_json(lock_path(root), {"schema": SCHEMA, "files": pinned})
    return pinned


def pin_problems(root: Path, files: list[Path]) -> list[str]:
    """Why the shared vocabulary may not be trusted yet (empty when it is exactly what was pinned)."""
    try:
        pinned = read_pins(root)
    except StoreError as exc:
        return [str(exc)]
    current = digests(root, files)
    if not current and not pinned:
        return []
    found = []
    for name, digest in sorted(current.items()):
        if pinned is None or name not in pinned:
            found.append(f"shared vocabulary {name} is not pinned; read it, then run `bdd vocabulary pin`")
        elif pinned[name] != digest:
            found.append(f"shared vocabulary {name} changed since it was pinned; read the change, then run `bdd vocabulary pin`")
    found += [f"{name} is pinned but no longer included; run `bdd vocabulary pin` to drop it"
              for name in sorted(set(pinned or {}) - set(current))]
    return found
