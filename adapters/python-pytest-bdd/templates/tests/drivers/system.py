"""The seams into the system under test. This is the one file of drivers that is specific to the project.

Every method says what it does and raises ExpectedMissing until the project implements the seam: during the
red phase that is the right failure. Use the most realistic seam available: the API first, then a domain
service, then a repository, then the raw database.
"""
from __future__ import annotations

from typing import Any

from .errors import ExpectedMissing


class System:
    # -- Given ---------------------------------------------------------------------------------
    def seed(self, entity: str, rows: list[dict[str, Any]]) -> None:
        """Create ``rows`` of ``entity``. An unknown column is an error."""
        raise ExpectedMissing(f"a way to create {entity} records")

    def authenticate(self, actor: str, role: str) -> dict[str, str]:
        """Sign ``actor`` in with ``role`` and return the HTTP headers that prove it."""
        raise ExpectedMissing(f"a way to sign in as {role}")

    def set_flag(self, flag: str, enabled: bool) -> None:
        raise ExpectedMissing(f"the {flag} feature flag")

    # -- When ----------------------------------------------------------------------------------
    def http(self):
        """An HTTP client with ``request(method, url, json=None, params=None, headers=None)`` returning an object
        with ``status_code`` and ``json()`` or ``text`` (FastAPI/Starlette TestClient, Flask test client wrappers,
        ``requests`` and ``httpx`` all fit)."""
        raise ExpectedMissing("an HTTP client for the application")

    def deliver_event(self, event: str, payload: Any) -> None:
        raise ExpectedMissing(f"a way to deliver the {event} event")

    def run_job(self, job: str) -> None:
        raise ExpectedMissing(f"the {job} job")

    # -- Then ----------------------------------------------------------------------------------
    def records(self, entity: str) -> list[dict[str, Any]]:
        """Every stored ``entity`` record, read through a seam that does not change anything."""
        raise ExpectedMissing(f"a way to read {entity} records")

    def published(self, event: str) -> list[Any]:
        """The payloads of ``event`` that the application published (a test double of the broker)."""
        raise ExpectedMissing(f"a captured {event} event")

    def reset(self) -> None:
        """Called after every scenario: drop data, close clients."""
