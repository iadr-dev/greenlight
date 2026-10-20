"""The injected clock. Application code reads ``world.clock.now()``, or the project freezes the process clock.

If ``time_machine`` is installed the clock also freezes ``datetime.now()`` and ``time.time()`` for the
scenario; without it, give the application a clock seam and note it in system.md.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .compare import duration_seconds


class Clock:
    def __init__(self) -> None:
        self._now: datetime | None = None
        self._traveller = None

    def set(self, text: str) -> None:
        moment = datetime.fromisoformat(text.strip().replace("Z", "+00:00").replace(" ", "T", 1))
        self._now = moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)
        self._freeze()

    def advance(self, text: str) -> None:
        assert self._now is not None, "set the current time first (Given the current time is ...)"
        self._now += timedelta(seconds=duration_seconds(text))
        self._freeze()

    def now(self) -> datetime:
        return self._now or datetime.now(timezone.utc)

    def _freeze(self) -> None:
        try:
            import time_machine
        except ImportError:
            return
        self.stop()
        self._traveller = time_machine.travel(self._now, tick=False)
        self._traveller.start()

    def stop(self) -> None:
        if self._traveller is not None:
            self._traveller.stop()
            self._traveller = None
