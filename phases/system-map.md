# Phase 5: System map

Agent: **system-analyst** (may read the whole code base). Cards: the instruction cards of the steps used.

Recording is the orchestrator's job: it runs `bdd state init`, `bdd gate`, `bdd assume`, `bdd cost`, `bdd lock` and `bdd approve` from your report. You run none of them, and your last message says what is ready to record.

## Inputs

- The approved feature files, `rules.md`, `test-design.md`.
- The code base and the adapter's `guide.md`.
- `templates/system.md`.

## Steps

1. For every step of every scenario, find the interface it exercises in this code base: the API operation, the
   command, the library function, the entity and how a test seeds and reads it, the event or job.
2. Write `system.md` from `templates/system.md`: a table of logical names to where they live, the data, the
   **Dependencies** (every external system a test may stub, one per line), how time reaches the code, events
   and jobs.
3. List the seams that do not exist yet: what the implementer will have to build, and what each must do. These
   stay as `ExpectedMissing` until then.
4. Where a step maps to nothing, list it as a design decision, not a guess. If the feature files themselves
   need to change, raise a change request (see `templates/change-requests.md`) instead of editing them.

## Output files

`system.md`.

## Gate

Every step maps to an interface, or is listed as a design decision. Then:

```sh
bdd gate FEAT-n system-map --result pass
```

## Pitfalls

- Guessing an interface that does not exist. Say it does not exist.
- Listing as a dependency something the system owns. Only external systems may be stubbed.
- Mapping to the database when an API or service exists: use the most realistic seam.
- Forgetting how time reaches the code. Without a clock seam the time steps do nothing.
