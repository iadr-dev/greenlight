---
id: C.ENTITY.VERIFY
kind: instruction
apply_when: "checking what was stored: records created or changed by the action"
---
## Semantics

Verify persisted state through a read seam. 'are' is the exact set, 'include' is a subset.

Kind: **then**. Profile: base. Carries: table.

## In practice

Read through a seam that does not change anything. `are` is the exact set (order ignored); `include` is a subset.

## Patterns

- `the {entity} records are:`
- `the {entity} records include:`

## Good and bad Gherkin

Good:

```gherkin
Then the order records include:
  | id | status |
  | 17 | placed |
```

Bad:

```gherkin
Then the table orders has one row where id = 17 (SQL in the feature)
```

## Python adapter

`System.records(entity)` returns dicts; `are` compares sorted lists, `include` uses subset matching.

These notes describe the `python-pytest-bdd` adapter; other adapters implement the same instruction with their own drivers.

## Known pitfalls

- Verifying only the response and not the stored state.
- Using `are` when other records may legitimately exist; use `include`.
- Comparing generated ids or timestamps; list only the fields the rule defines.
