"""Detect tampering by its effect, whatever command or tool produced it.

Text checks on a shell command (``guard``) can always be outrun by another spelling, so after every
file or shell tool call this looks at the result instead:

* the files that make greenlight enforce anything (Claude Code settings and hooks, the plugin's own
  files, ``.bdd/config.toml``) against a baseline of their hashes;
* the locked specs and bound steps against their locks.

A difference is reported to the model at once and kept in ``.bdd/.integrity/violations.json``; the
``implement`` and ``verify`` gates refuse to pass while one is open. A violation closes when the file
is back to what it was.

The baseline moves only when the person submits a prompt and nothing is open (``--accept``): an edit
made by the person between prompts is accepted, an edit made by the agent during a turn has already
been caught by then. The first run in a project records the baseline.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path

from . import claudepaths, config as cfg, lockfile, runner, store
from .errors import StoreError, UsageError

INTEGRITY_DIR = ".integrity"
BASELINE = "baseline.json"
VIOLATIONS = "violations.json"
SCHEMA = 1
BASELINE_WHAT = "integrity baseline"
RESTORED_BY_ACCEPT = (BASELINE_WHAT, "baseline backup")      # accepting writes both copies afresh
ACCEPTED_KEPT = 50
PROJECT_FILES = (".claude/settings.json", ".claude/settings.local.json", f"{cfg.BDD_DIR}/config.toml")
PLUGIN_FILES = ("hooks/hooks.json", ".claude-plugin/plugin.json", "tools/bdd/bdd", "tools/bdd/main.py")
PLUGIN_TREES = ("tools/bdd/bddlib",)
SKIPPED = {"__pycache__", "node_modules", ".git"}
_FEATURE_DIR = re.compile(r"(FEAT-\d+)(?:-.*)?")


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
        found +=[*site.glob("*.dist-info/entry_points.txt")]            # how plugins register themselves
        for package in PACKAGES:
            found += _files_under(site / package)
    return [p for p in found if p.is_file()]


def watched_files(root: Path, plugin_root: Path | None) -> list[Path]:
    """Every existing file whose change would weaken enforcement."""
    candidates = [root / rel for rel in PROJECT_FILES] + [claudepaths.config_dir() / "settings.json"]
    candidates += _files_under(root / ".claude" / "hooks")
    candidates += environment_files(root)
    if plugin_root is not None:
        candidates += [plugin_root / rel for rel in PLUGIN_FILES]
        for tree in PLUGIN_TREES:
            candidates += _files_under(plugin_root / tree)
    return sorted({p for p in candidates if p.is_file()})


def snapshot(root: Path, plugin_root: Path | None) -> dict[str, str]:
    return {p.resolve().as_posix(): lockfile.file_digest(p) for p in watched_files(root, plugin_root)}


# -- stored data ---------------------------------------------------------------------------
def _path(root: Path, name: str) -> Path:
    return root / cfg.BDD_DIR / INTEGRITY_DIR / name


def _load(root: Path, name: str, empty: dict) -> dict:
    path = _path(root, name)
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


def load_baseline(root: Path) -> dict[str, str] | None:
    data = _load(root, BASELINE, {})
    if data and not _valid_baseline(data):
        raise StoreError(f"{_path(root, BASELINE)} is not a valid integrity baseline")
    return data.get("files") if data else None


def violations(root: Path) -> list[dict]:
    return _load(root, VIOLATIONS, {"schema": SCHEMA, "items": []})["items"]


def open_violations(root: Path) -> list[dict]:
    return [v for v in violations(root) if v["open"]]


def _save_violations(root: Path, items: list[dict]) -> None:
    store.write_json(_path(root, VIOLATIONS), {"schema": SCHEMA, "items": items})


# -- findings ------------------------------------------------------------------------------
def baseline_findings(root: Path, plugin_root: Path | None, baseline: dict[str, str]) -> list[dict]:
    current = snapshot(root, plugin_root)
    found = [{"kind": "changed", "path": path} for path in sorted(current) if path in baseline and current[path] != baseline[path]]
    found += [{"kind": "added", "path": path} for path in sorted(set(current) - set(baseline))]
    found += [{"kind": "removed", "path": path} for path in sorted(set(baseline) - set(current))]
    return [{**f, "what": "enforcement file"} for f in found]


def lock_findings(root: Path) -> list[dict]:
    found = []
    features = store.features_dir(root)
    for feature_dir in sorted(p for p in features.glob("FEAT-*") if p.is_dir()) if features.is_dir() else []:
        match = _FEATURE_DIR.fullmatch(feature_dir.name)
        if match is None or not (feature_dir / lockfile.LOCK_FILE).is_file():
            continue
        for v in lockfile.check(root, feature_dir, match.group(1)):
            found.append({"kind": v.kind, "path": v.path, "what": f"{match.group(1)} {v.scope} lock"})
    return found


def _key(finding: dict) -> tuple[str, str, str]:
    return finding["what"], finding["kind"], finding["path"]


def check(root: Path, plugin_root: Path | None, tool: str | None = None) -> list[dict]:
    """Compare everything watched with what it should be. Returns the violations that are new.

    A missing baseline is a violation, not a first run: the baseline is taken when the person submits a
    prompt, which happens before any tool call, so only deleting it makes it vanish."""
    baseline = load_baseline(root)
    findings = lock_findings(root)
    if baseline is None:                                   # still compare with the backup, if there is one
        findings.insert(0, {"kind": "missing", "path": _path(root, BASELINE).as_posix(), "what": BASELINE_WHAT})
        try:
            backup = load_backup(root)
        except StoreError:
            findings.append({"kind": "corrupt", "path": backup_path(root).as_posix(), "what": "baseline backup"})
            backup = None
        findings += baseline_findings(root, plugin_root, backup["files"]) if backup else []
    else:
        findings += baseline_findings(root, plugin_root, baseline)
    current = {_key(f) for f in findings}
    items = violations(root)
    before = json.loads(json.dumps(items))
    now = store.utc_now()
    for item in items:
        if item["open"] and _key(item) not in current:
            item["open"], item["closed_at"] = False, now
    held = {_key(item) for item in items if item["open"]}
    new = [{**f, "id": len(items) + i, "at": now, "tool": tool, "open": True}
           for i, f in enumerate((f for f in findings if _key(f) not in held), start=1)]
    if new or items != before:
        _save_violations(root, items + new)
    return new


def _usable_backup(root: Path) -> dict | None:
    try:
        return load_backup(root)
    except StoreError:
        return None                                       # a corrupt backup is replaced by the new baseline


def accept(root: Path, plugin_root: Path | None) -> list[dict] | None:
    """Take the current state of the enforcement files as the baseline.

    Returns what differed from the previous baseline (also kept in its ``accepted`` history, so a change
    that slipped past the tool-call checks is at least on record), or None if a violation is open and
    nothing was accepted. A missing baseline does not stop this (restoring it is what this is for), but
    the differences from the backup copy are reported and recorded like any other accepted change."""
    items = violations(root)
    if any(v["open"] and v["what"] not in RESTORED_BY_ACCEPT for v in items):
        return None
    kept = _load(root, BASELINE, {})                                 # the project's copy, else the backup
    kept = kept if _valid_baseline(kept) else (_usable_backup(root) or {})
    now = store.utc_now()
    changes = [{**f, "at": now} for f in baseline_findings(root, plugin_root, kept["files"])] if kept else []
    history = (kept.get("accepted") or []) + changes
    data = {"schema": SCHEMA, "files": snapshot(root, plugin_root), "accepted": history[-ACCEPTED_KEPT:]}
    store.write_json(_path(root, BASELINE), data)
    try:
        store.write_json(backup_path(root), data)
    except OSError:
        pass                                                         # the backup is a safeguard, not a requirement
    if any(v["open"] for v in items):
        for v in items:
            if v["open"]:
                v["open"], v["closed_at"] = False, now
        _save_violations(root, items)
    return changes


def describe(item: dict) -> str:
    verb = {"changed": "was changed", "added": "was added", "removed": "was removed", "missing": "is missing"}.get(
        item["kind"], f"is {item['kind']}")
    return f"{item['path']} ({item['what']}) {verb}"


# -- hook entry ----------------------------------------------------------------------------
def _plugin_root() -> Path | None:
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
            return run_accept(root)
        new = check(root, _plugin_root(), payload.get("tool_name"))
    except (StoreError, OSError, cfg.ConfigError, KeyError, TypeError, ValueError) as exc:
        print(f"greenlight: the integrity check could not run ({exc}). The implement and verify gates will refuse "
              "until the integrity data under .bdd/.integrity is readable again; tell the person.", file=sys.stderr)
        return 2
    if new:
        print("greenlight: integrity check failed after this tool call:\n  " + "\n  ".join(describe(i) for i in new)
              + "\nThe implement and verify gates will refuse to pass until this is undone. Restore the file "
              "(for example with git) and tell the person what happened.", file=sys.stderr)
        return 2
    return 0


def run_accept(root: Path) -> int:
    """UserPromptSubmit: never blocks the prompt (exit 2 would), and says what it accepted or why not."""
    try:
        changes = accept(root, _plugin_root())
    except (StoreError, OSError, cfg.ConfigError, KeyError, TypeError, ValueError) as exc:
        print(f"greenlight: the integrity baseline could not be refreshed ({exc}); the implement and verify gates "
              "will refuse until .bdd/.integrity is readable again.")
        return 0
    if changes is None:
        print("greenlight: an integrity violation is still open, so the baseline was not refreshed.")
    elif changes:
        print("greenlight: accepted changes made since the last check: "
              + "; ".join(f"{c['path']} {c['kind']}" for c in changes) + ".")
    return 0
