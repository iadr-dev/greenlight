#!/usr/bin/env python3
"""Run a whole feature through greenlight with real agents, and measure what happened.

    python evals/run_e2e.py [--request discounts|adopt-billing] [--model haiku] [--autonomy standard,autopilot]
                            [--runs 3] [--arms plugin,baseline] [--hooks on|off] [--keep]

For every combination of arm, autonomy level and run number it copies the request's reference app (evals/apps/shop-api
for a feature, evals/apps/legacy-billing for an adoption) into a temporary project with its own virtual environment,
sets greenlight up (`bdd init`, proves the sample green), then asks Claude Code, headless, to run
`/greenlight:feature "<request>"` (`/greenlight:adopt "<area>"` for an adoption request). An adoption row also says
whether the adoption invariants hold (see adoption_invariants); it has no baseline arm. Afterwards it reads the project's own
records with the `bdd` CLI and git, never the conversation (evals/collect.py), and appends one metrics row per run to
a JSON-lines file in evals/results/. The summary table compares the means with the release targets (evals/README.md).

Arms: `plugin` is greenlight; `baseline` is the same request in plain Claude Code, with no plugin, scored with what is
measurable without one (do the app's own tests pass, what changed).

Hooks: `on` loads the plugin as it is; `off` loads a copy whose hooks file is empty, which is how a soft-enforcement
run is made. A row says whether hooks actually ran (`hooks_active`): if `on` was asked and they did not, the row is
marked and the run does not count as hard enforcement.

Standard autonomy needs a person at two gates. A headless run has none, so the harness sends the typed approval
commands as follow-up prompts in the same session (`--resume`) when the project says it is waiting for them. Those
approvals arrive as headless prompts, which greenlight grades below a keyboard-typed one; the row records the grade, so
a standard row measures the pipeline given scripted human decisions, not provenance of a real person.

Needs `claude`, `uv`, `git` and `sh` on PATH, working credentials, and some money: a run makes many model calls. Not
part of CI.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import collect  # noqa: E402  (a sibling module; the script directory is on the path when it is run directly)

REPO = Path(__file__).resolve().parents[1]
APPS = REPO / "evals" / "apps"
REQUESTS = REPO / "evals" / "requests"
RESULTS = REPO / "evals" / "results"
TOOLS = "Agent Bash Read Write Edit MultiEdit Grep Glob"
GIT = ["git", "-c", "user.name=e2e", "-c", "user.email=e2e@example.com", "-c", "commit.gpgsign=false",
       "-c", "gc.auto=0", "-c", "maintenance.auto=false"]
LEVELS = ("guided", "standard", "auto", "autopilot")
ARMS = ("plugin", "baseline")
WAITING = re.compile(r"/greenlight:approve (FEAT-\d+) (rules|examples)")
MAX_FOLLOW_UPS = 6

# What each request needs: its reference app, the skill that runs it and the packages the app and its tests import. A
# feature request is judged by reaching `done`, an adoption request also by the invariants in adoption_invariants.
REQUEST_KINDS = {
    "discounts": {"app": "shop-api", "skill": "feature", "packages": ["fastapi", "httpx"]},
    "adopt-billing": {"app": "legacy-billing", "skill": "adopt", "packages": ["flask", "flask-wtf"]},
}

# The model and the request are chosen from fixed tables, so nothing typed on the command line reaches a command.
MODELS = {"haiku": "haiku", "sonnet": "sonnet", "opus": "opus", "haiku-5.5": "us.anthropic.claude-haiku-5-5",
          "sonnet-5.5": "us.anthropic.claude-sonnet-5-5", "opus-5.5": "us.anthropic.claude-opus-5-5"}


def run(command: list[str], cwd: Path, env: dict, timeout: int = 600, check: bool = True,
        stdin_text: str | None = None) -> subprocess.CompletedProcess:
    done = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          input=stdin_text, stdin=None if stdin_text is not None else subprocess.DEVNULL, timeout=timeout)
    if check and done.returncode != 0:
        raise SystemExit(f"command failed ({done.returncode}): {' '.join(command)}\n{done.stdout}\n{done.stderr}")
    return done


def build_project(tmp: Path, kind: dict) -> tuple[Path, dict, str]:
    project = tmp / "project"
    shutil.copytree(APPS / kind["app"], project, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    venv = tmp / ".venv"
    run(["uv", "venv", "--python", "3.12", str(venv)], tmp, os.environ.copy())
    bin_dir = venv / ("Scripts" if os.name == "nt" else "bin")
    python = bin_dir / ("python.exe" if os.name == "nt" else "python")
    run(["uv", "pip", "install", "--python", str(python), *kind["packages"], "pytest", "pytest-bdd"], tmp, os.environ.copy())
    env = os.environ.copy()
    env["PATH"] = str(bin_dir) + os.pathsep + env["PATH"]       # `python` in the project is the venv's
    env["GREENLIGHT_CACHE_DIR"] = str(tmp / ".cache")
    env.pop("CLAUDE_PLUGIN_DATA", None)
    env["PYTHONUTF8"] = "1"
    return project, env, str(python)


def bdd(project: Path, env: dict, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return run(["sh", str(REPO / "tools" / "bdd" / "bdd"), *args], project, env, check=check)


def reader(project: Path, env: dict):
    """The collector's view of the project: one bdd command in, (exit code, stdout) out."""
    def read(*args: str) -> tuple[int, str]:
        done = bdd(project, env, *args, check=False)
        return done.returncode, done.stdout
    return read


