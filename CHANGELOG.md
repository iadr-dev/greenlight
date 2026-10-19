# Changelog

All notable changes are recorded here. Format: [Keep a Changelog](https://keepachangelog.com/),
versions follow [SemVer](https://semver.org/).

## [Unreleased]

### Added
- Repository skeleton, decisions record and verified platform notes.
- `bdd` CLI package skeleton (`tools/bdd`) with `--version`, and CI running the stdlib unit tests on Linux, Windows and macOS with Python 3.11 and 3.14.
- `tools/bdd/bdd` interpreter wrapper: tries `python3`, `python`, `py -3` by executing each (skips the Microsoft Store stub), caches the result in `${CLAUDE_PLUGIN_DATA}`, runs `python -I`; actionable message and exit 127 when no Python 3.11+. The cache lives in a private directory (never shared `/tmp`), is created with `umask 077`, and is trusted only if owned by the current user.
- `bdd doctor` (python, sh, git, hook-latency checks with fixes; `--json`).
