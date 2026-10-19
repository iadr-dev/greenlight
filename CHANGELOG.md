# Changelog

All notable changes are recorded here. Format: [Keep a Changelog](https://keepachangelog.com/),
versions follow [SemVer](https://semver.org/).

## [Unreleased]

### Added
- Repository skeleton, decisions record and verified platform notes (M0.1).
- `tools/bdd/bdd` interpreter wrapper: tries `python3`, `python`, `py -3` by executing each (skips the Microsoft Store stub), caches the result in `${CLAUDE_PLUGIN_DATA}`, runs `python -I`; actionable message and exit 127 when no Python 3.11+ (M0.5).
- `bdd doctor` (python, sh, git, hook-latency checks with fixes; `--json`) (M0.5).
