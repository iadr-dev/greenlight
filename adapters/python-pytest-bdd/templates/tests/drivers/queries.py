"""Counting the database statements an action runs, so that an N+1 problem is a failing scenario.

``QueryCounter`` is plain Python. The two hooks below attach it to SQLAlchemy and Django; both libraries are imported
only when a hook is used, so the tests need nothing extra. Create one counter when the project's ``System`` is built,
attach it to the application's engine or connection, and return ``counter.count`` from ``System.queries_executed``.
"""
from __future__ import annotations

from typing import Any, Callable


class QueryCounter:
    """Counts statements. Savepoints and transaction control are not counted: they say nothing about the data read."""

    IGNORED = ("SAVEPOINT", "RELEASE SAVEPOINT", "ROLLBACK TO SAVEPOINT", "BEGIN", "COMMIT", "ROLLBACK")

    def __init__(self) -> None:
        self.count = 0

    def record(self, statement: str) -> None:
        if not statement.lstrip().upper().startswith(self.IGNORED):
            self.count += 1

    def hook_sqlalchemy(self, engine: Any) -> None:
        """Count every statement the engine (or ``Session.bind``) executes."""
        from sqlalchemy import event

        def before_cursor_execute(connection, cursor, statement, parameters, context, executemany):
            self.record(statement)

        event.listen(engine, "before_cursor_execute", before_cursor_execute)

    def django_wrapper(self, execute: Callable[..., Any], sql: str, params: Any, many: bool, context: Any) -> Any:
        """A Django ``connection.execute_wrapper``: ``with connection.execute_wrapper(counter.django_wrapper): ...``."""
        self.record(sql)
        return execute(sql, params, many, context)
