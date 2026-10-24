"""`bdd doctor`: check the environment and print a fix for everything that is wrong.

Check functions are pure (inputs in, Check out) so they can be unit-tested without
touching the machine. `run_checks` wires them to the real environment.
"""
from __future__ import annotations

import json
import re
import shutil
import statistics
import subprocess
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path

from . import claudepaths, config as cfg, enforcement

MIN_PYTHON = (3, 11)
BUDGET_MS_POSIX = 200
BUDGET_MS_WINDOWS = 300
LATENCY = "hook latency"
DENY_RULES = "deny rules"
ENFORCEMENT = "enforcement"
CODEX_HOOKS = "codex hooks"
STANDARDS = "standards"
# Claude Code refuses a call matching one of these before any hook runs and no hook can override it
# (syntax tried live: Write/Edit path globs and Bash prefixes). The person adds them; greenlight cannot.
RECOMMENDED_DENY = (
    "Write(**/.bdd/**/state.json)", "Edit(**/.bdd/**/state.json)",
    "Write(**/.bdd/**/lock.json)", "Edit(**/.bdd/**/lock.json)",
    "Write(**/.claude/settings*.json)", "Edit(**/.claude/settings*.json)",
    "Bash(claude plugin disable:*)", "Bash(claude plugin uninstall:*)", "Bash(claude mcp add:*)",
)


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
        return Check(LATENCY, "warn", f"could not measure ({why})",
                     "Hooks call tools/bdd/bdd, so this likely means hooks will fail too. "
                     "Run `sh tools/bdd/bdd --version` and fix what it reports.")
    med = statistics.median(samples_ms)
    limit = budget_ms(platform)
    detail = f"median {med:.0f} ms over {len(samples_ms)} runs (budget {limit} ms)"
    if med <= limit:
        return Check(LATENCY, "ok", detail)
    return Check(LATENCY, "warn", detail,
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


def settings_files(root: Path) -> list[Path]:
    """The settings files that can carry permission rules, from the project up to the machine."""
    managed = {"win32": Path("C:/ProgramData/ClaudeCode/managed-settings.json"),
               "darwin": Path("/Library/Application Support/ClaudeCode/managed-settings.json")}
    return [root / ".claude" / "settings.json", root / ".claude" / "settings.local.json",
            claudepaths.config_dir() / "settings.json",
            managed.get(sys.platform, Path("/etc/claude-code/managed-settings.json"))]


def read_denied(paths: list[Path]) -> set[str]:
    """Every ``permissions.deny`` entry in the files that exist and parse (the others contribute nothing)."""
    denied: set[str] = set()
    for path in paths:
        try:
            rules = json.loads(path.read_text(encoding="utf-8")).get("permissions", {}).get("deny", [])
        except (OSError, ValueError, AttributeError):
            continue
        if isinstance(rules, list):
            denied.update(r for r in rules if isinstance(r, str))
    return denied


def check_deny_rules(denied: set[str]) -> Check:
    missing = [rule for rule in RECOMMENDED_DENY if rule not in denied]
    if not missing:
        return Check(DENY_RULES, "ok", f"all {len(RECOMMENDED_DENY)} recommended rules are set")
    snippet = json.dumps({"permissions": {"deny": missing}}, indent=2)
    return Check(DENY_RULES, "warn", f"{len(missing)} of {len(RECOMMENDED_DENY)} recommended deny rules are not set",
                 "Claude Code applies deny rules before any hook, so they hold even if a shell command is spelled in a way "
                 "the guard cannot read. Add them to .claude/settings.json (or managed settings for a team); "
                 "the agent is not allowed to edit that file, so this has to be you:\n" + snippet)


def check_enforcement(mode: str, hooks_seen: bool) -> Check:
    """What a project can actually rely on: hooks prevent, soft mode only detects afterwards."""
    soft_fix = ("Soft enforcement detects tampering afterwards and prevents nothing: run `bdd lock FEAT-n --check --require` "
                "in CI. To get prevention, use Claude Code with the plugin's hooks (needs a POSIX sh).")
    if mode == "soft":
        return Check(ENFORCEMENT, "warn", 'soft (enforcement = "soft"): violations are detected, not prevented', soft_fix)
    if mode == "hard":
        return Check(ENFORCEMENT, "ok" if hooks_seen else "warn",
                     'hard (enforcement = "hard"): approvals must be typed by the person' if hooks_seen else
                     'hard is required but no hook has run in this project yet; start it from Claude Code with the plugin',
                     "" if hooks_seen else "Hooks only run inside Claude Code with the greenlight plugin enabled.")
    if hooks_seen:
        return Check(ENFORCEMENT, "ok", "hooks have run in this project: approvals have to be typed by the person")
    return Check(ENFORCEMENT, "warn", "no hook has run in this project yet, so nothing is prevented (soft)", soft_fix)


def project_enforcement(project: Path) -> Check:
    try:
        return check_enforcement(cfg.load(project).enforcement, enforcement.hooks_seen(project))
    except cfg.ConfigError as exc:
        return Check(ENFORCEMENT, "warn", f"the project configuration cannot be read ({exc})",
                     "Fix .bdd/config.toml (or run `bdd migrate` if it is from an older greenlight).")


def check_codex_hooks(codex_on_path: bool, installed: bool, observed: bool) -> Check | None:
    """Codex is enforced only by hooks the person installed, and only once they have really run in this project."""
    if not (codex_on_path or installed):
        return None
    if installed and observed:
        return Check(CODEX_HOOKS, "ok", "greenlight's Codex hooks are installed and have run in this project")
    if installed:
        return Check(CODEX_HOOKS, "warn", "greenlight's Codex hooks are installed but have not run in this project yet",
                     "Start Codex in this project and review and trust the hooks when it asks. Until a hook has run, "
                     "work done in Codex is soft: detected afterwards, not prevented.")
    return Check(CODEX_HOOKS, "warn", "Codex is available but greenlight's hooks are not installed: work done in Codex is soft",
                 "Run `bdd install-hooks codex` to see the entries, then `bdd install-hooks codex --apply` to write them. "
                 "Without them nothing is prevented in Codex, only detected afterwards (`bdd lock FEAT-n --check --require`).")


def project_codex_hooks(project: Path) -> Check | None:
    from . import installhooks
    files = [installhooks.target(None), installhooks.target(project)]
    return check_codex_hooks(shutil.which("codex") is not None, any(installhooks.installed(p) for p in files),
                             (enforcement.marker_dir(project) / enforcement.CODEX_MARKER).is_file())


def check_standards(root: Path) -> Check:
    """Are the project's engineering standards in place? They are in force as soon as the file exists; only the person
    can edit it."""
    path = root / cfg.BDD_DIR / "standards.md"
    if not path.is_file():
        return Check(STANDARDS, "warn", ".bdd/standards.md does not exist: no language, style or deprecation rules are stated",
                     "Run `bdd init --standards` to add greenlight's default standards; the agents follow them from then on. "
                     "You may edit the file; agents cannot write it.")
    left = unfilled_placeholders(path.read_text(encoding="utf-8-sig", errors="replace"))
    if left:
        return Check(STANDARDS, "ok", f".bdd/standards.md is in force; {len(left)} placeholder(s) mean what the project "
                     f"already uses, for example {left[0]}")
    return Check(STANDARDS, "ok", ".bdd/standards.md is in force")


_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_FENCE = re.compile(r"^```.*?^```", re.DOTALL | re.MULTILINE)
_PLACEHOLDER = re.compile(r"<[A-Za-z][^<>\n]*\s[^<>\n]*>")     # `<tool and threshold>`; not `List<T>` or `<br>`


def unfilled_placeholders(text: str) -> list[str]:
    """The template's `<placeholder>` texts still in the file, outside comments and code blocks."""
    return _PLACEHOLDER.findall(_FENCE.sub("", _COMMENT.sub("", text)))


def run_checks() -> list[Check]:
    wrapper = Path(__file__).resolve().parents[1] / "bdd"
    samples, error = measure_wrapper(wrapper)
    project = cfg.find_root()
    deny = [check_deny_rules(read_denied(settings_files(project)))] if project else []
    mode = [project_enforcement(project)] if project else []
    standards = [check_standards(project)] if project else []
    codex = [c for c in [project_codex_hooks(project)] if c] if project else []
    return [
        check_python(sys.version_info, sys.executable),
        check_tool("sh", shutil.which("sh"),
                   "Hooks need a POSIX sh. On Windows install Git for Windows (https://git-scm.com/download/win); without it greenlight runs in soft enforcement only.", False),
        check_tool("git", shutil.which("git"), "Install git: https://git-scm.com/downloads", True),
        check_latency(samples, sys.platform, error),
        *mode,
        *codex,
        *standards,
        *deny,
    ]


def render(checks: list[Check]) -> str:
    mark = {"ok": "ok  ", "warn": "WARN", "fail": "FAIL"}
    lines = []
    for c in checks:
        lines.append(f"[{mark[c.status]}] {c.name}: {c.detail}")
        if c.fix and c.status != "ok":
            fix_lines = c.fix.splitlines()
            lines.append(f"       fix: {fix_lines[0]}")
            lines += [f"            {line}" for line in fix_lines[1:]]
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    checks = run_checks()
    if "--json" in argv:
        print(json.dumps([asdict(c) for c in checks], indent=2))
    else:
        print(render(checks))
    return 1 if any(c.status == "fail" for c in checks) else 0
