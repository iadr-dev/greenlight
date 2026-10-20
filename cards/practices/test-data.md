---
id: test-data
kind: practice
apply_when: writing the Given steps and drivers that create the records, files and clock a scenario depends on
output: data that each scenario creates for itself, with factories, fixed seeds and no personal data
phase: bind
pairs_with: [stability-rerun]
---
## Intent

A scenario that borrows data from another scenario, from a shared database or from today's date will pass
alone and fail in a suite, or pass today and fail next month. Each scenario should build the world it needs.

## How to apply

1. State in the Given steps only what matters to the rule; a factory in the driver fills in every other field
   with a valid default. A reader sees the one value that drives the outcome.
2. Create the data inside the scenario and remove it afterwards (a transaction rolled back, a workspace
   thrown away). Never rely on records left by an earlier scenario or by a migration.
3. Make everything deterministic: a fixed clock (`the current time is ...`), seeded random values, generated
   ids that do not collide when scenarios run in a random order or in parallel.
4. Use realistic values: real-looking names, amounts and dates exercise parsing and boundaries that `foo` and
   `123` do not.
5. Use invented personal data only. Never copy production records, and mask anything that looks real.

## Worked example

`Given the following customer exist:` with one row `| status | gold |` lets the factory supply name, email,
address and id. The scenario about gold discounts shows only what makes it a gold-discount scenario.

## Known pitfalls

- Shared fixtures that grow until nobody knows which test needs which row.
- Dates relative to "now" without freezing the clock, so the scenario breaks on a weekend or at month end.
- Fixed ids and emails that collide when scenarios run in a random order or in parallel (`--shuffle`).
- Cleaning up with a broad delete that also removes another scenario's data.
- Production data "just for this test": it carries personal information and changes under you.
