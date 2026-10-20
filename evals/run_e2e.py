#!/usr/bin/env python3
"""Run a whole feature through greenlight with real agents, and measure what happened.

    python evals/run_e2e.py [--request discounts|adopt-billing] [--model haiku] [--autonomy autopilot] [--keep]

It copies the request's reference app (evals/apps/shop-api for a feature, evals/apps/legacy-billing for an adoption)
into a temporary project with its own virtual environment, sets greenlight up (`bdd init --adapter
python-pytest-bdd`, proves the sample green), then asks Claude Code, headless, to run `/greenlight:feature
"<request>"` (`/greenlight:adopt "<area>"` for an adoption request). Afterwards it reads the project's own records, with the
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
APPS = REPO / "evals" / "apps"
REQUESTS = REPO / "evals" / "requests"
RESULTS = REPO / "evals" / "results"
TOOLS = "Agent Bash Read Write Edit MultiEdit Grep Glob"
GIT = ["git", "-c", "user.name=e2e", "-c", "user.email=e2e@example.com", "-c", "commit.gpgsign=false",
       "-c", "gc.auto=0", "-c", "maintenance.auto=false"]


# What each request needs: its reference app, the skill that runs it and the packages the app and its tests import.
# A feature request is judged by reaching `done`, an adoption request by the invariants in adoption_invariants.
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


def set_up(project: Path, env: dict, autonomy: str, python: str) -> None:
    run([*GIT, "init", "-q"], project, env)
    run([*GIT, "add", "-A"], project, env)
    run([*GIT, "commit", "-q", "-m", "reference app"], project, env)
    bdd(project, env, "init", "--adapter", "python-pytest-bdd", "--autonomy", autonomy, "--python", python)
    smoke = bdd(project, env, "init", "--smoke")
    print(smoke.stdout.strip())
    run([*GIT, "add", "-A"], project, env)
    run([*GIT, "commit", "-q", "-m", "greenlight set up"], project, env)


def ask(project: Path, env: dict, request: str, skill: str, model: str, autonomy: str, minutes: int) -> dict:
    prompt = f'/greenlight:{skill} "{request.strip()}" --autonomy {autonomy}'
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
    classify = read_json(project, env, "classify", feature, "--json")
    green = (classify.get("green") or {}).get("valid") if isinstance(classify, dict) else None
    return {"adopt_check_clean": check.returncode == 0, "adopt_check_output": (check.stdout + check.stderr).strip()[:600],
            "production_files_touched": touched, "green_valid": green,
            "holds": check.returncode == 0 and not touched and green is True}


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
        "kind": state.get("kind"),
    })
    if state.get("kind") == "adopt":
        row["adoption"] = adoption_invariants(project, env, feature)
    return row


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    requests = {p.stem: p for p in sorted(REQUESTS.glob("*.md"))}
    ap.add_argument("--request", default="discounts", choices=sorted(REQUEST_KINDS), help="a file in evals/requests/")
    ap.add_argument("--model", default="haiku", choices=sorted(MODELS), help="a name from the MODELS table")
    ap.add_argument("--autonomy", default="autopilot", choices=("guided", "standard", "auto", "autopilot"))
    ap.add_argument("--minutes", type=int, default=45, help="give up after this long")
    ap.add_argument("--keep", action="store_true", help="keep the temporary project and print its path")
    args = ap.parse_args()
    for tool in ("claude", "uv", "git", "sh"):
        if not shutil.which(tool):
            print(f"{tool} not found on PATH")
            return 2
    kind = REQUEST_KINDS[args.request]
    request = requests[args.request].read_text(encoding="utf-8")
    model = MODELS[args.model]
    tmp = Path(tempfile.mkdtemp(prefix="greenlight-e2e-")).resolve()
    try:
        project, env, python = build_project(tmp, kind)
        set_up(project, env, args.autonomy, python)
        output = ask(project, env, request, kind["skill"], model, args.autonomy, args.minutes)
        row = {"request": args.request, "model": args.model, "claude": {k: output.get(k) for k in (
            "exit", "seconds", "is_error", "num_turns", "total_cost_usd", "subtype")}, **collect(project, env)}
        RESULTS.mkdir(exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        (RESULTS / f"{stamp}-{args.request}-{args.model}.json").write_text(
            json.dumps({"row": row, "result_text": output.get("result") or output.get("raw")}, indent=2, ensure_ascii=False),
            encoding="utf-8")
        print(json.dumps(row, indent=2, ensure_ascii=False))
        print("\nlast words of the session:\n" + str(output.get("result") or output.get("raw") or "")[-1500:])
        held = row["adoption"]["holds"] if "adoption" in row else True
        return 0 if row.get("phase") == "done" and held else 1
    finally:
        if args.keep:
            print(f"\nkept: {tmp}")
        else:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
