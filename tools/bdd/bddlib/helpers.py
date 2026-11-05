"""Helper plugins: the Claude Code plugins greenlight's roles use when they are installed.

    bdd helpers [--json]               which helpers are installed, and the one line that installs the missing ones
    bdd helpers install [NAME ...] --yes   install the named helpers (default: every missing recommended one)
    bdd helpers --decline              remember that the person does not want to be asked again

greenlight works without any of them; each one only makes a role better (see README, "Plugins greenlight can use").
Nothing is installed by an agent: installing a plugin changes the person's Claude Code settings, which the tripwire
watches and the guard protects, and the guard refuses a ``bdd helpers install`` made through a tool call. The person types
the printed line themselves (the ``!`` prefix runs it in their own shell, between prompts), after being asked once.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from . import config as cfg
from . import store
from .errors import StoreError, UsageError

RECORD = "helpers.json"
LIST_TIMEOUT = 30
INSTALL_TIMEOUT = 300


@dataclass(frozen=True)
class Helper:
    id: str               # plugin@marketplace, as `claude plugin install` takes it
    name: str             # the short name people know it by
    adds: str
    used_by: str
    needs: str = ""
    recommended: bool = True


# Only plugins of Anthropic's own directories: installing one never adds a marketplace. They are used in report mode only.
CATALOG = (
    Helper("frontend-design@claude-plugins-official", "frontend-design", "a design plan for a new screen", "ui-engineer"),
    Helper("context7@claude-plugins-official", "context7", "the current documentation of a library", "writers and reviewers",
           "network"),
    Helper("microsoft-docs@claude-plugins-official", "microsoft-docs", "the current Microsoft and Azure documentation",
           "writers and reviewers", "network"),
    Helper("chrome-devtools-mcp@claude-plugins-official", "chrome-devtools-mcp", "accessibility and visual checks in a browser",
           "ui-reviewer", "Chrome, and the app running"),
    Helper("code-metrics-complexity-and-duplication-report@anthropic-plugin-directory", "code-metrics",
           "complexity and duplication of the changed files", "code-reviewer"),
    Helper("api-drift-detector-typescript-contract-checker@anthropic-plugin-directory", "api-drift-detector",
           "drift between API types, schemas and the database", "code-reviewer"),
    Helper("feature-dev@claude-plugins-official", "feature-dev", "a read-only code review checklist", "code-reviewer"),
    Helper("figma@claude-plugins-official", "figma", "building a screen from a Figma design", "ui-engineer",
           "a Figma login and a design URL", recommended=False),
)

# Installed plugins whose own hooks react to every edit, test files included. They can send an agent in circles; greenlight's
# guard keeps the tests locked whatever they ask. What is known about quieting each one.
HOOK_PLUGINS = {
    "impeccable": "turn the plugin off for the project in /plugin",
    "typescript-patterns-enforcer": "turn the plugin off for the project in /plugin",
    "security-guidance": "set ENABLE_STOP_REVIEW=0 (review at stop) or SECURITY_GUIDANCE_DISABLE=1 (everything)",
}


def claude_program() -> str | None:
    return shutil.which("claude")


def installed(run=subprocess.run) -> dict[str, str] | None:
    """{plugin id: version} of the plugins that are installed and on for this person; None when Claude Code's list cannot
    be read (not on the PATH, an error, or output that is not the list)."""
    program = claude_program()
    if program is None:
        return None
    try:
        done = run([program, "plugin", "list", "--json"], capture_output=True, text=True, encoding="utf-8", errors="replace",
                   timeout=LIST_TIMEOUT, stdin=subprocess.DEVNULL)
        entries = json.loads(done.stdout)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    if done.returncode != 0 or not isinstance(entries, list):
        return None
    return {str(e["id"]): str(e.get("version", "")) for e in entries
            if isinstance(e, dict) and "id" in e and e.get("enabled") and (e.get("scope") == "user" or e.get("projectEnabled"))}


def short_names(plugins: dict[str, str] | None) -> set[str]:
    return {plugin.split("@", 1)[0] for plugin in plugins or {}}


def missing(plugins: dict[str, str] | None, only_recommended: bool = True) -> list[Helper]:
    return [h for h in CATALOG if h.id not in (plugins or {}) and (h.recommended or not only_recommended)]


def record_path(root: Path) -> Path:
    return root / cfg.BDD_DIR / RECORD


def declined(root: Path | None) -> bool:
    if root is None or not record_path(root).is_file():
        return False
    try:
        return store.read_json(record_path(root), "the helpers record").get("decision") == "declined"
    except StoreError:
        return False


def install_line() -> str:
    wrapper = Path(__file__).resolve().parents[1] / "bdd"
    return f'! sh "{wrapper.as_posix()}" helpers install --yes'


def table(plugins: dict[str, str] | None) -> str:
    width = max(len(h.name) for h in CATALOG)
    rows = []
    for h in CATALOG:
        state = "unknown  " if plugins is None else ("installed" if h.id in plugins else "missing  ")
        extra = f"  [{h.needs}]" if h.needs else ""
        optional = "" if h.recommended else "  (optional)"
        rows.append(f"  {state}  {h.name:<{width}}  {h.adds} ({h.used_by}){extra}{optional}")
    return "\n".join(rows)


def report(plugins: dict[str, str] | None, root: Path | None) -> str:
    lines = ["greenlight works on its own. These Claude Code plugins make its roles better when they are installed:", "",
             table(plugins), ""]
    if plugins is None:
        lines.append("Claude Code's plugin list could not be read (is `claude` on the PATH?), so nothing is shown as installed.")
    gaps = missing(plugins)
    if gaps:
        lines += [f"{len(gaps)} recommended helper(s) not installed: {', '.join(h.name for h in gaps)}.",
                  "To install them, type this yourself. The leading ! runs it in your own shell, so Claude Code's settings",
                  "change between prompts and not during a tool call, and greenlight does not install anything on its own:", "",
                  f"  {install_line()}", "",
                  "Not now: nothing happens. Do not ask again: bdd helpers --decline"]
    elif plugins is not None:
        lines.append("Every recommended helper is installed.")
    if root is not None and declined(root):
        lines.append("(You chose not to be asked again in this project.)")
    return "\n".join(lines)


def as_json(plugins: dict[str, str] | None, root: Path | None) -> str:
    rows = [{**asdict(h), "installed": None if plugins is None else h.id in plugins,
             "version": (plugins or {}).get(h.id)} for h in CATALOG]
    return json.dumps({"claude_found": plugins is not None, "declined": declined(root), "helpers": rows,
                       "install": install_line() if missing(plugins) else None}, indent=2)


def choose(names: list[str]) -> list[Helper]:
    by_name = {h.name: h for h in CATALOG}
    unknown = [n for n in names if n not in by_name]
    if unknown:
        raise UsageError(f"not a helper: {', '.join(unknown)}; the helpers are {', '.join(by_name)}")
    return [by_name[n] for n in names]


def run_install(chosen: list[Helper], run=subprocess.run) -> int:
    program = claude_program()
    if program is None:
        raise UsageError("`claude` is not on the PATH, so nothing can be installed from here")
    failed = 0
    for helper in chosen:
        try:
            done = run([program, "plugin", "install", helper.id], capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=INSTALL_TIMEOUT, stdin=subprocess.DEVNULL)
            ok, said = done.returncode == 0, (done.stdout or done.stderr or "").strip().splitlines()
        except (OSError, subprocess.SubprocessError) as exc:
            ok, said = False, [str(exc)]
        failed += not ok
        print(f"{'installed' if ok else 'FAILED   '}  {helper.name}" + (f": {said[-1]}" if said else ""))
    return 1 if failed else 0


def run(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="bdd helpers", description="The helper plugins greenlight's roles can use.")
    ap.add_argument("action", nargs="?", choices=["list", "install"], default="list")
    ap.add_argument("names", nargs="*", help="for install: the helpers (default: every missing recommended one)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--yes", action="store_true", help="install: confirm that these plugins are to be installed")
    ap.add_argument("--decline", action="store_true", help="remember that the person does not want to be asked again")
    args = ap.parse_args(argv)
    root = cfg.find_root()
    try:
        if args.decline:
            if root is None:
                raise UsageError("not inside a greenlight project (no .bdd directory found)")
            store.write_json(record_path(root), {"schema": store.SCHEMA, "decision": "declined", "at": store.utc_now()})
            print("noted: greenlight will not offer the helper plugins again in this project (`bdd helpers` still lists them)")
            return 0
        plugins = installed()
        if args.action == "list":
            print(as_json(plugins, root) if args.json else report(plugins, root))
            return 0
        chosen = choose(args.names) if args.names else missing(plugins)
        chosen = [h for h in chosen if h.id not in (plugins or {})]
        if not chosen:
            print("nothing to install: those helpers are already installed")
            return 0
        if not args.yes:
            print("this would install: " + ", ".join(h.name for h in chosen) + "\nadd --yes to confirm", file=sys.stderr)
            return 2
        return run_install(chosen)
    except (UsageError, StoreError) as exc:
        print(f"bdd helpers: {exc}", file=sys.stderr)
        return 2
