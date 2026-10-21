# Evaluation

`evals/run_e2e.py` runs a feature request through greenlight with real agents on a reference app and measures what
happened. It reads the project's own records (`bdd status`, `state show`, `trace`, `classify`, `lock --check`, `lint`,
`approve --verify`, `report.md`, git), never the conversation. It costs real money and is not part of CI.

```sh
python evals/run_e2e.py --request discounts --model sonnet-5.5 --autonomy standard,autopilot --runs 3 --arms plugin,baseline
python evals/run_e2e.py --request discounts --model sonnet-5.5 --hooks off      # soft enforcement
python evals/run_e2e.py --request adopt-billing --model sonnet-5.5 --autonomy autopilot   # /greenlight:adopt on legacy-billing
python evals/collect.py [NAME.jsonl ...]                                        # summary table of stored rows (names in evals/results/)
```

Rows go to `evals/results/<time>-<request>-<model>.jsonl` (ignored by git), one line per run.

An adoption request (`adopt-billing`, on `evals/apps/legacy-billing`, which has no tests on purpose) has no baseline
arm and is judged also by invariants read from the project: `adoption.holds` is true when `bdd adopt FEAT-n --check` is
clean (every scenario `@existing`, the production source pinned at the bind gate and unchanged), the recorded run is a
valid green, and git sees no production file touched (`adoption.production_files_touched` is empty).

## Requests and reference apps

| Request (`--request`) | Reference app | Adapter | Profile | Skill |
|---|---|---|---|---|
| `discounts` | `evals/apps/shop-api` (Python, FastAPI) | `python-pytest-bdd` | api | `feature` |
| `adopt-billing` | `evals/apps/legacy-billing` (Python, Flask, no tests) | `python-pytest-bdd` | api | `adopt` |
| `csv-report` | `evals/apps/csv-tool` (Go, standard library only) | `generic-junit` | cli | `feature` |
| `money-convert` | `evals/apps/money-lib` (TypeScript) | `generic-junit` | lib | `feature` |

The table is `REQUEST_KINDS` in `run_e2e.py`. For the two `generic-junit` apps the harness acts as the person after
`bdd init`: it writes the app's own run line into `.bdd/config.toml` (`go run gotest.tools/gotestsum` for Go, an npm script
around `node --test` for TypeScript) and removes the sample. They need Go, or Node and npm, on PATH instead of `uv`, and the
baseline arm runs the app's own tests (`go test ./...`, `npm test`). No model-driven run has been made on `csv-report` or
`money-convert` yet.

## Targets

| Metric | Row field | Target |
|---|---|---|
| Rules with at least one example | `rules_with_examples_pct` | 100% |
| Valid red at the bind gate | `valid_red_pct` | at least 90% |
| Scenarios green after implement, without human code edits | `green_pct` | at least 80% |
| Locked-spec violations reaching verify (lock differences and open integrity violations) | `locked_spec_violations` | 0 |
| Steps that resolve to the vocabulary | `vocabulary_resolution_pct` | 100% |
| Approvals the transcript check calls invalid or unverifiable | `forged_approvals` | 0 |

The summary table prints the mean of each metric per arm, autonomy level, hooks setting and model, marked `ok` or `MISS`
against its target and `-` where nothing was measured (a red or green that never happened is not scored as a failure of
the run, it is not scored). Also recorded and reported, with no target: tokens and seconds per phase, cost in USD, which
cards the session and its subagents read (a card counts when a Read, Bash, Grep or Glob call names it; the agents, not
the orchestrator, read them, so the collector also reads `<session>/subagents/*.jsonl`), the auditor's verdict, the number of assumptions and, for autopilot, the agreement of the
assumptions with the scripted answers (`evals/requests/<request>.answers.json`).

## What the rows mean

- **Cost.** The plugin's `SubagentStop` hook notes every finished agent and `bdd cost FEAT-n --collect` turns the notes
  into tokens (from the agent's own transcript: input, output and cache writes, each model reply once) and seconds (from the
  hook when its payload says, otherwise from the first and last time stamp in the agent's transcript; in real runs the
  payload had no duration) per phase; the completion notice's own figure can differ by a few percent. `tokens` in a row is
  that sum and `cost_recorded` says whether anything was recorded. A run that stops early
  (for example at `auto`, which asks a blocking question nobody can answer headless) has nothing recorded, which is why a
  zero there is not a bug. `claude_cost_usd` (also `claude.total_cost_usd`) and `claude.tokens_reported` are Claude
  Code's own totals for the whole session. A row whose feature got past discover without recorded cost carries a
  `cost_warning`.
- **Isolation.** The plugin a run loads is a snapshot of the last commit (`plugin_commit`; `checkout_changes` counts the
  uncommitted changes that were left out), and the run has its own Codex home and, when the login is in the environment,
  its own Claude Code folder, so other work on the machine cannot change what the run's tripwire watches. What it cannot
  make its own (`~/.codex`, watched whatever `CODEX_HOME` says, and the person's Claude Code settings when the folder had to
  be shared) is hashed before and after: `host_changes` lists what changed. `foreign_violations` are the open integrity
  violations that name a file outside the run; a row with any is `contaminated` and is left out of the summary's targets
  and listed under it. Three early runs stopped at the implement gate for this reason (the plugin's checkout, the person's
  Claude Code settings and Codex configuration were edited by other work while they ran); greenlight's refusal was right,
  the measurement was not.
- **Enforcement.** `enforcement` is greenlight's classification of the feature. `hooks_active` is whether the guard
  hook ever ran in the project (`.bdd/.enforcement/_seen`). With `--hooks on`, a row where hooks did not run carries a
  `warning` and is not a hard-enforcement result. With `--hooks off` the plugin is loaded from a copy with an empty hooks
  file, so the run is soft by construction.
- **Standard autonomy.** The two human gates need a person. A headless run has none, so after the orchestrator stops
  waiting for an approval, the harness sends the typed command (`/greenlight:approve FEAT-n rules|examples`) as a
  follow-up prompt in the same session. Such a prompt reaches the approval hook as a headless prompt, which greenlight
  grades below a keyboard-typed one, so a standard row measures the pipeline given scripted human decisions, not the
  provenance of a real person's approval. Whether the hook accepts a headless approval in a given Claude Code version is
  not something this repository can promise; if it does not, the row stops at the first human gate and `completed` is
  false.
- **Baseline arm.** The same request in plain Claude Code with the reference app only. Without a spec there is no red, no
  trace and no locks, so the row has `tests_pass` (the app's own tests after the run), the git changes and the cost.
- **Several runs.** `--runs N` repeats every combination; the summary averages them. One run says little about a stochastic
  system; use at least three for a number you intend to quote.
