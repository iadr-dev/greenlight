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

- Core step vocabulary (`vocabulary/core.json`): 28 instructions in five profiles (`base`, `api`, `ui`, `cli`, `lib`) with English patterns and Traditional Chinese alternates, and `bddlib/vocabulary.py` to compile typed patterns (`{amount:int}`, `{state:enum(on,off)}`, `{duration}`), load a project's `vocabulary.toml` of domain steps that compose core instructions, and resolve step text to the instruction(s) it matches. Ambiguity is reported, never hidden.

- `bdd lint [paths]`: checks `.feature` files against the step vocabulary and reports `L001` parse errors, `L002` unresolved steps (with the closest pattern as a hint), `L003` ambiguous steps, `L007` instructions from a disabled profile, `L008` wrong table/doc-string shape, `L009` Scenario Outline parameter mismatches and `L011` `# proposed-step` warnings. Reads `.bdd/config.toml` and `.bdd/vocabulary.toml` when present; `--json` for tools; exit code 1 on errors, 2 on usage problems. It also enforces the rest of the vocabulary rules: `L004` implementation details in steps (URLs, HTTP verbs and status codes, SQL, selectors, code calls, class names; quoted values are data), `L005`/`L006` trace tags (`@FEAT-n`, `@R-n.m`, `@EX-n.m.k` present, well-formed, consistent and unique; `--no-trace-tags` for unmanaged files), and, for the project's own `vocabulary.toml`, `L010` near-duplicate patterns (similarity threshold from `.bdd/config.toml`, cleared by a `justification`) and `L012` domain steps that do not compose core instructions properly (must list them, in enabled profiles, and a `when`/`then` step must compose a `when`/`then` instruction). Because AI agents call it, it only reads `.feature` files and a `--vocabulary` `.toml` inside the project, so parse errors cannot be used to read other files.

- Hash locks: `bdd lock FEAT-n --scope spec|bind` records a SHA-256 for the approved `.feature` files (found by their `@FEAT-n` tag) or the step definitions and drivers proven red; `bdd lock FEAT-n --check [--require] [--json]` detects files that were changed, deleted, or (for specs) added after locking; `bdd unlock FEAT-n --scope S --reason "..."` releases a scope and keeps the reason in the lock history. Hashes ignore CRLF/LF differences so a Windows checkout is not mistaken for tampering. Only files inside the project can be locked. Data files are written atomically and carry a schema version; files from a newer greenlight are refused.

- Feature state in `.bdd/features/FEAT-n-slug/state.json`: `bdd state init|show`, `bdd gate FEAT-n <gate> --result pass|fail` for the machine gates, `bdd assume` (autonomous-run assumptions `A-n.k` with rationale and rejected alternatives), `bdd cost` (tokens and time per phase) and `bdd mode --switch LEVEL --reason "..."` (autonomy switches keep the user's words). Human gates (`rules`, `examples`) are refused here: only the person can approve them. Two gates are enforced by the tool: `implement` cannot be recorded as passed unless the spec and bind locks are intact (a weakened step or a spec added after locking is refused), and `verify` additionally needs `implement` to have passed. `bdd gate FEAT-n bind --record-red` records the git commit, whether production source had uncommitted changes, and a digest of the production source, so the red-before-code order can be proven later. State updates are serialised by a cross-process file lock (stale locks from crashed processes are broken) and writes retry briefly on Windows sharing violations.

### Added (tooling)
- `evals/platform-probe/probe.py`: re-verifies the Claude Code behaviours the design depends on (hook shell, agent naming, approval-hook behaviour, transcript origin markers, `/loop` scheduling) against the installed CLI.

### Fixed
- CLI output is UTF-8 with LF endings on every terminal and code page (PowerShell, cmd, Git Bash); the wrapper runs Python with `-X utf8`.
- Wrapper failed with `MSYS_NO_PATHCONV=1` on Windows (native `python.exe` received an unconverted `/c/...` path); it now uses `pwd -W`. `bdd doctor` also says why it could not measure hook latency.
