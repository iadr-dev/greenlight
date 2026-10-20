---
id: C.API.STATUS
kind: instruction
apply_when: checking whether an API call worked or was refused
---
## Semantics

Check the outcome by logical result, not raw HTTP codes (the driver maps them).

Kind: **then**. Profile: api. Carries: none.

## In practice

Judge the outcome by logical result, not raw HTTP codes. `succeeds` means a success response; `rejected with X` means a refusal that matches the logical error X.

## Patterns

- `the request succeeds`
- `the request is rejected with {error}`

## Good and bad Gherkin

Good:

```gherkin
Then the request is rejected with validation error
```

Bad:

```gherkin
Then the status code is 422
```

## Python adapter

`ERRORS` in `operations.py` maps a logical error to status codes, an exception name, an exit code or text in the body. Success is any 2xx.

These notes describe the `python-pytest-bdd` adapter; other adapters implement the same instruction with their own drivers.

## Known pitfalls

- Asserting only that something failed. Name the error, and check that nothing changed.
- Raw codes in the feature (lint rejects them).
- An error rule that is too loose (any 4xx), which passes for the wrong reason.
