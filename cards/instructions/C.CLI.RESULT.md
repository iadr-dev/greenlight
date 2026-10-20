---
id: C.CLI.RESULT
kind: instruction
apply_when: checking whether a command worked or failed
---
## Semantics

Check the outcome by logical result; the driver maps exit codes and messages.

Kind: **then**. Profile: cli. Carries: none.

## In practice

Judge by logical result: `succeeds` or `fails with X`; the driver maps exit codes and messages.

## Patterns

- `the command succeeds`
- `the command fails with {error}`

## Good and bad Gherkin

Good:

```gherkin
Then the command fails with usage error
```

Bad:

```gherkin
Then the exit code is 2
```

## Python adapter

`ERRORS` maps a logical error to an exit code and/or text in standard error.

These notes describe the `python-pytest-bdd` adapter; other adapters implement the same instruction with their own drivers.

## Known pitfalls

- Raw exit codes in features (lint rejects them).
- Accepting any non-zero exit as the expected failure.
- A command that prints an error and exits 0.
