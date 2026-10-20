---
id: C.LIB.RESULT
kind: instruction
apply_when: checking what a library call returned or the error it raised
---
## Semantics

Check the return value (exact or subset) or the logical error raised.

Kind: **then**. Profile: lib. Carries: table or docstring optional.

## In practice

`the result is:` is the exact value, `the result includes:` a subset, and `the call fails with X` the logical error raised.

## Patterns

- `the result is:`
- `the result includes:`
- `the call fails with {error}`

## Good and bad Gherkin

Good:

```gherkin
Then the call fails with negative input
```

Bad:

```gherkin
Then no exception of type ValueError with message 'negative numbers are not allowed' propagates
```

## Python adapter

`ERRORS` can match by exception class name. A result given as a doc string is parsed as JSON when possible.

These notes describe the `python-pytest-bdd` adapter; other adapters implement the same instruction with their own drivers.

## Known pitfalls

- Asserting the message text of an exception: it changes with wording. Match the logical error.
- Using `is` for large structures when only part matters; use `includes`.
- Calling a function twice and judging the first result.
