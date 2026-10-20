"""Errors the drivers raise. The marker in ExpectedMissing is what the red gate classifies on."""

MARKER = "BDD_EXPECTED_MISSING"


class ExpectedMissing(AssertionError):
    """The system under test does not have this yet. During the red phase this is the right failure."""

    def __init__(self, what: str):
        super().__init__(f"{MARKER}: {what} does not exist yet")


class UnstubbedCall(AssertionError):
    """The system called an external dependency that the scenario did not stub."""


class OutboundNetworkBlocked(AssertionError):
    """A real network connection was attempted. Stub the dependency instead."""


class NotMapped(LookupError):
    """A logical name in a feature has no entry in tests/drivers/operations.py. This is a defect of the test, not a missing feature."""

    def __init__(self, kind: str, name: str, known):
        super().__init__(f"NotMapped: no {kind} named {name!r} in tests/drivers/operations.py (known: {sorted(known)})")
