# Phase 10: Verify

Agent: **spec-auditor** (read-only, fresh context). Cards: every card cited in `test-design.md`, `mutation-check`,
`stability-rerun`. Checklist: `review/checklist.md`.

Recording is the orchestrator's job: it runs `bdd state init`, `bdd gate`, `bdd assume`, `bdd cost`, `bdd lock` and `bdd approve` from your report. You run none of them, and your last message says what is ready to record.

## Inputs

Artifacts only: rules, assumptions, test design, features, step definitions and drivers, system map, tasks, the
code diff, the recorded runs, `state.json` and `lock.json`, the cited cards and the checklist. Not the
implementer's explanations, history or expected verdict. A missing input makes the related items
`UNVERIFIABLE`; the auditor never guesses, and when two inputs conflict it reports the conflict.

## Steps

1. Gather evidence with the deterministic tools: `bdd status`, `bdd trace FEAT-n`, `bdd lock FEAT-n --check
   --require`, `bdd lint`, `bdd scan FEAT-n`, `bdd classify FEAT-n --expect green`.
2. For the cards cited in `test-design.md`, check the examples against each card's Known pitfalls.
3. Check the AI-test smells: tautology, a then step without an assertion, weakened assertions, shared state,
   fixed waits, the system under test mocked, missing negative examples.
4. Where it applies (time, concurrency, network, UI), run the stability rerun: `bdd run FEAT-n --shuffle` and
   `--isolated`, several times. Mutation testing on the changed files is optional; follow `mutation-check`.
5. Write `report.md` from `templates/report.md`: the verdict, autonomy and enforcement level, the trace
   matrix, gates, locks and approvals (every human approval must be hook-grade or labelled self-reported, and
   its hashes must match the current files), the checklist with evidence for every line, and the cost.
6. Under `autopilot` the report begins with the assumptions and the rules, and is labelled UNREVIEWED.

## Output files

`report.md` (returned as text to the orchestrator, which writes it).

## Gate

```sh
bdd gate FEAT-n verify --result pass
```

Passes only if `implement` passed and the recorded run is a valid green against the current files. The verdict is
`PASS` when no blocking checklist item failed, otherwise `FINDINGS`, grouped as must fix, should fix and
unverifiable.

## Pitfalls

- A check mark on a general impression. Each line needs evidence: a file and line, a scenario tag or command
  output.
- Passing a feature whose enforcement was soft without saying so in the header.
- Fixing things while auditing. The auditor reports; the others fix.
- Trusting the implementer's summary. Read the artifacts.
