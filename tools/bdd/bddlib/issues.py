"""The finding type shared by every lint rule."""
from __future__ import annotations

import re
from dataclasses import dataclass

ERROR, WARNING = "error", "warning"
_PLAIN_CELL = re.compile(r"[\w .\-/]{1,64}")
HIDDEN_CELL = "<cell not shown>"


def safe_cell(text: str) -> str:
    """A cell of a file an agent wrote, as a finding may show it to the person: only plain words, a name, an id or a path;
    anything else (a quote, a backtick, a link, a shell character, a long text) is not shown, so a cell cannot speak in
    greenlight's voice."""
    return text if _PLAIN_CELL.fullmatch(text) else HIDDEN_CELL


@dataclass(frozen=True)
class Issue:
    path: str
    line: int
    severity: str
    code: str
    message: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.severity} {self.code}: {self.message}"
