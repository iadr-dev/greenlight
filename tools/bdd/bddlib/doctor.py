"""`bdd doctor`: check the environment and print a fix for everything that is wrong.

Check functions are pure (inputs in, Check out) so they can be unit-tested without
touching the machine. `run_checks` wires them to the real environment.
"""
from __future__ import annotations

import json
import shutil
import statistics
import subprocess
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path

MIN_PYTHON = (3, 11)
BUDGET_MS_POSIX = 200
BUDGET_MS_WINDOWS = 300


@dataclass
class Check:
    name: str
    status: str  # ok | warn | fail
    detail: str
    fix: str = ""


def check_python(version_info, executable: str) -> Check:
    v = ".".join(str(x) for x in tuple(version_info)[:3])
    if tuple(version_info)[:2] < MIN_PYTHON:
        return Check("python", "fail", f"Python {v} at {executable}; need >= 3.11",
                     "Install Python 3.11 or newer (https://www.python.org/downloads/).")
    if "WindowsApps" in executable:
        return Check("python", "warn", f"Python {v} at {executable} is a Microsoft Store install",
                     "Works, but the Store alias can be unreliable; prefer the python.org installer.")
    return Check("python", "ok", f"Python {v} at {executable}")


def check_tool(name: str, found: str | None, fix: str, required: bool) -> Check:
    if found:
        return Check(name, "ok", found)
    return Check(name, "fail" if required else "warn", f"{name} not found on PATH", fix)


def budget_ms(platform: str) -> int:
    return BUDGET_MS_WINDOWS if platform.startswith("win") else BUDGET_MS_POSIX


def check_latency(samples_ms: list[float], platform: str, error: str = "") -> Check:
    if not samples_ms:
        why = error or "wrapper not found"
        return Check("hook latency", "warn", f"could not measure ({why})",
                     "Hooks call tools/bdd/bdd, so this likely means hooks will fail too. "
                     "Run `sh tools/bdd/bdd --version` and fix what it reports.")
    med = statistics.median(samples_ms)
    limit = budget_ms(platform)
    detail = f"median {med:.0f} ms over {len(samples_ms)} runs (budget {limit} ms)"
    if med <= limit:
        return Check("hook latency", "ok", detail)
    return Check("hook latency", "warn", detail,
                 "Hooks run on every edit. Exclude the plugin and Python folders from antivirus "
                 "real-time scanning, or move the repo off a network drive.")


def measure_wrapper(wrapper: Path, runs: int = 5) -> tuple[list[float], str]:
    """Time `bdd --version` through the real wrapper. Returns (samples_ms, error)."""
    sh = shutil.which("sh")
    if not sh:
        return [], "sh not found"
    if not wrapper.exists():
        return [], f"{wrapper} does not exist"
    samples = []
    for _ in range(runs):
        t = time.perf_counter()
        r = subprocess.run([sh, str(wrapper), "--version"], capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            msg = (r.stderr or r.stdout).strip().splitlines()
            return [], f"exit {r.returncode}: {msg[0] if msg else 'no output'}"
        samples.append((time.perf_counter() - t) * 1000)
    return samples[1:], ""  # first run may populate the interpreter cache


def run_checks() -> list[Check]:
    wrapper = Path(__file__).resolve().parents[1] / "bdd"
    samples, error = measure_wrapper(wrapper)
    return [
        check_python(sys.version_info, sys.executable),
        check_tool("sh", shutil.which("sh"),
                   "Hooks need a POSIX shell. On Windows install Git for Windows (Git Bash).", True),
        check_tool("git", shutil.which("git"), "Install git: https://git-scm.com/downloads", True),
        check_latency(samples, sys.platform, error),
    ]


def render(checks: list[Check]) -> str:
    mark = {"ok": "ok  ", "warn": "WARN", "fail": "FAIL"}
    lines = []
    for c in checks:
        lines.append(f"[{mark[c.status]}] {c.name}: {c.detail}")
        if c.fix and c.status != "ok":
            lines.append(f"       fix: {c.fix}")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    checks = run_checks()
    if "--json" in argv:
        print(json.dumps([asdict(c) for c in checks], indent=2))
    else:
        print(render(checks))
    return 1 if any(c.status == "fail" for c in checks) else 0
