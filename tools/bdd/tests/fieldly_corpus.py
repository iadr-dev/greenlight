"""Replay the guard refusals of the Fieldly run (``fixtures/guard/fieldly-refusals.jsonl``) through ``guard.evaluate``.

Each row is a refused tool call with its paths written as placeholders and a label: ``allow`` for legitimate work the guard
should let through, ``refuse`` for a call a protection must still stop. The replay builds a project shaped like Fieldly's
(the same adapter and folders) and a fake plugin and Claude Code folder, and puts each row's paths in it. Its locks are
the ones the refusals name: the three feature files (spec) and the drivers and support files the refusals call locked
(bind). A row made while a change request had released the feature files says ``"locks": "spec released"``.

    python -m tests.fieldly_corpus [ID ...]    prints each row's verdict and the start of the reason
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

from bddlib import guard, lockfile, state

CORPUS = Path(__file__).resolve().parent / "fixtures" / "guard" / "fieldly-refusals.jsonl"
CONFIG = """autonomy = "standard"
enforcement = "auto"

[[adapters]]
name = "ts-cucumber-js"
features = "tests/features"
steps = "tests/steps"
drivers = "tests/drivers"
support = ["tests/cucumber.mjs", "tests/package.json", "tests/package-lock.json", "tests/tsconfig.json"]
"""
FEATURES = {"FEAT-001": ("company-workspace-and-sign-in", "Company workspace and sign-in"),
            "FEAT-002": ("customer-records", "Customer records"),
            "FEAT-003": ("work-order-lifecycle", "Work order lifecycle")}
DRIVERS = ("api", "system", "work-orders-book", "world", "features/customers", "features/work-orders")
LOCKED_DRIVERS = ("clock", "errors", "feature-driver", "work-order-barrier")
SPEC_RELEASED = "spec released"
FOLDERS = ("api/src/application/ports", "api/src/application/work-order", "api/src/application/customer",
           "api/src/application/sign-in", "api/src/domain/shared", "api/src/domain/work-order", "api/src/domain/customer",
           "api/src/testing", "api/src/interfaces/http/routes", "api/src/infrastructure/postgres", "api/node_modules",
           "tests/node_modules", "tests/steps", "design/screens", "design/assets", "design/.impeccable", "supabase/migrations",
           "supabase/rollbacks", "docs")


def rows() -> list[dict]:
    return [json.loads(line) for line in CORPUS.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write(path: Path, text: str = "x\n") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def build(base: Path, locks: str = "") -> dict[str, Path]:
    """A project shaped like Fieldly's under ``base``, with a plugin copy and a Claude Code folder next to it."""
    places = {"project": base / "Fieldly", "home": base / "home", "config": base / "home" / ".claude"}
    places["plugin"] = places["config"] / "plugins" / "cache" / "greenlight" / "greenlight" / "1.2.1"
    root = places["project"]
    _write(root / ".bdd" / "config.toml", CONFIG)
    _write(root / ".bdd" / "standards.md", "# standards\n")
    _write(root / ".bdd" / "glossary.md", "# glossary\n")
    for folder in FOLDERS:
        (root / folder).mkdir(parents=True, exist_ok=True)
    support = [_write(root / "tests" / name, "{}\n") for name in ("cucumber.mjs", "package.json")]
    for name in DRIVERS:
        _write(root / "tests" / "drivers" / f"{name}.ts")
    drivers = [_write(root / "tests" / "drivers" / f"{name}.ts") for name in LOCKED_DRIVERS]
    for number, (slug, title) in FEATURES.items():
        feature = _write(root / "tests" / "features" / f"{slug}.feature", f"@{number}\nFeature: {title}\n")
        folder = state.create(root, number, title, "standard")
        (folder / "reviews").mkdir()
        _write(folder / "tasks.md", "# tasks\n")
        lockfile.lock(root, folder, number, "spec", [feature])
        if number == "FEAT-001":
            lockfile.lock(root, folder, number, "bind", support + drivers)
        if locks == SPEC_RELEASED:
            lockfile.unlock(folder, number, "spec", "a change request reopened the examples")
    for name in ("tools/bdd/bdd", "tools/bdd/bddlib/guard.py", "hooks/hooks.json", ".claude-plugin/plugin.json"):
        _write(places["plugin"] / name)
    (places["config"] / "projects" / "project-key" / "memory").mkdir(parents=True)
    (places["home"] / "other-folder" / ".claude" / "hooks").mkdir(parents=True)
    places["temp"] = Path(tempfile.gettempdir())
    return places


def payload(row: dict, places: dict[str, Path]) -> dict:
    def fill(value):
        if isinstance(value, str):
            for name in ("project", "plugin", "config", "home", "temp"):
                value = value.replace(f"<{name}>", places[name].as_posix())
            return value
        if isinstance(value, list):
            return [fill(v) for v in value]
        if isinstance(value, dict):
            return {k: fill(v) for k, v in value.items()}
        return value
    found = {"tool_name": row["tool_name"], "tool_input": fill(row["tool_input"]), "cwd": fill(row["cwd"])}
    if row.get("agent_type"):
        found["agent_type"] = row["agent_type"]
    return found


@contextmanager
def fieldly(locks: str = ""):
    """The project, with the environment the hooks would see: the plugin's root and the Claude Code folder."""
    with tempfile.TemporaryDirectory() as folder:
        places = build(Path(folder).resolve(), locks)
        env = {guard.PLUGIN_ROOT_ENV: str(places["plugin"]), "CLAUDE_CONFIG_DIR": str(places["config"]),
               "HOME": str(places["home"]), "USERPROFILE": str(places["home"])}
        with mock.patch.dict(os.environ, env):
            yield places


def replay(selected: list[dict]) -> list[tuple[dict, str | None]]:
    verdicts = {}
    for locks in ("", SPEC_RELEASED):
        with fieldly(locks) as places:
            for row in selected:
                if row.get("locks", "") == locks:
                    verdicts[row["id"]] = guard.evaluate(payload(row, places))
    return [(row, verdicts[row["id"]]) for row in selected]


def main(argv: list[str]) -> int:
    wanted = {int(a) for a in argv}
    for row, reason in replay([r for r in rows() if not wanted or r["id"] in wanted]):
        verdict = "refuse" if reason else "allow"
        mark = "  " if verdict == row["label"] else "!!"
        print(f"{mark} {row['id']:>3} {row['class']} {row['label']:<6} -> {verdict:<6} {(reason or '')[12:100]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
