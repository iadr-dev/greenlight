"""Running an adapter's tests for one feature and keeping what happened.

``bdd run`` is the only thing that writes ``.bdd/.runs/<FEAT>/latest.json`` (the guard keeps everyone
else out of that folder), so a classification made from it rests on a run that really happened.
"""
from __future__ import annotations

import hashlib
import os
import random
import re
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

from . import config as cfg
from . import featurefiles, junit, lockfile, store
from .errors import UsageError

RUNS_DIR = ".runs"
LATEST = "latest.json"
RED = "red.json"
SCHEMA = 1
TAIL_CHARS = 4000
# Variables that change what a program loads or runs never reach the test runner, whatever the adapter says; the adapter's
# ``scrub_env`` adds to this list. (A project that needs PYTHONPATH sets ``pythonpath`` in its bound pytest.ini.)
NEVER_PASSED_PREFIXES = ("PYTHON", "LD_", "DYLD_")
NEVER_PASSED_NAMES = {"BASH_ENV", "ENV", "NODE_OPTIONS"}
KEPT = {"PYTHONUTF8", "PYTHONIOENCODING"}


def runner_environment(scrub: tuple[str, ...] = ()) -> dict[str, str]:
    """The environment of a test run: ours, minus the variables that steer a program and the adapter's own list."""
    blocked = NEVER_PASSED_PREFIXES + tuple(scrub)
    return {k: v for k, v in os.environ.items()
            if k in KEPT or not (k in NEVER_PASSED_NAMES or k.startswith(blocked))}
SKIPPED = {"__pycache__", "node_modules", ".git"}


def runs_dir(root: Path, feature_id: str) -> Path:
    return root / cfg.BDD_DIR / RUNS_DIR / feature_id


def latest_path(root: Path, feature_id: str) -> Path:
    return runs_dir(root, feature_id) / LATEST


def inputs_digest(root: Path, feature_id: str) -> str:
    """One hash of everything a run depends on: the feature's files and every step and driver file.

    A recorded run only backs a gate while this still matches, so editing a test after running it
    means running it again."""
    files = list(featurefiles.spec_files(root, feature_id))
    files += [f for f in cfg.load(root).support_files if f.is_file()]
    for directory in cfg.load(root).step_dirs:
        for dirpath, dirnames, filenames in os.walk(directory):
            dirnames[:] = sorted(d for d in dirnames if d not in SKIPPED and not d.startswith("."))
            files += [Path(dirpath) / name for name in sorted(filenames)]
    digest = hashlib.sha256()
    for path in sorted({f.resolve() for f in files}):
        digest.update(f"{lockfile.relative(root, path)}\n{lockfile.file_digest(path)}\n".encode("utf-8"))
    return digest.hexdigest()


def project_python(root: Path) -> str:
    """The interpreter a Python project's tests run with: its own environment, not the one running bdd.

    In order: ``python = "..."`` in ``.bdd/config.toml`` (the person's choice, written by ``bdd init --python``),
    a ``.venv`` or ``venv`` folder in the project, and finally the interpreter that runs bdd. Environment variables
    are deliberately not consulted: a process can set them for a single command, and this program produces the
    evidence that gates accept."""
    chosen = cfg.load(root).python
    if chosen:
        path = Path(chosen) if Path(chosen).is_absolute() else root / chosen
        if not path.is_file():
            raise UsageError(f"python = {chosen!r} in .bdd/config.toml is not a file")
        return str(path)
    for environment in (root / ".venv", root / "venv"):
        for relative in ("Scripts/python.exe", "bin/python"):
            if (environment / relative).is_file():
                return str(environment / relative)
    return sys.executable


def interpreter_identity(root: Path) -> dict:
    """Which program ran the tests: its path and hash. A gate only accepts a run made with the interpreter the
    project resolves to now, so a run cannot be made with a program chosen just for that run."""
    path = Path(project_python(root))
    return {"path": str(path), "sha256": lockfile.file_digest(path) if path.is_file() else None}


def pick_rules(config: cfg.Config, adapter: str | None) -> cfg.RunRules:
    if not config.runs:
        raise UsageError("no [adapters.run] table in .bdd/config.toml; the adapter says how to run its tests")
    if adapter:
        found = [r for r in config.runs if r.adapter == adapter]
        if not found:
            raise UsageError(f"no adapter named {adapter} has a run command; choose from "
                             f"{', '.join(r.adapter or '(unnamed)' for r in config.runs)}")
        return found[0]
    if len(config.runs) > 1:
        raise UsageError("several adapters have a run command; choose one with --adapter "
                         f"({', '.join(r.adapter or '(unnamed)' for r in config.runs)})")
    return config.runs[0]


