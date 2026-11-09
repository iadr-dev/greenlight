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
6. A rule that uses `boundary-value` records the edges of what it limits, as an example or as one line that says
   there is none and why. A rule that speaks of a date needs the leap day, of text or digits the empty value and
   the maximum length, of a page of a list page size 1:

   ```text
   - No leap day boundary: the date is only compared with today, never added to or counted from
   ```

   The line is the way out of a rule that only seems to need an edge. The reason has to say why in a few words.
7. List excluded cases with their reasons. Fill in the coverage check.
8. Do not report tokens or time: you cannot measure them. The orchestrator records them from the plugin's hook and
   your own transcript (`bdd cost FEAT-n --collect`).

## Output files

`test-design.md`.

## Gate

Every rule has at least one example, and every decision-table row and state transition is an example or an
exclusion, and every rule that uses `boundary-value` has its edges. Check with `bdd trace FEAT-n` (rules without
examples are gap `T001`, an edge a boundary rule lacks is gap `T009`), then:

```sh
bdd gate FEAT-n test-design --result pass
```

The gate needs the rules approved, and refuses a boundary rule that lacks an edge (it names the rule, the edge and the
line to add).

## Pitfalls

- Choosing techniques by habit. Match the card's `apply_when` to the rule and say so.
- Skipping the pitfalls section of the cards you cited: the auditor checks it, and the gate checks the edges above.
- A `No <edge> boundary:` line with no real reason ("n/a"): the gate refuses a reason of one word, and the auditor reads
  the others.
- Varying several inputs at once, so a failure points nowhere.
- Examples with vague expected results ("works correctly"). State what is observable.
