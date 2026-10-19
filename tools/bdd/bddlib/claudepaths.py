"""Where Claude Code keeps things greenlight reads or must protect."""
from __future__ import annotations

import os
from pathlib import Path

TRANSCRIPT_ROOT_ENV = "GREENLIGHT_TRANSCRIPT_ROOT"    # tests, and unusual installations


def config_dir() -> Path:
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")


def transcript_roots() -> list[Path]:
    """Folders under which session transcripts live (resolved)."""
    roots = [config_dir() / "projects"]
    if os.environ.get(TRANSCRIPT_ROOT_ENV):
        roots.append(Path(os.environ[TRANSCRIPT_ROOT_ENV]))
    return [root.resolve() for root in roots]
