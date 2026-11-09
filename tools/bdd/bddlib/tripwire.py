"""Detect tampering by its effect, whatever command or tool produced it.

Text checks on a shell command (``guard``) can always be outrun by another spelling, so after every
file or shell tool call this looks at the result instead:

* the files that make greenlight enforce anything (Claude Code settings, hooks and plugin records, the
  plugin's own files, ``.bdd/config.toml``) against a baseline of their hashes;
* the locked specs and bound steps against their locks;
* the project's own test environment: the Python interpreter and test packages, and the entry points and manifests of
  the installed node test tooling.

A difference is reported to the model at once and kept in ``.bdd/.integrity/violations.json``, with the
digest of what was found; the ``implement`` and ``verify`` gates refuse to pass while one is open. A
violation closes when the file is back to what it was, or when the person acknowledges it by typing
``/greenlight:approve integrity #n <reason>`` (``integrityack``); nothing else closes it, because no
signal on this machine tells the person's edit apart from one a tool call, a background shell or a
delayed write of the agent made.

The baseline moves only when the person submits a prompt (``--accept``) and no such violation is open,
so a change made between prompts that no tool call saw is accepted there; the first prompt in a project
takes the first baseline. Only the plugin copy Claude Code runs is watched (Codex is soft, D11). Its files
are keyed by their path in the plugin and its folder and version are recorded: at a prompt after Claude
Code installed a new version, the plugin's files are taken afresh with one line on record instead of a
list of files.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from . import claudepaths, config as cfg, lockfile, runner, sharedvocab, store
from .errors import StoreError, UsageError

INTEGRITY_DIR = ".integrity"
BASELINE = "baseline.json"
VIOLATIONS = "violations.json"
ACKNOWLEDGEMENTS = "acknowledgements.json"
SCHEMA = 1
BASELINE_WHAT = "integrity baseline"
ACKS_WHAT = "integrity acknowledgements"
CHECK_WHAT = "integrity check"
FILE_WHAT = "enforcement file"
RESTORED_BY_ACCEPT = (BASELINE_WHAT, "baseline backup", ACKS_WHAT)      # the next prompt writes these afresh
ACCEPTED_KEPT = 50
PLUGIN_KEY = "plugin:"
PLUGIN_MANIFEST = ".claude-plugin/plugin.json"
PLUGIN_UPDATED = "plugin updated"
ACKNOWLEDGE_COMMAND = "/greenlight:approve integrity #n <reason>"
PROJECT_FILES = (".claude/settings.json", ".claude/settings.local.json", f"{cfg.BDD_DIR}/config.toml",
                 f"{cfg.BDD_DIR}/standards.md", f"{cfg.BDD_DIR}/{sharedvocab.LOCK_NAME}",
                 ".codex/hooks.json", ".codex/config.toml")      # Codex's own: they keep its hooks running
INSTALLED = "plugins/installed_plugins.json"                    # in the Claude Code folder: which copy of each plugin runs
REGISTRY_FILES = (INSTALLED, "plugins/known_marketplaces.json")
PLUGIN_FILES = ("hooks/hooks.json", ".claude-plugin/plugin.json", "tools/bdd/bdd", "tools/bdd/main.py")
PLUGIN_TREES = ("tools/bdd/bddlib",)
SKIPPED = {"__pycache__", "node_modules", ".git"}
_FEATURE_DIR = re.compile(r"(FEAT-\d+)(?:-.*)?")
_UNKNOWN = object()


# -- what is watched -----------------------------------------------------------------------
def _files_under(folder: Path) -> list[Path]:
    found = []
    for dirpath, dirnames, filenames in os.walk(folder):
        dirnames[:] = [d for d in dirnames if d not in SKIPPED]
        found += [Path(dirpath) / name for name in filenames]
    return found


PACKAGES = ("_pytest", "pytest", "pluggy", "iniconfig", "packaging", "pytest_bdd", "gherkin", "parse", "parse_type",
            "mako", "markupsafe")                              # what runs the tests and decides which ones


def environment_files(root: Path) -> list[Path]:
    """The project's own interpreter and what steers it: pyvenv.cfg, startup hooks (.pth, sitecustomize) and the test
    runner's packages. Only when the environment lives inside the project."""
    try:
        interpreter = Path(runner.project_python(root))
    except UsageError:
        return []
    if not interpreter.is_file() or root.resolve() not in interpreter.resolve().parents:
        return []
    environment = interpreter.parent.parent
    found = [interpreter, environment / "pyvenv.cfg"]
    for site in [environment / "Lib" / "site-packages", *environment.glob("lib/python*/site-packages")]:
        if not site.is_dir():
            continue
        found += [*site.glob("*.pth"), site / "sitecustomize.py", site / "usercustomize.py"]
        found += [*site.glob("*.dist-info/entry_points.txt"), *site.glob("*.egg-info/entry_points.txt")]  # how plugins register
        for package in PACKAGES:
            found += _files_under(site / package)
    return [p for p in found if p.is_file()]


