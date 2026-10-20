# Quick path: one small rule

For a change of one rule that touches one behaviour. The gates are the same; the artifacts are smaller.

## When to use it

- One rule is added or changed, with at most three examples.
- No new core instruction, no new adapter seam beyond one small one.
- If the change grows past that, stop and start the normal flow.

## Steps

1. Create the feature (`bdd state init FEAT-n --title "<title>" --autonomy standard`). Write a three-line brief and
   the one rule (`rules.md`, one line). Pass the discover gate. The person still approves the rules.
2. Write the examples directly in the feature file, with their tags (`@FEAT-n`, `@R-n.m`, `@EX-n.m.k`). Use the
   boundary-value and negative-cases cards. `bdd lint` and `bdd trace FEAT-n` must be clean. The person still
   approves the examples, which locks them.
3. Bind and run: `bdd run FEAT-n`, `bdd classify FEAT-n --expect red`, lock the bound files and record the bind
   gate with `--record-red`. Skip `system.md` and `tasks.md`: pass those gates with `--detail quick=true`.
4. Implement, `bdd run FEAT-n`, `bdd gate FEAT-n implement --result pass`.
5. Verify with the checklist items that apply and a short `report.md`.

## What does not change

Human approvals of the rules and the examples, the red gate, the locks and the guard are never skipped on the
quick path.

## Pitfalls

- Using the quick path to avoid asking the person. The approvals are the point.
- A "small" change that adds a column to a table that other features read. That is not one rule.
