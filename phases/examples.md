# Phase 4: Examples (specification by example)

Agent: **qa-designer**. Cards: the instruction cards of the steps you use (`cards/instructions/C.*.md`).

## Inputs

- `rules.md` and `test-design.md`.
- `vocabulary/core.json`, and the project's `.bdd/vocabulary.toml` if it has one.
- The feature directory from `.bdd/config.toml`.

## Steps

1. Write one `.feature` file per feature: the `Feature` tagged `@FEAT-n`, one `Rule:` block per business rule
   tagged `@R-n.m`, and one scenario per example tagged `@EX-n.m.k`. Use a `Scenario Outline` with
   `Examples` for partitions and boundaries.
2. Write in business language: no selectors, URLs, SQL, status codes or class names (lint refuses them).
3. Use steps from the vocabulary: domain steps first, core steps allowed. For a step that needs something new,
   write it with a `# proposed-step` comment; it is resolved in the refine phase.
4. Run `bdd lint` and fix everything it reports. `bdd trace FEAT-n` must show no gaps between rules, examples
   and scenarios.
5. Show the person the scenarios.

## Output files

`.feature` files in the project's feature directory.

## Gate (human)

The person approves the examples with `/greenlight:approve FEAT-n examples`. Approving locks the feature files
(`bdd lock` scope `spec` is done for you); from then on only the change flow can edit them. See the specify
playbook for the `auto` and soft-enforcement variants. The gate needs the test-design gate passed and the
rules approved.

## Pitfalls

- Scenarios that describe how (clicks, requests) instead of what. Declarative style, one behaviour each.
- A scenario with several actions. One When per scenario.
- Missing trace tags, or two examples sharing an id (lint L005 and L006).
- Near-duplicate steps that mean the same thing. Reuse the existing step.
- Editing a feature file after approval. The lock will refuse it, and so does the guard.