def build_command(rules: cfg.RunRules, root: Path, tag: str, out: Path, *, seed: int | None = None,
                 scenario: str | None = None) -> list[str]:
    """The words to run: the by-tag command, the report words, and the shuffle or isolation words if asked."""
    template = " ".join(part for part in (rules.by_tag, rules.report, rules.shuffle if seed is not None else "",
                                          rules.isolated if scenario is not None else "") if part)
    if seed is not None and not rules.shuffle:
        raise UsageError(f"adapter {rules.adapter} has no shuffle words in [adapters.run]")
    if scenario is not None and not rules.isolated:
        raise UsageError(f"adapter {rules.adapter} has no isolated words in [adapters.run]")
    values = {"{root}": str(root), "{python}": sys.executable, "{project_python}": project_python(root), "{tag}": tag,
              "{marker}": re.sub(r"\W", "_", tag),
              "{out}": str(out), "{seed}": str(seed if seed is not None else ""), "{scenario}": scenario or ""}
    words = []
    for word in shlex.split(template):
        for placeholder, value in values.items():
            word = word.replace(placeholder, value)
        words.append(word)
    return words


def execute(words: list[str], root: Path, timeout: int, scrub: tuple[str, ...] = ()) -> tuple[int, str]:
    """(exit status, combined output). A command that cannot start or runs too long is a usage problem.
    Variables whose names start with one of ``scrub`` (such as PYTEST_ADDOPTS) are not passed on: they can change
    which tests run."""
    program = shutil.which(words[0])
    if not program:
        raise UsageError(f"cannot run {words[0]!r}: it is not on PATH; install the adapter's requirements first")
    try:
        env = runner_environment(scrub)
        # the program as found on PATH, so a script shim such as npm.cmd or gradlew.bat starts on Windows without a shell
        done = subprocess.run([program, *words[1:]], cwd=root, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=timeout, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired as exc:
        raise UsageError(f"the test run took longer than {timeout} s and was stopped") from exc
    return done.returncode, (done.stdout or "") + (done.stderr or "")


def one_run(rules: cfg.RunRules, root: Path, folder: Path, index: int, tag: str, **options) -> tuple[dict, list[junit.Case]]:
    report = folder / f"report-{index}.xml"
    report.unlink(missing_ok=True)
    words = build_command(rules, root, tag, report, **options)
    started = time.perf_counter()
    status, output = execute(words, root, rules.timeout, rules.scrub_env)
    entry = {"command": words, "exit": status, "seconds": round(time.perf_counter() - started, 2),
             "scenario": options.get("scenario"), "report": report.is_file(), "tail": output[-TAIL_CHARS:]}
    return entry, junit.parse_file(report) if report.is_file() else []


def run_feature(root: Path, feature_id: str, scenarios: list[str], rules: cfg.RunRules, *, shuffle: bool = False,
                isolated: bool = False, seed: int | None = None) -> dict:
    """Run the feature's tests (one process per scenario when ``isolated``) and record the outcome."""
    folder = runs_dir(root, feature_id)
    folder.mkdir(parents=True, exist_ok=True)
    seed = (seed if seed is not None else random.SystemRandom().randrange(1, 10**6)) if shuffle else None
    runs, cases = [], []
    plan = [{"scenario": name} for name in scenarios] if isolated else [{}]
    for index, options in enumerate(plan, start=1):
        entry, found = one_run(rules, root, folder, index, feature_id, seed=seed, **options)
        runs.append(entry)
        cases += found
    record = {"schema": SCHEMA, "feature": feature_id, "adapter": rules.adapter, "at": store.utc_now(), "inputs": inputs_digest(root, feature_id),
              "interpreter": interpreter_identity(root),
              "mode": "isolated" if isolated else "shuffle" if shuffle else "all", "seed": seed, "runs": runs,
              "cases": [{"name": c.name, "classname": c.classname, "outcome": c.outcome, "text": c.text} for c in cases]}
    store.write_json(latest_path(root, feature_id), record)
    return record


def latest_bytes(root: Path, feature_id: str) -> bytes | None:
    """The last run exactly as stored (read once, so what is checked is what is kept), or None."""
    path = latest_path(root, feature_id)
    return path.read_bytes() if path.is_file() else None


def keep_red(root: Path, feature_id: str, raw: bytes) -> dict:
    """Keep the run that proved the red, so later runs (the green, the auditor's reruns) cannot overwrite the evidence.
    ``raw`` is the very bytes that were checked."""
    target = runs_dir(root, feature_id) / RED
    target.write_bytes(raw)
    return {"file": RED, "sha256": hashlib.sha256(raw).hexdigest(), "at": store.utc_now()}


def load_red(root: Path, feature_id: str, kept: dict | None) -> dict:
    """The kept red run, if it is still what was recorded at the bind gate."""
    path = runs_dir(root, feature_id) / RED
    if not kept or not path.is_file():
        raise UsageError(f"no red run was kept for {feature_id}: the bind gate has not passed with a recorded run")
    if hashlib.sha256(path.read_bytes()).hexdigest() != kept["sha256"]:
        raise UsageError(f"the kept red run of {feature_id} does not match what the bind gate recorded")
    return store.read_json(path, "the kept red run")


def load_latest(root: Path, feature_id: str) -> dict:
    path = latest_path(root, feature_id)
    if not path.is_file():
        raise UsageError(f"{feature_id} has not been run yet; run `bdd run {feature_id}` first")
    return store.read_json(path, "the last test run")
