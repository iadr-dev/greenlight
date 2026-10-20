---
id: C.OUTPUT.CONTAINS
kind: instruction
apply_when: checking what a command printed
---
## Semantics

Match stdout or stderr with normalized line endings and whitespace; no regular expressions in features.

Kind: **then**. Profile: cli. Carries: table or docstring.

## In practice

Match standard output or standard error after normalising line endings and surrounding whitespace. No regular expressions in features.

## Patterns

- `the {stream:enum(stdout,stderr)} output contains:`

## Good and bad Gherkin

Good:

```gherkin
Then the stdout output contains:
  """
  3 orders exported
  """
```

Bad:

```gherkin
Then the stdout output matches /^\d+ orders/
```

## Python adapter

`compare.assert_text_contains(actual, expected, what)`; blank lines and trailing spaces are ignored.

These notes describe the `python-pytest-bdd` adapter; other adapters implement the same instruction with their own drivers.

## Known pitfalls

- Matching whole output when only one line matters.
- Colours and progress bars in the output: turn them off in the command map.
- Checking stdout when the message goes to stderr.
