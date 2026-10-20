"""pytest wiring for the greenlight scenarios: a fresh world per scenario, no real network, and the two
options `bdd run` uses to look for scenarios that depend on each other."""
from __future__ import annotations

import random

import pytest

from tests.drivers.sockets import block_network
from tests.drivers.world import new_world
from tests.steps.core_steps import *  # noqa: F401,F403  (the step definitions register themselves as fixtures)


def pytest_addoption(parser):
    group = parser.getgroup("greenlight")
    group.addoption("--bdd-shuffle-seed", type=int, default=None, help="run the scenarios in a random order for this seed")
    group.addoption("--bdd-scenario", default=None, help="run only the scenario with this exact name")


def scenario_name(item) -> str | None:
    """pytest-bdd gives each scenario function the doc string '<feature file>: <scenario name>'."""
    doc = getattr(getattr(item, "obj", None), "__doc__", None) or ""
    return doc.partition(".feature: ")[2] or None


def pytest_collection_modifyitems(config, items):
    wanted = config.getoption("--bdd-scenario")
    if wanted is not None:
        kept = [item for item in items if scenario_name(item) == wanted]
        config.hook.pytest_deselected(items=[item for item in items if item not in kept])
        items[:] = kept
    seed = config.getoption("--bdd-shuffle-seed")
    if seed is not None:
        random.Random(seed).shuffle(items)


@pytest.fixture
def world(tmp_path):
    world = new_world(tmp_path)
    with block_network():
        yield world
    world.clock.stop()
    world.system.reset()
