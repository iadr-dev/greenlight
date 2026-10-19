"""Flat front-matter parser for skills, agents and knowledge cards.

Claude Code and Codex require YAML-style front matter in SKILL.md, so the format is fixed,
but greenlight only needs a small, strict subset and does not depend on a YAML library:

    ---
    key: scalar value        # everything after the first colon, trimmed, quotes optional
    list_key: [a, b, c]      # flat list of scalars
    ---
    body...

Anything else (nesting, multi-line values, duplicate keys) is an error so that malformed
cards fail loudly instead of being half-read.
"""
from __future__ import annotations

import re

_KEY = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*):(.*)$")


class FrontmatterError(ValueError):
    pass


def _scalar(raw: str) -> str:
    raw = raw.strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
        return raw[1:-1]
    return raw


def _value(raw: str):
    raw = raw.strip()
    if raw.startswith("["):
        if not raw.endswith("]"):
            raise FrontmatterError(f"unterminated list: {raw!r}")
        inner = raw[1:-1].strip()
        return [_scalar(x) for x in inner.split(",")] if inner else []
    return _scalar(raw)


def parse(text: str) -> tuple[dict, str]:
    """Return (metadata, body). Raises FrontmatterError if absent or malformed."""
    lines = text.lstrip("\ufeff").splitlines()
    if not lines or lines[0].strip() != "---":
        raise FrontmatterError("missing front matter: file must start with '---'")
    meta: dict = {}
    for n, line in enumerate(lines[1:], start=2):
        if line.strip() == "---":
            return meta, "\n".join(lines[n:]).lstrip("\n")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = _KEY.match(line)
        if not m:
            raise FrontmatterError(f"line {n}: expected 'key: value', got {line!r}")
        key, raw = m.group(1), m.group(2)
        if key in meta:
            raise FrontmatterError(f"line {n}: duplicate key {key!r}")
        if not raw.strip():
            raise FrontmatterError(f"line {n}: key {key!r} has no value (nested or multi-line values are not supported)")
        meta[key] = _value(raw)
    raise FrontmatterError("front matter is not closed with '---'")
