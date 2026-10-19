"""Reading and writing greenlight's per-feature JSON files (``state.json``, ``lock.json``).

Writes are atomic (temp file + replace) so a crash or a concurrent reader never sees half a
file. Every file carries a ``schema`` number; a file written by a newer greenlight is refused
rather than silently misread.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .config import BDD_DIR
from .errors import StoreError, UsageError

SCHEMA = 1
FEATURE_ID = re.compile(r"FEAT-\d+")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def features_dir(root: Path) -> Path:
    return root / BDD_DIR / "features"


def parse_feature_id(text: str) -> str:
    if not FEATURE_ID.fullmatch(text):
        raise UsageError(f"{text!r} is not a feature id (expected FEAT-<number>, e.g. FEAT-007)")
    return text


def find_feature_dir(root: Path, feature_id: str) -> Path:
    """The directory ``.bdd/features/<FEAT-id>`` or ``<FEAT-id>-<slug>``."""
    parse_feature_id(feature_id)
    base = features_dir(root)
    matches = sorted(p for p in base.glob(f"{feature_id}*") if p.is_dir()
                     and (p.name == feature_id or p.name.startswith(feature_id + "-")))
    if not matches:
        raise UsageError(f"no feature directory for {feature_id} under {base}")
    if len(matches) > 1:
        raise UsageError(f"{feature_id} is ambiguous: {', '.join(m.name for m in matches)}")
    return matches[0]


def read_json(path: Path, what: str) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise
    except (OSError, ValueError) as exc:
        raise StoreError(f"{path}: cannot read {what}: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("schema"), int):
        raise StoreError(f"{path}: {what} has no schema version")
    if data["schema"] > SCHEMA:
        raise StoreError(f"{path}: {what} uses schema {data['schema']}, newer than this greenlight "
                         f"understands ({SCHEMA}); upgrade greenlight")
    return data


def write_json(path: Path, data: dict) -> None:
    """Atomically write ``data`` as UTF-8 JSON with LF endings."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
