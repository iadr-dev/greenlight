# Phase 9: Implement (red to green)

Agent: **implementer**, or **ui-engineer** for a task with screens: the writer `bdd route FEAT-n` names for the task.
Then the **reviewers** it names (**code-reviewer** always; **ui-reviewer** for screens; **security-reviewer**
for signing in, access, money, credentials or personal data). Writers change production code only; reviewers write only
their report. Features, step definitions and drivers are read-only for all of them.

Recording is the orchestrator's job: it runs `bdd state init`, `bdd gate`, `bdd assume`, `bdd cost`, `bdd lock` and `bdd approve` from your report. You run none of them, and your last message says what is ready to record.

## Inputs

- `tasks.md`, `system.md` (the seams to build), `design.md`, the red record.
- `.bdd/standards.md`: the declared language and toolchain, style, quality rules and deprecation policy, in force as
  written; a placeholder left in it means what the project already uses, never a tool to add. The practice card of the
  project's language (`cards/practices`) lists the toolchain commands and the usual pitfalls.
- The locked feature files and bound steps.
- `bdd route FEAT-n`: for each task, the writer, the reviewers and the cards to read (`cards/practices`). Read every card
  it lists for your task before you write or review.

## Steps

Per task, in order:

1. Pick the task's scenarios. Write the smallest production code that turns them green; build the seams that
   `system.md` lists.
2. Run the feature recorded: `bdd run FEAT-n`, then `bdd classify FEAT-n`. Refactor with the tests green.
3. When a scenario cannot pass without changing a locked file, **stop** and raise a change request
   (`templates/change-requests.md`). Do not edit the file, do not loosen an assertion, do not delete a
   scenario. The change flow unlocks, edits, gets approval and re-locks.
4. Use the current API of every library you call, from its current documentation (the installed package's own docs and
   types, or a documentation tool such as context7 or Microsoft Learn when one is available), and fix a deprecation warning instead of
   silencing it. Say in your return which documentation you read for each task (see *Return* of your agent file): the
   orchestrator records it with `bdd docs FEAT-n --task T-n.m --library NAME --version V --source URL_OR_FILE`, or
   `--none "reason"` for a task that calls no library, and the implement gate refuses a task with neither. Do not upgrade a toolchain or dependency and do not add one; return the question.
   When the code touches an API or a database, read the matching cards first: `api-design`, `database-schema`,
   `database-migrations`, `database-performance`, `database-engines`. Load related records together instead of
   one query per record, bound every result, and write a migration that can be undone. Do not edit a migration that
   has been applied.
5. Do not report tokens or time: you cannot measure them. The orchestrator records them from the plugin's hook and
   your own transcript (`bdd cost FEAT-n --collect`).

When all tasks are done, run the whole feature once more with `bdd run FEAT-n`.

## Reviews

The orchestrator starts the reviewers of a task once its scenarios are green. Each reads the task's diff (against the
commit of the red record), the cards `bdd route` lists, `.bdd/standards.md` and `design.md`, and writes
`reviews/<task id>-<reviewer>.md` in the feature folder:

```markdown
# <reviewer>: T-007.1 <task title>

Verdict: PASS | FINDINGS

## Must fix
- path:line - what is wrong, the rule or card it breaks, what to do instead

## Should fix
## Not checked
## Helpers used
```

Only the reviewer itself writes its report: the guard refuses the writers, the orchestrator, other agents and any shell
command, and where the hooks run the gate accepts a report only with exactly the content its reviewer last wrote, in the implement phase (the reviewer writes the whole report with the Write tool; if a report is changed afterwards, or an old one put back, the reviewer runs again). `FINDINGS` when *Must fix* is not empty. The must-fix items go back to the task's writer; the reviewer then runs again
and writes its report fresh. Where the hooks run, the gate also refuses a report older than the code: when the reviewer finishes, its report is
sealed with the hashes of the task's production files (the changed files that the paths of the task's `Areas:` line in
`tasks.md` name; a feature of one task with no matching paths uses every changed file; a feature of several tasks needs
`Areas:` paths that name real files, or its reviews are not judged). A file that changed after the seal makes the report
stale and the reviewer runs again, unless another report of the same kind of reviewer was sealed with that file as it is
now. A report with no seal is stale too. A finding needs evidence from the files: a reviewer that could not check something says so
under *Not checked* instead of passing it or inventing a finding. Reviewers never edit code or tests, and use a helper
plugin only to report, never in a mode that fixes.

## Output files

Production code. Nothing under the test directories.

## Gate

The spec and bind locks must still be intact (`bdd lock FEAT-n --check --require`), no integrity violation
may be open (`bdd status`), every review `bdd route FEAT-n` asks for must be in `reviews/` with a verdict, and every task must have a documentation record (`bdd docs FEAT-n --list`). When the project configured quality checks (`[adapters.quality.NAME]` in `.bdd/config.toml`),
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
- Restyling a screen and renaming a test id, label or component name a step relies on. The scenarios are locked; the
  screen keeps the names they use.
- Following a plugin hook that asks you to fix a test file. Tests are read-only; leave it and say so in your return.
