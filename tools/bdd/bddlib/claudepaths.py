"""Where Claude Code keeps things greenlight reads or must protect, and which parts of its settings can switch
greenlight off."""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

TRANSCRIPT_ROOT_ENV = "GREENLIGHT_TRANSCRIPT_ROOT"    # tests, and unusual installations
SETTINGS_NAMES = {"settings.json", "settings.local.json"}
# Claude Code refuses a call matching one of these before any hook runs and no hook can override it (syntax tried live:
# Write/Edit path globs and Bash prefixes). The person adds them (`bdd doctor --add-deny-rules`); greenlight cannot.
RECOMMENDED_DENY = (
    "Write(**/.bdd/**/state.json)", "Edit(**/.bdd/**/state.json)",
    "Write(**/.bdd/**/lock.json)", "Edit(**/.bdd/**/lock.json)",
    "Bash(claude plugin disable:*)", "Bash(claude plugin uninstall:*)", "Bash(claude mcp add:*)",
)
# The settings Claude may change. Everything else can run a command outside the hooks (hooks, statusLine,
# apiKeyHelper, ...), load code (enabledPlugins, extraKnownMarketplaces, MCP servers) or loosen what is asked
# (permissions.defaultMode), so it is the person's; so is a key Claude Code adds later, until it is listed here.
HARMLESS_KEYS = ("$schema", "model", "outputStyle", "includeCoAuthoredBy", "alwaysThinkingEnabled", "language",
                 "spinnerTipsEnabled", "env", "permissions")
HARMLESS_PERMISSIONS = ("allow", "ask", "deny")
# Environment variables that steer the hooks' shell, Python, the tools they find, or where greenlight looks.
STEERING_ENV = re.compile(
    r"PATH|PATHEXT|ENV|BASH_ENV|BASH_FUNC_.*|SHELL|SHELLOPTS|BASHOPTS|IFS|CDPATH|PS4|PROMPT_COMMAND|HOME|USERPROFILE|"
    r"HOMEDRIVE|HOMEPATH|APPDATA|LOCALAPPDATA|PROGRAMDATA|ALLUSERSPROFILE|SYSTEMROOT|SYSTEMDRIVE|WINDIR|COMSPEC|TEMP|TMP|"
    r"TMPDIR|LD_.*|DYLD_.*|PYTHON.*|PERL.*|RUBY.*|NODE_.*|GIT_.*|MSYS.*|MINGW.*|CHERE_INVOKING|XDG_.*|CLAUDE.*|"
    r"ANTHROPIC.*|GREENLIGHT.*|CODEX.*|"
    r"PYTEST.*|PY_.*|PIP_.*|UV_.*|POETRY_.*|CONDA_.*|VIRTUAL_ENV|JAVA_.*|_JAVA_.*|JDK_.*|MAVEN_.*|GRADLE_.*|ORG_GRADLE_.*|"
    r"NPM_.*|YARN_.*|PNPM_.*|BUN_.*|DENO_.*|COREPACK_.*|TS_NODE_.*|TSX_.*|CUCUMBER_.*|PLAYWRIGHT_.*|VITEST_.*|JEST_.*|"
    r"MOCHA_.*|CYPRESS_.*|DOTNET_.*|NUGET_.*|MSBUILD.*|CGO_.*|GO(?:FLAGS|PATH|ROOT|OS|ARCH|PROXY|SUMDB|NOSUMDB|PRIVATE|"
    r"NOPROXY|INSECURE|TOOLCHAIN|EXPERIMENT|CACHE|MODCACHE|WORK|ENV|DEBUG|BIN)|CARGO_.*|RUSTFLAGS|RUSTUP_.*|RUSTC_.*|"
    r"DART_.*|FLUTTER_.*|PUB_.*|GEM_HOME|GEM_PATH|BUNDLE_.*|PHP_.*|COMPOSER_.*|ANDROID_.*|KOTLIN_.*|BDD_.*|CI|"
    r"CORECLR_.*|COR_.*|COMPLUS_.*|POSIXLY_CORRECT|GLOBIGNORE|BASH_.*|ERL_.*|ELIXIR_.*|MIX_.*|LUA_.*|R_.*|LANG|LC_.*",
    re.IGNORECASE)                 # and what steers the test runners, which decide red and green
_ENV_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")      # a name any shell takes as one, with a text value


def config_dir() -> Path:
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")


def transcript_roots() -> list[Path]:
    """Folders under which session transcripts live (resolved)."""
    roots = [config_dir() / "projects"]
    if os.environ.get(TRANSCRIPT_ROOT_ENV):
        roots.append(Path(os.environ[TRANSCRIPT_ROOT_ENV]))
    return [root.resolve() for root in roots]