# The programs a test run starts and the manifests that name their versions, relative to node_modules. Whole packages are
# thousands of files, too many to hash on every tool call within the hook's time budget.
NODE_ENTRY_FILES = (".package-lock.json", ".pnpm/lock.yaml", "@playwright/test/package.json", "@playwright/test/cli.js", "playwright/package.json",
                    "playwright/lib/program.js", "playwright-core/package.json", "playwright-bdd/package.json",
                    "playwright-bdd/dist/cli/index.js")


def _node_entry_copies(modules: Path, entry: str) -> list[Path]:
    """Where an entry point is installed. npm puts every package in ``node_modules``. pnpm links only the project's own
    dependencies there and keeps all packages, the dependencies of dependencies included (``playwright`` under
    ``@playwright/test``), in ``node_modules/.pnpm/<name>@<version>/node_modules/<name>``. Every installed copy is watched,
    the one at the top (a link into the store, with pnpm) and each version or peer-dependency variant in the store: which
    of them a run loads depends on who asks for it."""
    parts = entry.split("/")
    name = "/".join(parts[:2] if parts[0].startswith("@") else parts[:1])
    stored = sorted((modules / ".pnpm").glob(f"{name.replace('/', '+')}@*/node_modules/{entry}"))
    return [modules / entry, *stored]


def node_environment_files(root: Path) -> list[Path]:
    """The installed node tooling next to a bound ``package.json``: the package manager's record of the installed tree (npm's
    ``.package-lock.json``, pnpm's ``.pnpm/lock.yaml``), the entry points the run starts and the manifests of the test packages,
    wherever the package manager put them. Only the entry points: the rest of the packages is guarded against writes by agents
    and covered by the bound lockfile, not watched. An entry point a project does not have (the Cucumber adapter has no
    Playwright) is not watched; one that was watched and is gone is reported as a change."""
    found: list[Path] = []
    for manifest in cfg.load(root).support_files:
        modules = manifest.parent / "node_modules"
        if manifest.name == "package.json" and modules.is_dir():
            for entry in NODE_ENTRY_FILES:
                found += _node_entry_copies(modules, entry)
    return [p for p in found if p.is_file()]


def watched_files(root: Path, plugin_root: Path | None) -> list[Path]:
    """Every existing file whose change would weaken enforcement."""
    config_dir = claudepaths.config_dir()
    candidates = [root / rel for rel in PROJECT_FILES] + [config_dir / "settings.json"]
    candidates += [config_dir / rel for rel in REGISTRY_FILES]           # which plugins and which copies Claude Code runs
    candidates += [home / name for home in {claudepaths.codex_home(), Path.home() / ".codex"} for name in ("hooks.json", "config.toml")]
    candidates += _files_under(root / ".claude" / "hooks")
    candidates += environment_files(root) + node_environment_files(root)
    candidates += sharedvocab.protected_files(cfg.load(root).vocabulary_file)          # the shared vocabularies the project includes
    candidates += [m.path / cfg.BDD_DIR / "config.toml" for m in cfg.load(root).workspace]      # the rules a member runs by
    candidates += plugin_files(plugin_root) if plugin_root is not None else []
    return sorted({p for p in candidates if p.is_file()})


def plugin_files(plugin_root: Path) -> list[Path]:
    candidates = [plugin_root / rel for rel in PLUGIN_FILES]
    for tree in PLUGIN_TREES:
        candidates += _files_under(plugin_root / tree)
    return [p for p in candidates if p.is_file()]


