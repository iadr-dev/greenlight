#!/usr/bin/env python3
"""Run a whole feature through greenlight with real agents, and measure what happened.

    python evals/run_e2e.py [--request discounts] [--model haiku] [--autonomy standard,autopilot]
                            [--runs 3] [--arms plugin,baseline] [--hooks on|off] [--keep]

For every combination of arm, autonomy level and run number it copies the request's reference app (evals/apps/: shop-api,
csv-tool or money-lib) into a temporary project (with its own virtual environment for the Python app), sets greenlight up
(`bdd init`, proves the sample green),
then asks Claude Code, headless, to run `/greenlight:feature "<request>"`. Afterwards it reads the project's own
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
REQUESTS = REPO / "evals" / "requests"
RESULTS = REPO / "evals" / "results"
TOOLS = "Agent Bash Read Write Edit MultiEdit Grep Glob"
GIT = ["git", "-c", "user.name=e2e", "-c", "user.email=e2e@example.com", "-c", "commit.gpgsign=false",
       "-c", "gc.auto=0", "-c", "maintenance.auto=false"]
LEVELS = ("guided", "standard", "auto", "autopilot")
ARMS = ("plugin", "baseline")
WAITING = re.compile(r"/greenlight:approve (FEAT-\d+) (rules|examples)")
MAX_FOLLOW_UPS = 6

# The model and the request are chosen from fixed tables, so nothing typed on the command line reaches a command.
MODELS = {"haiku": "haiku", "sonnet": "sonnet", "opus": "opus", "haiku-5.5": "us.anthropic.claude-haiku-5-5",
          "sonnet-5.5": "us.anthropic.claude-sonnet-5-5", "opus-5.5": "us.anthropic.claude-opus-5-5"}


# Each request runs on one reference app with one adapter (its scripted answers are in evals/requests/<request>.answers.json).
# A fixed table, so nothing typed on the command line reaches a command.
CASES = {"discounts": ("shop-api", "python-pytest-bdd"), "csv-report": ("csv-tool", "generic-junit"),
         "money-convert": ("money-lib", "generic-junit")}
TOOLCHAINS = {"shop-api": ("uv",), "csv-tool": ("go",), "money-lib": ("node", "npm")}
# How the no-plugin arm runs the app's own tests ("python" is the project's interpreter).
BASELINE_TESTS = {"shop-api": ["{python}", "-m", "pytest", "-q", "-p", "no:cacheprovider"], "csv-tool": ["go", "test", "./..."],
                  "money-lib": ["npm", "test", "--silent"]}

# What the person does after `bdd init --adapter generic-junit`: the run line for the app's own runner and the files that
# decide how scenarios run (they are bound with the steps). Go test names carry the marker ending in "_"; the node
# script `bdd` (package.json) compiles the TypeScript and runs node's own test runner with a JUnit reporter.
GENERIC_RUNS = {
    "csv-tool": ("{python} -I tests/run_junit.py --reports go-report.xml --command "
                 "\"go run gotest.tools/gotestsum@v1.12.1 --junitfile go-report.xml -- -count=1 ./tests/... -run {marker}_\"",
                 ["tests/run_junit.py", "go.mod"]),
    "money-lib": ("{python} -I tests/run_junit.py --reports node-report.xml --command \"npm run bdd --silent -- {marker}_ dist/tests/\"",
                  ["tests/run_junit.py", "package.json", "package-lock.json", "tsconfig.json"]),
}


def run(command: list[str], cwd: Path, env: dict, timeout: int = 600, check: bool = True,
        stdin_text: str | None = None) -> subprocess.CompletedProcess:
    done = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          input=stdin_text, stdin=None if stdin_text is not None else subprocess.DEVNULL, timeout=timeout)
    if check and done.returncode != 0:
        raise SystemExit(f"command failed ({done.returncode}): {' '.join(command)}\n{done.stdout}\n{done.stderr}")
    return done


def base_environment(tmp: Path) -> dict:
    env = os.environ.copy()
    env["GREENLIGHT_CACHE_DIR"] = str(tmp / ".cache")
    env.pop("CLAUDE_PLUGIN_DATA", None)
    env["PYTHONUTF8"] = "1"
    return env


def build_project(tmp: Path, case: str = "discounts") -> tuple[Path, dict, str]:
    app, adapter = CASES[case]
    project = tmp / "project"
    shutil.copytree(REPO / "evals" / "apps" / app, project,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "node_modules", "dist"))
    if adapter != "python-pytest-bdd":
        env = base_environment(tmp)
        if app == "money-lib":
            run(["npm", "ci", "--ignore-scripts", "--no-audit", "--no-fund"], project, env, timeout=900)
        return project, env, sys.executable
    venv = tmp / ".venv"
    run(["uv", "venv", "--python", "3.12", str(venv)], tmp, os.environ.copy())
    bin_dir = venv / ("Scripts" if os.name == "nt" else "bin")
    python = bin_dir / ("python.exe" if os.name == "nt" else "python")
    run(["uv", "pip", "install", "--python", str(python), "fastapi", "httpx", "pytest", "pytest-bdd"], tmp, os.environ.copy())
    env = base_environment(tmp)
    env["PATH"] = str(bin_dir) + os.pathsep + env["PATH"]       # `python` in the project is the venv's
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


def swap_run_line(project: Path, case: str) -> None:
    """Act as the person: point the generic-junit adapter at the app's own runner, as its guide says to do.

    The sample runner and its feature are removed, and the runner's own files are bound with the steps."""
    by_tag, support = GENERIC_RUNS[CASES[case][0]]
    config = project / ".bdd" / "config.toml"
    text = config.read_text(encoding="utf-8")
    text = re.sub(r"(?m)^by_tag = .*$", lambda _: "by_tag = " + json.dumps(by_tag), text, count=1)
    text = re.sub(r"(?m)^support = .*$", lambda _: "support = " + json.dumps(support), text, count=1)
    config.write_text(text, encoding="utf-8", newline="\n")
    for sample in ("tests/features/sample.feature", "tests/steps/sample_domain.py", "tests/steps/sample_tests.py",
                   "tests/run_tests.py"):
        (project / sample).unlink(missing_ok=True)


