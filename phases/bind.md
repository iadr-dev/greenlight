# Phase 7: Bind (the red gate)

Agent: **step-engineer**. Cards: `test-data`, the instruction cards, and the adapter guide. No production code is
written in this phase.

Recording is the orchestrator's job: it runs `bdd state init`, `bdd gate`, `bdd assume`, `bdd cost`, `bdd lock` and `bdd approve` from your report. You run none of them, and your last message says what is ready to record.

## Inputs

- The approved, locked feature files, `system.md`, `.bdd/vocabulary.toml`.
- The adapter's `guide.md` and templates (`bdd adapter apply NAME` puts them in the project).

## Steps

1. Fill in the adapter's seams from `system.md`: the logical-name maps (API operations, commands, library
   functions, files, errors) and the system seams. A seam the system does not have yet stays as it is, so it
   fails as an expected failure.
2. Write project step modules for the domain steps, calling the same drivers. Steps only call drivers.
3. Read `test-data`: each scenario creates its own data.
4. Never edit the adapter's core drivers (`api.py`, `cli.py`, `lib.py`, `compare.py`, `world.py` and the like).
   Project differences go in `system.py` (including `complete`, which fills in a request field the scenario left
   out), `operations.py` and your own step modules. Do not install packages; if the requirements are missing,
   say so.
5. Run the feature, recorded: `bdd run FEAT-n`. Then `bdd classify FEAT-n`.
6. The **red gate**: every scenario must fail as `expected-fail`. Fix every `test-defect` and `unknown` (an
   unmapped name, an import error, an undefined step). A scenario that passes is either behaviour that already
   exists (it should have been tagged `@existing` in the examples phase; as the spec is locked, return a change
   request for the orchestrator) or a tautology to fix.
7. Run the checks: `bdd scan FEAT-n` (assertion-free then steps, fixed waits, stubs of undeclared dependencies),
   `bdd run FEAT-n --shuffle` and `bdd run FEAT-n --isolated` (they must not depend on each other); run
   `bdd run FEAT-n` again last so the recorded run is the plain one.
8. Report that the red is valid; after checking it, the orchestrator locks the bound files with `bdd lock FEAT-n
   --scope bind tests/steps tests/drivers` (the paths the adapter uses).

## Output files

Step modules and drivers under the adapter's paths; `.bdd/.runs/FEAT-n/latest.json` (written by `bdd run`).

## Gate

```sh
bdd classify FEAT-n --expect red
bdd gate FEAT-n bind --result pass --record-red
```

`--record-red` stores the commit and a digest of the production source, so it can be shown later that the
tests were red before any production code changed. The gate needs a valid red from a run recorded against the
files as they are now.

## Pitfalls

- Making a scenario pass by stubbing the system under test. Stub only declared external dependencies.
- Weakening an assertion to get past red. Red is the goal; fix the code later.
- Editing the run record or running the tests by hand and calling it red. Only `bdd run` counts.
- Touching production code in this phase. The red record would show it.
