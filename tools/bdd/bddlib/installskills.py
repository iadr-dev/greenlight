"""`bdd install-skills`: make greenlight usable from agent tools other than Claude Code.

    bdd install-skills codex      [--user] [--dry-run] [--force]
    bdd install-skills agents-md  [--dry-run] [--force]

``codex`` writes one ``greenlight-<skill>/SKILL.md`` per skill under ``.agents/skills`` in the project (or under
``~/.agents/skills`` with ``--user``), the folders Codex scans. ``agents-md`` adds a marked block to ``AGENTS.md``
in the project root, the file most coding agents read. Both are plain text; the skills keep pointing at this
installation of greenlight for the playbooks and the ``bdd`` command, so they have to be installed again after the
plugin moves.

Nothing is overwritten without ``--force``: a file that differs is reported and left alone, and ``AGENTS.md`` is only
ever changed between its own begin and end markers. Without hooks the project is in soft enforcement, and the text
written here says so.
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from . import config as cfg
from . import frontmatter
from .errors import UsageError
from .statecmd import guarded

PLUGIN_ROOT = Path(__file__).resolve().parents[3]
BEGIN = "<!-- greenlight:begin (managed by `bdd install-skills`; edit outside this block) -->"
END = "<!-- greenlight:end -->"
PREFIX = "greenlight-"
TARGETS = ("codex", "agents-md")
_PLUGIN_ROOT_VARIABLE = "${CLAUDE_PLUGIN_ROOT}"
_SLASH_COMMAND = re.compile(r"/greenlight:([a-z]+)")
NOTE = ("> Installed for a tool other than Claude Code. There are no hooks here, so enforcement is soft: locks and\n"
        "> evidence are checked after the fact, not prevented. Skills are invoked by name (`$greenlight-<skill>` in\n"
        "> Codex). Read the greenlight block in `AGENTS.md` first, and never record an approval for the person.\n\n")


@dataclass
class Action:
    path: Path
    kind: str               # create | update | append | same | refuse
    text: str = ""
    why: str = ""


def plugin_root_text() -> str:
    return PLUGIN_ROOT.as_posix()


def agents_block() -> str:
    body = (PLUGIN_ROOT / "templates" / "agents-md.md").read_text(encoding="utf-8")
    return f"{BEGIN}\n{body.replace('{plugin_root}', plugin_root_text()).rstrip()}\n{END}\n"


def skill_text(source: Path) -> tuple[str, str]:
    """(skill name, the text to install): only name and description survive, with a prefixed name and this
    installation's paths, so the file is valid for tools that do not know Claude Code's extra keys."""
    meta, body = frontmatter.parse(source.read_text(encoding="utf-8"))
    name = PREFIX + str(meta["name"])
    description = str(meta["description"]).replace('"', "'")
    body = body.replace(_PLUGIN_ROOT_VARIABLE, plugin_root_text())
    body = _SLASH_COMMAND.sub(lambda m: f"${PREFIX}{m.group(1)}", body)
    return name, f'---\nname: {name}\ndescription: "{description}"\n---\n\n{NOTE}{body.rstrip()}\n'


def skill_sources() -> list[Path]:
    return sorted(p for p in (PLUGIN_ROOT / "skills").glob("*/SKILL.md") if p.is_file())


def _inside(base: Path, path: Path) -> bool:
    """Is ``path`` under ``base`` once links are resolved (a link out of the folder is not followed)?"""
    return path.resolve().is_relative_to(base.resolve())


def plan_file(base: Path, path: Path, text: str, force: bool) -> Action:
    if not _inside(base, path) or path.is_symlink():
        return Action(path, "refuse", why="it is, or sits behind, a link that leaves the folder")
    if not path.exists():
        return Action(path, "create", text)
    if not path.is_file():
        return Action(path, "refuse", why="it exists and is not a file")
    if path.read_text(encoding="utf-8") == text:
        return Action(path, "same")
    if force:
        return Action(path, "update", text)
    return Action(path, "refuse", why="it exists and differs; use --force to replace it")


def plan_block(path: Path, block: str, force: bool) -> Action:
    if path.is_symlink() or (path.exists() and not path.is_file()):
        return Action(path, "refuse", why="it is a link or not a file")
    if not path.exists():
        return Action(path, "create", block)
    current = path.read_text(encoding="utf-8")
    begin, end = current.find(BEGIN.split(" (")[0]), current.find(END)
    if begin < 0 and end < 0:
        return Action(path, "append", current.rstrip("\n") + "\n\n" + block if current.strip() else block)
    if begin < 0 or end < begin:
        return Action(path, "refuse", why="its greenlight markers are not a begin followed by an end; fix them by hand")
    stop = end + len(END) + (1 if current[end + len(END):end + len(END) + 1] == "\n" else 0)
    if current[begin:stop] == block:
        return Action(path, "same")
    if force:
        return Action(path, "update", current[:begin] + block + current[stop:])
    return Action(path, "refuse", why="its greenlight block differs; use --force to replace that block only")


def plan(root: Path, target: str, user: bool, force: bool) -> list[Action]:
    if target == "agents-md":
        return [plan_block(root / "AGENTS.md", agents_block(), force)]
    base = (Path.home() if user else root) / ".agents" / "skills"
    actions = []
    for source in skill_sources():
        name, text = skill_text(source)
        actions.append(plan_file(base.parent.parent, base / name / "SKILL.md", text, force))
    return actions


def apply(actions: list[Action]) -> None:
    for action in actions:
        if action.kind in ("create", "update", "append"):
            action.path.parent.mkdir(parents=True, exist_ok=True)
            action.path.write_text(action.text, encoding="utf-8", newline="\n")


def run(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="bdd install-skills", description="Install greenlight for agent tools other than Claude Code.")
    ap.add_argument("target", choices=TARGETS, help="codex: skills under .agents/skills; agents-md: a block in AGENTS.md")
    ap.add_argument("--user", action="store_true", help="codex only: install for the user (~/.agents/skills), not the project")
    ap.add_argument("--dry-run", action="store_true", help="say what would happen and change nothing")
    ap.add_argument("--force", action="store_true", help="replace a file or block that differs")
    args = ap.parse_args(argv)
    if args.user and args.target != "codex":
        print("bdd install-skills: --user goes with the codex target", file=sys.stderr)
        return 2

    def action() -> int:
        root = cfg.find_root(Path.cwd())
        if root is None:
            raise UsageError("not inside a greenlight project; run bdd init first")
        actions = plan(root, args.target, args.user, args.force)
        shown = "would " if args.dry_run else ""
        for item in actions:
            tail = f": {item.why}" if item.why else ""
            print(f"{shown}{item.kind:<7} {item.path}{tail}")
        refused = [a for a in actions if a.kind == "refuse"]
        if not args.dry_run and not refused:
            apply(actions)
        elif refused and not args.dry_run:
            print("nothing was written because something was refused", file=sys.stderr)
        if not refused:
            print("soft enforcement: this tool has no hooks, so locks and evidence are checked afterwards "
                  "(bdd lock FEAT-n --check --require), not prevented.")
        return 1 if refused else 0

    return guarded("install-skills", action)
