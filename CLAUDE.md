# CLAUDE.md — greenlight

greenlight is a Claude Code plugin for AI × BDD spec-driven development: a feature request
becomes human-approved rules and examples, then red tests, then green code, under gates the
AI cannot bypass. Plugin name and repo: `greenlight`. CLI: `bdd`. Project data: `.bdd/`.

## How to work
- One task per branch and PR (`lint-near-duplicates`, …). The PR description lists the task's
  acceptance criteria and how each was verified (command output or test name).
- Run `claude plugin validate . --strict` and `claude plugin validate skills --strict`
  before releases (a root-level `CLAUDE.md` warning on the plugin manifest is expected).
- Squash-merge when checks pass. Update `CHANGELOG.md` under *Unreleased* in every PR.
- Record new design decisions in `docs/dev/decisions.md`; platform facts in
  `docs/dev/platform-notes.md` (verified by experiment, with the date).
- **Dogfood**: specify greenlight's own CLI behaviour as Gherkin in `specs/` before
  implementing it, using the rules the plugin enforces (trace tags, vocabulary, red first).
- Never weaken a test to make it pass; fix the code or raise the spec issue.

## Engineering rules
- `tools/bdd` is **Python 3.11+, stdlib only** (TOML via `tomllib`). No third-party imports
  at runtime. Dev/test-only dependencies go in `requirements-dev.txt`.
- Cross-platform: Windows (hooks need Git for Windows, D11), macOS, Linux. Run `python evals/platform-probe/probe.py` after Claude Code upgrades. Use `pathlib`. Hooks run under Git Bash
  on Windows. Hooks and skills call `${CLAUDE_PLUGIN_ROOT}/tools/bdd/bdd`, never `python`
  directly; the wrapper is POSIX `sh`, LF line endings (see `.gitattributes`), and runs
  Python with `-I`.
- Hooks must be no-ops outside repos with `.bdd/` and finish in < 200 ms (macOS/Linux) or
  < 300 ms (Windows).
- Deterministic work (lint, hash, trace, status, classify) belongs in the CLI, never in a prompt.
- File formats: TOML for human-edited files, JSON for tool-owned files (D1).
- Human approvals are written only by `bdd approve --from-hook` (UserPromptSubmit).
  `--self-reported` exists for soft mode and must refuse when hard enforcement is active.
  Never present soft enforcement as hard.
- Only 6 skills (`init`, `feature`, `approve`, `status`, `change`, `adopt`); phase logic goes
  in `phases/<phase>.md`; reusable knowledge goes in `cards/` (frontmatter + *Known pitfalls*).
- Agents: explicit tool lists, read artifacts not chat history, state their output files.

## Definition of done (per task)
- Acceptance criteria met and demonstrated.
- Unit tests for CLI changes; CI green on all three OSes.
- Docs and CHANGELOG updated.
