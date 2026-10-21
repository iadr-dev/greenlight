"""`bdd install-skills`: make greenlight usable without the Claude Code plugin, or from other agent tools.

    bdd install-skills claude     [--project] [--dry-run] [--force]
    bdd install-skills codex      [--user] [--dry-run] [--force]
    bdd install-skills agents-md  [--dry-run] [--force]
    bdd install-skills TARGET --uninstall [--user | --project] [--dry-run]

``claude`` writes one ``greenlight-<skill>/SKILL.md`` per skill under ``~/.claude/skills`` (``.claude/skills`` in the
project with ``--project``), so the skills work in Claude Code without the plugin, as ``/greenlight-<skill>``. ``codex``
writes the same under ``.agents/skills`` in the project (or ``~/.agents/skills`` with ``--user``), the folders Codex
scans; a skill only the person may start (``approve``) also gets ``agents/openai.yaml`` with
``allow_implicit_invocation: false``, Codex's way of keeping the model from picking it. ``agents-md`` adds a marked block to ``AGENTS.md`` in the project root, the file most coding agents read. All
are plain text; the skills keep pointing at this installation of greenlight for the playbooks and the ``bdd`` command,
so they have to be installed again after the plugin moves.

Nothing is overwritten without ``--force``: a file that differs is reported and left alone, and ``AGENTS.md`` is only
ever changed between its own begin and end markers. ``--uninstall`` removes exactly what this command wrote: a skill
file that carries its installation note, and the marked block (the file itself only when nothing else is in it);
anything else is kept, and folders left empty are removed. Without hooks the project is in soft enforcement, and the
text written here says so.
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from . import claudepaths
from . import config as cfg
from . import frontmatter
from .errors import UsageError
from .statecmd import guarded

PLUGIN_ROOT = Path(__file__).resolve().parents[3]
BEGIN = "<!-- greenlight:begin (managed by `bdd install-skills`; edit outside this block) -->"
END = "<!-- greenlight:end -->"
PREFIX = "greenlight-"
TARGETS = ("claude", "codex", "agents-md")
_PLUGIN_ROOT_VARIABLE = "${CLAUDE_PLUGIN_ROOT}"
_SLASH_COMMAND = re.compile(r"/greenlight:([a-z]+)")
CODEX_MARK = "> Installed for a tool other than Claude Code."
CLAUDE_MARK = "> Installed without the greenlight plugin by `bdd install-skills claude`."
MARKS = (CODEX_MARK, CLAUDE_MARK)
CODEX_NOTE = (CODEX_MARK + " There are no hooks here, so enforcement is soft: locks and\n"
              "> evidence are checked after the fact, not prevented. Skills are invoked by name (`$greenlight-<skill>` in\n"
              "> Codex). Read the greenlight block in `AGENTS.md` first, and never record an approval for the person.\n"
              "> `bdd` is not on the PATH in Codex. Run the command line as `sh \"{wrapper}\" <arguments>`; the commands\n"
              "> below name that path, so put `sh` in front of them.\n\n")
CODEX_APPROVE_NOTE = ("> The approval hook has already answered in your context, in a line that starts with `greenlight approval:`.\n"
                      "> Repeat that line and what has to happen first, then stop. Do not search for files or run commands to find out more.\n\n")
CLAUDE_NOTE = (CLAUDE_MARK + " The plugin's hooks are not active here, so enforcement is\n"
               "> soft: locks and evidence are checked after the fact, not prevented. Invoke the skills as\n"
               "> `/greenlight-<skill>`, and never record an approval for the person. With the plugin installed, use the\n"
               "> plugin's skills instead of these.\n\n")


@dataclass
class Action:
    path: Path
    kind: str               # create | update | append | same | refuse | remove | strip | keep | absent | note
    text: str = ""
    why: str = ""
    container: Path | None = None       # uninstall: the folder that is never removed, nor anything above it


@dataclass(frozen=True)
class Scope:
    target: str
    user: bool
    root: Path

    @property
    def container(self) -> Path:
        """The folder everything written must stay inside."""
        if self.target == "claude":
            return claudepaths.config_dir() if self.user else self.root
        return Path.home() if self.user else self.root

    @property
    def skills(self) -> Path:
        if self.target == "claude":
            return self.container / "skills" if self.user else self.root / ".claude" / "skills"
        return self.container / ".agents" / "skills"


def plugin_root_text() -> str:
    return PLUGIN_ROOT.as_posix()


def agents_block() -> str:
    body = (PLUGIN_ROOT / "templates" / "agents-md.md").read_text(encoding="utf-8")
    return f"{BEGIN}\n{body.replace('{plugin_root}', plugin_root_text()).rstrip()}\n{END}\n"


def skill_sources() -> list[Path]:
    return sorted(p for p in (PLUGIN_ROOT / "skills").glob("*/SKILL.md") if p.is_file())


def skill_text(source: Path) -> tuple[str, str]:
    """(skill name, the text to install for Codex): only name and description survive, with a prefixed name and this
    installation's paths, so the file is valid for tools that do not know Claude Code's extra keys."""
    meta, body = frontmatter.parse(source.read_text(encoding="utf-8"))
    name = PREFIX + str(meta["name"])
    description = str(meta["description"]).replace('"', "'")
    body = body.replace(_PLUGIN_ROOT_VARIABLE, plugin_root_text())
    body = _SLASH_COMMAND.sub(lambda m: f"${PREFIX}{m.group(1)}", body)
    note = CODEX_NOTE.replace("{wrapper}", f"{plugin_root_text()}/tools/bdd/bdd")
    if name == PREFIX + "approve":
        note += CODEX_APPROVE_NOTE
    return name, f'---\nname: {name}\ndescription: "{description}"\n---\n\n{note}{body.rstrip()}\n'


def claude_skill_text(source: Path) -> tuple[str, str]:
    """(skill name, the text to install for Claude Code): the skill's own front matter, which Claude Code understands
    (so ``approve`` stays out of the model's reach), with a prefixed name, and this installation's paths."""
    text = source.read_text(encoding="utf-8")
    meta, body = frontmatter.parse(text)
    name = PREFIX + str(meta["name"])
    lines = text.splitlines()
    front = [f"name: {name}" if line.startswith("name:") else line for line in lines[1:lines.index("---", 1)]]
    body = body.replace(_PLUGIN_ROOT_VARIABLE, plugin_root_text())
    body = _SLASH_COMMAND.sub(lambda m: f"/{PREFIX}{m.group(1)}", body)
    return name, "---\n" + "\n".join(front) + f"\n---\n\n{CLAUDE_NOTE}{body.rstrip()}\n"


CODEX_POLICY_FILE = Path("agents") / "openai.yaml"
CODEX_POLICY = ("# " + CODEX_MARK + " Written by `bdd install-skills codex`.\n"
                "# Only the person invokes this skill (typed as $greenlight-<skill>); the model may not pick it on its own.\n"
                "policy:\n  allow_implicit_invocation: false\n")
AGENTS_LIMIT_BYTES = 32 * 1024          # Codex reads at most this much of the AGENTS.md files together (project_doc_max_bytes)


def person_only(source: Path) -> bool:
    """Is this a skill only the person may start (``disable-model-invocation`` in its Claude Code front matter)?"""
    meta, _ = frontmatter.parse(source.read_text(encoding="utf-8"))
    return str(meta.get("disable-model-invocation", "")).casefold() == "true"


def is_ours(text: str) -> bool:
    return any(mark in text for mark in MARKS)


def _inside(base: Path, path: Path) -> bool:
    """Is ``path`` under ``base`` once links are resolved (a link out of the folder is not followed)?"""
    return path.resolve().is_relative_to(base.resolve())


def _linked(container: Path, path: Path) -> bool:
    return not _inside(container, path) or path.is_symlink()


def plan_file(base: Path, path: Path, text: str, force: bool) -> Action:
    if _linked(base, path):
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


def block_span(current: str) -> tuple[int, int] | None:
    """Where the greenlight block starts and stops in ``current``; None if there is none. Markers that are not a begin
    followed by an end raise UsageError."""
    begin, end = current.find(BEGIN.split(" (")[0]), current.find(END)
    if begin < 0 and end < 0:
        return None
    if begin < 0 or end < begin:
        raise UsageError("its greenlight markers are not a begin followed by an end; fix them by hand")
    return begin, end + len(END) + (1 if current[end + len(END):end + len(END) + 1] == "\n" else 0)


def plan_block(path: Path, block: str, force: bool) -> Action:
    if path.is_symlink() or (path.exists() and not path.is_file()):
        return Action(path, "refuse", why="it is a link or not a file")
    if not path.exists():
        return Action(path, "create", block)
    current = path.read_text(encoding="utf-8")
    try:
        span = block_span(current)
    except UsageError as exc:
        return Action(path, "refuse", why=str(exc))
    if span is None:
        return Action(path, "append", current.rstrip("\n") + "\n\n" + block if current.strip() else block)
    begin, stop = span
    if current[begin:stop] == block:
        return Action(path, "same")
    if force:
        return Action(path, "update", current[:begin] + block + current[stop:])
    return Action(path, "refuse", why="its greenlight block differs; use --force to replace that block only")


def plan(scope: Scope, force: bool) -> list[Action]:
    if scope.target == "agents-md":
        return [plan_block(scope.root / "AGENTS.md", agents_block(), force), *agents_notes(scope.root, agents_block())]
    make = claude_skill_text if scope.target == "claude" else skill_text
    actions = []
    for source in skill_sources():
        name, text = make(source)
        actions.append(plan_file(scope.container, scope.skills / name / "SKILL.md", text, force))
        if scope.target == "codex" and person_only(source):      # Codex's way of saying "the model may not invoke this"
            actions.append(plan_file(scope.container, scope.skills / name / CODEX_POLICY_FILE, CODEX_POLICY, force))
    return actions


def agents_notes(root: Path, block: str) -> list[Action]:
    """What would keep Codex from reading the block: an ``AGENTS.override.md`` beside it (Codex reads at most one file per
    folder and takes the override first) or more text than it reads."""
    notes = []
    override = root / "AGENTS.override.md"
    if override.exists():
        notes.append(Action(override, "note", why="Codex reads this file instead of AGENTS.md in the same folder, so the "
                            "greenlight block will not be seen; copy the block into it yourself"))
    current = (root / "AGENTS.md").read_text(encoding="utf-8") if (root / "AGENTS.md").is_file() else ""
    if len((current + block).encode("utf-8")) > AGENTS_LIMIT_BYTES:
        notes.append(Action(root / "AGENTS.md", "note", why="with the block the file is over the 32 KiB Codex reads by default "
                            "(project_doc_max_bytes), so part of it may be cut off"))
    return notes


# -- uninstall -----------------------------------------------------------------------------
def plan_unblock(path: Path, container: Path) -> Action:
    if path.is_symlink() or (path.exists() and not path.is_file()):
        return Action(path, "refuse", why="it is a link or not a file")
    if not path.exists():
        return Action(path, "absent", why="there is no AGENTS.md")
    current = path.read_text(encoding="utf-8")
    try:
        span = block_span(current)
    except UsageError as exc:
        return Action(path, "refuse", why=str(exc))
    if span is None:
        return Action(path, "absent", why="it has no greenlight block")
    before, after = current[:span[0]].rstrip("\n"), current[span[1]:].lstrip("\n")
    if not before.strip() and not after.strip():
        return Action(path, "remove", container=container)
    kept = "\n\n".join(part for part in (before, after.rstrip("\n")) if part.strip())
    return Action(path, "strip", kept + "\n")


def plan_unskill(scope: Scope) -> list[Action]:
    actions = []
    base = scope.skills
    folders = sorted(p for p in base.glob(PREFIX + "*") if p.is_dir() or p.is_symlink()) if base.is_dir() else []
    for folder in folders:
        path = folder / "SKILL.md"
        if _linked(scope.container, folder) or _linked(scope.container, path):
            actions.append(Action(path, "refuse", why="it is, or sits behind, a link that leaves the folder"))
        elif path.is_file() and is_ours(path.read_text(encoding="utf-8")):
            actions += policy_removal(scope, folder)
            actions.append(Action(path, "remove", container=scope.container))
        elif path.exists():
            actions.append(Action(path, "keep", why="it was not written by bdd install-skills"))
    return actions


def policy_removal(scope: Scope, folder: Path) -> list[Action]:
    """The Codex policy file next to a skill this command wrote, if this command wrote that too."""
    policy = folder / CODEX_POLICY_FILE
    if not policy.exists():
        return []
    if _linked(scope.container, policy) or not policy.is_file():
        return [Action(policy, "refuse", why="it is, or sits behind, a link that leaves the folder")]
    if is_ours(policy.read_text(encoding="utf-8")):
        return [Action(policy, "remove", container=scope.container)]
    return [Action(policy, "keep", why="it was not written by bdd install-skills")]


def plan_uninstall(scope: Scope) -> list[Action]:
    if scope.target == "agents-md":
        return [plan_unblock(scope.root / "AGENTS.md", scope.root)]
    return plan_unskill(scope)


def prune(folder: Path, container: Path) -> None:
    """Remove ``folder`` and the folders above it that are left empty, never ``container`` or anything above it."""
    container = container.resolve()
    while folder.resolve() != container and container in folder.resolve().parents:
        try:
            folder.rmdir()
        except OSError:
            return                                              # not empty: something else lives there
        folder = folder.parent


def apply(actions: list[Action]) -> None:
    for action in actions:
        if action.kind in ("create", "update", "append", "strip"):
            action.path.parent.mkdir(parents=True, exist_ok=True)
            action.path.write_text(action.text, encoding="utf-8", newline="\n")
        elif action.kind == "remove":
            action.path.unlink()
            if action.container is not None:
                prune(action.path.parent, action.container)


# -- command -------------------------------------------------------------------------------
def resolve_scope(target: str, user: bool, project: bool, root: Path) -> Scope:
    if user and project:
        raise UsageError("--user and --project exclude each other")
    if user and target == "agents-md":
        raise UsageError("--user goes with the claude and codex targets; AGENTS.md belongs to the project")
    if target == "claude":
        return Scope(target, not project, root)
    return Scope(target, user, root)


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="bdd install-skills",
                                 description="Install greenlight without the plugin, or for other agent tools.")
    ap.add_argument("target", choices=TARGETS, help="claude: skills under ~/.claude/skills; codex: skills under "
                    ".agents/skills; agents-md: a block in AGENTS.md")
    ap.add_argument("--user", action="store_true", help="codex: install for the user (~/.agents/skills) instead of the project")
    ap.add_argument("--project", action="store_true", help="claude: install into the project (.claude/skills) instead of "
                    "for the user")
    ap.add_argument("--uninstall", action="store_true", help="remove what this command wrote for the target")
    ap.add_argument("--dry-run", action="store_true", help="say what would happen and change nothing")
    ap.add_argument("--force", action="store_true", help="replace a file or block that differs")
    return ap


def report(actions: list[Action], dry_run: bool) -> None:
    shown = "would " if dry_run else ""
    for item in actions:
        tail = f": {item.why}" if item.why else ""
        print(f"{shown}{item.kind:<7} {item.path}{tail}")


def run(argv: list[str]) -> int:
    args = parser().parse_args(argv)
    if args.uninstall and args.force:
        print("bdd install-skills: --force goes with installing, not with --uninstall", file=sys.stderr)
        return 2

    def action() -> int:
        root = cfg.find_root(Path.cwd())
        if root is None:
            raise UsageError("not inside a greenlight project; run bdd init first")
        scope = resolve_scope(args.target, args.user, args.project, root)
        actions = plan_uninstall(scope) if args.uninstall else plan(scope, args.force)
        report(actions, args.dry_run)
        refused = [a for a in actions if a.kind == "refuse"]
        if not args.dry_run and not refused:
            apply(actions)
        elif refused and not args.dry_run:
            print(f"nothing was {'removed' if args.uninstall else 'written'} because something was refused", file=sys.stderr)
        if not refused and not args.uninstall:
            print("soft enforcement: this installation has no hooks, so locks and evidence are checked afterwards "
                  "(bdd lock FEAT-n --check --require), not prevented.")
        return 1 if refused else 0

    return guarded("install-skills", action)
