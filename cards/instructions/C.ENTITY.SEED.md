---
id: C.ENTITY.SEED
kind: instruction
apply_when: "a scenario needs records to exist before the action: customers, orders, products, accounts"
---
## Semantics

Create records via the most realistic seam (API, then domain service, then repository, then raw DB). Columns map to fields; unknown columns are an error.

Kind: **given**. Profile: base. Carries: table.

## In practice

State only the columns that matter to the rule; the driver fills every other field with a valid default (see the test-data card). Seeding goes through the most realistic seam available, so the data is shaped like production data.

## Patterns

- `the following {entity} exist:`

## Good and bad Gherkin

Good:

```gherkin
Given the following customer exist:
  | status |
  | gold   |
```

Bad:

```gherkin
Given the following customer exist:
  | id | name | email | address | phone | created_at | status |
  (seven columns, six of them irrelevant to the rule)
```

## Python adapter

`System.seed(entity, rows)` in `tests/drivers/system.py`. Rows arrive as dicts with JSON-parsed values. An unknown column must raise. Calls `world.track(entity)` so `no X records changed` can compare.

These notes describe the `python-pytest-bdd` adapter; other adapters implement the same instruction with their own drivers.

## Known pitfalls

- Seeding through raw SQL when an API or service exists: it skips validation and hides integration bugs.
- Columns that the rule does not care about, which bury the one value that matters.
- Hard-coded ids that collide when scenarios run shuffled or in parallel.
- Forgetting that the entity name is a logical name: it is mapped in the driver, not a table name.
