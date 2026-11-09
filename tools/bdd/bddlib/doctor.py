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

from . import claudepaths, config as cfg, enforcement, helpers, models

MIN_PYTHON = (3, 11)
BUDGET_MS_POSIX = 200
BUDGET_MS_WINDOWS = 300
LATENCY = "hook latency"
DENY_RULES = "deny rules"
ENFORCEMENT = "enforcement"
CODEX_HOOKS = "codex hooks"
STANDARDS = "standards"
HELPERS = "helpers"
PLUGIN_HOOKS = "plugin hooks"
MODELS = "models"
INTEGRITY = "integrity"
RECOMMENDED_DENY = claudepaths.RECOMMENDED_DENY
ADD_DENY_RULES = "--add-deny-rules"


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


def add_deny_line() -> str:
    wrapper = Path(__file__).resolve().parents[1] / "bdd"
    return f'! sh "{wrapper.as_posix()}" doctor {ADD_DENY_RULES}'


def check_deny_rules(denied: set[str]) -> Check:
    missing = [rule for rule in RECOMMENDED_DENY if rule not in denied]
    if not missing:
        return Check(DENY_RULES, "ok", f"all {len(RECOMMENDED_DENY)} recommended rules are set")
    return Check(DENY_RULES, "warn", f"{len(missing)} of {len(RECOMMENDED_DENY)} recommended deny rules are not set",
                 "Claude Code applies deny rules before any hook, so they hold even if a shell command is spelled in a way "
                 "the guard cannot read. Only you can add them: type this line in Claude Code (the leading ! runs it in "
                 "your own shell). It adds the missing ones to .claude/settings.json and keeps everything else:\n"
                 + add_deny_line())


def add_deny_rules(root: Path) -> tuple[int, str]:
    """Merge the missing recommended deny rules into the project's ``.claude/settings.json``, keeping every other key
    and rule as it is. Idempotent. A file that is not valid settings JSON is left alone."""
    path = root / ".claude" / "settings.json"
    try:
        data = claudepaths.parse_settings(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        return 2, f"bdd doctor: {path.as_posix()} cannot be read as settings ({exc}); fix it first, nothing was changed"
    permissions = data.setdefault("permissions", {})
    deny = permissions.setdefault("deny", []) if isinstance(permissions, dict) else None
    if not isinstance(deny, list):
        return 2, "bdd doctor: permissions.deny in .claude/settings.json is not a list; fix it first, nothing was changed"
    missing = [rule for rule in RECOMMENDED_DENY if rule not in deny]
    if not missing:
        return 0, "every recommended deny rule is already in .claude/settings.json"
    deny += missing
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return 0, f"added {len(missing)} deny rule(s) to .claude/settings.json: " + ", ".join(missing)


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


def check_integrity(root: Path) -> Check:
    from . import tripwire
    from .errors import StoreError
    try:
        status, detail = tripwire.summary(root)
    except (StoreError, OSError, KeyError, TypeError, ValueError) as exc:
        return Check(INTEGRITY, "warn", f"the integrity data cannot be read ({exc})",
                     "The implement and verify gates refuse until .bdd/.integrity is readable again; see docs/troubleshooting.md.")
    if enforcement.codex_seen(root) or shutil.which("codex"):
        detail += "; the plugin copy Codex runs is not watched (Codex is soft, D11)"
    return Check(INTEGRITY, status, detail, "" if status == "ok" else
                 "Undo a change you did not make (for example with git). If you made it or want it, type "
                 f"{tripwire.ACKNOWLEDGE_COMMAND} in Claude Code, with the ids `bdd status` lists.")


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


def check_helpers(plugins: dict[str, str] | None, declined: bool) -> list[Check]:
    """Which of the helper plugins are installed (information only: greenlight works without them), and the installed
    plugins whose hooks react to every edit."""
    if plugins is None:
        return [Check(HELPERS, "ok", "Claude Code's plugin list could not be read, so the helper plugins are not checked")]
    gaps = helpers.missing(plugins)
    have = len(helpers.CATALOG) - len(helpers.missing(plugins, only_recommended=False))
    detail = f"{have} of {len(helpers.CATALOG)} helper plugins installed" + (
        f"; recommended and missing: {', '.join(h.name for h in gaps)} (`bdd helpers` shows how to install them)"
        if gaps and not declined else "")
    out = [Check(HELPERS, "ok", detail)]
    reacting = sorted(n for n in helpers.short_names(plugins) if n in helpers.HOOK_PLUGINS)
    if reacting:
        notes = "; ".join(f"{n}: {helpers.HOOK_PLUGINS[n]}" for n in reacting)
        out.append(Check(PLUGIN_HOOKS, "ok", "installed plugins whose hooks react to every edit, test files included, and may ask "
                         "an agent to change a test (it leaves tests alone, the guard sees to that): " + notes))
    return out


def check_models(root: Path) -> Check:
    """Can every choice in [models] be passed on an Agent call? The Agent tool takes an alias only."""
    try:
        chosen = cfg.load(root).models
    except cfg.ConfigError as exc:
        return Check(MODELS, "fail", f"the [models] table cannot be read: {exc}", "Fix .bdd/config.toml.")
    found = models.problems(chosen)
    if found:
        return Check(MODELS, "fail", "; ".join(found),
                     f"Name one of {', '.join(models.ACCEPTED)} for an agent in [models] of .bdd/config.toml, "
                     "or remove the line to use the model of its agent file.")
    return Check(MODELS, "ok", f"{len(chosen)} chosen in .bdd/config.toml" if chosen
                 else "every agent runs on the model of its agent file (no [models] in .bdd/config.toml)")


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
    standards = [check_standards(project), check_models(project)] if project else []
    integrity = [check_integrity(project)] if project else []
    codex = [c for c in [project_codex_hooks(project)] if c] if project else []
    plugin_checks = check_helpers(helpers.installed(), helpers.declined(project))
    return [
        check_python(sys.version_info, sys.executable),
        check_tool("sh", shutil.which("sh"),
                   "Hooks need a POSIX sh. On Windows install Git for Windows (https://git-scm.com/download/win); without it greenlight runs in soft enforcement only.", False),
        check_tool("git", shutil.which("git"), "Install git: https://git-scm.com/downloads", True),
        check_latency(samples, sys.platform, error),
        *mode,
        *integrity,
        *codex,
        *standards,
        *deny,
        *plugin_checks,
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
    if ADD_DENY_RULES in argv:
        root = cfg.find_root()
        if root is None:
            print("bdd doctor: not inside a greenlight project (no .bdd directory found)", file=sys.stderr)
            return 2
        code, said = add_deny_rules(root)
        print(said, file=sys.stderr if code else sys.stdout)
        return code
    checks = run_checks()
    if "--json" in argv:
        print(json.dumps([asdict(c) for c in checks], indent=2))
    else:
        print(render(checks))
    return 1 if any(c.status == "fail" for c in checks) else 0
