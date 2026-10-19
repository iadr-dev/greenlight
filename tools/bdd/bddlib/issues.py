"""The finding type shared by every lint rule."""
from __future__ import annotations

from dataclasses import dataclass

ERROR, WARNING = "error", "warning"


@dataclass(frozen=True)
class Issue:
    path: str
    line: int
    severity: str
    code: str
    message: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.severity} {self.code}: {self.message}"
