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
- `bdd route FEAT-n`: for each task, the writer, the reviewers and the cards to read (`cards/practices`), and what the
  task builds against: `design:` (the sections of `design.md` and the inventory rows of its screens), `risks:` (the
  known risks its code must handle), `blocks:` (each building block: field, library, package, the version the project
  declares, and its documentation) and `services:` (each outside service it may call: the call, and the official page,
  MCP server and CLI that `.bdd/sources.toml` names). Read every card it lists for your task before you write or review.

## Steps

Per task, in order:

1. Pick the task's scenarios. Read the sections of `design.md` that `design:` names and the screen file of each row it
   names. Write the smallest production code that turns them green; build the seams that `system.md` lists, put each
   piece where the Architecture section says, copy the example file of each pattern it uses, and use each building
   block's library instead of writing your own parser, formatter or validator.
2. **Handle each risk of the task** in the code, or know why it does not apply: two writes at once (a transaction, a
   unique key, a conditional update), a retried or duplicated request (an idempotency key), a rate limit on the call,
   a storage error mapped to the error the design says the user sees, the server-side authorisation check, personal
   data kept out of logs, time stored with its zone, and a list with a page size and a maximum. Say in your return,
   for each risk, the file and line that handles it or why it does not apply. The code reviewer checks each one.
3. **Check every outside call against its source.** For each service of `services:` the task calls, look the call up
   where `.bdd/sources.toml` points: its MCP server when one is installed, its CLI (`--help`, or a dry run that changes
   nothing), else its official page. Use the SDK and version the project declares; never a remembered signature or a
   page from another site.
4. Run the feature recorded: `bdd run FEAT-n`, then `bdd classify FEAT-n`. Refactor with the tests green.
5. When a scenario cannot pass without changing a locked file, **stop** and raise a change request
   (`templates/change-requests.md`). Do not edit the file, do not loosen an assertion, do not delete a
   scenario. The change flow unlocks, edits, gets approval and re-locks.
6. Use the current API of every library you call, from its current documentation (the installed package's own docs and
   types, or a documentation tool such as context7 or Microsoft Learn when one is available), and fix a deprecation warning instead of
   silencing it. Say in your return which documentation you read for each task (see *Return* of your agent file): the
   orchestrator records it with `bdd docs FEAT-n --task T-n.m --library NAME --version V --source URL_OR_FILE`, or
   `--none "reason"` for a task that calls no library, and the implement gate refuses a task with neither. For each
   outside service the task calls, say what you checked the call against; the orchestrator records it with
   `bdd docs FEAT-n --task T-n.m --service NAME --mcp SERVER --query TEXT` (or `--source URL` on the official site, or
   `--cli COMMAND`). Do not upgrade a toolchain or dependency and do not add one; return the question.
   When the code touches an API or a database, read the matching cards first: `api-design`, `database-schema`,
   `database-migrations`, `database-performance`, `database-engines`. Load related records together instead of
   one query per record, bound every result, keep each operation within the budget the design gives it, and write a
   migration that can be undone. Do not edit a migration that has been applied.
7. Do not report tokens or time: you cannot measure them. The orchestrator records them from the plugin's hook and
   your own transcript (`bdd cost FEAT-n --collect`).

After each task the orchestrator runs `bdd check FEAT-n --task T-n.m` when the project configured quality checks: the
formatter, linter, type checker and the architecture checker (dependency-cruiser, import-linter or the project's own)
run over the code as it is, so a layer reached past is found while the next task can still avoid building on it. A
failed check comes back to you with its output. When all tasks are done, run the whole feature once more with
`bdd run FEAT-n`.

## Order and parallel work

`bdd route FEAT-n` prints `runs in: group N` for each task (`group`, `after` and `alongside` in `--json`). A task waits
for the tasks it depends on and for every earlier task whose `Areas:` overlap its own; tasks of one group touch
different files. The orchestrator starts the writers of one group together, and starts the next group's writers only
when every task they wait for has passed its reviews.

## Reviews

The orchestrator starts the reviewers of a task together once its scenarios are green, at most three at once (they
read the same diff and do not wait for each other). Each reads the task's diff (against the commit of the red record),
the cards `bdd route` lists, `.bdd/standards.md` and `design.md`, and writes `reviews/<task id>-<reviewer>.md` in the
feature folder:

```markdown
# <reviewer>: T-007.1 <task title>

Verdict: PASS | FINDINGS

## Risks
- Risk rate limits: handled in src/api/sessions.ts:42
- Risk time zones: not applicable: the task stores no date or time
- Risk authorisation: missing

## Side by side
- O-SI-01 375 px: T-007.1-O-SI-01-375-built.png | T-007.1-O-SI-01-375-design.png
- O-SI-01 1280 px: T-007.1-O-SI-01-1280-built.png | T-007.1-O-SI-01-1280-design.png

## Must fix
- path:line - what is wrong, the rule or card it breaks, what to do instead

## Should fix
## Not checked
## Helpers used
```

The code-reviewer writes *Risks*, one line per risk `bdd route` names for the task; the ui-reviewer writes *Side by
side*, each screen row of the task at both widths. For a feature started with this version, the implement gate refuses a code review that has no `Risk <name>:` line for
a risk of its task or says one is `missing`, an answer that names neither a `file:line` nor a reason, and a `file:line`
that is not a line of a file of the project. It refuses a UI review that neither lists each screen row of the task at
375 and 1280 px under *Side by side*, with every screenshot a different PNG file in `reviews/`, nor names the row under
*Not checked* with the reason it could not be compared (no browser tool, the application not running), in a sentence.

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
the orchestrator runs `bdd check FEAT-n` after your last change and the result must pass and be current. For a feature
started with this version, every task also needs a passing `bdd check FEAT-n --task T-n.m` of its own, every task of
`tasks.md` a `Design:` and a `Risks:` line, and the reviews their risk and side-by-side lines (see *Reviews*). A feature
started before keeps the gate it had.

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
- Handling the risk on the screen only: disabling a button does not stop a second request. The server makes the
  write safe to repeat and to race.
- A storage error passed through as it came from the database driver. Map each one to the error the design's Errors
  and resilience section says the user sees.