def snapshot(root: Path, plugin_root: Path | None) -> dict[str, str]:
    """Digest of every watched file: the plugin's by ``plugin:<path in the plugin>``, which stays the same across
    versions, the others by their absolute path."""
    found = {p.resolve().as_posix(): lockfile.file_digest(p) for p in watched_files(root, None)}
    if plugin_root is not None:
        found |= {PLUGIN_KEY + p.relative_to(plugin_root).as_posix(): lockfile.file_digest(p) for p in plugin_files(plugin_root)}
    return found


def _differences(current: dict[str, str], baseline: dict, plugin_root: Path | None) -> list[dict]:
    """What differs from the baseline. Without a plugin folder (a caller other than Claude Code's hooks) the plugin's
    recorded files are neither compared nor dropped."""
    files = baseline["files"] if plugin_root is not None else {k: v for k, v in baseline["files"].items() if not k.startswith(PLUGIN_KEY)}
    return compare(current, files)


# -- the plugin ------------------------------------------------------------------------------
def plugin_version(plugin_root: Path) -> str | None:
    try:
        data = json.loads((plugin_root / PLUGIN_MANIFEST).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    version = data.get("version") if isinstance(data, dict) else None
    return version if isinstance(version, str) else None


def plugin_record(plugin_root: Path) -> dict:
    return {"root": plugin_root.as_posix(), "version": plugin_version(plugin_root)}


def names_this_copy(plugin_root: Path) -> bool:
    """Does Claude Code's own record of installed plugins hold exactly one entry for this plugin, naming exactly this folder
    of its plugin cache (``plugins/cache/<marketplace>/<plugin>/<version>``) at this folder's version?"""
    cache = (claudepaths.config_dir() / "plugins" / "cache").resolve()
    folder = plugin_root.resolve()
    parts = folder.relative_to(cache).parts if folder.is_relative_to(cache) else ()
    version = plugin_version(plugin_root)
    try:
        data = json.loads((claudepaths.config_dir() / INSTALLED).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    plugins = data.get("plugins") if isinstance(data, dict) else None
    entries = plugins.get(f"{parts[1]}@{parts[0]}") if len(parts) == 3 and isinstance(plugins, dict) else None
    if version is None or not isinstance(entries, list) or len(entries) != 1 or not isinstance(entries[0], dict):
        return False
    path = entries[0].get("installPath")
    return isinstance(path, str) and entries[0].get("version") == version and Path(path).resolve() == folder


def plugin_update(baseline: dict, plugin_root: Path | None) -> dict | None:
    """The update to name at a prompt when Claude Code now runs another version of the plugin, else None.

    It changes only how the prompt reports what it takes, never what it takes: a prompt with a violation open takes
    nothing, and the tool-call check never takes plugin files afresh (there a new version is a set of findings like any
    other change). It counts only for another folder of Claude Code's plugin cache that Claude Code's own record names
    exactly, at another version."""
    old = baseline.get("plugin")
    if plugin_root is None or not old or old.get("root") == plugin_root.as_posix():
        return None
    new = plugin_record(plugin_root)
    if old.get("version") == new["version"] or not names_this_copy(plugin_root):
        return None
    return {"kind": PLUGIN_UPDATED, "from": old.get("version"), "to": new["version"]}


def updated_text(entry: dict) -> str:
    return f"plugin updated from {entry['from'] or 'an earlier version'} to {entry['to'] or 'an unknown version'}"


def _normalized(data: dict) -> dict:
    """A baseline in the current form. One written before plugin files were keyed by their path in the plugin has them by
    absolute path, under the folder that holds the plugin's manifest; their keys are rewritten and that folder and its
    version (if it is still there) are recorded. It has no ``taken_at`` until the next prompt writes one."""
    if "plugin" in data:
        return data
    suffix = "/" + PLUGIN_MANIFEST
    manifest = next((k for k in data["files"] if k.endswith(suffix)), None)
    if manifest is None:
        return {**data, "plugin": None}
    old_root = manifest.removesuffix(suffix)
    prefix = old_root + "/"
    files = {(PLUGIN_KEY + k.removeprefix(prefix) if k.startswith(prefix) else k): v for k, v in data["files"].items()}
    return {**data, "files": files, "plugin": {"root": old_root, "version": plugin_version(Path(old_root))}}


# -- stored data ---------------------------------------------------------------------------
def path_of(root: Path, name: str) -> Path:
    return root / cfg.BDD_DIR / INTEGRITY_DIR / name


def load(root: Path, name: str, empty: dict) -> dict:
    path = path_of(root, name)
    if not path.is_file():
        return empty
    data = store.read_json(path, f"the integrity {name.removesuffix('.json')}")
    if data.get("schema") != SCHEMA:
        raise StoreError(f"{path} has an unsupported schema {data.get('schema')!r}")
    return data


def backup_path(root: Path) -> Path:
    """A second copy of the baseline outside the project, so deleting the project's copy loses nothing."""
    key = hashlib.sha256(root.resolve().as_posix().encode("utf-8")).hexdigest()[:16]
    return claudepaths.config_dir() / "greenlight" / key / BASELINE


def _valid_baseline(data: object) -> bool:
    files = data.get("files") if isinstance(data, dict) else None
    return (isinstance(data, dict) and data.get("schema") == SCHEMA and isinstance(files, dict)
            and all(isinstance(k, str) and isinstance(v, str) for k, v in files.items()))


def load_backup(root: Path) -> dict | None:
    """The backup copy, or None if there is none. A backup that exists but is unusable raises StoreError."""
    path = backup_path(root)
    if not path.is_file():
        return None
    data = store.read_json(path, "the baseline backup")
    if not _valid_baseline(data):
        raise StoreError(f"{path} is not a valid integrity baseline")
    return data


def baseline_data(root: Path) -> dict | None:
    """The project's baseline in the current form, or None if there is none."""
    data = load(root, BASELINE, {})
    if data and not _valid_baseline(data):
        raise StoreError(f"{path_of(root, BASELINE)} is not a valid integrity baseline")
    return _normalized(data) if data else None


def load_baseline(root: Path) -> dict[str, str] | None:
    data = baseline_data(root)
    return data["files"] if data else None


def _usable_backup(root: Path) -> dict | None:
    try:
        backup = load_backup(root)
    except StoreError:
        return None                                       # a corrupt backup is replaced by the new baseline
    return _normalized(backup) if backup else None


def kept_baseline(root: Path) -> dict | None:
    """The baseline to build on: the project's copy if it is readable, else the backup."""
    try:
        return baseline_data(root) or _usable_backup(root)
    except StoreError:
        return _usable_backup(root)


def write_baseline(root: Path, data: dict, backup: bool = True) -> None:
    store.write_json(path_of(root, BASELINE), data)
    if backup:
        try:
            store.write_json(backup_path(root), data)
        except OSError:
            pass                                                     # the backup is a safeguard, not a requirement


def violations(root: Path) -> list[dict]:
    return load(root, VIOLATIONS, {"schema": SCHEMA, "items": []})["items"]


def open_violations(root: Path) -> list[dict]:
    return [v for v in violations(root) if v["open"]]


def save_violations(root: Path, items: list[dict]) -> None:
    store.write_json(path_of(root, VIOLATIONS), {"schema": SCHEMA, "items": items})


@contextmanager
def exclusive(root: Path):
    """One writer at a time for the integrity data: hooks of parallel agents and the two prompt hooks run at once."""
    with store.file_lock(path_of(root, VIOLATIONS)):
        yield


def close(item: dict, how: str, now: str) -> None:
    item["open"], item["closed_at"], item["closed_by"] = False, now, how


# -- findings ------------------------------------------------------------------------------
def compare(current: dict[str, str], baseline: dict[str, str]) -> list[dict]:
    found = [{"kind": "changed", "path": path} for path in sorted(current) if path in baseline and current[path] != baseline[path]]
    found += [{"kind": "added", "path": path} for path in sorted(set(current) - set(baseline))]
    found += [{"kind": "removed", "path": path} for path in sorted(set(baseline) - set(current))]
    return [{**f, "what": FILE_WHAT, "digest": current.get(f["path"])} for f in found]


def baseline_findings(root: Path, plugin_root: Path | None, baseline: dict[str, str]) -> list[dict]:
    return compare(snapshot(root, plugin_root), baseline)


def lock_findings(root: Path, label: str = "") -> list[dict]:
    """Locks that no longer match the disk, here and in every member repository of a workspace (named by ``label``)."""
    found = []
    if not label:
        for member in cfg.load(root).workspace:
            if member.path.is_dir() and (member.path / cfg.BDD_DIR).is_dir():
                found += lock_findings(member.path, f"{member.name}: ")
    features = store.features_dir(root)
    for feature_dir in sorted(p for p in features.glob("FEAT-*") if p.is_dir()) if features.is_dir() else []:
        match = _FEATURE_DIR.fullmatch(feature_dir.name)
        if match is None or not (feature_dir / lockfile.LOCK_FILE).is_file():
            continue
        for v in lockfile.check(root, feature_dir, match.group(1)):
            found.append({"kind": v.kind, "path": v.path, "what": f"{label}{match.group(1)} {v.scope} lock"})
    return found


def _key(finding: dict) -> tuple[str, str, str]:
    return finding["what"], finding["kind"], finding["path"]


def _settle(root: Path) -> list[dict]:
    """Apply the person's confirmed acknowledgements. Unreadable acknowledgements are a finding, never a reason to skip
    the comparison."""
    from . import integrityack
    try:
        integrityack.settle_held(root)
    except (StoreError, OSError, KeyError, TypeError, ValueError, AttributeError):
        return [{"kind": "corrupt", "path": path_of(root, ACKNOWLEDGEMENTS).as_posix(), "what": ACKS_WHAT}]
    return []


def check(root: Path, plugin_root: Path | None, tool: str | None = None) -> list[dict]:
    """Compare everything watched with what it should be. Returns the violations that are new.

    A missing baseline is a violation until the person's next prompt takes it; only deleting it makes it vanish later."""
    with exclusive(root):
        findings = _settle(root)
        return _check(root, plugin_root, tool, findings)


def _check(root: Path, plugin_root: Path | None, tool: str | None, findings: list[dict]) -> list[dict]:
    current = snapshot(root, plugin_root)
    try:
        baseline = baseline_data(root)
    except StoreError:
        findings.append({"kind": "corrupt", "path": path_of(root, BASELINE).as_posix(), "what": BASELINE_WHAT})
        baseline = None
    findings += lock_findings(root)
    if baseline is None:                                   # still compare with the backup, if there is one
        if not any(f["what"] == BASELINE_WHAT for f in findings):
            findings.insert(0, {"kind": "missing", "path": path_of(root, BASELINE).as_posix(), "what": BASELINE_WHAT})
        try:
            backup = load_backup(root)
        except StoreError:
            findings.append({"kind": "corrupt", "path": backup_path(root).as_posix(), "what": "baseline backup"})
            backup = None
        if backup:
            findings += _differences(current, _normalized(backup), plugin_root)
    else:
        findings += _differences(current, baseline, plugin_root)
    return _record(root, findings, tool)


def _record(root: Path, findings: list[dict], tool: str | None) -> list[dict]:
    seen = {_key(f): f for f in findings}
    items = violations(root)
    before = json.loads(json.dumps(items))
    now = store.utc_now()
    for item in items:
        if item["open"] and _key(item) not in seen:
            close(item, "undone", now)
        elif item["open"] and item["what"] == FILE_WHAT and item.get("digest", _UNKNOWN) != seen[_key(item)]["digest"]:
            close(item, "changed again", now)                # what was reported is not what is there now
    held = {_key(item) for item in items if item["open"]}
    new = [{**f, "id": len(items) + i, "at": now, "tool": tool, "open": True}
           for i, f in enumerate((f for f in findings if _key(f) not in held), start=1)]
    if new or items != before:
        save_violations(root, items + new)
    return new


def _blocking(item: dict) -> bool:
    """Does this open violation stop the next prompt from taking the baseline? Every one does, except the integrity
    data itself, which the prompt writes afresh."""
    return item["open"] and item["what"] not in RESTORED_BY_ACCEPT


def accept(root: Path, plugin_root: Path | None) -> list[dict] | None:
    """Take the current state of the enforcement files as the baseline.

    Returns what differed from the previous baseline (also kept in its ``accepted`` history, so a change
    that slipped past the tool-call checks is at least on record), or None if a violation is open and
    nothing was accepted. A missing or unreadable baseline does not stop this (restoring it is what this
    is for); the differences from the previous baseline, or its backup copy, are reported and recorded
    like any other accepted change. A plugin update comes first in the list."""
    with exclusive(root):
        if _settle(root):
            _set_aside(path_of(root, ACKNOWLEDGEMENTS))
        _close_undone(root, plugin_root)
        if any(_blocking(v) for v in violations(root)):
            return None
        return _take(root, plugin_root)


def _close_undone(root: Path, plugin_root: Path | None) -> None:
    """Close the open violations whose finding is gone, as the tool-call check would: a file put back, a changed file in a
    plugin copy that no longer runs, or one an older greenlight named by a path it no longer uses. Nothing new is opened."""
    kept = kept_baseline(root)
    items = violations(root)
    if kept is None or not any(v["open"] for v in items):
        return
    findings = {_key(f) for f in lock_findings(root) + _differences(snapshot(root, plugin_root), kept, plugin_root)}
    now, closed = store.utc_now(), False
    for v in items:
        unseen_plugin = plugin_root is None and v["path"].startswith(PLUGIN_KEY)
        if v["open"] and not unseen_plugin and v["what"] not in RESTORED_BY_ACCEPT + (CHECK_WHAT,) and _key(v) not in findings:
            close(v, "undone", now)
            closed = True
    if closed:
        save_violations(root, items)


def _set_aside(path: Path) -> None:
    """Keep an unreadable file for inspection under another name; the next write starts it afresh."""
    path.replace(path.with_name(f"{path.name}.unreadable-{datetime.now(timezone.utc):%Y%m%dT%H%M%S}"))


def _take(root: Path, plugin_root: Path | None) -> list[dict]:
    items = violations(root)
    kept = kept_baseline(root)                                   # the project's copy, else the backup
    current = snapshot(root, plugin_root)
    update = plugin_update(kept, plugin_root) if kept else None
    now = store.utc_now()
    changes = [{**f, "at": now} for f in _differences(current, kept, plugin_root)] if kept else []
    if update:
        changes = [{**update, "at": now}] + [c for c in changes if not c["path"].startswith(PLUGIN_KEY)]
    history = ((kept.get("accepted") or []) if kept else []) + changes
    unseen = {k: v for k, v in (kept or {"files": {}})["files"].items() if k.startswith(PLUGIN_KEY)} if plugin_root is None else {}
    write_baseline(root, {"schema": SCHEMA, "files": {**unseen, **current},
                          "plugin": plugin_record(plugin_root) if plugin_root is not None else (kept or {}).get("plugin"),
                          "taken_at": datetime.now(timezone.utc).isoformat(), "accepted": history[-ACCEPTED_KEPT:]})
    if any(v["open"] for v in items):
        for v in items:
            if v["open"]:
                close(v, "prompt", now)
        save_violations(root, items)
    return changes


def summary(root: Path) -> tuple[str, str]:
    """(ok | warn, one line) for ``bdd doctor``."""
    held = open_violations(root)
    if held:
        return "warn", f"{len(held)} violation(s) open (`bdd status` lists them)"
    baseline = baseline_data(root)
    if baseline is None:
        return "warn", "no baseline yet; the next prompt takes it"
    version = (baseline.get("plugin") or {}).get("version")
    updates = [e for e in baseline.get("accepted") or [] if e.get("kind") == PLUGIN_UPDATED]
    if updates and updates[-1]["to"] == version:
        return "ok", f"{updated_text(updates[-1])}; baseline refreshed"
    return "ok", "no violation open"


def describe(item: dict) -> str:
    verb = {"changed": "was changed", "added": "was added", "removed": "was removed", "missing": "is missing"}.get(
        item["kind"], f"is {item['kind']}")
    path = item["path"]
    shown = "the plugin's " + path.removeprefix(PLUGIN_KEY) if path.startswith(PLUGIN_KEY) else path
    return f"{shown} ({item['what']}) {verb}"


def listing(items: list[dict]) -> str:
    return "".join(f"\n  #{v['id']} {describe(v)}" + (f" (sha256 {v['digest'][:12]})" if v.get("digest") else "") for v in items)


def how_to_acknowledge(items: list[dict]) -> str:
    """The one line that closes the enforcement-file violations listed, in the person's words."""
    files = [v for v in items if v["what"] == FILE_WHAT]
    if not files:
        return "The next prompt restores the integrity data; a lock is changed through /greenlight:change."
    line = "/greenlight:approve integrity " + ",".join(f"#{v['id']}" for v in files) + " <reason>"
    return (f"If the person made these changes or wants them, they type one line in Claude Code: {line} (it closes those "
            "violations if the files are still as listed). Anything else: undo it, for example with git.")


def show_open(root: Path, offer_ack: bool = True) -> str:
    held = open_violations(root)
    return listing(held) + ("\n" + how_to_acknowledge(held) if offer_ack and held else "")


# -- hook entry ----------------------------------------------------------------------------
def plugin_root() -> Path | None:
    value = os.environ.get("CLAUDE_PLUGIN_ROOT")
    return Path(value).resolve() if value else None


def main(argv: list[str]) -> int:
    """PostToolUse (no arguments) or UserPromptSubmit (``--accept``). Does nothing outside a project."""
    if argv not in ([], ["--accept"]):
        print("usage: bdd tripwire [--accept]   (reads hook input on stdin)", file=sys.stderr)
        return 2
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        return 0
    if not isinstance(payload, dict):
        return 0
    root = cfg.find_root(Path(payload.get("cwd") or "."))
    if root is None:
        return 0
    try:
        if argv:
            return run_accept(root, plugin_root())
        new = check(root, plugin_root(), payload.get("tool_name"))
        shown = show_open(root) if new else ""
    except Exception as exc:                                     # any failure fails closed, never open
        _record_failure(root, exc)
        print(f"greenlight: the integrity check could not run ({exc}). The implement and verify gates will refuse "
              "until it runs again; tell the person.", file=sys.stderr)
        return 2
    if new:
        print("greenlight: integrity check failed after this tool call:" + listing(new)
              + "\nThe implement and verify gates will refuse to pass until this is resolved. Do not try to undo a change "
              "you did not make; tell the person what you see. Open now:" + shown, file=sys.stderr)
        return 2
    return 0


def _record_failure(root: Path, exc: Exception) -> None:
    """Keep the gates shut after a check that could not run: an open violation that the next check that runs closes. If
    even that cannot be written, the violations file is unreadable, and the gates refuse on that."""
    try:
        items = violations(root)
        if not any(v["open"] and v["what"] == CHECK_WHAT for v in items):
            items.append({"kind": "failed", "path": f"{type(exc).__name__}: {exc}"[:200], "what": CHECK_WHAT,
                          "id": len(items) + 1, "at": store.utc_now(), "tool": None, "open": True})
            save_violations(root, items)
    except Exception:
        pass


def run_accept(root: Path, plugin: Path | None, offer_ack: bool = True) -> int:
    """UserPromptSubmit: never blocks the prompt (exit 2 would), and says what it accepted or why not. ``plugin`` is the
    copy Claude Code's hooks run, None where none is watched (Codex), which also gets no offer of an acknowledgement it
    cannot type."""
    try:
        changes = accept(root, plugin)
        held = len([v for v in open_violations(root) if _blocking(v)]) if changes is None else 0
        shown = show_open(root, offer_ack) if changes is None else ""
    except Exception as exc:                                     # the prompt goes through; nothing was accepted
        print(f"greenlight: the integrity baseline could not be refreshed ({exc}); the implement and verify gates "
              "will refuse until .bdd/.integrity is readable again.")
        return 0
    if changes is None:
        print(f"greenlight: an integrity violation is still open, so the baseline was not refreshed ({held} open):" + shown)
        return 0
    for update in (c for c in changes if c["kind"] == PLUGIN_UPDATED):
        print(f"greenlight: {updated_text(update)}; baseline refreshed.")
    others = [c for c in changes if c["kind"] != PLUGIN_UPDATED]
    if others:
        print("greenlight: accepted changes made since the last check: "
              + "; ".join(f"{c['path']} {c['kind']}" for c in others) + ".")
    return 0
