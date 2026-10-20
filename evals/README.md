# Evaluation

`evals/run_e2e.py` runs a feature request through greenlight with real agents on a reference app and measures what
happened. It reads the project's own records (`bdd status`, `state show`, `trace`, `classify`, `lock --check`, `lint`,
`approve --verify`, `report.md`, git), never the conversation. It costs real money and is not part of CI.

```sh
python evals/run_e2e.py --request discounts --model sonnet-5.5 --autonomy standard,autopilot --runs 3 --arms plugin,baseline
python evals/run_e2e.py --request discounts --model sonnet-5.5 --hooks off      # soft enforcement
python evals/collect.py [NAME.jsonl ...]                                        # summary table of stored rows (names in evals/results/)
```

Rows go to `evals/results/<time>-<request>-<model>.jsonl` (ignored by git), one line per run.

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
cards the session read, the auditor's verdict, the number of assumptions and, for autopilot, the agreement of the
assumptions with the scripted answers (`evals/requests/<request>.answers.json`).

## What the rows mean

- **Cost.** The orchestrator records tokens and seconds per phase with `bdd cost` from the subagents' completion
  notices; `tokens` in a row is that sum and `cost_recorded` says whether anything was recorded. A run that stops early
  (for example at `auto`, which asks a blocking question nobody can answer headless) has nothing recorded, which is why a
  zero there is not a bug. `claude.total_cost_usd` and `claude.tokens_reported` are Claude Code's own totals for the
  whole session. A row whose feature got past discover without recorded cost carries a `cost_warning`.
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
