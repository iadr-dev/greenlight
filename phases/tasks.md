# Phase 8: Tasks

Agent: the **orchestrator** (the main session). Cards: `story-splitting`.

## Inputs

- `rules.md`, `test-design.md`, `system.md`, the red run.
- `templates/tasks.md`.

## Steps

1. Group the examples into vertical slices, in build order. Each task starts with its id (`T-<feature>.<n>`)
   and names the examples it turns green (`Covers: EX-...`), the areas it will touch, its dependencies and its
   size (S, M or L).
2. Put the thinnest end-to-end path first, so the plumbing is proved before the exceptions.
3. Every example is owned by exactly one task. Check with `bdd trace FEAT-n`: an unowned example is gap `T006`,
   an unknown example in a task `T005`.

## Output files

`tasks.md`.

## Gate

```sh
bdd gate FEAT-n tasks --result pass
```

## Pitfalls

- Tasks by technical layer (database, API, UI). Each task must turn scenarios green on its own.
- One task owning everything. Split it until each has a handful of examples.
- Leaving a scenario owned by two tasks. Exactly one.