def commit_all(project: Path, env: dict, message: str) -> None:
    run([*GIT, "add", "-A"], project, env)
    run([*GIT, "commit", "-q", "-m", message], project, env)


def set_up(project: Path, env: dict, autonomy: str, python: str) -> None:
    run([*GIT, "init", "-q"], project, env)
    commit_all(project, env, "reference app")
    bdd(project, env, "init", "--adapter", "python-pytest-bdd", "--autonomy", autonomy, "--python", python)
    print(bdd(project, env, "init", "--smoke").stdout.strip())
    commit_all(project, env, "greenlight set up")


def plugin_directory(tmp: Path, hooks: str) -> Path:
    """The plugin as it is, or (hooks off) a copy whose hooks file is empty, for a soft-enforcement arm."""
    if hooks == "on":
        return REPO
    copy = tmp / "plugin-without-hooks"
    shutil.copytree(REPO, copy, ignore=shutil.ignore_patterns(".git", "evals", "bdd-forge-plan", "__pycache__", ".claude", "node_modules"))
    (copy / "hooks" / "hooks.json").write_text(json.dumps({"hooks": {}}), encoding="utf-8")
    return copy


def parse_output(text: str) -> dict:
    try:
        value = json.loads(text)
    except ValueError:
        return {"raw": text[-4000:]}
    return value if isinstance(value, dict) else {"raw": text[-4000:]}


def claude(project: Path, env: dict, prompt: str, model: str, minutes: int, plugin: Path | None, resume: str | None = None) -> dict:
    command = ["claude", "-p", "--model", model, "--allowedTools", TOOLS, "--output-format", "json", "--setting-sources", "project"]
    if plugin is not None:
        command += ["--plugin-dir", str(plugin)]
    if resume:
        command += ["--resume", resume]                                 # the prompt goes in on stdin
    started = time.time()
    try:
        done = run(command, project, env, timeout=minutes * 60, check=False, stdin_text=prompt)
        text, code = done.stdout, done.returncode
    except subprocess.TimeoutExpired as exc:
        text, code = (exc.stdout or "") if isinstance(exc.stdout, str) else "", "timeout"
    output = parse_output(text)
    output["exit"], output["seconds"] = code, round(time.time() - started)
    return output


def merge_usage(total: dict, part: dict) -> dict:
    """Add the cost, turns and time of a follow-up prompt to the run's totals."""
    for key in ("total_cost_usd", "num_turns", "seconds"):
        total[key] = (total.get(key) or 0) + (part.get(key) or 0)
    usage = total.setdefault("usage", {})
    for key, value in (part.get("usage") or {}).items():
        if isinstance(value, (int, float)):
            usage[key] = usage.get(key, 0) + value
    for key in ("exit", "is_error", "subtype", "session_id", "result", "raw"):
        if part.get(key) is not None:
            total[key] = part[key]
    return total


def next_human_step(project: Path, env: dict) -> str | None:
    """The approval command the project is waiting for, if any, from `bdd status --json`."""
    _, text = reader(project, env)("status", "--json")
    for row in collect.load_json(text).get("features", []):
        match = WAITING.search(row.get("waiting_for", ""))
        if match:
            return f"/greenlight:approve {match.group(1)} {match.group(2)}"
    return None


