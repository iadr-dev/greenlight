---
id: C.STATE.VERIFY
kind: instruction
apply_when: the outcome is what the browser or app remembers rather than what it shows
---
## Semantics

Client-side state check.

Kind: **then**. Profile: ui. Carries: table.

## In practice

Check what the client stored after an action: a preference, a draft, a token that was cleared. One row per entry, with `key` and `value` columns; the stored value must match. Prefer checking what the person sees; use this when the stored value is the behaviour itself.

## Patterns

- `the application state includes:`

## Good and bad Gherkin

Good:

```gherkin
Then the application state includes:
  | key   | value |
  | theme | dark  |
```

Bad:

```gherkin
Then window.localStorage.theme equals "dark"
```

## Playwright adapter

The check reads the browser storage of the page that was acted on last (a `storage` column with `session` reads session storage) and compares each entry; JSON values are compared as data. A missing entry fails with an assertion, which is an expected failure in the red phase. A page has to be open first.

These notes describe the `ts-playwright-bdd` adapter; other adapters implement the same instruction with their own drivers.

## Known pitfalls

- Checking storage when the visible effect would say more.
- Entries written asynchronously: check after a Then that shows the result, so the write has happened.
- Secrets in the table: do not put real tokens in a feature.
