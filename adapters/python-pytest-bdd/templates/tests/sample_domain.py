"""Code under test for the sample feature. Delete it together with tests/features/sample.feature."""


def add(a: int, b: int) -> int:
    if a < 0 or b < 0:
        raise ValueError("negative numbers are not allowed")
    return a + b
