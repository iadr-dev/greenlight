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


def pick_all(config: cfg.Config, adapter: str | None) -> list[cfg.RunRules]:
    """The adapters to run: the one named, or every adapter that has a run command (a repository with a backend and a
    web front end has two, and a feature can have scenarios in both)."""
    if not config.runs:
        raise UsageError("no [adapters.run] table in .bdd/config.toml; the adapter says how to run its tests")
    return [pick_rules(config, adapter)] if adapter else list(config.runs)


def build_command(rules: cfg.RunRules, root: Path, tag: str, out: Path, *, seed: int | None = None,
                 scenario: str | None = None) -> list[str]:
    """The words to run: the by-tag command, the report words, and the shuffle or isolation words if asked."""
    template = " ".join(part for part in (rules.by_tag, rules.report, rules.shuffle if seed is not None else "",
                                          rules.isolated if scenario is not None else "") if part)
    if seed is not None and not rules.shuffle:
        raise UsageError(f"adapter {rules.adapter} has no shuffle words in [adapters.run]")
    if scenario is not None and not rules.isolated:
        raise UsageError(f"adapter {rules.adapter} has no isolated words in [adapters.run]")
    values = {"{root}": str(root), "{base}": str(root / rules.base) if rules.base else str(root), "{python}": sys.executable, "{project_python}": project_python(root), "{tag}": tag,
              "{marker}": re.sub(r"\W", "_", tag),
              "{out}": str(out), "{seed}": str(seed if seed is not None else ""), "{scenario}": scenario or ""}
    words = []
    for word in shlex.split(template):
        for placeholder, value in values.items():
            word = word.replace(placeholder, value)
        words.append(word)
    return words


BATCH_SUFFIXES = (".bat", ".cmd")
CMD_METACHARACTERS = '"&|<>^%!\r\n'


def executable_suffixes(environ: dict | None = None) -> tuple[str, ...]:
    """The suffixes Windows runs without being told (PATHEXT); empty on other systems, where the mode bit decides."""
    if os.name != "nt":
        return ()
    value = (environ if environ is not None else os.environ).get("PATHEXT") or ".COM;.EXE;.BAT;.CMD"
    return tuple(part.lower() for part in value.split(";") if part.startswith("."))


def resolve_program(word: str, root: Path, search_path: str, suffixes: tuple[str, ...]) -> str | None:
    """The file that ``word`` names, or None.

    A word with a path separator is an explicit path, relative to the project (``./gradlew``). A bare name such as
    ``ruff`` is looked up only in the absolute folders of ``search_path`` (PATH): never in the project or the working
    directory, which Windows would otherwise search first, so a file planted in the project cannot stand in for a tool."""
    path = Path(word)
    explicit = any(separator in word for separator in ("/", "\\"))
    folders = ([path.parent if path.is_absolute() else root / path.parent] if explicit else
               [Path(entry) for entry in search_path.split(os.pathsep) if entry and Path(entry).is_absolute()])
    names = [path.name] if not suffixes or path.suffix.lower() in suffixes else [path.name + suffix for suffix in suffixes]
    for folder in folders:
        for name in names:
            candidate = folder / name
            if candidate.is_file() and (bool(suffixes) or os.access(candidate, os.X_OK)):
                return str(candidate)
    return None


def batch_problem(program: str, arguments: list[str]) -> str | None:
    """Why a batch file may not be started with these arguments, or None. Windows hands a .bat or .cmd file to cmd.exe,
    which reads quotes, & | < > ^ % ! and line breaks as its own syntax, so an argument holding one could add a command."""
    if not program.lower().endswith(BATCH_SUFFIXES):
        return None
    for argument in arguments:
        if any(char in argument for char in CMD_METACHARACTERS):
            return (f"{Path(program).name} is a batch file and an argument contains a character that cmd.exe would read as "
                    f"syntax ({argument!r}); start the tool through its real executable, or name it with a path that is not a batch file")
    return None


