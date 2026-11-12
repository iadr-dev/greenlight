# README and docs audit, 2026-11-08 (by two read-only agents that ran the commands in scratch projects)

Version at the time: 1.2.1. Line numbers refer to README.md and docs/quickstart.md of that date; re-find them.

## Wrong, outdated or incomplete (apply these)

README.md
- Pipeline line (about line 26): `request -> rules -> examples -> system map + design -> red tests -> green code -> audit report` leaves out test design and tasks. The code has 10 phases (tools/bdd/bddlib/state.py PHASES: discover, specify, test-design, examples, system-map, refine, bind, tasks, implement, verify, done). Use `request -> rules -> test design -> examples -> system map + design -> red tests -> tasks -> green code -> audit report` or mark it simplified.
- Phase list (about lines 97-98): "discover, specify, test design, examples, system map and design, then refine and bind" omits tasks (after bind, before implement). "Design" is not its own phase; design.md is written in system-map and checked by `bdd design`.
- Verify (about line 104): says the auditor "writes report.md". The spec-auditor agent is read-only and returns the report as text; the orchestrator saves it to report.md. Also `Verdict: PASS` means no blocking checklist item failed (review/checklist.md), which covers more than "every rule has examples, every example has a passing test, nothing changed afterwards": it includes hook-grade approvals (L2), red before code (L3), reviews done (Q6), standards (Q2), shuffled and isolated runs (E2).
- `bdd check` (about lines 40-41 and 106): runs the formatter, linter and type checker only once they are named in `[adapters.quality.NAME]` tables of .bdd/config.toml; init writes none (adapters/python-pytest-bdd/guide.md:107-113). Say so.
- CI (about line 107): "CI re-checks locks, approvals and traceability" only after the person copies adapters/<adapter>/ci/github-actions.yml to .github/workflows/.
- Init (about lines 95-96): `/greenlight:init` recommends an adapter for the person to confirm (not "picks"); the sample run needs the adapter's test requirements installed first (skills/init/SKILL.md step 4).
- Install section (about lines 133-134): "CI uses Node 22" is now 26; "CI uses JDK 21" is now 25 (only the Kotlin language-card job holds 21); Go and others: re-check against .github/workflows/ci.yml. "Go 1.24 or newer" matches adapters/go-godog/templates/tests/go.mod.
- Windows lines (about 128-130): hooks tested from Git Bash and PowerShell only, "a cmd.exe launch was not tested" (docs/dev/platform-notes.md P13). "Without Git for Windows greenlight still works, soft only" is unverified: the only entry point is the POSIX sh wrapper tools/bdd/bdd; say how to run the CLI without sh or drop "still works".
- Python requirements: "pytest 8+ and pytest-bdd 8+" (adapters/python-pytest-bdd/adapter.toml).
- "Plugins greenlight can use" table (about lines 140-159): `/greenlight:init` offers the recommended plugins that `bdd helpers` lists (tools/bdd/bddlib/helpers.py CATALOG: frontend-design, context7, microsoft-docs, chrome-devtools-mcp, code-metrics, api-drift-detector, feature-dev; figma is optional and not offered). impeccable, pstack and open-code-review are NOT in the catalog (they are third-party, used when the person installs them themselves). The plugin names in the table must be the real ids: code-metrics-complexity-and-duplication-report@anthropic-plugin-directory (bdd calls it code-metrics), api-drift-detector-typescript-contract-checker@anthropic-plugin-directory; local ids of the third-party ones: impeccable@impeccable, pstack@pstack-claude, open-code-review@open-code-review. context7 and microsoft-docs are tools of the writers only (implementer, ui-engineer), not the reviewers.
- Uninstall (about lines 137-138): also mention `bdd install-hooks codex --uninstall` and that the person removes any deny rules they added to .claude/settings.json.
- "Use" section (about lines 171-174): `bdd` is not on PATH; show how to run it (`sh <plugin dir>/tools/bdd/bdd route FEAT-001`, or ask Claude to run it). Feature ids are zero-padded in the CLI (`bdd state next-id` prints FEAT-001).
- Known limits: the Next.js sentence says "Turbopack" but againstred.py:36-38 copies any dependency folder that holds next/package.json.

docs/quickstart.md
- line 24: "see adapters for the seven" -> nine (bdd adapter list prints 9).
- line 23: python-pytest-bdd is detected only for a Python project whose pyproject/requirements mentions pytest, fastapi, flask, django or starlette; say "a Python project that uses pytest (or FastAPI, Flask, Django)".
- line 51: "At guided and standard the work stops twice" is wrong for guided (it also stops after test design and shows design.md before binding; README autonomy table agrees).
- Mention PULL_REQUEST.md for `bdd pr --write`.

## Missing for a newcomer (add)
- How to run `bdd` by its path (above).
- The deny rules: `bdd doctor` asks the person to add them to .claude/settings.json; project scope is best (committed, shared). After P2 merges there is a typed line, `! sh "<plugin>/tools/bdd/bdd" doctor --add-deny-rules`; document whichever is merged when you write this.
- Doctor's first-run warnings are normal: "enforcement: no hook has run in this project yet, so nothing is prevented (soft)" before the first session; a Codex hooks warning only where Codex is present.
- `/greenlight:status` (the only one of the six skills never named), `--quick` (phases/quick.md), `bdd report FEAT-n --out reports/FEAT-n.html`, mid-run autonomy switches (`bdd mode FEAT-n --switch autopilot`), `bdd init --detect` and `--smoke`.
- Four of the ten agents are never named: product-analyst, qa-designer, system-analyst, step-engineer; the auditor is spec-auditor.
- The integrity acknowledgement (P1): `/greenlight:approve integrity #3 <reason>`; plugin update line; the approval summary `bdd approve FEAT-n rules|examples --summary` (P5); shared plumbing lock (P3, `bdd unlock --plumbing`, `bdd lock --plumbing`); agent models `[models]` and `bdd cost --amend` (P6); earlier checks lint L026, classify @existing, test-design edges T009, review freshness (P4). docs/upgrading.md needs "Upgrading with features in progress": what a new version reopens (P4: a feature already in implement or verify re-runs its reviewers once) and how.

## Verified correct (do not churn)
Hard vs soft enforcement text; the six slash commands; approvals typed by the person; autopilot UNREVIEWED; red must fail for the intended reason; locks and tripwire sentences; standards.md; nine stacks; Kotlin device runs; Flutter widget tests; install-skills claude|codex|agents-md; install-hooks codex prints only unless --apply; adopt; route/reviewers sentence; Python 3.11+ stdlib only; tags @FEAT-n/@R-n.m/@EX-n.m.k; install commands `/plugin marketplace add iadr-dev/greenlight` and `/plugin install greenlight@greenlight`; MIT; doc links all resolve.

## Unverifiable (leave or soften)
Video lengths and the "re-enacted approvals" sentences; "about ten minutes".
