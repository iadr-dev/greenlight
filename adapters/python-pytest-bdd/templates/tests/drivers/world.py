"""Everything one scenario knows. A fresh World is made for every scenario, so nothing leaks between them."""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .clock import Clock
from .files import Workspace
from .operations import ERRORS
from .errors import NotMapped
from .stubs import Stubs
from .system import System


@dataclass
class Outcome:
    """What the last action did: an API response, a command, or a library call."""
    kind: str                           # api | cli | lib
    status: int | None = None           # api
    body: Any = None                    # api: parsed body; lib: the returned value
    exit_code: int | None = None        # cli
    stdout: str = ""                    # cli
    stderr: str = ""                    # cli
    exception: BaseException | None = None   # lib

    def matches_error(self, name: str) -> bool:
        rule = ERRORS.get(name)
        if rule is None:
            raise NotMapped("error", name, ERRORS)
        text = " ".join(str(x) for x in (self.body, self.stderr, self.stdout, self.exception) if x)
        checks = [(not rule.statuses) or self.status in rule.statuses,
                  (not rule.exception) or type(self.exception).__name__ == rule.exception,
                  rule.exit_code is None or self.exit_code == rule.exit_code,
                  (not rule.text) or rule.text.casefold() in text.casefold()]
        return all(checks) and any([rule.statuses, rule.exception, rule.exit_code is not None, rule.text])


@dataclass
class World:
    system: System
    clock: Clock
    stubs: Stubs
    workspace: Workspace
    headers: dict[str, dict[str, str]] = field(default_factory=dict)      # actor -> auth headers
    outcome: Outcome | None = None
    tracked: set[str] = field(default_factory=set)                         # entities seeded or verified
    before: dict[str, list[dict[str, Any]]] | None = None

    def track(self, entity: str) -> None:
        self.tracked.add(entity)

    def act(self) -> None:
        """Called before the first action: remember what every tracked entity looks like."""
        if self.before is None:
            self.before = {e: copy.deepcopy(self.system.records(e)) for e in sorted(self.tracked)}

    def last(self, kind: str) -> Outcome:
        assert self.outcome is not None, f"there is no result yet: a When step ({kind}) has to run first"
        assert self.outcome.kind == kind, f"the last action was {self.outcome.kind}, not {kind}"
        return self.outcome


def new_world(root: Path) -> World:
    return World(System(), Clock(), Stubs(), Workspace(root))
