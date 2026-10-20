"""An isolated workspace per scenario, with files addressed by logical name."""
from __future__ import annotations

from pathlib import Path

from .compare import normalise_text
from .errors import NotMapped
from .operations import FILES


class Workspace:
    def __init__(self, root: Path) -> None:
        self.root = root

    def path(self, name: str) -> Path:
        if name not in FILES:
            raise NotMapped("file", name, FILES)
        target = (self.root / FILES[name]).resolve()
        assert self.root.resolve() in target.parents, f"{name!r} maps outside the workspace"
        return target

    def write(self, name: str, content: str) -> None:
        target = self.path(name)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8", newline="\n")

    def read(self, name: str) -> str:
        target = self.path(name)
        assert target.is_file(), f"the file {name!r} ({FILES[name]}) was not produced"
        return target.read_text(encoding="utf-8")

    def assert_contains(self, name: str, expected: str) -> None:
        wanted, got = normalise_text(expected), normalise_text(self.read(name))
        assert wanted in got, f"file {name!r} does not contain {wanted!r}; it is {got!r}"
