"""`bdd adopt FEAT-n --check`: is an adoption feature still only a description of what the system already does?

An adoption feature (``bdd state init --adopt``) is written for code that exists. Its scenarios are characterisations,
so the rules that make a normal feature trustworthy are turned around:

    A1  every scenario is tagged ``@existing`` (nothing new is being asked for)
    A2  the bind gate recorded the production source (``--record-red``)
    A3  the production source is still exactly what the bind gate recorded

The implement and verify gates of an adoption feature refuse while any of these fails, so the adoption cannot
quietly turn into a change of behaviour.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import classify, redrecord, state
from . import config as cfg
from .errors import StoreError, UsageError

CHECKED_GATES = ("implement", "verify")


def problems(root: Path, data: dict) -> list[str]:
    """Reasons ``data`` (the state of an adoption feature) no longer describes only existing behaviour."""
    scenarios = classify.feature_scenarios(root, data["feature"])
    found = [f'A1 scenario "{s["name"]}" ({s["example"] or "no example id"}) is not tagged @existing: adoption describes '
             "only behaviour the system already has" for s in scenarios if not s["existing"]]
    if not scenarios:
        found.append("A1 the feature has no scenarios")
    red = data.get("red")
    if not red:
        return found + ["A2 the bind gate was not recorded with --record-red, so the production source is not pinned"]
    if redrecord.source_digest(root, cfg.load(root).test_dirs) != red["source_hash"]:
        found.append("A3 production source changed since the bind gate recorded it: adoption does not edit production "
                     "code; revert the change, or follow /greenlight:change if the behaviour itself should change")
    return found


def run(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="bdd adopt", description="Check an adoption feature (bdd state init --adopt).")
    ap.add_argument("feature", help="feature id, e.g. FEAT-007")
    ap.add_argument("--check", action="store_true", required=True, help="report why the feature is not a pure adoption")
    args = ap.parse_args(argv)
    try:
        from .statecmd import feature_dir_of, project_root      # statecmd imports gates, which imports this module
        root = project_root()
        data = state.load(feature_dir_of(root, args.feature))
        if data.get("kind") != "adopt":
            raise UsageError(f"{args.feature} is not an adoption feature; create one with `bdd state init --adopt`")
        found = problems(root, data)
    except (UsageError, StoreError, cfg.ConfigError) as exc:
        print(f"bdd adopt: {exc}", file=sys.stderr)
        return 2
    print("\n".join(found) if found else f"{args.feature}: only existing behaviour is described, production source unchanged")
    return 1 if found else 0
