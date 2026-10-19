"""Errors shared by every command."""
from __future__ import annotations


class UsageError(ValueError):
    """The command line asked for something the tool refuses to do or cannot make sense of."""


class StoreError(RuntimeError):
    """A greenlight data file is unreadable, corrupt, or written by a newer version."""
