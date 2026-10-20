"""What the sample feature exercises. Delete it with the sample."""


class NegativeInput(ValueError):
    pass


def add(a, b):
    if a < 0 or b < 0:
        raise NegativeInput("negative input")
    return a + b
