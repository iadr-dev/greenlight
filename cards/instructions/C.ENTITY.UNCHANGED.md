---
id: C.ENTITY.UNCHANGED
kind: instruction
apply_when: a refusal or a no-op must leave the data exactly as it was
---
## Semantics

Snapshot-compare.

Kind: **then**. Profile: base. Carries: none.

## In practice

Compare the records before the first action with the records now. Only entities seeded by a Given step are tracked.

## Patterns

- `no {entity} records changed`

## Good and bad Gherkin

Good:

```gherkin
Then no order records changed
```

Bad:

```gherkin
Then nothing bad happened
```

## Python adapter

`World.act()` snapshots every tracked entity before the first action; the step asserts equality with the current records and fails clearly if the entity was never seeded.

These notes describe the `python-pytest-bdd` adapter; other adapters implement the same instruction with their own drivers.

## Known pitfalls

- Using it for an entity no Given step created: seed it first so there is something to compare.
- Two actions in one scenario, so the snapshot predates the first of them.
- Fields that always change (updated_at). The driver's `records` should leave them out.