def execute(words: list[str], root: Path, timeout: int, scrub: tuple[str, ...] = (), cwd: Path | None = None) -> tuple[int, str]:
    """(exit status, combined output). A command that cannot start or runs too long is a usage problem.
    Variables whose names start with one of ``scrub`` (such as PYTEST_ADDOPTS) are not passed on: they can change
    which tests run. The command runs in ``cwd`` (the adapter's folder, by default the project)."""
    workdir = cwd or root
    program = resolve_program(words[0], workdir, os.environ.get("PATH", ""), executable_suffixes())
    if not program:
        raise UsageError(f"cannot run {words[0]!r}: it is not on PATH; install the adapter's requirements first")
    problem = batch_problem(program, words[1:])
    if problem:
        raise UsageError(problem)
    try:
        env = runner_environment(scrub)
        if os.name == "nt":
            env["NoDefaultCurrentDirectoryInExePath"] = "1"          # nothing the tool starts looks in the project first
        # the program as found, so a script shim such as npm.cmd or gradlew.bat starts on Windows without a shell
        done = subprocess.run([program, *words[1:]], cwd=workdir, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=timeout, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired as exc:
        raise UsageError(f"the test run took longer than {timeout} s and was stopped") from exc
    return done.returncode, (done.stdout or "") + (done.stderr or "")


def one_run(rules: cfg.RunRules, root: Path, folder: Path, index: int, tag: str, **options) -> tuple[dict, list[junit.Case]]:
    report = folder / f"report-{index}.xml"
    report.unlink(missing_ok=True)
    words = build_command(rules, root, tag, report, **options)
    started = time.perf_counter()
    status, output = execute(words, root, rules.timeout, rules.scrub_env, root / rules.base if rules.base else None)
    entry = {"adapter": rules.adapter, "command": words, "exit": status, "seconds": round(time.perf_counter() - started, 2),
             "scenario": options.get("scenario"), "report": report.is_file(), "tail": output[-TAIL_CHARS:]}
    return entry, junit.parse_file(report) if report.is_file() else []


def scenarios_of(rules: cfg.RunRules, scenarios: list[dict], several: bool) -> list[str]:
    """The names of the scenarios one adapter runs one at a time: those in its own feature folder when the repository
    has several adapters, all of them otherwise."""
    prefix = rules.features.rstrip("/") + "/" if rules.features else ""
    return [s["name"] for s in scenarios if not several or not prefix or s["path"].startswith(prefix)]


def fresh_seed() -> int:
    """A new shuffle seed, recorded with the run so the order can be repeated."""
    return random.SystemRandom().randrange(1, 10**6)


def run_feature(root: Path, feature_id: str, scenarios: list[dict], adapters: list[cfg.RunRules], *, shuffle: bool = False,
                isolated: bool = False, seed: int | None = None) -> dict:
    """Run the feature's tests with every adapter in ``adapters`` (one process per scenario when ``isolated``) and
    record the outcome as one run: the cases of all of them, side by side."""
    folder = runs_dir(root, feature_id)
    folder.mkdir(parents=True, exist_ok=True)
    seed = (seed if seed is not None else fresh_seed()) if shuffle else None
    runs, cases = [], []
    for rules in adapters:
        names = scenarios_of(rules, scenarios, len(adapters) > 1)
        if len(adapters) > 1 and not names:
            continue                                          # this adapter has no scenario of the feature
        plan = [{"scenario": name} for name in names] if isolated else [{}]
        for options in plan:
            entry, found = one_run(rules, root, folder, len(runs) + 1, feature_id, seed=seed, **options)
            runs.append(entry)
            cases += found
    record = {"schema": SCHEMA, "feature": feature_id, "adapter": ", ".join(r.adapter for r in adapters), "at": store.utc_now(), "inputs": inputs_digest(root, feature_id),
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
