# Phase 9: Implement (red to green)

Agent: **implementer**. Production code only. Features, step definitions and drivers are read-only.

Recording is the orchestrator's job: it runs `bdd state init`, `bdd gate`, `bdd assume`, `bdd cost`, `bdd lock` and `bdd approve` from your report. You run none of them, and your last message says what is ready to record.

## Inputs

- `tasks.md`, `system.md` (the seams to build), `design.md`, the red record.
- `.bdd/standards.md`: the declared language and toolchain, style, quality rules and deprecation policy, in force as
  written; a placeholder left in it means what the project already uses, never a tool to add. The practice card of the
  project's language (`cards/practices`) lists the toolchain commands and the usual pitfalls.
- The locked feature files and bound steps.

## Steps

Per task, in order:

1. Pick the task's scenarios. Write the smallest production code that turns them green; build the seams that
   `system.md` lists.
2. Run the feature recorded: `bdd run FEAT-n`, then `bdd classify FEAT-n`. Refactor with the tests green.
3. When a scenario cannot pass without changing a locked file, **stop** and raise a change request
   (`templates/change-requests.md`). Do not edit the file, do not loosen an assertion, do not delete a
   scenario. The change flow unlocks, edits, gets approval and re-locks.
4. Use the current API of every library you call, from its current documentation, and fix a deprecation warning instead of
   silencing it. Do not upgrade a toolchain or dependency and do not add one; return the question.
   When the code touches an API or a database, read the matching cards first: `api-design`, `database-schema`,
   `database-migrations`, `database-performance`, `database-engines`. Load related records together instead of
   one query per record, bound every result, and write a migration that can be undone. Do not edit a migration that
   has been applied.
5. Report the tokens and time you spent; the orchestrator records them with `bdd cost FEAT-n --phase implement
   --tokens N --seconds S`.

When all tasks are done, run the whole feature once more with `bdd run FEAT-n`.

## Output files

Production code. Nothing under the test directories.

## Gate

The spec and bind locks must still be intact (`bdd lock FEAT-n --check --require`) and no integrity violation
may be open (`bdd status`). When the project configured quality checks (`[adapters.quality.NAME]` in `.bdd/config.toml`),
the orchestrator runs `bdd check FEAT-n` after your last change and the result must pass and be current.

```sh
bdd gate FEAT-n implement --result pass
```

The gate refuses if a locked step was weakened, a spec file was added after locking, or a violation is open.

## Pitfalls

- Editing a test to make it pass. The guard and the lock refuse it, and it is the failure the whole process
  exists to stop.
- Gold plating: code no scenario asks for.
- Writing against remembered library APIs. Read the current documentation, and use what it recommends today.
- Sidestepping the guard with a shell trick. The integrity check looks at the result, and a violation blocks
  the gate.
- Skipping the run between tasks. Small steps keep the red-to-green record meaningful.
