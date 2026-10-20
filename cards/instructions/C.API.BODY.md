---
id: C.API.BODY
kind: instruction
apply_when: checking what a response contains
---
## Semantics

Subset match on fields; table rows for lists.

Kind: **then**. Profile: api. Carries: table or docstring.

## In practice

Subset match: every field you list must be present with that value; extra fields are fine. Table rows for lists mean each listed item must appear.

## Patterns

- `the response contains:`

## Good and bad Gherkin

Good:

```gherkin
Then the response contains:
  | total | discount |
  | 900   | 100      |
```

Bad:

```gherkin
Then the response is exactly the JSON file golden/order-17.json
```

## Python adapter

`compare.assert_subset(actual, expected, what)`. Values are parsed as JSON where possible, so `900` is a number and `true` a boolean.

These notes describe the `python-pytest-bdd` adapter; other adapters implement the same instruction with their own drivers.

## Known pitfalls

- Asserting the whole body, which fails on every harmless new field.
- Asserting only that a field exists; check its value.
- Comparing floats for money. Use integer cents or strings, as the API does.