def codex_home() -> Path:
    """Codex's home folder: its hook and settings files live here, next to its sessions."""
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")


def is_settings_file(path: Path) -> bool:
    """A Claude Code settings file: ``settings.json`` or ``settings.local.json`` in a ``.claude`` folder or in Claude
    Code's own folder. Both spellings count: the path as written (a ``.claude`` that is itself a link elsewhere) and
    the resolved one (a link *to* a ``.claude``)."""
    resolved = Path(os.path.realpath(path))
    for spelling in (path, resolved):
        names = [part.casefold() for part in spelling.parts]
        if names and names[-1] in SETTINGS_NAMES and ".claude" in names[:-1]:
            return True
    return resolved.name.casefold() in SETTINGS_NAMES and resolved.parent == Path(os.path.realpath(config_dir()))


def _not_json(value: str) -> None:
    raise ValueError(f"{value} is not JSON")


def _no_duplicates(pairs: list[tuple[str, object]]) -> dict:
    keys = [key for key, _ in pairs]
    if len(set(keys)) != len(keys):
        raise ValueError(f"a key appears twice ({sorted(k for k in keys if keys.count(k) > 1)[0]!r})")
    return dict(pairs)


def parse_settings(text: str) -> dict:
    """A settings file as Claude Code reads it: strict JSON, an object at the top. A key given twice is refused, so no
    reader can take a different one of the two; so are ``NaN`` and ``Infinity``, which JavaScript does not read."""
    data = json.loads(text, object_pairs_hook=_no_duplicates, parse_constant=_not_json)
    if not isinstance(data, dict):
        raise ValueError("the settings are not a JSON object")
    return data


HARMLESS_TYPES = {"$schema": str, "model": str, "outputStyle": str, "language": str, "includeCoAuthoredBy": bool,
                  "alwaysThinkingEnabled": bool, "spinnerTipsEnabled": bool}


def _strings(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def settings_view(data: dict) -> dict:
    """The parts of a settings file that can switch greenlight off: everything but the harmless keys, the environment
    variables that steer the tools, and greenlight's own deny rules. Two files with the same view are the same to it."""
    view = {key: value for key, value in data.items()                # a harmless key of the wrong type may break the file
            if key not in HARMLESS_KEYS or (key in HARMLESS_TYPES and not isinstance(value, HARMLESS_TYPES[key]))}
    env = data.get("env")
    if isinstance(env, dict):
        steering = {name: value for name, value in env.items()
                    if STEERING_ENV.fullmatch(name) or not _ENV_NAME.fullmatch(name) or not isinstance(value, str)}
        if steering:
            view["env"] = steering
    elif env is not None:
        view["env"] = env
    permissions = data.get("permissions")
    if isinstance(permissions, dict):
        kept = {key: value for key, value in permissions.items() if key not in HARMLESS_PERMISSIONS or not _strings(value)}
        deny = permissions.get("deny", [])
        if not isinstance(deny, list):
            kept["deny"] = deny
        elif any(rule in RECOMMENDED_DENY for rule in deny):
            kept["deny"] = sorted({rule for rule in deny if rule in RECOMMENDED_DENY})
        if kept:
            view["permissions"] = kept
    elif permissions is not None:
        view["permissions"] = permissions
    return view


def view_differences(before: dict, after: dict) -> list[str]:
    """The settings that differ between two files' views, by name (``hooks``, ``permissions.defaultMode``, ``env.PATH``)."""
    old, new = settings_view(before), settings_view(after)
    names = []
    for key in sorted(set(old) | set(new), key=str):
        if (key in old, old.get(key)) == (key in new, new.get(key)):
            continue
        inner_old, inner_new = old.get(key, {}), new.get(key, {})
        if isinstance(inner_old, dict) and isinstance(inner_new, dict) and inner_old != inner_new:
            names += [f"{key}.{name}" for name in sorted(set(inner_old) | set(inner_new), key=str)
                      if inner_old.get(name) != inner_new.get(name)]
        else:
            names.append(key)
    return names


SETTINGS_DIGEST = "settings-view:"


def settings_digest(path: Path, raw_digest: str) -> str:
    """What the integrity check fingerprints for a settings file: its view (``settings_view``), so a harmless change
    is no violation; the bytes (``raw_digest``) when it cannot be read as settings, so any change to it is one."""
    try:
        view = settings_view(parse_settings(path.read_text(encoding="utf-8")))
    except (OSError, UnicodeDecodeError, ValueError):
        return raw_digest
    canonical = json.dumps(view, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return SETTINGS_DIGEST + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
