"""Calling an API operation by its logical name and judging the response by logical result."""
from __future__ import annotations

from typing import Any

from .errors import NotMapped
from .operations import API
from .world import Outcome, World


def call(world: World, actor: str, operation: str, data: Any) -> Outcome:
    if operation not in API:
        raise NotMapped("API operation", operation, API)
    route = API[operation]
    fields = data if isinstance(data, dict) else {}
    path = route.path.format(**fields)
    used = {name for name in fields if "{" + name + "}" in route.path}
    sent = {k: v for k, v in fields.items() if k not in used} if isinstance(data, dict) else data
    options: dict[str, Any] = {"headers": world.headers.get(actor, {})}
    options["params" if route.method.upper() == "GET" else "json"] = sent or None
    response = world.system.http().request(route.method.upper(), path, **options)
    try:
        body = response.json()
    except ValueError:
        body = response.text
    world.outcome = Outcome("api", status=response.status_code, body=body)
    return world.outcome


def assert_succeeds(world: World) -> None:
    outcome = world.last("api")
    assert 200 <= outcome.status < 300, f"the request should succeed but got status {outcome.status}: {outcome.body!r}"


def assert_rejected(world: World, error: str) -> None:
    outcome = world.last("api")
    assert outcome.status >= 400 or outcome.exception, f"the request should be rejected but got status {outcome.status}"
    assert outcome.matches_error(error), f"the request was rejected, but not with {error!r}: status {outcome.status}, {outcome.body!r}"
