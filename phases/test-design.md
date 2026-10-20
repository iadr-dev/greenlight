# Phase 3: Test design

Agent: **qa-designer**. Cards: every technique card, chosen per rule.

Recording is the orchestrator's job: it runs `bdd state init`, `bdd gate`, `bdd assume`, `bdd cost`, `bdd lock` and `bdd approve` from your report. You run none of them, and your last message says what is ready to record.

## Inputs

- `rules.md`, approved.
- The card index: `bdd cards list --kind technique` (front matter only).
- `templates/test-design.md`.

## Steps

1. For each rule, read the `apply_when` of the technique cards and choose those that fit. Read the full card of
   each chosen technique, including its Known pitfalls.
2. Write `test-design.md` from `templates/test-design.md`: per rule, the techniques (card ids) and why they
   fit, then the examples, one line each starting with `EX-<feature>.<rule>.<n>` and naming the technique.
3. Keep it proportionate: the smallest set of examples that covers every rule through its chosen techniques,
   usually two to five per rule. Do not test behaviour the request did not touch.
4. Apply the technique's output shape: both sides and the edge of every boundary, one example per class, one
   example per decision-table row or an exclusion, one example per state transition.
5. Every rule with inputs gets a negative example (card `negative-cases`) or an exclusion with a reason.
6. List excluded cases with their reasons. Fill in the coverage check.
7. Report the tokens and time you spent; the orchestrator records them with `bdd cost`.

## Output files

`test-design.md`.

## Gate

Every rule has at least one example, and every decision-table row and state transition is an example or an
exclusion. Check with `bdd trace FEAT-n` (rules without examples are gap `T001`), then:

```sh
bdd gate FEAT-n test-design --result pass
```

The gate needs the rules approved.

## Pitfalls

- Choosing techniques by habit. Match the card's `apply_when` to the rule and say so.
- Skipping the pitfalls section of the cards you cited: the auditor checks it.
- Varying several inputs at once, so a failure points nowhere.
- Examples with vague expected results ("works correctly"). State what is observable.
