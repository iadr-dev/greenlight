"""Features that span several repositories.

One repository is the home of a feature: its ``.bdd/features/FEAT-n-*/`` holds the brief, the rules, the state and the
report, and its ``.bdd/config.toml`` names the other repositories in a ``[workspace]`` table::

    [workspace]
    web = "../shop-web"        # a name and the directory of the other repository (relative to this one, or absolute)

Each member is a greenlight project of its own: it keeps the scenarios, steps, locks and recorded runs for the rules it
covers, tagged with the same ``@FEAT-n``, ``@R-`` and ``@EX-`` ids. The home allocates the ids (``bdd state next-id``);
a member learns one by creating the feature with that id (``bdd --in web state init FEAT-n --title ...``).

What this module gives the rest of the tool: finding a member, saying why its evidence cannot be read here (it is not on
this machine, or a link leads out of it), running a command inside a member (``bdd --in NAME ...``) and in all of them
(``--workspace``). The home's gates read each member's evidence from the member's own ``.bdd`` (see ``gates``).
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
from collections.abc import Callable, Iterator
from pathlib import Path

from . import config as cfg
from .errors import UsageError

IN_FLAG = "--in"
WORKSPACE_FLAG = "--workspace"
CHECKED_GATES = ("bind", "implement", "verify")


def members_of(root: Path) -> tuple[cfg.Member, ...]:
    return cfg.load(root).workspace


def find(root: Path, name: str) -> cfg.Member:
    members = members_of(root)
    for member in members:
        if member.name == name:
            return member
    known = ", ".join(m.name for m in members) or "none: add a [workspace] table to .bdd/config.toml"
    raise UsageError(f"{name!r} is not a member of this workspace (members: {known})")


def _inside(base: Path, target: Path) -> bool:
    real_base, real_target = Path(os.path.realpath(base)), Path(os.path.realpath(target))
    return real_target == real_base or real_base in real_target.parents


def unobserved(member: cfg.Member) -> str | None:
    """Why the evidence of ``member`` cannot be read from here, or None when it can.

    A member that is not on this machine, or whose ``.bdd`` leads out of the repository through a link, is not observed:
    nothing it says may back a gate."""
    path = member.path
    if not path.is_dir():
        return f"{path} does not exist on this machine"
    if not (path / cfg.BDD_DIR / "config.toml").is_file():
        return f"{path} is not a greenlight project (no .bdd/config.toml)"
    for relative in (cfg.BDD_DIR, f"{cfg.BDD_DIR}/features", f"{cfg.BDD_DIR}/.runs", f"{cfg.BDD_DIR}/.integrity"):
        if (path / relative).exists() and not _inside(path, path / relative):
            return f"{relative} leads out of the repository through a link"
    return None


@contextlib.contextmanager
def entered(member: cfg.Member) -> Iterator[None]:
    """Run commands as if started in ``member``'s repository."""
    why = unobserved(member)
    if why:
        raise UsageError(f"{member.name} is not observed here: {why}")
    here = os.getcwd()
    os.chdir(member.path)
    try:
        yield
    finally:
        os.chdir(here)


def take_in_flag(argv: list[str]) -> tuple[str | None, list[str]]:
    """``bdd --in NAME COMMAND ...``: the member name and the rest of the arguments."""
    if not argv or argv[0] != IN_FLAG:
        return None, argv
    if len(argv) < 3:
        raise UsageError("usage: bdd --in NAME COMMAND [options]")
    if argv[2] == IN_FLAG:
        raise UsageError("--in cannot be repeated: a member's own workspace is not entered from here")
    return argv[1], argv[2:]


def run_in(name: str, argv: list[str], dispatch: Callable[[list[str]], int]) -> int:
    root = cfg.find_root()
    if root is None:
        raise UsageError("not inside a greenlight project (no .bdd directory found); run /greenlight:init first")
    with entered(find(root, name)):
        return dispatch(argv)


def fan_out(root: Path, command: Callable[[list[str]], int], argv: list[str], include_home: bool = True) -> int:
    """Run ``command`` in the home repository and then in every member; the exit status is the worst of them."""
    members = members_of(root)
    status = 0
    if include_home:
        if members:
            print("== home ==")
        status = command(argv)
    for member in members:
        print(f"== {member.name} ==")
        try:
            with entered(member):
                status = max(status, command(argv))
        except UsageError as exc:
            print(f"not observed here: {exc}", file=sys.stderr)
            status = max(status, 1)
    return status


def without_flag(argv: list[str]) -> tuple[bool, list[str]]:
    return WORKSPACE_FLAG in argv, [a for a in argv if a != WORKSPACE_FLAG]


def run(argv: list[str]) -> int:
    """``bdd workspace list`` and ``bdd workspace check FEAT-n --gate bind|implement|verify``."""
    from . import gates, store

    ap = argparse.ArgumentParser(prog="bdd workspace", description="The other repositories of a feature that spans several.")
    sub = ap.add_subparsers(dest="action", required=True)
    listing = sub.add_parser("list", help="the members and whether their evidence can be read here")
    listing.add_argument("--json", action="store_true")
    check = sub.add_parser("check", help="what the members' evidence says about a gate")
    check.add_argument("feature", help="feature id, e.g. FEAT-007")
    check.add_argument("--gate", choices=CHECKED_GATES, default="verify")
    check.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    root = cfg.find_root()
    if root is None:
        print("bdd workspace: not inside a greenlight project", file=sys.stderr)
        return 2
    try:
        members = members_of(root)
        if args.action == "list":
            rows = [{"name": m.name, "path": str(m.path), "observed": unobserved(m) is None, "reason": unobserved(m)}
                    for m in members]
            print(json.dumps(rows, indent=2) if args.json else
                  "\n".join(f"{r['name']}  {r['path']}  " + ("observed" if r["observed"] else f"NOT OBSERVED: {r['reason']}")
                            for r in rows) or "no workspace: this feature lives in one repository")
            return 0
        store.parse_feature_id(args.feature)
        problems = gates.workspace_problems(root, args.feature, args.gate)
        if args.json:
            print(json.dumps({"feature": args.feature, "gate": args.gate, "members": [m.name for m in members],
                              "problems": problems, "ok": not problems}, indent=2))
        else:
            print("\n".join(problems) if problems else f"{args.feature}: {len(members)} member(s) agree with the {args.gate} gate")
        return 1 if problems else 0
    except (UsageError, cfg.ConfigError) as exc:
        print(f"bdd workspace: {exc}", file=sys.stderr)
        return 2
