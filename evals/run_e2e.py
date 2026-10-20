#!/usr/bin/env python3
"""Run a whole feature through greenlight with real agents, and measure what happened.

    python evals/run_e2e.py [--request discounts] [--model haiku] [--autonomy autopilot] [--keep]

It copies the request's reference app (evals/apps/: shop-api, csv-tool or money-lib) into a temporary project, with its own
virtual environment for the Python app, sets greenlight up (`bdd init`, proves the sample green), then asks Claude Code,
headless, to run `/greenlight:feature "<request>"`. Afterwards it reads the project's own records, with the
`bdd` CLI and git, never the conversation, and writes one metrics row to evals/results/.

Needs `claude`, `uv`, `git` and `sh` on PATH, working credentials, and some money: a run makes many model
calls. Not part of CI. Autopilot is the default because a headless run has no person to approve; the approvals
are then recorded as automatic and the report says so.
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

REPO = Path(__file__).resolve().parents[1]
REQUESTS = REPO / "evals" / "requests"
RESULTS = REPO / "evals" / "results"
TOOLS = "Agent Bash Read Write Edit MultiEdit Grep Glob"
GIT = ["git", "-c", "user.name=e2e", "-c", "user.email=e2e@example.com", "-c", "commit.gpgsign=false",
       "-c", "gc.auto=0", "-c", "maintenance.auto=false"]


# The model and the request are chosen from fixed tables, so nothing typed on the command line reaches a command.
MODELS = {"haiku": "haiku", "sonnet": "sonnet", "opus": "opus", "haiku-5.5": "us.anthropic.claude-haiku-5-5",
          "sonnet-5.5": "us.anthropic.claude-sonnet-5-5", "opus-5.5": "us.anthropic.claude-opus-5-5"}


# Each request runs on one reference app with one adapter; the answers a person would give are in
# evals/requests/answers/<request>.md. A fixed table, so nothing typed on the command line reaches a command.
CASES = {"discounts": ("shop-api", "python-pytest-bdd"), "csv-report": ("csv-tool", "generic-junit"),
         "money-convert": ("money-lib", "generic-junit")}
TOOLCHAINS = {"shop-api": ("uv",), "csv-tool": ("go",), "money-lib": ("node", "npm")}

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
    run([*GIT, "add", "-A"], project, env)
    run([*GIT, "commit", "-q", "-m", "reference app"], project, env)
    adapter = CASES[case][1]
    bdd(project, env, "init", "--adapter", adapter, "--autonomy", autonomy, *(["--python", python] if adapter == "python-pytest-bdd" else []))
    smoke = bdd(project, env, "init", "--smoke")
    print(smoke.stdout.strip())
    if adapter == "generic-junit":
        swap_run_line(project, case)
    run([*GIT, "add", "-A"], project, env)
    run([*GIT, "commit", "-q", "-m", "greenlight set up"], project, env)


def ask(project: Path, env: dict, request: str, model: str, autonomy: str, minutes: int) -> dict:
    prompt = f'/greenlight:feature "{request.strip()}" --autonomy {autonomy}'
    command = ["claude", "-p", "--plugin-dir", str(REPO), "--model", model, "--allowedTools", TOOLS,
               "--output-format", "json", "--setting-sources", "project"]          # the prompt goes in on stdin
    started = time.time()
    try:
        done = run(command, project, env, timeout=minutes * 60, check=False, stdin_text=prompt)
        text, code = done.stdout, done.returncode
    except subprocess.TimeoutExpired as exc:
        text, code = (exc.stdout or "") if isinstance(exc.stdout, str) else "", "timeout"
    try:
        output = json.loads(text)
    except ValueError:
        output = {"raw": text[-4000:]}
    output["exit"], output["seconds"] = code, round(time.time() - started)
    return output


def read_json(project: Path, env: dict, *args: str) -> object:
    done = bdd(project, env, *args, check=False)
    try:
        return json.loads(done.stdout)
    except ValueError:
        return {"error": (done.stderr or done.stdout).strip()[:500]}


def collect(project: Path, env: dict) -> dict:
    status = read_json(project, env, "status", "--json")
    features = status.get("features", []) if isinstance(status, dict) else []
    row: dict = {"features": len(features), "open_violations": status.get("open_violations") if isinstance(status, dict) else None}
    if not features:
        return row
    feature = features[0]["feature"]
    state = read_json(project, env, "state", "show", feature, "--json")
    trace = read_json(project, env, "trace", feature, "--json")
    locks = bdd(project, env, "lock", feature, "--check", "--require", check=False)
    classify = read_json(project, env, "classify", feature, "--json")
    changed = run([*GIT, "diff", "--stat", "HEAD"], project, env, check=False).stdout.strip().splitlines()
    untracked = run([*GIT, "ls-files", "--others", "--exclude-standard"], project, env, check=False).stdout.split()
    row.update({
        "feature": feature, "phase": state.get("phase"), "autonomy": (state.get("autonomy") or {}).get("level"),
        "gates": {name: g["result"] for name, g in (state.get("gates") or {}).items()},
        "approvals": [(a["gate"], a["grade"], a["origin"]) for a in state.get("approvals", [])],
        "enforcement": (state.get("enforcement") or {}).get("level"), "assumptions": len(state.get("assumptions", [])),
        "red_recorded": bool(state.get("red")), "locks_intact": locks.returncode == 0,
        "locks_message": (locks.stdout + locks.stderr).strip()[:300],
        "trace_gaps": [g["code"] for g in trace.get("gaps", [])] if isinstance(trace, dict) else None,
        "totals": trace.get("totals") if isinstance(trace, dict) else None,
        "green": (classify.get("green") or {}).get("valid") if isinstance(classify, dict) else None,
        "green_problems": (classify.get("green") or {}).get("problems") if isinstance(classify, dict) else None,
        "tokens": sum(c.get("tokens", 0) for c in (state.get("cost") or {}).values()),
        "files_changed": changed[-1] if changed else "", "new_files": len(untracked),
        "report_written": any(f.endswith("report.md") for f in untracked),
    })
    return row


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    requests = {p.stem: p for p in sorted(REQUESTS.glob("*.md"))}
    ap.add_argument("--request", default="discounts", choices=sorted(set(requests) & set(CASES)),
                    help="a file in evals/requests/ (each runs on its own reference app)")
    ap.add_argument("--model", default="haiku", choices=sorted(MODELS), help="a name from the MODELS table")
    ap.add_argument("--autonomy", default="autopilot", choices=("guided", "standard", "auto", "autopilot"))
    ap.add_argument("--minutes", type=int, default=45, help="give up after this long")
    ap.add_argument("--keep", action="store_true", help="keep the temporary project and print its path")
    args = ap.parse_args()
    for tool in ("claude", "git", "sh", *TOOLCHAINS[CASES[args.request][0]]):
        if not shutil.which(tool):
            print(f"{tool} not found on PATH")
            return 2
    request = requests[args.request].read_text(encoding="utf-8")
    model = MODELS[args.model]
    tmp = Path(tempfile.mkdtemp(prefix="greenlight-e2e-")).resolve()
    try:
        project, env, python = build_project(tmp, args.request)
        set_up(project, env, args.autonomy, python, args.request)
        output = ask(project, env, request, model, args.autonomy, args.minutes)
        row = {"request": args.request, "model": args.model, "claude": {k: output.get(k) for k in (
            "exit", "seconds", "is_error", "num_turns", "total_cost_usd", "subtype")}, **collect(project, env)}
        RESULTS.mkdir(exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        (RESULTS / f"{stamp}-{args.request}-{args.model}.json").write_text(
            json.dumps({"row": row, "result_text": output.get("result") or output.get("raw")}, indent=2, ensure_ascii=False),
            encoding="utf-8")
        print(json.dumps(row, indent=2, ensure_ascii=False))
        print("\nlast words of the session:\n" + str(output.get("result") or output.get("raw") or "")[-1500:])
        return 0 if row.get("phase") == "done" else 1
    finally:
        if args.keep:
            print(f"\nkept: {tmp}")
        else:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