def drive(project: Path, env: dict, request: str, skill: str, model: str, level: str, minutes: int, plugin: Path) -> dict:
    """Run the orchestrator; at standard/guided, deliver the scripted approvals until none is awaited."""
    total = claude(project, env, f'/greenlight:{skill} "{request.strip()}" --autonomy {level}', model, minutes, plugin)
    if level in ("autopilot", "auto"):
        return total
    for _ in range(MAX_FOLLOW_UPS):
        step = next_human_step(project, env)
        if step is None or not total.get("session_id"):
            break
        part = claude(project, env, step, model, minutes, plugin, resume=total["session_id"])
        total = merge_usage(total, part)
        if next_human_step(project, env) is None:
            part = claude(project, env, "continue the feature from where it stopped", model, minutes, plugin, resume=total["session_id"])
            total = merge_usage(total, part)
    return total


def tokens_reported(output: dict) -> int:
    usage = output.get("usage") or {}
    return sum(int(usage.get(k) or 0) for k in ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))


def transcript_of(output: dict, project: Path) -> Path | None:
    """Where Claude Code kept this session's transcript, if it can be found."""
    session = output.get("session_id")
    if not session:
        return None
    base = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude") / "projects"
    found = sorted(base.glob(f"*/{session}.jsonl")) if base.is_dir() else []
    return found[0] if found else None


def claude_summary(output: dict) -> dict:
    row = {k: output.get(k) for k in ("exit", "seconds", "is_error", "num_turns", "total_cost_usd", "subtype", "session_id")}
    row["tokens_reported"] = tokens_reported(output)
    return row


def git_changes(project: Path, env: dict) -> dict:
    changed = run([*GIT, "diff", "--stat", "HEAD"], project, env, check=False).stdout.strip().splitlines()
    untracked = run([*GIT, "ls-files", "--others", "--exclude-standard"], project, env, check=False).stdout.split()
    return {"files_changed": changed[-1] if changed else "", "new_files": len(untracked)}


NOT_PRODUCTION = (".bdd/", "tests/", ".gitignore", ".claude/")
# What Python writes next to a module when it imports it. Only an untracked file of exactly this shape is skipped: a
# .py under __pycache__ or a .pyc elsewhere can be imported, so it is source (the same rule as the red record).
GENERATED_BYTECODE = re.compile(r"(?:.*/)?__pycache__/[^/]+\.cpython-\d+(?:\.opt-[12])?\.pyc")


def production_changes(porcelain: list[str]) -> list[str]:
    """The paths in `git status --porcelain --untracked-files=all` output that are production code: everything except
    greenlight's own data, the test folder, ignore files and generated bytecode. An adoption must leave this empty."""
    paths = []
    for line in porcelain:
        path = line[3:].split(" -> ")[-1].strip().strip('"')
        generated = line.startswith("??") and GENERATED_BYTECODE.fullmatch(path) is not None
        if path and not generated and not path.startswith(NOT_PRODUCTION):
            paths.append(path)
    return paths


def adoption_invariants(project: Path, env: dict, feature: str) -> dict:
    """What an adoption must satisfy, read from the project and never from the conversation: `bdd adopt --check` is
    clean (every scenario is @existing, the bind gate pinned the production source and it is unchanged), the recorded
    run is a valid green, and git sees no production file touched since greenlight was set up."""
    check = bdd(project, env, "adopt", feature, "--check", check=False)
    porcelain = run([*GIT, "status", "--porcelain", "--untracked-files=all"], project, env, check=False).stdout.splitlines()
    touched = production_changes(porcelain)
    classified = collect.load_json(bdd(project, env, "classify", feature, "--json", check=False).stdout)
    green = (classified.get("green") or {}).get("valid")
    return {"adopt_check_clean": check.returncode == 0, "adopt_check_output": (check.stdout + check.stderr).strip()[:600],
            "production_files_touched": touched, "green_valid": green,
            "holds": check.returncode == 0 and not touched and green is True}


def plugin_row(tmp: Path, args: argparse.Namespace, request: str, level: str, answers: list[dict]) -> dict:
    kind = REQUEST_KINDS[args.request]
    project, env, python = build_project(tmp, kind)
    set_up(project, env, level, python)
    output = drive(project, env, request, kind["skill"], MODELS[args.model], level, args.minutes, plugin_directory(tmp, args.hooks))
    row = collect.collect_row(reader(project, env), project, answers, transcript_of(output, project))
    marker = project / ".bdd" / ".enforcement" / "_seen"
    row.update(git_changes(project, env))
    if kind["skill"] == "adopt" and row.get("feature"):
        row["adoption"] = adoption_invariants(project, env, row["feature"])
    row.update({"hooks_active": marker.is_file(), "claude": claude_summary(output)})
    if args.hooks == "on" and not row["hooks_active"]:
        row["warning"] = "hooks were requested but did not run; this row is not a hard-enforcement result"
    if row.get("phase") not in (None, "discover") and not row.get("cost_recorded"):
        row["cost_warning"] = "the orchestrator recorded no cost with `bdd cost`; the totals above are claude's own"
    row["completed"] = row.get("phase") == "done" and (row["adoption"]["holds"] if "adoption" in row else kind["skill"] != "adopt")
    return row


