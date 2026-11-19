# Phase 8: Tasks

Agent: the **orchestrator** (the main session), and the **code-reviewer**, **security-reviewer** and **ui-reviewer**
for the design review. Cards: `story-splitting`.

## Inputs

- `rules.md`, `test-design.md`, `system.md`, `design.md`, the red run.
- `templates/tasks.md`.

## Steps

1. **Review the design before the tasks.** For a feature started with the technical design (`bdd design FEAT-n` checks
   its fourteen sections), run the code-reviewer, the security-reviewer and, when the design shows a screen, the
   ui-reviewer on `design.md`, in parallel, at most three at once. Tell each one to *review the design* of FEAT-n. Each
   writes `reviews/design-<reviewer>.md` with the `Design:` digest `bdd design FEAT-n` prints and a `Verdict:` line.
   Must-fix items go back to the system-analyst, who changes `design.md`; then `bdd design FEAT-n` again, and the
   reviewers review the changed design (its digest changed, so their old reports no longer count). Optional helpers,
   when installed: pstack's `thermos` and `interrogate` for the code-reviewer, the security-guidance plugin's rules for
   the security-reviewer, impeccable's `audit` for the ui-reviewer.
2. **Building blocks the project does not have.** The tasks gate names each library of the design's Building blocks
   that no manifest declares, with the one line that adds it. Ask the person to type it (`! pnpm add ...`); an agent
   never installs a package, and the guard refuses it.
3. Group the examples into vertical slices, in build order. Each task starts with its id (`T-<feature>.<n>`)
   and names the examples it turns green (`Covers: EX-...`), the areas it will touch (folders or files, comma-separated:
   the implement gate judges the task's reviews against the production files there), its dependencies and its size
   (S, M or L).
4. Put the thinnest end-to-end path first, so the plumbing is proved before the exceptions.
5. Every example is owned by exactly one task. Check with `bdd trace FEAT-n`: an unowned example is gap `T006`,
   an unknown example in a task `T005`.

## Output files

`tasks.md`; the reviewers' `reviews/design-<reviewer>.md`.

## Gate

The tasks gate checks the technical design again, waits for a `PASS` from each design reviewer on the design as it is
now (where the hooks run, written by that reviewer itself), and for every building block to be a dependency of the
project.

```sh
bdd gate FEAT-n tasks --result pass
```

## Pitfalls

- Tasks by technical layer (database, API, UI). Each task must turn scenarios green on its own.
- One task owning everything. Split it until each has a handful of examples.
- Leaving a scenario owned by two tasks. Exactly one.
- Writing the tasks while a design review has must-fix items: the code is then built against a design the reviewers
  refused. Send the items back to the system-analyst first.
- Running the three reviewers one after another: they read the same file and do not depend on each other.