def set_up(project: Path, env: dict, autonomy: str, python: str, case: str = "discounts") -> None:
    run([*GIT, "init", "-q"], project, env)
    commit_all(project, env, "reference app")
    adapter = CASES[case][1]
    bdd(project, env, "init", "--adapter", adapter, "--autonomy", autonomy,
        *(["--python", python] if adapter == "python-pytest-bdd" else []))
    print(bdd(project, env, "init", "--smoke").stdout.strip())
    if adapter == "generic-junit":
        swap_run_line(project, case)
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


def drive(project: Path, env: dict, request: str, model: str, level: str, minutes: int, plugin: Path) -> dict:
    """Run the orchestrator; at standard/guided, deliver the scripted approvals until none is awaited."""
    total = claude(project, env, f'/greenlight:feature "{request.strip()}" --autonomy {level}', model, minutes, plugin)
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


def plugin_row(tmp: Path, args: argparse.Namespace, request: str, level: str, answers: list[dict]) -> dict:
    project, env, python = build_project(tmp, args.request)
    set_up(project, env, level, python, args.request)
    output = drive(project, env, request, MODELS[args.model], level, args.minutes, plugin_directory(tmp, args.hooks))
    row = collect.collect_row(reader(project, env), project, answers, transcript_of(output, project))
    marker = project / ".bdd" / ".enforcement" / "_seen"
    row.update(git_changes(project, env))
    row.update({"hooks_active": marker.is_file(), "claude": claude_summary(output)})
    if args.hooks == "on" and not row["hooks_active"]:
        row["warning"] = "hooks were requested but did not run; this row is not a hard-enforcement result"
    if row.get("phase") not in (None, "discover") and not row.get("cost_recorded"):
        row["cost_warning"] = "the orchestrator recorded no cost with `bdd cost`; the totals above are claude's own"
    row["completed"] = row.get("phase") == "done"
    return row


def baseline_row(tmp: Path, args: argparse.Namespace, request: str) -> dict:
    """The same request without the plugin: what plain Claude Code leaves behind, judged by the app's own tests."""
    project, env, python = build_project(tmp, args.request)
    run([*GIT, "init", "-q"], project, env)
    commit_all(project, env, "reference app")
    prompt = (f"{request.strip()}\n\nImplement this in the project in the current directory. Write tests for it and run "
              "the project's tests. Do not ask questions; decide and state your assumptions.")
    output = claude(project, env, prompt, MODELS[args.model], args.minutes, None)
    command = [python if word == "{python}" else word for word in BASELINE_TESTS[CASES[args.request][0]]]
    tests = run(command, project, env, check=False)
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
    ap.add_argument("--request", default="discounts", choices=sorted(set(requests) & set(CASES)),
                    help="a file in evals/requests/ (each runs on its own reference app)")
    ap.add_argument("--model", default="haiku", choices=sorted(MODELS), help="a name from the MODELS table")
    ap.add_argument("--autonomy", default="autopilot", type=lambda v: parse_list(v, LEVELS, "autonomy"),
                    help="one level or a comma-separated list, e.g. standard,autopilot")
    ap.add_argument("--arms", default="plugin", type=lambda v: parse_list(v, ARMS, "arms"), help="plugin, baseline or both")
    ap.add_argument("--hooks", default="on", choices=("on", "off"), help="off: the plugin's hooks are removed (soft enforcement)")
    ap.add_argument("--runs", type=int, default=1, help="repeat every combination this many times")
    ap.add_argument("--minutes", type=int, default=45, help="give up on one run after this long")
    ap.add_argument("--keep", action="store_true", help="keep the temporary projects and print their paths")
    args = ap.parse_args()
    for tool in ("claude", "git", "sh", *TOOLCHAINS[CASES[args.request][0]]):
        if not shutil.which(tool):
            print(f"{tool} not found on PATH")
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
