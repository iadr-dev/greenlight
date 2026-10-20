# Phase 6: Refine (resolve the vocabulary)

Agent: **step-engineer**. Cards: the instruction cards for any core step you compose.

Recording is the orchestrator's job: it runs `bdd state init`, `bdd gate`, `bdd assume`, `bdd cost`, `bdd lock` and `bdd approve` from your report. You run none of them, and your last message says what is ready to record.

## Inputs

- The approved feature files and `bdd lint` output.
- `vocabulary/core.json`, `.bdd/vocabulary.toml`.

## Steps

1. For every `# proposed-step`, choose one: reuse an existing step, generalise an existing step, or register a
   new **domain step** in `.bdd/vocabulary.toml` (pattern, description, parameters, and the core instructions it
   composes; a `when` step composes `when` instructions, a `then` step `then` instructions).
2. If wording of an approved step has to change, that is a change of the spec, not a refinement: raise a change
   request and stop.
3. Run `bdd lint` until it has no errors: every step resolves, none is ambiguous, no near-duplicate is left
   without a justification, and domain steps compose core instructions properly.

## Output files

`.bdd/vocabulary.toml` (project domain steps).

## Gate

`bdd lint` is clean on the feature files. Then:

```sh
bdd gate FEAT-n refine --result pass
```

## Pitfalls

- Registering a domain step that duplicates a core one. Reuse first.
- A domain step that hides a long script. It composes core instructions and nothing else.
- Editing the locked feature files to make a step resolve. The vocabulary changes, not the spec.
