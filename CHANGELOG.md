# Changelog

All notable changes are recorded here. Format: [Keep a Changelog](https://keepachangelog.com/),
versions follow [SemVer](https://semver.org/).

## [Unreleased]

### Added
- Repository skeleton, decisions record and verified platform notes.
- `bdd` CLI package skeleton (`tools/bdd`) with `--version`, and CI running the stdlib unit tests on Linux, Windows and macOS with Python 3.11 and 3.14.
- `tools/bdd/bdd` interpreter wrapper: tries `python3`, `python`, `py -3` by executing each (skips the Microsoft Store stub), caches the result in `${CLAUDE_PLUGIN_DATA}`, runs `python -I`; actionable message and exit 127 when no Python 3.11+. The cache lives in a private directory (never shared `/tmp`), is created with `umask 077`, and is trusted only if owned by the current user.
- `bdd doctor` (python, sh, git, hook-latency checks with fixes; `--json`).
- Plugin manifest and single-plugin marketplace (`/plugin marketplace add iadr-dev/greenlight`, `/plugin install greenlight@greenlight`), and an `init` skill that runs `bdd doctor`. Unit tests check the manifests, skill front matter and version agreement; `claude plugin validate` is part of the release checklist.

- Gherkin parser (`bddlib/gherkin.py`): Feature, Rule, Background, Scenario, Scenario Outline, Examples, steps, data tables, doc strings, tags and comments, with localized keywords for 80 languages (`# language: zh-TW`), line-numbered errors, and tag inheritance helpers. The keyword table is a trimmed copy of Cucumber's `gherkin-languages.json` (MIT).

### Added (tooling)
- `evals/platform-probe/probe.py`: re-verifies the Claude Code behaviours the design depends on (hook shell, agent naming, approval-hook behaviour, transcript origin markers, `/loop` scheduling) against the installed CLI.

### Fixed
- CLI output is UTF-8 with LF endings on every terminal and code page (PowerShell, cmd, Git Bash); the wrapper runs Python with `-X utf8`.
- Wrapper failed with `MSYS_NO_PATHCONV=1` on Windows (native `python.exe` received an unconverted `/c/...` path); it now uses `pwd -W`. `bdd doctor` also says why it could not measure hook latency.
