"""Binds every .feature file under specs/features to pytest. The tags on a scenario become pytest markers,
so `pytest -m FEAT-007` runs one feature."""
from pytest_bdd import scenarios

scenarios("../features")