def baseline_row(tmp: Path, args: argparse.Namespace, request: str) -> dict:
    """The same request without the plugin: what plain Claude Code leaves behind, judged by the app's own tests."""
    project, env, python = build_project(tmp, REQUEST_KINDS[args.request])
    run([*GIT, "init", "-q"], project, env)
    commit_all(project, env, "reference app")
    prompt =(f"{request.strip()}\n\nImplement this in the project in the current directory. Write tests for it and run "
              "the project's tests. Do not ask questions; decide and state your assumptions.")
    output = claude(project, env, prompt, MODELS[args.model], args.minutes, None)
    tests = run([python, "-m", "pytest", "-q", "-p", "no:cacheprovider"], project, env, check=False)
    row = {"features": 0, "tests_pass": tests.returncode == 0, "claude": claude_summary(output), **git_changes(project, env)}
    row["completed"] = row["tests_pass"]
    return row


def append_row(path: Path, row: dict) -> None:
    RESULTS.mkdir(exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def parse_list(value: str, allowed: tuple[str, ...], what: str) -> list[str]:
    names = [v.strip() for v in value.split(",") if v.strip()]
    bad = [n for n in names if n not in allowed]
    if bad or not names:
        raise argparse.ArgumentTypeError(f"{what}: choose from {', '.join(allowed)}")
    return names


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    requests = {p.stem: p for p in sorted(REQUESTS.glob("*.md"))}
    ap.add_argument("--request", default="discounts", choices=sorted(REQUEST_KINDS), help="a file in evals/requests/")
    ap.add_argument("--model", default="haiku", choices=sorted(MODELS), help="a name from the MODELS table")
    ap.add_argument("--autonomy", default="autopilot", type=lambda v: parse_list(v, LEVELS, "autonomy"),
                    help="one level or a comma-separated list, e.g. standard,autopilot")
    ap.add_argument("--arms", default="plugin", type=lambda v: parse_list(v, ARMS, "arms"), help="plugin, baseline or both")
    ap.add_argument("--hooks", default="on", choices=("on", "off"), help="off: the plugin's hooks are removed (soft enforcement)")
    ap.add_argument("--runs", type=int, default=1, help="repeat every combination this many times")
    ap.add_argument("--minutes", type=int, default=45, help="give up on one run after this long")
    ap.add_argument("--keep", action="store_true", help="keep the temporary projects and print their paths")
    args = ap.parse_args()
    for tool in ("claude", "uv", "git", "sh"):
        if not shutil.which(tool):
            print(f"{tool} not found on PATH")
            return 2
    if REQUEST_KINDS[args.request]["skill"] == "adopt" and "baseline" in args.arms:
        print("an adoption request has no baseline arm: plain Claude Code has nothing to adopt against")
        return 2
    request = requests[args.request].read_text(encoding="utf-8")
    answers_file = REQUESTS / f"{args.request}.answers.json"
    answers = json.loads(answers_file.read_text(encoding="utf-8")) if answers_file.is_file() else []
    out = RESULTS / f"{time.strftime('%Y%m%d-%H%M%S')}-{args.request}-{args.model}.jsonl"
    rows: list[dict] = []
    plan = [("plugin", level) for level in args.autonomy if "plugin" in args.arms] + [("baseline", None)] * ("baseline" in args.arms)
    for number in range(1, args.runs + 1):
        for arm, level in plan:
            tmp = Path(tempfile.mkdtemp(prefix="greenlight-e2e-")).resolve()
            try:
                row = plugin_row(tmp, args, request, level, answers) if arm == "plugin" else baseline_row(tmp, args, request)
            finally:
                if args.keep:
                    print(f"kept: {tmp}")
                else:
                    shutil.rmtree(tmp, ignore_errors=True)
            row.update({"request": args.request, "model": args.model, "arm": arm, "autonomy_requested": level,
                        "hooks": args.hooks if arm == "plugin" else "n/a", "run": number})
            append_row(out, row)
            rows.append(row)
    print(collect.summary_table(rows))
    print(f"\nrows: {out}")
    return 0 if all(r.get("completed") for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
